import asyncio
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Command, CommandPalette
from textual.containers import Horizontal
from textual.geometry import Offset
from textual.theme import ThemeProvider
from textual.widgets import Footer, Header, Input, Markdown, MarkdownViewer, Static, TextArea
from textual.widgets._markdown import MarkdownBlock, MarkdownTableOfContents

from .html import HTMLMarkdown
from .editor import MarkdownEditor
from .live import RenderHost
from .rendered import RenderMarkdown, aligned_snapshot, styled_source
from .document import MARKDOWN_SUFFIXES, load_document
from .preview import AlignedPreview
from .scrollbar import SolidScrollBarRender
from .theme import load_theme, register_visible_ansi_themes, save_theme


class DocumentViewer(MarkdownViewer):
    def on_mount(self) -> None:
        self.vertical_scrollbar.renderer = SolidScrollBarRender

    def compose(self):
        markdown = HTMLMarkdown(open_links=False)
        markdown.can_focus = True
        yield markdown
        yield MarkdownTableOfContents(markdown)

    async def _on_markdown_link_clicked(self, message: Markdown.LinkClicked) -> None:
        # stop() only prevents bubbling; suppress MarkdownViewer's handler too.
        message.prevent_default()
        message.stop()
        if message.href.startswith("#"):
            self.document.goto_anchor(message.href[1:])
        elif urlsplit(message.href).scheme.lower() in {"http", "https"}:
            try:
                opened = await asyncio.to_thread(webbrowser.open, message.href, new=2)
                if not opened:
                    self.notify(message.href, title="Could not open browser", severity="error", markup=False)
            except Exception as error:
                self.notify(str(error), title="Could not open browser", severity="error", markup=False)
        else:
            self.notify(message.href, title="Link", markup=False)


class ViewerCommandPalette(CommandPalette):
    DEFAULT_CSS = """
    ViewerCommandPalette {
        background: transparent;
        align-horizontal: right;
    }
    ViewerCommandPalette > Vertical {
        width: 32;
        max-width: 50%;
        height: auto;
        margin-top: 1;
    }
    """


class Viewer(App):
    TITLE = "mdv"
    CSS = """
    Screen { background: $surface; }
    MarkdownViewer { height: 1fr; }
    #panes { height: 1fr; }
    #editor { display: none; width: 1fr; height: 1fr; background: $surface; color: $foreground; }
    Screen.editing #editor { display: block; }
    AlignedPreview { display: none; }
    Screen.editing AlignedPreview { display: block; }
    Screen.editing.live-edit #editor { border: none; padding: 1 3; }
    Screen.editing.live-edit AlignedPreview { display: none; }
    Screen.editing MarkdownViewer { display: none; }
    #edit-toc { display: none; width: 28; max-width: 35%; height: 1fr; }
    Screen.editing.live-edit.toc-visible #edit-toc { display: block; }
    Markdown { padding: 1 3; }
    MarkdownTableOfContents { width: 28; max-width: 35%; }
    #status { height: 1; padding: 0 1; background: $boost; color: $text-muted; }
    """
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("ctrl+shift+c,super+c", "copy_selection", "Copy", priority=True),
        Binding("t", "toc", "Sidebar", show=False),
        Binding("ctrl+t", "toggle_toc", "Sidebar", priority=True),
        Binding("r", "reload", "Reload"),
        Binding("e", "edit", "Edit"),
        Binding("ctrl+l", "toggle_live_edit", "Live / split", priority=True),
        Binding("ctrl+s", "save", "Save", priority=True),
        Binding("escape", "close_editor", "Read", priority=True),
        Binding("ctrl+d", "discard", "Discard edits", priority=True),
        Binding("j", "down", "Down", show=False),
        Binding("k", "up", "Up", show=False),
        Binding("g", "top", "Top", show=False),
        Binding("G", "bottom", "Bottom", show=False),
    ]

    def __init__(self, path: Path, *, show_toc: bool = False, start_editing: bool = False, live_edit: bool | None = None):
        super().__init__()
        register_visible_ansi_themes(self)
        self.theme = load_theme()
        self.initial_theme = self.theme
        self._theme_preview_original: str | None = None
        self.path = path
        self.show_toc = show_toc
        self.start_editing = start_editing or live_edit is True
        self.live_edit = True if live_edit is None else live_edit
        self.sub_title = path.name
        self.editing = False
        self.content: str | None = None
        self._syncing_scroll = False
        self._refreshing_preview = False
        self._render_generation = 0
        self._preview_scheduled = False
        self._preview_running = False
        self._preview_pending = False
        self._render_key = None
        self._typing_timer = None
        self._projection_key = None
        self._saved_lines: list[str] = []
        self._editor_status: str | None = None

    def compose(self) -> ComposeResult:
        renderer = RenderMarkdown(id="edit-layout")
        yield Header()
        with Horizontal(id="panes"):
            yield MarkdownTableOfContents(renderer, id="edit-toc")
            yield MarkdownEditor(id="editor", show_line_numbers=True)
            yield AlignedPreview()
            yield RenderHost(renderer)
            yield DocumentViewer("", show_table_of_contents=self.show_toc, open_links=False)
        yield Static(str(self.path), id="status", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.screen.set_class(self.show_toc, "toc-visible")
        editor = self.query_one("#editor", TextArea)
        preview = self.query_one(AlignedPreview)
        self.watch(editor, "scroll_y", lambda: self.sync_scroll(editor, preview), init=False)
        self.watch(preview, "scroll_y", lambda: self.sync_scroll(preview, editor), init=False)
        self.query_one(MarkdownViewer).document.focus()
        self.action_reload()

    def sync_scroll(self, source: TextArea | AlignedPreview, target: TextArea | AlignedPreview) -> None:
        if not self.editing or self.live_edit or self._syncing_scroll or self._refreshing_preview:
            return
        self._syncing_scroll = True
        try:
            target.scroll_to(y=source.scroll_y, animate=False, immediate=True)
        finally:
            self._syncing_scroll = False

    @work(group="render")
    async def sync_preview(self) -> None:
        if not self.editing:
            return
        # Let an in-flight DOM update finish; then render only the newest buffer.
        if self._preview_running:
            self._preview_pending = True
            return
        self._preview_running = True
        self._preview_pending = False
        self._render_generation += 1
        generation = self._render_generation
        editor = self.query_one("#editor", MarkdownEditor)
        preview = self.query_one(AlignedPreview)
        host = self.query_one(RenderHost)
        renderer = self.query_one(RenderMarkdown)
        target = editor if self.live_edit else preview
        renderer.projection_width = max(10, target.scrollable_content_region.width)
        host.styles.width = renderer.projection_width
        renderer.set_class(self.live_edit, "controls")
        renderer.controls = self.live_edit
        renderer.breaks = True
        key = (editor.text, self.live_edit, self.theme)
        # Width-only changes can reflow the existing widget tree.
        if key != self._render_key:
            await renderer.update(editor.text)
            self._render_key = key
        for block in renderer.query("MarkdownFence"):
            content = getattr(block, "_mdv_content", None)
            if content is not None and getattr(block, "_mdv_content_applied", None) is not content:
                block.set_content(content)
                block._mdv_content_applied = content
        self.call_after_refresh(self.finish_projection, generation)

    def finish_projection(self, generation: int) -> None:
        if generation != self._render_generation:
            return
        self._preview_running = False
        if not self.editing:
            return
        renderer = self.query_one(RenderMarkdown)
        editor = self.query_one("#editor", MarkdownEditor)
        if renderer.source != editor.text or renderer.controls != self.live_edit:
            self.schedule_scroll_sync()
            return
        projection_key = (self._render_key, editor.wrap_width, editor.indent_width,
                          renderer.projection_width)
        if projection_key != self._projection_key:
            if self.live_edit:
                editor.set_styles(styled_source(renderer, editor.document.lines), renderer)
            else:
                self.query_one(AlignedPreview).set_projection(aligned_snapshot(renderer, editor))
            self._projection_key = projection_key
        self._refreshing_preview = False
        if not self.live_edit:
            self.sync_scroll(editor, self.query_one(AlignedPreview))
        target = editor if self.live_edit else self.query_one(AlignedPreview)
        if self._preview_pending or renderer.projection_width != max(10, target.scrollable_content_region.width):
            self.schedule_scroll_sync()

    def on_resize(self) -> None:
        self.call_after_refresh(self.schedule_scroll_sync)

    def schedule_scroll_sync(self) -> None:
        if self.editing:
            self._refreshing_preview = True
            if self._preview_running:
                self._preview_pending = True
            elif not self._preview_scheduled:
                self._preview_scheduled = True
                self.call_after_refresh(self._start_preview)

    def _start_preview(self) -> None:
        self._preview_scheduled = False
        self.sync_preview()

    async def on_aligned_preview_link_clicked(self, event: AlignedPreview.LinkClicked) -> None:
        document = self.query_one(MarkdownViewer).document
        if event.href.startswith("#"):
            # Resolve anchors using the normal Markdown renderer's heading IDs.
            from textual._slug import TrackedSlugs

            renderer = self.query_one(RenderMarkdown)
            slugs = TrackedSlugs()
            for _, title, block_id in renderer.table_of_contents or []:
                if slugs.slug(title) == event.href[1:]:
                    block = renderer.query_one(f"#{block_id}")
                    preview = self.query_one(AlignedPreview)
                    if preview.projection is not None:
                        offset = preview.projection.offset((block.source_range[0], 0))
                        preview.scroll_to(y=offset.y, animate=False)
                    break
        else:
            document.post_message(Markdown.LinkClicked(document, event.href))

    def on_markdown_table_of_contents_updated(self, event: Markdown.TableOfContentsUpdated) -> None:
        if event.markdown is self.query_one(RenderMarkdown):
            tokens = event.markdown.source_tokens
            titles = []
            for index, token in enumerate(tokens[:-1]):
                if token.type == "heading_open" and tokens[index + 1].type == "inline":
                    inline = tokens[index + 1]
                    titles.append("".join(child.content for child in inline.children or []
                                          if child.type in {"text", "code_inline", "image"}) or inline.content)
            contents = [(level, titles[index] if index < len(titles) else title, block_id)
                        for index, (level, title, block_id) in enumerate(event.table_of_contents)]
            self.query_one("#edit-toc", MarkdownTableOfContents).table_of_contents = contents

    def on_markdown_table_of_contents_selected(self, event: Markdown.TableOfContentsSelected) -> None:
        if event.markdown is not self.query_one(RenderMarkdown):
            return
        block = self.query_one(RenderMarkdown).query_one(f"#{event.block_id}")
        editor = self.query_one(MarkdownEditor)
        editor.move_cursor((block.source_range[0], 0))
        editor.scroll_to(y=editor.wrapped_document.location_to_offset(editor.cursor_location).y,
                         animate=False, immediate=True)
        editor.focus()
        event.stop()

    def on_unmount(self) -> None:
        if self.theme != self.initial_theme:
            try:
                save_theme(self.theme)
            except OSError as error:
                print(f"mdv: unable to save theme: {error}", file=sys.stderr)

    def action_change_theme(self) -> None:
        self._theme_preview_original = self.theme
        self.push_screen(ViewerCommandPalette(providers=[ThemeProvider], placeholder="Search for themes…",
                                              id="theme-palette"))

    def action_command_palette(self) -> None:
        if self.use_command_palette and not CommandPalette.is_open(self):
            self.push_screen(ViewerCommandPalette(id="--command-palette"))

    def on_command_palette_option_highlighted(self, event: CommandPalette.OptionHighlighted) -> None:
        if self._theme_preview_original is None:
            return
        option = event.highlighted_event.option
        if isinstance(option, Command) and option.hit.text in self.available_themes:
            self.theme = option.hit.text

    def on_command_palette_closed(self, event: CommandPalette.Closed) -> None:
        if self._theme_preview_original is not None:
            if not event.option_selected:
                self.theme = self._theme_preview_original
            self._theme_preview_original = None

    @work(exclusive=True)
    async def action_reload(self) -> None:
        viewer = self.query_one(MarkdownViewer)
        status = self.query_one("#status", Static)
        status.update(f"Loading {self.path.name}…")
        try:
            if self.start_editing and not self.path.exists() and self.path.suffix.lower() in MARKDOWN_SUFFIXES:
                content = ""
            else:
                content = await asyncio.to_thread(load_document, self.path)
            self.content = content
            # Direct editing needs only the edit renderer. Populate the hidden
            # read view when leaving the editor instead of rendering twice.
            if not (self.start_editing and self.path.suffix.lower() in MARKDOWN_SUFFIXES):
                await viewer.document.update(content)
                status.update(f"{self.path}  ·  {len(content.splitlines()):,} lines")
            if self.start_editing:
                self.start_editing = False
                self.action_edit()
        except Exception as error:
            status.update(f"Unable to load: {error}")
            self.notify(str(error), title="Unable to load document", severity="error", timeout=10)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in {"save", "close_editor", "discard", "toggle_live_edit"}:
            # Priority bindings must not intercept keys on the command palette.
            return self.editing and self.screen is self.query_one("#editor", TextArea).screen
        if action == "toggle_toc":
            return (self.screen is self.query_one("#editor", TextArea).screen
                    and (not self.editing or self.live_edit))
        if action == "quit":
            return self.screen is self.query_one("#editor", TextArea).screen
        if action in {"toc", "reload", "edit", "down", "up", "top", "bottom"}:
            return not self.editing
        return True

    def action_copy_selection(self) -> None:
        text = self.screen.get_selected_text()
        focused = self.focused
        if not text and isinstance(focused, (Input, TextArea)):
            text = focused.selected_text
        if text:
            self.copy_to_clipboard(text)

    def copy_to_clipboard(self, text: str) -> None:
        super().copy_to_clipboard(text)
        # macOS Terminal doesn't support Textual's OSC 52 clipboard escape.
        if sys.platform == "darwin":
            try:
                subprocess.run(
                    ["/usr/bin/pbcopy"], input=text.encode("utf-8"),
                    check=True, timeout=2, capture_output=True,
                )
            except (OSError, subprocess.SubprocessError):
                self.notify("Unable to copy to the macOS clipboard.", severity="error")

    @property
    def dirty(self) -> bool:
        return self.editing and self.query_one("#editor", TextArea).document.lines != self._saved_lines

    def action_edit(self) -> None:
        if self.content is None:
            return
        if self.path.suffix.lower() not in MARKDOWN_SUFFIXES:
            self.notify("Editing is available for Markdown files only.")
            return
        viewer = self.query_one(MarkdownViewer)
        read_row = self._read_top_source_row(viewer)
        self.show_toc = viewer.show_table_of_contents
        self.editing = True
        self.screen.add_class("editing")
        editor = self.query_one("#editor", TextArea)
        self.screen.set_class(self.live_edit, "live-edit")
        self.query_one("#editor", MarkdownEditor).set_live_render(self.live_edit)
        editor.load_text(self.content)
        self._saved_lines = editor.document.lines.copy()
        if read_row:
            editor.move_cursor((min(read_row, editor.document.line_count - 1), 0))
            self.call_after_refresh(self._scroll_editor_to_cursor)
        editor.focus()
        self.schedule_scroll_sync()
        self.update_editor_status()
        self.refresh_bindings()

    def action_toggle_live_edit(self) -> None:
        self.live_edit = not self.live_edit
        self.screen.set_class(self.live_edit, "live-edit")
        editor = self.query_one("#editor", MarkdownEditor)
        editor.set_live_render(self.live_edit)
        editor.focus()
        self.schedule_scroll_sync()
        self.update_editor_status()
        self.refresh_bindings()

    def update_editor_status(self) -> None:
        marker = "Unsaved changes" if self.dirty else ("Saved" if self.path.exists() else "New file")
        status = (f"{self.path}  ·  {marker}  ·  Ctrl+L live/split · Ctrl+S save "
                  "· Ctrl+C quit · Esc read · Ctrl+D discard")
        if status != self._editor_status:
            self._editor_status = status
            self.query_one("#status", Static).update(status)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self.editing:
            lines = self.query_one(MarkdownEditor).document.line_count
            if lines < 300:
                # Small documents can maintain continuous Markdown rendering.
                if self._typing_timer is None:
                    self._typing_timer = self.set_timer(0.12, self._refresh_after_typing)
            else:
                # Reparse a large document after a brief pause so a render
                # cannot block the next key in an uninterrupted typing burst.
                if self._typing_timer is not None:
                    self._typing_timer.stop()
                self._typing_timer = self.set_timer(0.12, self._refresh_after_typing)
            self.update_editor_status()

    def _refresh_after_typing(self) -> None:
        self._typing_timer = None
        self.schedule_scroll_sync()

    def action_save(self) -> None:
        content = self.query_one("#editor", TextArea).text
        try:
            self.path.write_text(content, encoding="utf-8")
        except OSError as error:
            self.notify(str(error), title="Unable to save", severity="error", markup=False)
            return
        self.content = content
        self._saved_lines = self.query_one("#editor", TextArea).document.lines.copy()
        self.update_editor_status()

    async def action_close_editor(self) -> None:
        if self.dirty:
            self.notify("Save with Ctrl+S or discard with Ctrl+D before leaving the editor.")
            return
        editor = self.query_one(MarkdownEditor)
        edit_row = editor.wrapped_document.offset_to_location(Offset(0, int(editor.scroll_y)))[0]
        self.editing = False
        self._editor_status = None
        self.screen.remove_class("editing")
        viewer = self.query_one(MarkdownViewer)
        # Keep the hidden read view out of the typing path.
        if viewer.document.source != (self.content or ""):
            await viewer.document.update(self.content or "")
        viewer.show_table_of_contents = self.show_toc
        self.call_after_refresh(self._scroll_reader_to_row, edit_row)
        viewer.document.focus()
        self.query_one("#status", Static).update(str(self.path))
        self.refresh_bindings()

    async def action_discard(self) -> None:
        self.query_one("#editor", TextArea).load_text(self.content or "")
        await self.action_close_editor()

    def action_quit(self) -> None:
        if self.dirty:
            self.notify("Save with Ctrl+S or discard with Ctrl+D before quitting.")
            return
        self.exit()

    def action_toc(self) -> None:
        self.action_toggle_toc()

    def action_toggle_toc(self) -> None:
        self.show_toc = not self.show_toc
        viewer = self.query_one(MarkdownViewer)
        viewer.show_table_of_contents = self.show_toc
        self.screen.set_class(self.show_toc, "toc-visible")
        if self.editing:
            self.schedule_scroll_sync()

    @staticmethod
    def _read_top_source_row(viewer: MarkdownViewer) -> int:
        blocks = [block for block in viewer.document.query(MarkdownBlock)
                  if block.region.height and block.source_range]
        visible = [block for block in blocks if block.region.bottom > viewer.content_region.y]
        return min(visible, key=lambda block: block.region.y).source_range[0] if visible else 0

    def _scroll_editor_to_cursor(self) -> None:
        if self.editing:
            editor = self.query_one(MarkdownEditor)
            y = editor.wrapped_document.location_to_offset(editor.cursor_location).y
            editor.scroll_to(y=y, animate=False, immediate=True)

    def _scroll_reader_to_row(self, row: int) -> None:
        if self.editing:
            return
        viewer = self.query_one(MarkdownViewer)
        blocks = [block for block in viewer.document.query(MarkdownBlock)
                  if block.region.height and block.source_range and block.source_range[0] <= row]
        if blocks:
            block = max(blocks, key=lambda block: block.source_range[0])
            viewer.scroll_to_widget(block, top=True, animate=False)

    def action_down(self) -> None:
        self.query_one(MarkdownViewer).scroll_down()

    def action_up(self) -> None:
        self.query_one(MarkdownViewer).scroll_up()

    def action_top(self) -> None:
        self.query_one(MarkdownViewer).scroll_home()

    def action_bottom(self) -> None:
        self.query_one(MarkdownViewer).scroll_end()
