# Card description body — format that survives the FB Markdown pipeline

**When to read this:** any time you're about to write a long card description composed from a GitHub issue / PR body, a gist, a Slack message, or any Markdown blob. Comments have their own sanitizer rules (see `endpoints-comments.md`) — this doc is descriptions only.

**Bottom line:** convert Markdown to **explicit HTML** and PUT that. Do NOT paste raw Markdown, do NOT wrap in `<pre>`, do NOT emit HTML tables. Each of those is a specific failure mode documented below.

---

## The three failure modes

### 1. Raw Markdown newlines → collapsed to spaces on save

Sending `## Summary\n\nFree ships the MCP Connector…` stores as `## Summary Free ships the MCP Connector…`. The whole body reads as one paragraph in the UI; headings and lists dissolve. This is the revamped-editor storage behavior — the pre-revamp editor used to preserve newlines from a Markdown POST.

**Fix:** wrap every structural block in an HTML tag (`<p>`, `<h1>`–`<h6>`, `<ul>`/`<li>`, `<blockquote>`). The tag carries the structural break, and the storage layer round-trips it to well-formed Markdown.

### 2. Code fences (` ``` `) → broken language-picker widget

The revamped Markdown editor attaches a language-picker widget above every code fence. Its "Search language" popover renders an **unbounded magnifying-glass SVG** that spans the viewport width and eats the layout. The picker fires regardless of the `language-*` class you set — `bash`, `php`, `plaintext`, `text` all show the giant icon; the small pill next to it reads "Text" regardless. FB strips `class` on `<pre>`/`<code>` on save, so you can't hint the picker to stay collapsed either. This is a FB CSS bug affecting other users' cards too, observed 2026-08-17.

**All of these produce fences and are equally broken:**
- `<pre>content</pre>`
- `<pre><code>content</code></pre>`
- `<pre><code class="language-bash">content</code></pre>` (class stripped by sanitizer)
- `<pre class="wp-block-code">content</pre>`

**Fix:** convert every fenced code block into a `<blockquote>` containing one `<code>` per line joined by `<br>`. Storage becomes:

```
> `line 1`
> `line 2`
```

which the FB Markdown renderer displays as a bordered blockquote of monospace lines. Not a "real" syntax-highlighted code block, but visually clean, no picker, no giant icon.

### 3. HTML `<table>` → cells concatenate with no separator

The sanitizer strips every row and cell tag on save. `<td>Alpha</td><td>Beta</td>` becomes `AlphaBeta` — no space, no delimiter. All cell text runs together, columns are unrecoverable.

**Fix:** flatten Markdown tables into a `<ul>` where each `<li>` is one row. First cell as-is; the remaining cells inlined as bold-labelled clauses joined by middot:

```html
<ul>
  <li><code>ability-name</code> &mdash;
      <strong>Scope:</strong> read &middot;
      <strong>Backs onto:</strong> <code>endpoint</code> &middot;
      <strong>Description:</strong> …
  </li>
  …
</ul>
```

Column alignment is lost, but the columnar meaning is preserved as labelled fields.

---

## Tag survival table (post-revamp, verified against probe cards)

| Tag | What survives on save | Safe? |
|---|---|---|
| `<h1>`–`<h6>` | Becomes `# `/`## `/…. Structural breaks preserved. | ✅ |
| `<p>` | Paragraph, blank-line separated. | ✅ |
| `<ul>`/`<ol>` + `<li>` | `- item` / `1. item` on separate lines. | ✅ |
| `<a href="…">text</a>` | `[text](url)`. | ✅ |
| Inline `<code>` | Backticks around the text. | ✅ |
| `<strong>` / `<em>` | `**bold**` / `*italic*`. | ✅ |
| `<blockquote>` | `> line`. | ✅ |
| `<br>` inside `<p>`/`<blockquote>` | Newline within the block. | ✅ |
| `<hr>` | `---`. | ✅ |
| `<pre>` (any variant) | Becomes ``` fence — **triggers the broken picker widget.** | ❌ |
| `<pre class="wp-block-code">` | `class` stripped, same fence, same picker. | ❌ |
| `<div style="…">` | `style` attribute stripped; content flattens to one line. | ❌ |
| `<table>` + `<tr>` + `<td>` | All row/cell tags stripped; text concatenates. | ❌ |
| Raw newlines outside any tag | Collapsed to spaces. | ❌ |

---

## Recipe

Small HTML header (GitHub link + author, etc.) + `md_to_html(body_md)` where the converter:

- Emits the safe tags above for headings / paragraphs / lists / quotes / rules / links / inline code / bold / italic.
- **Fenced code blocks** (` ``` `) → `<blockquote>` with one `<code>...</code>` per line joined by `<br>`. Not `<pre><code>`.
- **Markdown tables** → `<ul>` per-row with `<strong>Header:</strong> value` clauses. Not `<table>`.
- **Nested inline `<code>` inside `[text](url)`** — the token-stash pass MUST loop until stable. A single `re.sub` pass doesn't recurse into substituted text; a nested token becomes literal `[0]`.
- **Bare-URL autolinker** must NOT wrap URLs already inside `[text](url)` syntax. Protect existing links via stash before autolinking, restore after.

```python
from md2html import md_to_html   # see scripts/

header_html = (
    f'<p><strong>GitHub:</strong> <a href="{url}">{url}</a><br>'
    f'<strong>Author:</strong> {author}</p>'
)
DESC = header_html + "\n" + md_to_html(body_md)

# PUT /projects/{board_id}/tasks/{task_id}  property=description value=DESC
```

Reference implementation: `scripts/md2html.py`.

---

## Probe methodology (validate any storage question in one throwaway card)

When the storage layer's behavior on some new markup is unknown, don't iterate on live cards. Create a **probe card** on some board with N labeled variants of the same content:

```html
<h3>Probe A — variant 1</h3>
<pre>…</pre>

<h3>Probe B — variant 2</h3>
<blockquote><code>…</code></blockquote>

<h3>Probe C — variant 3</h3>
…
```

`PUT` the description, `GET` it back, read the stored form. Anything that came back with a ` ``` ` fence triggers the picker in the UI; anything else is safe. Anything where the visible structure is different from what you sent has been transformed by the sanitizer — read the stored form as the source of truth. Delete the probe card after.

The 2026-08-17 probe (card 84343) ran six variants of code-block markup and identified the blockquote form as the only safe multi-line code representation.
