r"""
Fluentboards Markdown → HTML converter, revamped-editor safe.

Key finding (2026-08-17): the revamped FB Markdown editor attaches a language-picker
widget above every code-fence block, and its "Search language" popover renders an
UNBOUNDED magnifying-glass SVG that eats the layout. Setting `language-text`,
`language-bash`, etc. does NOT suppress the picker — every fence triggers it, and
FB's HTML sanitizer strips <pre>/<code> classes on save so we can't hint the
picker to stay collapsed.

Workaround: don't emit code fences. Convert Markdown ``` blocks to a blockquote
containing one <code>...</code> per line joined by <br> (stored form:
> `line` — clean, no fence, no picker). Confirmed via probe card 84343.

See references/description-body-format.md for the full failure-mode catalogue.
"""
import re
from html import escape as esc


def is_table_row(line):
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 2

def is_table_sep(line):
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")): return False
    cells = [c.strip() for c in s.strip("|").split("|")]
    return all(re.match(r'^:?-{3,}:?$', c) for c in cells) and len(cells) >= 1

def parse_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def md_to_html(md):
    lines = md.split("\n")
    out, i, n = [], 0, len(lines)
    in_ul = False
    in_ol = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul: out.append("</ul>"); in_ul = False
        if in_ol: out.append("</ol>"); in_ol = False

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Fenced code block → <blockquote> with <code> per line + <br>
        m = re.match(r'^```([\w+-]*)\s*$', stripped)
        if m:
            close_lists()
            i += 1
            block = []
            while i < n and not re.match(r'^```\s*$', lines[i].strip()):
                block.append(lines[i])
                i += 1
            i += 1
            # blockquote-based code block — avoids the FB picker/search-icon bug
            code_lines = [f"<code>{esc(bl)}</code>" for bl in (block or [""])]
            out.append("<blockquote>" + "<br>".join(code_lines) + "</blockquote>")
            continue

        # Markdown table → <ul><li> per row (HTML <table> is stripped by FB)
        if is_table_row(line) and i + 1 < n and is_table_sep(lines[i+1]):
            close_lists()
            header_cells = parse_row(line)
            i += 2
            data_rows = []
            while i < n and is_table_row(lines[i]):
                data_rows.append(parse_row(lines[i]))
                i += 1
            out.append("<ul>")
            for row in data_rows:
                while len(row) < len(header_cells): row.append("")
                first = fmt_inline(row[0])
                tail_parts = []
                for h, v in zip(header_cells[1:], row[1:len(header_cells)]):
                    if not v: continue
                    tail_parts.append(f"<strong>{esc(h)}:</strong> {fmt_inline(v)}")
                if tail_parts:
                    out.append(f"<li>{first} &mdash; " + " &middot; ".join(tail_parts) + "</li>")
                else:
                    out.append(f"<li>{first}</li>")
            out.append("</ul>")
            continue

        if not stripped:
            close_lists()
            out.append("")
            i += 1
            continue

        m = re.match(r'^(#{1,6})\s+(.*)$', stripped)
        if m:
            close_lists()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{fmt_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        if stripped.startswith(">"):
            close_lists()
            content = stripped.lstrip(">").strip()
            out.append(f"<blockquote>{fmt_inline(content)}</blockquote>")
            i += 1
            continue

        if re.match(r'^-{3,}$', stripped) or re.match(r'^\*{3,}$', stripped):
            close_lists()
            out.append("<hr>")
            i += 1
            continue

        if re.match(r'^[-*+]\s+', stripped):
            if in_ol: out.append("</ol>"); in_ol = False
            if not in_ul: out.append("<ul>"); in_ul = True
            item = re.sub(r'^[-*+]\s+', '', stripped)
            item = re.sub(r'^\[ \]\s*', '☐ ', item)
            item = re.sub(r'^\[x\]\s*', '☑ ', item, flags=re.I)
            out.append(f"<li>{fmt_inline(item)}</li>")
            i += 1
            continue

        if re.match(r'^\d+\.\s+', stripped):
            if in_ul: out.append("</ul>"); in_ul = False
            if not in_ol: out.append("<ol>"); in_ol = True
            item = re.sub(r'^\d+\.\s+', '', stripped)
            out.append(f"<li>{fmt_inline(item)}</li>")
            i += 1
            continue

        close_lists()
        out.append(f"<p>{fmt_inline(stripped)}</p>")
        i += 1

    close_lists()
    return "\n".join(out)


def fmt_inline(s):
    tokens = []
    def stash_code(m):
        tokens.append(f"<code>{esc(m.group(1))}</code>")
        return f"\x00{len(tokens)-1}\x00"
    s = re.sub(r'`([^`]+)`', stash_code, s)

    def stash_link(m):
        text = esc(m.group(1), quote=False)
        url = m.group(2).strip()
        tokens.append(f'<a href="{esc(url, quote=True)}">{text}</a>')
        return f"\x00{len(tokens)-1}\x00"
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', stash_link, s)

    s = esc(s, quote=False)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', s)
    s = re.sub(r'(?<![">\x00])(https?://[^\s<]+[^\s<.,;:!?)\]}])', r'<a href="\1">\1</a>', s)

    def unstash(m): return tokens[int(m.group(1))]
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'\x00(\d+)\x00', unstash, s)
    return s
