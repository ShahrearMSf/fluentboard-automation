# Comments endpoints

Base: `/wp-json/fluent-boards/v2`. For posting, prefer `post-comment.sh`. For everything else use `request.sh`.

| # | Method | Path | Purpose |
|---|--------|------|---------|
| 1 | GET | `/projects/{board_id}/tasks/{task_id}/comments` | Paginated comment list. |
| 2 | POST | `/projects/{board_id}/tasks/{task_id}/comments` | Create a comment or a threaded reply. |
| 3 | PUT | `/projects/{board_id}/tasks/comments/{comment_id}` | Edit an existing comment. ⚠ Path omits `tasks/{task_id}` (same shape as DELETE). |
| 4 | DELETE | `/projects/{board_id}/tasks/comments/{comment_id}` | Delete a comment. ⚠ Path omits `tasks/{task_id}`. |
| 5 | POST | `/projects/{board_id}/tasks/{task_id}/comment-image-upload` | Upload an image to embed in a comment. |

## 1. GET — list

Query: `page` (1), `per_page` (10), `type`, `privacy`, `include_replies` (true), `include_images` (true).

Each comment record has: `id`, `board_id`, `task_id`, `parent_id`, `type`, `privacy`, `description`, `created_by`, `created_at`, `replies_count`, `avatar`, `user`, `images`.

## 2. POST — create (or reply)

```json
{
  "comment": "Deployed the fix to staging.",
  "comment_type": "comment",
  "parent_id": 4821,
  "images": [12, 13],
  "mentionData": [42]
}
```

- `comment` (string, required) — the body; URLs auto-linkify.
- `comment_type` (`comment` | `reply`) — required. Use `reply` with `parent_id`.
- `parent_id` (integer) — required for replies, omit for top-level comments.
- `comment_by` (integer, optional) — post as another user (requires permissions).
- `images` — array of image IDs produced by endpoint #5.
- `mentionData` — array of user IDs to @-mention.

`post-comment.sh` handles the JSON escaping and the `comment`/`reply` switch automatically.

## Body sanitization & formatting (what survives, what doesn't)

The server runs every comment body through WordPress's `wp_kses` sanitizer. The exact filter applied depends on the **posting user's WordPress role** — specifically, whether they have the `unfiltered_html` capability (Editor / Administrator on single-site WP). Most app-password setups use a least-privilege Contributor account, which gets the strict filter. Plan accordingly.

### What survives (any role)

- **Plain text** — preserved verbatim, including line breaks (`\n`) and Unicode (emoji, box-drawing chars, ✅ ❌ ☐ 📋 1️⃣ ── ▶).
- **Auto-linked URLs** — write `https://example.com` plain in the body, and the server wraps it in `<a class="fbs_link" target="_blank" rel="noopener noreferrer" href="...">…</a>` automatically (via `make_clickable()` after sanitization). Don't author the anchor yourself.
- **HTML-escaped angle brackets** — `&lt;` / `&gt;` are kept as literal `<` / `>` when rendered. Always escape angle brackets in code-like content (Gutenberg blocks, HTML/XML snippets, file globs) **before** posting; otherwise the sanitizer eats them as real HTML.

### What gets stripped on Contributor-role accounts

- **Headings** (`<h1>`–`<h6>`), **tables** (`<table>`/`<tr>`/`<td>`), **lists** (`<ul>`/`<ol>`/`<li>`), **bold/italic** (`<strong>`/`<em>`), **inline code** (`<code>`), **code blocks** (`<pre>`), and most attributes on surviving tags.
- **Real HTML comments** `<!-- ... -->` — the sanitizer strips these entirely. To include them visibly, encode as `&lt;!-- ... --&gt;`.
- **Hand-authored anchors** with custom classes — including `<a class="fbs_mention" …>` (see Mentions below).

### Formatting recipe that always works

Treat the body as plain text with structural cues drawn in Unicode:

```text
✅ Found okay

Branch: feature/foo
Plugin: BetterDocs 4.3.12

──────────────────────────────────────────────────
🔍 Findings
──────────────────────────────────────────────────

1️⃣ Security validation
  • Reproduced the LFI on master with payload …
  • Fix branch blocks the same payload.

📊 Functional regression — none observed
  ✅ Category Grid · default     → 200 / 0 / OK
  ✅ Category Grid · layout-2    → 200 / 0 / OK

cc: Abu Hurayra
```

Tables collapse to plain lines on save, so render them as ASCII-aligned rows (monospace alignment is preserved if you indent each row to the same width using regular spaces).

## Mentions

```jsonc
{
  "comment": "...cc: Abu Hurayra bhai",
  "comment_type": "comment",
  "mentionData": [17]    // array of WP user IDs
}
```

`mentionData` fires the in-app + email notification regardless of how the comment body looks — that part **always works** via API.

The visible clickable `@Name` link, however, is a UI-editor artifact:

- The Fluentboards admin SPA inserts `<a class="fbs_mention" href="…/member/{user_id}/tasks">Display Name</a>` into the body when a user is picked from the `@`-dropdown. UI posters with `unfiltered_html` (Editors/Admins) keep the anchor on save.
- API posters **without** `unfiltered_html` (Contributor app passwords) get the anchor stripped on save, even when `mentionData` is also passed and even when the anchor is identical to the format used by surviving UI comments. This was confirmed by experiment (POST and PUT, with/without `<p>` wrapping, with/without `mentionData`, with the exact byte-for-byte anchor copied from a UI-posted comment) — every variant stripped on a Contributor account.

**Practical guidance for API mentions:**

1. Pass `mentionData: [user_id, …]` so the notification fires.
2. Write the name in the body as plain text (`cc: Abu Hurayra` or `Hi Abu Hurayra,`). It won't be a clickable link, but the recipient still gets the notification.
3. If a clickable visible mention is required (visual emphasis, design consistency), the only known workarounds are:
   - Have the posting user open the card and add the `@`-mention manually via the UI.
   - Use an Editor/Admin WordPress account for the app password (this requires explicit authorization — Contributor is the recommended least-privilege default and shouldn't be bumped casually).

Don't waste cycles re-trying anchor variants on a Contributor account; the limitation is `unfiltered_html`, not the payload shape.

## 5. POST — upload image for a comment

Multipart body with `file` (single file). Accepted types: JPEG, GIF, PNG, BMP, TIFF, WebP, AVIF, ICO, HEIC.

Response returns an image record with `id`, `full_url`, `secure_url`, `file_size`, `file_hash`, timestamps. Reference the `id` in the `images` array of a subsequent comment create/update.

Note: there is no pre-built script for comment-image upload; use `request.sh` with multipart — or compose a one-off `curl -u "$FLUENTBOARDS_USER:$FLUENTBOARDS_APP_PASSWORD" -F file=@path …` call.
