# Markdown in mdv

This guide shows Markdown source followed by its result in a Markdown renderer. `mdv` reads the same source in a terminal, so its visual layout differs from a web page. The features below are supported in the interactive reader and editor. The `--print` view supports the same Markdown syntax, with some terminal-specific presentation differences noted below.

## Headings and paragraphs

### Markdown

```markdown
# Heading 1

## Heading 2

### Heading 3

A paragraph is separated from the next by a blank line.

Another paragraph.
```

### Result

# Heading 1

## Heading 2

### Heading 3

A paragraph is separated from the next by a blank line.

Another paragraph.

Headings can use up to six `#` characters. The first two levels also accept underline syntax:

### Markdown

```markdown
Heading 1
=========

Heading 2
---------
```

### Result

Heading 1
=========

Heading 2
---------

## Inline formatting

### Markdown

```markdown
*italic* or _italic_

**bold** or __bold__

***bold and italic***

~~strikethrough~~

Use `inline code` for commands and names.
```

### Result

*italic* or _italic_

**bold** or __bold__

***bold and italic***

~~strikethrough~~

Use `inline code` for commands and names.

Use two backticks around inline code that contains a backtick: ``code with a ` backtick``.

Backslash escapes keep Markdown punctuation literal:

### Markdown

```markdown
\*not italic\* and \[not a link\]
```

### Result

\*not italic\* and \[not a link\]

A backslash before a newline makes a hard line break:

### Markdown

```markdown
First line.\
Second line.
```

### Result

First line.\
Second line.

## Blockquotes

### Markdown

```markdown
> First paragraph.
>
> Second paragraph with **bold** text.
>
> > A nested quote.
```

### Result

> First paragraph.
>
> Second paragraph with **bold** text.
>
> > A nested quote.

## Lists

Unordered lists accept `-`, `*`, or `+`. Ordered lists accept numbers followed by a period or closing parenthesis.

### Markdown

```markdown
- First item
- Second item
  - Nested item

1. First step
2. Second step
   1. Nested step
   2. Another step
```

### Result

- First item
- Second item
  - Nested item

1. First step
2. Second step
   1. Nested step
   2. Another step

The first number sets an ordered list's starting value. Later source numbers do not need to be sequential. Blank lines and indentation allow multiple paragraphs within an item:

### Markdown

```markdown
5. First paragraph in the item.

   Second paragraph in the same item.

6. Next item.
```

### Result

5. First paragraph in the item.

   Second paragraph in the same item.

6. Next item.

Task lists render with checked and unchecked markers:

### Markdown

```markdown
- [x] Finished
- [ ] Still to do
  - [x] Nested task
```

### Result

- [x] Finished
- [ ] Still to do
  - [x] Nested task

## Links and images

Inline links, optional titles, reference links, and angle bracket autolinks work:

### Markdown

```markdown
[Example](https://example.com)

[Example with title](https://example.com "Example website")

[Reference link][example]

<https://example.com>

<hello@example.com>

https://example.com

[example]: https://example.com
```

### Result

[Example](https://example.com)

[Example with title](https://example.com "Example website")

[Reference link][example]

<https://example.com>

<hello@example.com>

https://example.com

[example]: https://example.com

Collapsed (`[Example][]`) and shortcut (`[Example]`) references also work when a matching definition exists. HTTP and HTTPS links open in your browser from the interactive reader. Heading links, such as `[Go to lists](#lists)`, navigate within the document. Other destinations are shown in the app. Anchor names are generated from heading text.

Images use standard Markdown syntax. Because the terminal cannot show the bitmap, `mdv` displays the alt text instead:

### Markdown

```markdown
![A description of the image](diagram.png)
```

## Footnotes

Footnote references receive numbers in order of first use. Their definitions render where they appear in the source.

### Markdown

```markdown
This has a footnote.[^detail]

[^detail]: The note can contain **formatting**.
```

### Result

This has a footnote.[^detail]

[^detail]: The note can contain **formatting**.

## Code blocks

Fence code with backticks or tildes. A language after the opening fence enables syntax highlighting when a lexer is available:

### Markdown

````markdown
```python
print("Hello, Markdown!")
```
````

### Result

```python
print("Hello, Markdown!")
```

Indenting by four spaces also creates a code block:

### Markdown

```markdown
    Code without a fence.
    Whitespace is preserved.
```

### Result

    Code without a fence.
    Whitespace is preserved.

## Rules and tables

A line of at least three hyphens, asterisks, or underscores makes a horizontal rule:

### Markdown

```markdown
---
```

### Result

---

Pipe tables support left, center, and right alignment. Cells can contain inline formatting:

### Markdown

```markdown
| Left | Center | Right |
|:-----|:------:|------:|
| **A** | `code` | 10 |
| B | [Link](https://example.com) | 20 |
```

### Result

| Left | Center | Right |
|:-----|:------:|------:|
| **A** | `code` | 10 |
| B | [Link](https://example.com) | 20 |

## Embedded HTML

`mdv` converts common HTML blocks such as headings, paragraphs, lists, tables, and links for terminal display. Inline `<strong>`, `<em>`, `<del>`, `<code>`, `<a>`, `<br>`, and `<img>` tags are handled. HTML entities and ordinary Unicode characters display as text. HTML source stays intact while editing.

### Markdown

```markdown
<strong>Bold HTML</strong> and <em>italic HTML</em>.

First line.<br>Second line.

&lt;tag&gt; &amp; ©
```

### Result

<strong>Bold HTML</strong> and <em>italic HTML</em>.

First line.<br>Second line.

&lt;tag&gt; &amp; ©

A `<details>` block has a clickable summary in the interactive reader. In `--print`, its content is shown without a collapsible control:

### Markdown

```markdown
<details>
<summary>Example</summary>

Hidden content goes here.

</details>
```

### Result

<details>
<summary>Example</summary>

Hidden content goes here.

</details>

HTML comments are hidden, and scripts and styles are discarded. CSS and JavaScript are not executed.

## GitHub alerts

The five GitHub alert types render with a labeled quote and colored border in the interactive reader. `--print` shows a bold label.

### Markdown

```markdown
> [!NOTE]
> Useful information.

> [!WARNING]
> Be careful.
```

### Result

> [!NOTE]
> Useful information.

> [!WARNING]
> Be careful.

`TIP`, `IMPORTANT`, and `CAUTION` use the same syntax.

## Combining features

### Markdown

````markdown
# Release notes

Version **2.0** includes:

1. Better tables
2. Syntax-highlighted code

> See [the project page](https://example.com) for details.

| Feature | Status |
|---|---|
| Reader | Ready |

```python
print("Done")
```
````

### Result

# Release notes

Version **2.0** includes:

1. Better tables
2. Syntax-highlighted code

> See [the project page](https://example.com) for details.

| Feature | Status |
|---|---|
| Reader | Ready |

```python
print("Done")
```
