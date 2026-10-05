"""Translate embedded HTML to terminal-friendly Markdown without changing source."""

import asyncio
from html.parser import HTMLParser
from collections import OrderedDict
from copy import deepcopy
import re

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.footnote import footnote_plugin
from markdownify import markdownify
from bs4 import BeautifulSoup
from rich.markdown import Markdown as RichMarkdown
from rich.markdown import ListItem as RichListItem
from rich.segment import Segment
from textual import events
from textual.await_complete import AwaitComplete
from textual.binding import Binding
from textual.widgets._markdown import MarkdownBlockQuote, MarkdownUnorderedListItem

from .scrollbar import SolidScrollBarRender


class InlineHTML(HTMLParser):
    """Translate supported HTML tags to the inline tokens both renderers know."""

    TAGS = {"b": "strong", "strong": "strong", "i": "em", "em": "em",
            "s": "s", "del": "s", "strike": "s", "a": "link"}

    def __init__(self):
        super().__init__()
        self.tokens = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.TAGS:
            token = Token(self.TAGS[tag] + "_open", self.TAGS[tag], 1)
            if tag == "a":
                token.attrs = {"href": attrs.get("href", "")}
            self.tokens.append(token)
        elif tag == "br":
            self.tokens.append(Token("hardbreak", "br", 0))
        elif tag == "img":
            token = Token("text", "", 0)
            token.content = attrs.get("alt", "")
            self.tokens.append(token)

    def handle_endtag(self, tag):
        if tag in self.TAGS:
            self.tokens.append(Token(self.TAGS[tag] + "_close", self.TAGS[tag], -1))


def html_children(children):
    result = []
    # Ignore unmatched closing tags so partially typed HTML remains renderable.
    stack = []
    code = None
    for child in children or []:
        if child.type == "html_inline" and child.content.lower().startswith("<code"):
            code = ""
            continue
        if child.type == "html_inline" and child.content.lower() == "</code>" and code is not None:
            token = Token("code_inline", "code", 0)
            token.content = code
            result.append(token)
            code = None
            continue
        if code is not None:
            code += child.content
            continue
        if child.type != "html_inline":
            result.append(child)
            continue
        parser = InlineHTML()
        parser.feed(child.content)
        for token in parser.tokens:
            if token.nesting == 1:
                stack.append(token.type[:-5])
            elif token.nesting == -1:
                if not stack or stack[-1] != token.type[:-6]:
                    continue
                stack.pop()
            result.append(token)
    if code is not None:
        token = Token("code_inline", "code", 0)
        token.content = code
        result.append(token)
    for kind in reversed(stack):
        result.append(Token(kind + "_close", kind, -1))
    return result


def html_markdown(source):
    soup = BeautifulSoup(source, "html.parser")
    for element in soup(["script", "style"]):
        element.decompose()
    return markdownify(str(soup), heading_style="ATX")


def copy_inline_tokens(tokens):
    """Copy mutable token fields without deep-copying immutable text and flags."""
    return [Token(token.type, token.tag, token.nesting,
                  attrs=token.attrs.copy(),
                  map=token.map.copy() if token.map is not None else None,
                  level=token.level,
                  children=copy_inline_tokens(token.children) if token.children is not None else None,
                  content=token.content,
                  markup=token.markup,
                  info=token.info,
                  meta=deepcopy(token.meta) if token.meta else {},
                  block=token.block,
                  hidden=token.hidden)
            for token in tokens]


class HTMLMarkdownParser(MarkdownIt):
    def __init__(self, *, editing=False, details=False):
        super().__init__("gfm-like")
        self.use(footnote_plugin, inline=False, move_to_end=False)
        self.editing = editing
        self.details = details
        if editing:
            self._inline_cache = OrderedDict()
            self.core.ruler.at("inline", self._parse_cached_inline)

    def _parse_cached_inline(self, state):
        # Block parsing remains document-wide: references and list / fence
        # boundaries can change far from the edited line. Inline parsing can
        # safely reuse results when both the text and reference environment match.
        environment = repr(state.env)
        for token in state.tokens:
            if token.type != "inline":
                continue
            if "[^" in token.content:
                # Footnote references register their use in state.env during
                # inline parsing. Reusing their tokens skips that side effect,
                # changes the final environment, and invalidates every block
                # in the edit renderer on the next keystroke.
                children = []
                state.md.inline.parse(token.content, state.md, state.env, children)
                token.children = children
                continue
            key = (token.content, environment)
            children = self._inline_cache.get(key)
            if children is None:
                children = []
                state.md.inline.parse(token.content, state.md, state.env, children)
                self._inline_cache[key] = copy_inline_tokens(children)
                if len(self._inline_cache) > 2048:
                    self._inline_cache.popitem(last=False)
            else:
                self._inline_cache.move_to_end(key)
                # Later core rules and the editor mutate tokens (soft breaks,
                # HTML and source metadata); never expose the cached objects.
                children = copy_inline_tokens(children)
            token.children = children

    def parse(self, src, env=None):
        env = {} if env is None else env
        tokens = super().parse(src, env)
        if self.editing:
            lines = src.splitlines()
            for index, token in enumerate(tokens):
                if (token.type == "heading_open" and token.tag == "h2" and token.markup == "-"
                        and token.map and index + 2 < len(tokens)):
                    underline = lines[token.map[1] - 1]
                    if re.fullmatch(r"[ \t]*(?:>[ \t]*)*-[ \t]*", underline):
                        # A single dash is ambiguous while beginning a bullet.
                        # Preserve the source as a paragraph until it has text
                        # or enough dashes to be an intentional heading underline.
                        token.type, token.tag, token.markup = "paragraph_open", "p", ""
                        tokens[index + 1].map = token.map.copy()
                        closing = tokens[index + 2]
                        closing.type, closing.tag, closing.markup = "paragraph_close", "p", ""
        expanded = []
        skip_definition = False
        for token in tokens:
            if token.type == "footnote_reference_open":
                number = env["footnotes"]["refs"].get(":" + token.meta["label"], -1) + 1
                skip_definition = number < 1
                if skip_definition:
                    continue
                opening = Token("ordered_list_open", "ol", 1,
                                attrs={"start": number}, map=token.map)
                item = Token("list_item_open", "li", 1, info=str(number), map=token.map)
                expanded.extend([opening, item])
            elif token.type == "footnote_reference_close":
                if not skip_definition:
                    expanded.extend([Token("list_item_close", "li", -1),
                                     Token("ordered_list_close", "ol", -1)])
                skip_definition = False
            elif not skip_definition:
                expanded.append(token)
        tokens = expanded
        result = []
        list_items = []
        quotes = []
        for token in tokens:
            if token.type == "inline":
                token.children = html_children(token.children)
                if list_items and list_items[-1] is not None and token.children:
                    first = token.children[0]
                    match = re.match(r"^\[([ xX])\][ \t]+", first.content) if first.type == "text" else None
                    if match:
                        list_items[-1].meta["task"] = match[1].lower() == "x"
                        first.content = first.content[match.end():]
                    list_items[-1] = None
                if quotes and quotes[-1] is not None and token.children:
                    first = token.children[0]
                    match = re.fullmatch(r"\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]", first.content) if first.type == "text" else None
                    if match:
                        kind = match[1]
                        quotes[-1].meta["alert"] = kind.lower()
                        label = Token("text", "", 0, content=kind.title() + ":")
                        token.children[:1] = [Token("strong_open", "strong", 1), label,
                                              Token("strong_close", "strong", -1)]
                    quotes[-1] = None
                children = []
                for child in token.children or []:
                    if child.type == "footnote_ref":
                        children.append(Token("text", "", 0, content=f"[{child.meta['id'] + 1}]"))
                    else:
                        children.append(child)
                token.children = children
            if token.type == "list_item_open":
                list_items.append(token)
            elif token.type == "list_item_close":
                list_items.pop()
            elif token.type == "blockquote_open":
                quotes.append(token)
            elif token.type == "blockquote_close":
                quotes.pop()
            if token.type != "html_block":
                result.append(token)
                continue
            if self.details:
                soup = BeautifulSoup(token.content, "html.parser")
                if soup.find("details") is not None:
                    opening = Token("details_open", "details", 1)
                    opening.map = token.map.copy()
                    summary = soup.find("summary")
                    opening.meta["title"] = summary.get_text(" ", strip=True) if summary else "Details"
                    result.append(opening)
                    if summary:
                        summary.decompose()
                    body = html_markdown(str(soup))
                    for child in super().parse(body, env):
                        if child.map is not None:
                            child.map = token.map.copy()
                        result.append(child)
                    if "</details>" in token.content.lower():
                        closing = Token("details_close", "details", -1)
                        closing.map = token.map.copy()
                        result.append(closing)
                    continue
                if token.content.strip().lower() == "</details>":
                    closing = Token("details_close", "details", -1)
                    closing.map = token.map.copy()
                    result.append(closing)
                    continue
            converted = html_markdown(token.content)
            if self.editing:
                # One source range keeps the original HTML editable, with tags gray.
                opening = Token("paragraph_open", "p", 1)
                opening.map = token.map
                inline = super().parseInline(converted.strip(), env)[0]
                inline.map = token.map
                for child in inline.children or []:
                    if child.type == "softbreak":
                        child.type = "hardbreak"
                result.extend([opening, inline, Token("paragraph_close", "p", -1)])
            else:
                translated = super().parse(converted, env)
                for child in translated:
                    if child.map is not None:
                        child.map = token.map.copy()
                    if child.type == "inline":
                        child.children = html_children(child.children)
                result.extend(translated)
        return result



class PrintListItem(RichListItem):
    @classmethod
    def create(cls, markdown, token):
        item = cls()
        item.task = token.meta.get("task")
        return item

    def render_bullet(self, console, options):
        if self.task is None:
            yield from super().render_bullet(console, options)
            return
        render_options = options.update(width=options.max_width - 3)
        lines = console.render_lines(self.elements, render_options, style=self.style)
        style = console.get_style("markdown.item.bullet", default="none")
        for index, line in enumerate(lines):
            yield Segment((" ☑ " if self.task else " ☐ ") if index == 0 else "   ", style)
            yield from line
            yield Segment("\n")


class PrintMarkdown(RichMarkdown):
    elements = {**RichMarkdown.elements, "list_item_open": PrintListItem}

    def __init__(self, markup, **kwargs):
        super().__init__(markup, **kwargs)
        self.parsed = HTMLMarkdownParser().parse(markup)


# The read view keeps details sections as real expandable terminal controls.
from textual.widgets import Button, Collapsible, Markdown
from textual.widgets._markdown import MarkdownBlock, MarkdownFence


class CopyableMarkdownFence(MarkdownFence, can_focus=True):
    _horizontal_scroll_active = False
    _horizontal_scroll_timer = None
    BINDINGS = [
        Binding("left", "scroll_left", "Scroll code left", show=False),
        Binding("right", "scroll_right", "Scroll code right", show=False),
    ]
    DEFAULT_CSS = """
    CopyableMarkdownFence {
        background: #161c24;
        color: #eef2f7;
        border: none;
        layers: code controls;
        overflow: auto hidden;
        scrollbar-size-horizontal: 1;
        scrollbar-background: #161c24;
        scrollbar-background-hover: #161c24;
        scrollbar-background-active: #161c24;
        scrollbar-color: #536777;
        scrollbar-color-hover: #70879f;
        scrollbar-color-active: #8aa3bd;
    }
    CopyableMarkdownFence:light {
        background: #f0f3f6;
        color: #1f2328;
        scrollbar-background: #f0f3f6;
        scrollbar-background-hover: #f0f3f6;
        scrollbar-background-active: #f0f3f6;
        scrollbar-color: #afb8c1;
        scrollbar-color-hover: #8c959f;
        scrollbar-color-active: #6e7781;
    }
    CopyableMarkdownFence > Label {
        padding: 1 10 1 2;
        layer: code;
    }
    CopyableMarkdownFence Button.copy-code {
        dock: right;
        offset: 0 1;
        layer: controls;
        height: 1;
        min-width: 8;
        width: 8;
        border: none;
        padding: 0;
        margin: 0 1 0 0;
        background: transparent;
        color: #c9d1d9;
        text-style: bold;
    }
    CopyableMarkdownFence:light Button.copy-code {
        color: #57606a;
    }
    CopyableMarkdownFence Button.copy-code:hover,
    CopyableMarkdownFence Button.copy-code:focus {
        background: transparent;
        color: $foreground;
        text-style: bold;
    }
    """

    def compose(self):
        yield Button("⧉ Copy", classes="copy-code", compact=True)
        yield from super().compose()

    def on_mount(self) -> None:
        self.horizontal_scrollbar.renderer = SolidScrollBarRender

    def _scroll_horizontal(self, event: events.MouseEvent, direction: int) -> None:
        # Momentum can lose Shift after the user releases it. Keep one axis
        # until the wheel stream pauses, and consume events at either edge.
        self._horizontal_scroll_active = True
        if self._horizontal_scroll_timer is not None:
            self._horizontal_scroll_timer.stop()
        self._horizontal_scroll_timer = self.set_timer(0.25, self._end_horizontal_scroll)
        if direction > 0:
            self._scroll_right_for_pointer(animate=False)
        else:
            self._scroll_left_for_pointer(animate=False)
        event.prevent_default()
        event.stop()

    def _end_horizontal_scroll(self) -> None:
        self._horizontal_scroll_active = False
        self._horizontal_scroll_timer = None

    def _on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        if event.shift or event.ctrl or self._horizontal_scroll_active:
            self._scroll_horizontal(event, 1)
        else:
            super()._on_mouse_scroll_down(event)

    def _on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        if event.shift or event.ctrl or self._horizontal_scroll_active:
            self._scroll_horizontal(event, -1)
        else:
            super()._on_mouse_scroll_up(event)

    def _on_mouse_scroll_right(self, event: events.MouseScrollRight) -> None:
        self._scroll_horizontal(event, 1)

    def _on_mouse_scroll_left(self, event: events.MouseScrollLeft) -> None:
        self._scroll_horizontal(event, -1)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        # The display trims trailing whitespace; copying preserves the code.
        self.app.copy_to_clipboard(self._token.content)


class MarkdownTaskItem(MarkdownUnorderedListItem):
    def __init__(self, markdown, token, bullet):
        task = token.meta.get("task")
        super().__init__(markdown, token, "☑ " if task else "☐ " if task is False else bullet)


class MarkdownAlert(MarkdownBlockQuote):
    DEFAULT_CSS = """
    MarkdownAlert.mdv-alert-note { border-left: outer $primary; }
    MarkdownAlert.mdv-alert-tip { border-left: outer $success; }
    MarkdownAlert.mdv-alert-important { border-left: outer $primary; }
    MarkdownAlert.mdv-alert-warning { border-left: outer $warning; }
    MarkdownAlert.mdv-alert-caution { border-left: outer $error; }
    """

    def __init__(self, markdown, token):
        super().__init__(markdown, token)
        if kind := token.meta.get("alert"):
            self.add_class(f"mdv-alert-{kind}")


class MarkdownDetails(MarkdownBlock):
    def compose(self):
        yield Collapsible(*self._blocks, title=self._token.meta["title"], collapsed=True)
        self._blocks.clear()


class HTMLMarkdown(Markdown):
    def __init__(self, *args, **kwargs):
        kwargs["parser_factory"] = lambda: HTMLMarkdownParser(details=True)
        super().__init__(*args, **kwargs)

    def on_resize(self) -> None:
        # Leave text room even when the pane is narrower than its usual margins.
        self.styles.padding = (1, min(3, max(0, (self.size.width - 1) // 2)))

    def update(self, markdown: str) -> AwaitComplete:
        # MarkdownViewer updates its initially empty document during mount.
        # Textual's empty update awaits removal of an empty node list, which
        # can hold up the parent's mount (and the whole viewer startup).
        if not markdown and not self.source and not self.children:
            self._markdown = ""
            self._table_of_contents = None
            return AwaitComplete(asyncio.sleep(0))
        return super().update(markdown)

    def get_block_class(self, token_type):
        if token_type in {"fence", "code_block"}:
            return CopyableMarkdownFence
        if token_type == "list_item_unordered_open":
            return MarkdownTaskItem
        if token_type == "blockquote_open":
            return MarkdownAlert
        return super().get_block_class(token_type)

    def _parse_markdown(self, tokens):
        tokens = list(tokens)
        index = 0
        ordinary = []
        while index < len(tokens):
            token = tokens[index]
            if token.type != "details_open":
                ordinary.append(token)
                index += 1
                continue
            yield from super()._parse_markdown(ordinary)
            ordinary.clear()
            depth, end = 1, index + 1
            while end < len(tokens):
                depth += (tokens[end].type == "details_open") - (tokens[end].type == "details_close")
                if depth == 0:
                    break
                end += 1
            block = MarkdownDetails(self, token)
            block._blocks = list(self._parse_markdown(tokens[index + 1:end]))
            if end < len(tokens):
                block.source_range = (token.map[0], tokens[end].map[1])
            yield block
            index = end + 1
        yield from super()._parse_markdown(ordinary)
