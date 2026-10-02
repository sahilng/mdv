# Markdown Guide

This guide demonstrates common Markdown features by showing the **Markdown source first**, followed by the **rendered result**.

> Markdown has multiple dialects. Core features work nearly everywhere, while sections marked **GFM** or **extension** may depend on your renderer.

---

## 1. Headings

### Markdown

```markdown
# Heading 1

## Heading 2

### Heading 3

#### Heading 4

##### Heading 5

###### Heading 6
```

### Result

# Heading 1

## Heading 2

### Heading 3

#### Heading 4

##### Heading 5

###### Heading 6

You can also make the first two heading levels like this:

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

---

## 2. Paragraphs

Separate paragraphs with a blank line.

### Markdown

```markdown
This is the first paragraph.

This is the second paragraph.
```

### Result

This is the first paragraph.

This is the second paragraph.

---

## 3. Line Breaks

A common Markdown line break uses two spaces at the end of a line.

### Markdown

```markdown
First line.  
Second line.
```

### Result

First line.  
Second line.

---

## 4. Italic

### Markdown

```markdown
*italic text*

_italic text_
```

### Result

*italic text*

_italic text_

---

## 5. Bold

### Markdown

```markdown
**bold text**

__bold text__
```

### Result

**bold text**

__bold text__

---

## 6. Bold and Italic

### Markdown

```markdown
***bold and italic***

___bold and italic___

**bold with *italic inside***
```

### Result

***bold and italic***

___bold and italic___

**bold with *italic inside***

---

## 7. Strikethrough

**GFM / common extension**

### Markdown

```markdown
~~strikethrough text~~
```

### Result

~~strikethrough text~~

---

## 8. Escaping Markdown Characters

Use a backslash when you want Markdown punctuation to appear literally.

### Markdown

```markdown
\*not italic\*

\# not a heading

\[not a link\]

\`not inline code\`
```

### Result

\*not italic\*

\# not a heading

\[not a link\]

\`not inline code\`

---

## 9. Blockquotes

### Markdown

```markdown
> This is a blockquote.
```

### Result

> This is a blockquote.

Blockquotes can contain multiple paragraphs:

### Markdown

```markdown
> First paragraph.
>
> Second paragraph.
```

### Result

> First paragraph.
>
> Second paragraph.

They can also be nested:

### Markdown

```markdown
> Outer quote
>
> > Nested quote
```

### Result

> Outer quote
>
> > Nested quote

And they can contain other Markdown:

### Markdown

```markdown
> ## Heading in a quote
>
> - list item
> - another item
>
> **bold text**
>
> `inline code`
```

### Result

> ## Heading in a quote
>
> - list item
> - another item
>
> **bold text**
>
> `inline code`

---

## 10. Unordered Lists

You can use `-`, `*`, or `+`.

### Markdown

```markdown
- First item
- Second item
- Third item
```

### Result

- First item
- Second item
- Third item

### Markdown

```markdown
* First item
* Second item
```

### Result

* First item
* Second item

### Markdown

```markdown
+ First item
+ Second item
```

### Result

+ First item
+ Second item

---

## 11. Nested Lists

### Markdown

```markdown
- Parent item
  - Child item
    - Grandchild item
```

### Result

- Parent item
  - Child item
    - Grandchild item

---

## 12. Ordered Lists

### Markdown

```markdown
1. First
2. Second
3. Third
```

### Result

1. First
2. Second
3. Third

Markdown can usually auto-number lists:

### Markdown

```markdown
1. First
1. Second
1. Third
```

### Result

1. First
1. Second
1. Third

You can also start at a different number:

### Markdown

```markdown
5. Five
6. Six
7. Seven
```

### Result

5. Five
6. Six
7. Seven

---

## 13. Mixed Lists

### Markdown

```markdown
1. First item
   - Child A
   - Child B
2. Second item
   1. Nested ordered item
   2. Another nested item
```

### Result

1. First item
   - Child A
   - Child B
2. Second item
   1. Nested ordered item
   2. Another nested item

---

## 14. Multi-Paragraph List Items

### Markdown

```markdown
1. First paragraph in the item.

   Second paragraph in the same item.

2. Next item.
```

### Result

1. First paragraph in the item.

   Second paragraph in the same item.

2. Next item.

---

## 15. Task Lists

**GFM / common extension**

### Markdown

```markdown
- [x] Completed task
- [ ] Incomplete task
- [x] Another completed task
  - [ ] Nested task
```

### Result

- [x] Completed task
- [ ] Incomplete task
- [x] Another completed task
  - [ ] Nested task

---

## 16. Inline Links

### Markdown

```markdown
[Google](https://google.com)
```

### Result

[Google](https://google.com)

---

## 17. Links With Titles

The title may appear as a tooltip in some renderers.

### Markdown

```markdown
[OpenAI](https://openai.com "OpenAI website")
```

### Result

[OpenAI](https://openai.com "OpenAI website")

---

## 18. Reference-Style Links

### Markdown

```markdown
Read more at [OpenAI][openai].

[openai]: https://openai.com
```

### Result

Read more at [OpenAI][openai].

[openai]: https://openai.com

---

## 19. Collapsed Reference Links

### Markdown

```markdown
Visit [Example][].

[Example]: https://example.com
```

### Result

Visit [Example][].

[Example]: https://example.com

---

## 20. Shortcut Reference Links

### Markdown

```markdown
Read about [Markdown].

[Markdown]: https://daringfireball.net/projects/markdown/
```

### Result

Read about [Markdown].

[Markdown]: https://daringfireball.net/projects/markdown/

---

## 21. Relative Links

Useful for linking between files in the same project.

### Markdown

```markdown
[Open another file](./other-file.md)
```

### Result

[Open another file](./other-file.md)

---

## 22. Heading / Anchor Links

### Markdown

```markdown
[Jump to the headings section](#1-headings)
```

### Result

[Jump to the headings section](#1-headings)

Exact anchor generation varies slightly by renderer.

---

## 23. Autolinks

### Markdown

```markdown
<https://example.com>
```

### Result

<https://example.com>

GFM also commonly recognizes plain URLs:

### Markdown

```markdown
https://example.com
```

### Result

https://example.com

---

## 24. Email Autolinks

### Markdown

```markdown
<hello@example.com>
```

### Result

<hello@example.com>

---

## 25. Inline Code

### Markdown

```markdown
Use `git status` to inspect the repository.
```

### Result

Use `git status` to inspect the repository.

If your code itself contains a backtick, surround it with two backticks:

### Markdown

```markdown
``code with a ` backtick``
```

### Result

``code with a ` backtick``

---

## 26. Fenced Code Blocks

### Markdown

````markdown
```
plain text
inside a code block
```
````

### Result

```
plain text
inside a code block
```

---

## 27. Syntax Highlighting

Add a language name after the opening fence.

### Markdown

````markdown
```python
def greet(name):
    return f"Hello, {name}!"

print(greet("world"))
```
````

### Result

```python
def greet(name):
    return f"Hello, {name}!"

print(greet("world"))
```

### JavaScript

#### Markdown

````markdown
```javascript
const add = (a, b) => a + b;
console.log(add(2, 3));
```
````

#### Result

```javascript
const add = (a, b) => a + b;
console.log(add(2, 3));
```

### JSON

#### Markdown

````markdown
```json
{
  "name": "Markdown",
  "works": true
}
```
````

#### Result

```json
{
  "name": "Markdown",
  "works": true
}
```

### Bash

#### Markdown

````markdown
```bash
echo "Hello"
ls -la
```
````

#### Result

```bash
echo "Hello"
ls -la
```

### SQL

#### Markdown

````markdown
```sql
SELECT name, COUNT(*)
FROM users
GROUP BY name;
```
````

#### Result

```sql
SELECT name, COUNT(*)
FROM users
GROUP BY name;
```

---

## 28. Indented Code Blocks

Indent by four spaces.

### Markdown

```markdown
    This is an indented code block.
    Whitespace is preserved.
```

### Result

    This is an indented code block.
    Whitespace is preserved.

---

## 29. Horizontal Rules

Three or more hyphens:

### Markdown

```markdown
---
```

### Result

---

Three or more asterisks:

### Markdown

```markdown
***
```

### Result

***

Three or more underscores:

### Markdown

```markdown
___
```

### Result

___

---

## 30. Tables

**GFM / common extension**

### Markdown

```markdown
| Left | Center | Right |
|:-----|:------:|------:|
| A    | B      | C     |
| 1    | 2      | 3     |
```

### Result

| Left | Center | Right |
|:-----|:------:|------:|
| A    | B      | C     |
| 1    | 2      | 3     |

---

## 31. Formatting Inside Tables

### Markdown

```markdown
| Feature | Example |
|---|---|
| Bold | **bold** |
| Italic | *italic* |
| Code | `code` |
| Link | [Example](https://example.com) |
```

### Result

| Feature | Example |
|---|---|
| Bold | **bold** |
| Italic | *italic* |
| Code | `code` |
| Link | [Example](https://example.com) |

---

## 32. Footnotes

**Common extension**

### Markdown

```markdown
This sentence has a footnote.[^1]

[^1]: This is the footnote text.
```

### Result

This sentence has a footnote.[^1]

[^1]: This is the footnote text.

Named footnotes also work in many renderers:

### Markdown

```markdown
Markdown can have named footnotes.[^markdown-note]

[^markdown-note]: This is a named footnote.
```

### Result

Markdown can have named footnotes.[^markdown-note]

[^markdown-note]: This is a named footnote.

---

## 33. Definition Lists

**Extension**

### Markdown

```markdown
Markdown
: A lightweight markup language.

Renderer
: Software that turns Markdown into formatted output.
```

### Result

Markdown
: A lightweight markup language.

Renderer
: Software that turns Markdown into formatted output.

---

## 34. Raw HTML

Most Markdown renderers allow at least some HTML.

### Markdown

```markdown
<strong>Bold HTML</strong>

<em>Italic HTML</em>
```

### Result

<strong>Bold HTML</strong>

<em>Italic HTML</em>

---

## 35. HTML Line Break

### Markdown

```markdown
First line.<br>
Second line.
```

### Result

First line.<br>
Second line.

---

## 36. Keyboard Keys

Uses inline HTML.

### Markdown

```markdown
Press <kbd>Ctrl</kbd> + <kbd>C</kbd>.
```

### Result

Press <kbd>Ctrl</kbd> + <kbd>C</kbd>.

---

## 37. Highlighting With HTML

### Markdown

```markdown
This is <mark>highlighted</mark>.
```

### Result

This is <mark>highlighted</mark>.

---

## 38. Subscript and Superscript With HTML

### Markdown

```markdown
H<sub>2</sub>O

E = mc<sup>2</sup>
```

### Result

H<sub>2</sub>O

E = mc<sup>2</sup>

---

## 39. Deleted and Inserted Text With HTML

### Markdown

```markdown
<del>Old text</del>

<ins>New text</ins>
```

### Result

<del>Old text</del>

<ins>New text</ins>

---

## 40. Collapsible Sections

Supported by GitHub and many HTML-capable renderers.

### Markdown

```markdown
<details>
<summary>Click to expand</summary>

Hidden content goes here.

</details>
```

### Result

<details>
<summary>Click to expand</summary>

Hidden content goes here.

</details>

You can open it by default:

### Markdown

```markdown
<details open>
<summary>Open by default</summary>

Visible content.

</details>
```

### Result

<details open>
<summary>Open by default</summary>

Visible content.

</details>

---

## 41. GitHub Alerts / Admonitions

**GFM-specific**

### Markdown

```markdown
> [!NOTE]
> Useful information.
```

### Result

> [!NOTE]
> Useful information.

### Markdown

```markdown
> [!TIP]
> A helpful suggestion.
```

### Result

> [!TIP]
> A helpful suggestion.

### Markdown

```markdown
> [!IMPORTANT]
> Important information.
```

### Result

> [!IMPORTANT]
> Important information.

### Markdown

```markdown
> [!WARNING]
> Something could go wrong.
```

### Result

> [!WARNING]
> Something could go wrong.

### Markdown

```markdown
> [!CAUTION]
> Be careful.
```

### Result

> [!CAUTION]
> Be careful.

---

## 42. Emoji

Unicode emoji works directly.

### Markdown

```markdown
😀 🚀 ✅ ⚠️ ❤️
```

### Result

😀 🚀 ✅ ⚠️ ❤️

Some platforms also support shortcode syntax.

### Markdown

```markdown
:smile: :rocket: :white_check_mark:
```

### Result

:smile: :rocket: :white_check_mark:

Shortcode support depends on the renderer.

---

## 43. HTML Comments

HTML comments exist in the source but usually disappear from rendered output.

### Markdown

```markdown
Visible text.

<!-- This comment is hidden. -->

More visible text.
```

### Result

Visible text.

<!-- This comment is hidden. -->

More visible text.

---

## 44. HTML Entities

### Markdown

```markdown
&amp;

&lt;

&gt;

&copy;

&reg;

&trade;
```

### Result

&amp;

&lt;

&gt;

&copy;

&reg;

&trade;

---

## 45. Unicode Characters

Markdown supports ordinary Unicode text.

### Markdown

```markdown
— – … “quotes” © ® ™ ✓ → ∞
```

### Result

— – … “quotes” © ® ™ ✓ → ∞

---

## 46. Math

**Renderer-specific extension**

Inline math:

### Markdown

```markdown
$E = mc^2$
```

### Result

$E = mc^2$

Display math:

### Markdown

```markdown
$$
\sum_{i=1}^{n} i = \frac{n(n+1)}{2}
$$
```

### Result

$$
\sum_{i=1}^{n} i = \frac{n(n+1)}{2}
$$

Another example:

### Markdown

```markdown
$$
\int_{-\infty}^{\infty} e^{-x^2}\,dx = \sqrt{\pi}
$$
```

### Result

$$
\int_{-\infty}^{\infty} e^{-x^2}\,dx = \sqrt{\pi}
$$

---

## 47. Highlight Syntax

**Renderer-specific extension**

### Markdown

```markdown
==highlighted text==
```

### Result

==highlighted text==

If your renderer does not support this syntax, it will simply remain visible as plain text.

---

## 48. Subscript and Superscript Extensions

Some Markdown dialects support these forms.

### Markdown

```markdown
H~2~O

2^10^
```

### Result

H~2~O

2^10^

These are not universally supported.

---

## 49. Wiki Links

**Renderer-specific extension**

Common in editors such as Obsidian.

### Markdown

```markdown
[[Another Page]]

[[Another Page|Custom label]]
```

### Result

[[Another Page]]

[[Another Page|Custom label]]

On unsupported renderers, these remain ordinary text.

---

## 50. Pandoc Citations

**Pandoc extension**

### Markdown

```markdown
According to prior research [@doe2024].

A page-specific citation might look like [@doe2024, pp. 10-12].
```

### Result

According to prior research [@doe2024].

A page-specific citation might look like [@doe2024, pp. 10-12].

Actual citation rendering requires citation metadata and a Pandoc-compatible workflow.

---

## 51. Attribute Lists

**Renderer-specific extension**

### Markdown

```markdown
A paragraph with attributes.
{#custom-id .custom-class}
```

### Result

A paragraph with attributes.
{#custom-id .custom-class}

Support varies by renderer.

---

## 52. Custom Heading IDs

**Renderer-specific extension**

### Markdown

```markdown
## My Heading {#custom-heading}
```

### Result

## My Heading {#custom-heading}

If supported, the heading receives the ID `custom-heading`.

---

## 53. Fenced Divs

**Pandoc / extension**

### Markdown

```markdown
::: warning
This is content inside a custom container.
:::
```

### Result

::: warning
This is content inside a custom container.
:::

Unsupported renderers will display the delimiters as text.

---

## 54. Nested Formatting

Markdown features can often be combined.

### Markdown

```markdown
> ## Release Notes
>
> Version **2.0** includes:
>
> 1. Better formatting
>    - tables
>    - task lists
>    - footnotes
> 2. Better code:
>
>    ```python
>    features = ["tables", "tasks", "footnotes"]
>    print(features)
>    ```
>
> > Nested blockquotes work too.
```

### Result

> ## Release Notes
>
> Version **2.0** includes:
>
> 1. Better formatting
>    - tables
>    - task lists
>    - footnotes
> 2. Better code:
>
>    ```python
>    features = ["tables", "tasks", "footnotes"]
>    print(features)
>    ```
>
> > Nested blockquotes work too.

---

## 55. Markdown Inside HTML

Support varies depending on the renderer.

### Markdown

```markdown
<details>
<summary>Expand me</summary>

- Markdown list
- **Bold Markdown**
- `inline code`

</details>
```

### Result

<details>
<summary>Expand me</summary>

- Markdown list
- **Bold Markdown**
- `inline code`

</details>

---

## 56. Showing Markdown Without Rendering It

The easiest way to document Markdown is to put it inside a fenced code block.

### Markdown

````markdown
```markdown
# Heading

**bold**

*italic*

- list item

[link](https://example.com)
```
````

### Result

```markdown
# Heading

**bold**

*italic*

- list item

[link](https://example.com)
```

---

## 57. Quick Reference

| Feature | Syntax |
|---|---|
| Heading | `# Heading` |
| Bold | `**bold**` |
| Italic | `*italic*` |
| Bold + italic | `***text***` |
| Strikethrough | `~~text~~` |
| Inline code | `` `code` `` |
| Link | `[text](https://example.com)` |
| Blockquote | `> quote` |
| Unordered list | `- item` |
| Ordered list | `1. item` |
| Task | `- [ ] task` |
| Horizontal rule | `---` |
| Footnote | `[^1]` |
| Table | `| A | B |` |
| HTML | `<strong>text</strong>` |

---

## 58. Final Example

### Markdown

````markdown
# My Document

This is **bold**, this is *italic*, and this is `code`.

> A useful quote.

1. First item
2. Second item
   - Nested item

- [x] Done
- [ ] Not done

| Name | Value |
|---|---:|
| A | 10 |
| B | 20 |

[Visit Example](https://example.com)

```python
print("Hello, Markdown!")
```

---

**The end.**
````

### Result

# My Document

This is **bold**, this is *italic*, and this is `code`.

> A useful quote.

1. First item
2. Second item
   - Nested item

- [x] Done
- [ ] Not done

| Name | Value |
|---|---:|
| A | 10 |
| B | 20 |

[Visit Example](https://example.com)

```python
print("Hello, Markdown!")
```

---

**The end.**
