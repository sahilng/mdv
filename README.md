# mdv

A keyboard-friendly terminal Markdown viewer built with Textual. Other document
formats are converted to Markdown using [Microsoft MarkItDown](https://github.com/microsoft/markitdown).

## Install

Requires Python 3.10 or newer. No pipx needed. From the project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
mdv README.md
```

Already installed? Just run `source .venv/bin/activate` from the project
directory in each new terminal, then use `mdv`.

### Use from any terminal

For zsh (the default shell on macOS), run this once from the project directory
to add the installation to your PATH:

```sh
printf '\nexport PATH="%s/.venv/bin:$PATH"\n' "$PWD" >> ~/.zshrc
source ~/.zshrc
```

You can now run `mdv /path/to/report.pdf` from any directory without activating
the environment. Keep the project directory in place; repeat this setup if you
move it.

## Usage

```sh
mdv README.md
mdv report.pdf
mdv slides.pptx
mdv document.docx --toc        # start with the sidebar shown
mdv README.md --print         # render in the current terminal
md README.md                 # shortcut for mdv --print
mdv README.md --edit          # start in the editor
mde notes.md                 # edit an existing or new Markdown file
mdv notes.md --live-edit     # single-pane editor with live Markdown styling
mdv report.pdf --raw > report.md
cat README.md | mdv           # render piped Markdown
```

Interactive mode includes headings, tables, syntax-highlighted code, and a
clickable table of contents sidebar, hidden by default. Use arrow keys, Page Up /
Page Down, or `j` / `k` to scroll; `g` / `G` jump to the start / end. Press
`Ctrl+T` to toggle the sidebar in reading and live editing (`t` also works while
reading), `r` to reload, and `Ctrl+C` to quit. Conversion runs in the background so the UI
stays responsive. Click HTTP or HTTPS links to open them in your default browser.
Heading links navigate within the document; other links display their destination.
Embedded HTML headings, paragraphs, lists, tables, links, and common inline
formatting render as terminal Markdown. HTML source stays intact while editing,
with tags visible in gray in live mode. `<details>` sections have clickable
summary controls in the read view. CSS and JavaScript are not executed.

Press `e` on a Markdown file to edit in the single-pane live editor. The
contents sidebar stays available; select a heading to jump to its source. The
live editor uses the same top and side margins as the read view.
Use `Ctrl+L` to switch to the split source and preview view, `Ctrl+S` to save,
`Ctrl+C` to quit directly, and `Esc` to return to reading. The preview preserves read-mode text styles, code highlighting, and theme,
while aligning each row with the source, including wrapped lines and blank lines.
Tables use source-aligned rows, and scrolling either pane keeps the rows together.

The whole document stays rendered in the default editor, including the text being
edited, with Markdown syntax visible in gray throughout. Newlines and blank
lines remain visible and editable. H1 headings stay centered in live mode and
in the split preview. Source list markers,
quote markers, and rules appear once, without duplicate rendered markers. Arrow keys, selection,
undo, and redo work across the entire document; `Ctrl+Home` / `Ctrl+End` jump to
the start / end. Long code lines wrap with the source. Both edit modes follow the
selected read-view theme, including changes made while editing.

Unsaved changes prevent leaving the editor; `Ctrl+D` discards them and returns
to reading. Viewer shortcuts become normal text while editing. Converted
documents (PDF, Office, HTML, etc.) are read-only.

Use `--edit` or `mde` to start editing immediately. A new Markdown file is
created on `Ctrl+S`; its parent directory must already exist. Editing requires
an interactive terminal. Opening a missing file without `--edit` reports an
error before starting the viewer. After updating, rerun
`python -m pip install -e .` to install the `md` and `mde` shortcuts.

Piped input is treated as UTF-8 Markdown and rendered without a full-screen UI.
Redirected output is plain Markdown, useful for saving converted documents.

Choose a theme in the command palette (`Ctrl+P` → Change theme). Highlighting a
theme previews it immediately; `Enter` keeps it and `Esc` restores the previous theme. The selection
is saved when you close the viewer and reused by the interactive `mdv` viewer.
`md --print` uses your terminal's colors for readable output. Settings live in
`~/.config/mdv/theme` (or under `XDG_CONFIG_HOME` if set). `TEXTUAL_THEME`
overrides the saved selection in the interactive viewer.

PDF, Word, PowerPoint, Excel, Outlook, HTML, and MarkItDown's base formats are
included. Conversion quality depends on the source document; scanned PDF OCR
and AI image descriptions are not configured. This viewer accepts local files.

## Development

```sh
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pytest
```

Measure editing refresh performance in both modes with a generated document:

```sh
.venv/bin/python scripts/benchmark_editing.py --paragraphs 1000
```

The benchmark reports median source-edit, Markdown-render, and projection times.
Editing reuses unchanged blocks and inline parsing, skips hidden document layout,
and coalesces refreshes at 40 ms while typing continues.
