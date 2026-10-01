"""Translate embedded HTML to terminal-friendly Markdown without changing source."""

import asyncio
from html.parser import HTMLParser
from collections import OrderedDict
from copy import deepcopy
import re

from markdown_it import MarkdownIt
from markdown_it.token import Token
from markdownify import markdownify
from bs4 import BeautifulSoup
from rich.markdown import Markdown as RichMarkdown
from textual.await_complete import AwaitComplete


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
        result = []
        for token in tokens:
            if token.type == "inline":
                token.children = html_children(token.children)
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



class PrintMarkdown(RichMarkdown):
    def __init__(self, markup, **kwargs):
        super().__init__(markup, **kwargs)
        self.parsed = HTMLMarkdownParser().parse(markup)


# The read view keeps details sections as real expandable terminal controls.
from textual.widgets import Collapsible, Markdown
from textual.widgets._markdown import MarkdownBlock


class MarkdownDetails(MarkdownBlock):
    def compose(self):
        yield Collapsible(*self._blocks, title=self._token.meta["title"], collapsed=True)
        self._blocks.clear()


class HTMLMarkdown(Markdown):
    def __init__(self, *args, **kwargs):
        kwargs["parser_factory"] = lambda: HTMLMarkdownParser(details=True)
        super().__init__(*args, **kwargs)

    def update(self, markdown: str) -> AwaitComplete:
        # MarkdownViewer updates its initially empty document during mount.
        # Textual's empty update awaits removal of an empty node list, which
        # can hold up the parent's mount (and the whole viewer startup).
        if not markdown and not self.source and not self.children:
            self._markdown = ""
            self._table_of_contents = None
            return AwaitComplete(asyncio.sleep(0))
        return super().update(markdown)

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
