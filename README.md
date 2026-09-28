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
mdv document.docx --no-toc
mdv README.md --print         # render in the current terminal
mdv report.pdf --raw > report.md
cat README.md | mdv           # render piped Markdown
```

Interactive mode includes headings, tables, syntax-highlighted code, and a
clickable table of contents. Use arrow keys, Page Up / Page Down, or `j` / `k`
to scroll; `g` / `G` jump to the start / end. Press `t` to toggle contents,
`r` to reload, and `q` to quit. Conversion runs in the background so the UI
stays responsive. Click HTTP or HTTPS links to open them in your default browser.
Heading links navigate within the document; other links display their destination.

Press `e` on a Markdown file to edit its source in the left pane with a live
preview on the right. Use `Ctrl+S` to save and `Esc` to return to reading.
Unsaved changes prevent leaving the editor; `Ctrl+D` discards them and returns
to reading. Viewer shortcuts become normal text while editing. Converted
documents (PDF, Office, HTML, etc.) are read-only.

Piped input is treated as UTF-8 Markdown and rendered without a full-screen UI.
Redirected output is plain Markdown, useful for saving converted documents.

PDF, Word, PowerPoint, Excel, Outlook, HTML, and MarkItDown's base formats are
included. Conversion quality depends on the source document; scanned PDF OCR
and AI image descriptions are not configured. This viewer accepts local files.

## Development

```sh
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pytest
```
