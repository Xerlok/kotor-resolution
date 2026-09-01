"""Render docs/MOD_PAGE.md into docs/MOD_PAGE.html, a standalone local preview.

    python tools/build_mod_page.py

MOD_PAGE.md is the source of truth. This script renders it three ways in one
file: a decorated "Page Preview" (readable here, not what gets pasted), a
"DeadlyStream Paste" tab built only from tags DeadlyStream's CKEditor paste
filter actually keeps (headings, bold, links, lists, tables, code,
blockquote - no custom classes or colour, since those get stripped on paste
regardless), and the raw Markdown for reference. "Copy Rich Text" copies the
DeadlyStream tab's real DOM selection, so pasting keeps formatting instead of
landing as literal `#`/`**` text. No network access and no JS library: the
HTML is fully rendered here, and the only remote thing in it is the webfont
link, which degrades to system fonts offline.

The decorated blocks (tinted TL;DR panel, numbered prerequisite cards, amber
callouts, coloured compatibility tiers) are derived from the markdown's own
structure, never hand-written, so editing the .md is always enough:

  * everything under "## TL;DR"                -> tinted panel
  * "**<n>. Name** ... <url>" under Requirements -> numbered card
  * a paragraph opening with bold that ends ":" -> amber callout
  * the closing paragraph of Compatibility      -> amber callout
  * "### <tier>" under Compatibility            -> coloured tier card
  * the bullet list under "What the patcher does" -> ticked list

If a rule ever stops matching, that block simply renders as plain markdown -
the preview degrades, it does not break.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "MOD_PAGE.md"
OUT = ROOT / "docs" / "MOD_PAGE.html"

# Compatibility tiers, in the order they read as "best" to "worst".
TIERS = {
    "Tested and working": "c-tested",
    "Compatible": "c-ok",
    "Works, with one setting turned off": "c-partial",
    "Expected to work, not tested": "c-maybe",
    "Not tested": "c-untested",
    "Incompatible": "c-bad",
    "Not supported": "c-no",
}

CARD_RE = re.compile(r"^\*\*(\d+)\.\s*(.+?)\*\*(.*)$", re.S)
URL_RE = re.compile(r"https?://\S+")
LEAD_BOLD_RE = re.compile(r"^\*\*(.+?)\*\*")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def inline(text: str) -> str:
    """Markdown inline formatting -> HTML. Code spans are protected first."""
    spans: list[str] = []

    def stash(m: re.Match) -> str:
        spans.append(html.escape(m.group(1)))
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = URL_RE.sub(lambda m: f'<a href="{m.group(0)}">{m.group(0)}</a>', text)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{spans[int(m.group(1))]}</code>", text)


# --------------------------------------------------------------------------
# markdown -> blocks
# --------------------------------------------------------------------------

def parse(md: str) -> list[dict]:
    lines = md.splitlines()
    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1
            blocks.append({"t": "pre", "text": "\n".join(body)})
            continue

        m = re.match(r"^(#{1,3}) (.*)$", line)
        if m:
            blocks.append({"t": f"h{len(m.group(1))}", "text": m.group(2).strip()})
            i += 1
            continue

        if line.startswith("|") and i + 1 < len(lines) and set(lines[i + 1]) <= set("|-: "):
            head = [c.strip() for c in line.strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            blocks.append({"t": "table", "head": head, "rows": rows})
            continue

        m_ul = re.match(r"^- (.*)", line)
        m_ol = re.match(r"^\d+\. (.*)", line)
        if m_ul or m_ol:
            pat = r"^- (.*)" if m_ul else r"^\d+\. (.*)"
            items = []
            while i < len(lines):
                m = re.match(pat, lines[i])
                if not m:
                    break
                items.append(m.group(1))
                i += 1
            blocks.append({"t": "ul" if m_ul else "ol", "items": items})
            continue

        if not line.strip():
            i += 1
            continue

        para: list[str] = []
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,3} |[-|`]|\d+\. )", lines[i]):
            para.append(lines[i].strip())
            i += 1
        if para:
            blocks.append({"t": "p", "text": " ".join(para)})
        else:
            i += 1

    return blocks


# --------------------------------------------------------------------------
# blocks -> html
# --------------------------------------------------------------------------

def plain(block: dict) -> str:
    t = block["t"]
    if t == "p":
        return f"<p>{inline(block['text'])}</p>"
    if t == "pre":
        return "<pre><code>" + html.escape(block["text"]) + "</code></pre>"
    if t == "table":
        th = "".join(f'<th scope="col">{inline(c)}</th>' for c in block["head"])
        tb = "".join(
            "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in block["rows"]
        )
        return f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>'
    if t in ("ul", "ol"):
        cls = ' class="steps"' if t == "ol" else ""
        body = "".join(f"<li>{inline(it)}</li>" for it in block["items"])
        return f"<{t}{cls}>{body}</{t}>"
    if t == "h3":
        return f"<h3>{inline(block['text'])}</h3>"
    return f"<p>{inline(block.get('text', ''))}</p>"


def is_callout(block: dict) -> bool:
    """A paragraph that opens with bold ending in a colon is a warning."""
    if block["t"] != "p":
        return False
    m = LEAD_BOLD_RE.match(block["text"])
    return bool(m and m.group(1).rstrip().endswith(":"))


def prereq_card(header: dict, body: list[dict]) -> str:
    m = CARD_RE.match(header["text"])
    if not m:
        return plain(header) + "".join(plain(b) for b in body)
    num, name, rest = m.group(1), m.group(2).strip(), m.group(3)

    url_m = URL_RE.search(rest)
    url = url_m.group(0) if url_m else ""
    tag = URL_RE.sub("", rest).strip().strip("()").strip()

    head = f'<span class="prereq-n">{int(num):02d}</span>'
    head += f'<span class="prereq-name">{inline(name)}</span>'
    if tag:
        head += f'<span class="tag">{inline(tag)}</span>'

    inner = ""
    if url:
        label = re.sub(r"^https?://", "", url)
        inner += f'<a class="lnk" href="{url}">{html.escape(label)}</a>'
    inner += "".join(plain(b) for b in body)

    return (
        '<div class="prereq">'
        f'<div class="prereq-head">{head}</div>'
        f'<div class="prereq-body">{inner}</div>'
        "</div>"
    )


def plain_safe(block: dict) -> str:
    """Same as plain(), minus the decorative classes - only tags a CKEditor
    paste filter (DeadlyStream's editor) actually keeps survive here."""
    t = block["t"]
    if t == "table":
        th = "".join(f"<th>{inline(c)}</th>" for c in block["head"])
        tb = "".join(
            "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in block["rows"]
        )
        return f"<table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>"
    if t in ("ul", "ol"):
        body = "".join(f"<li>{inline(it)}</li>" for it in block["items"])
        return f"<{t}>{body}</{t}>"
    if t == "h3":
        return f"<h4>{inline(block['text'])}</h4>"
    return plain(block)


def assemble_safe(blocks: list[dict]) -> str:
    """Render using only tags DeadlyStream's CKEditor paste filter keeps:
    headings, bold/italic, links, code, lists, tables, blockquote, hr.
    No custom classes, no colour, no cards - those get stripped on paste
    regardless, so building them here would just be lying about the result.
    Headings are shifted down one level (h1->h2 etc.) since the page title
    is its own field on DeadlyStream; the body shouldn't repeat it as h1."""
    out: list[str] = []
    i = 0
    section = ""

    while i < len(blocks):
        b = blocks[i]

        if b["t"] == "h1":
            out.append(f"<h2>{inline(b['text'])}</h2>")
            if i + 1 < len(blocks) and blocks[i + 1]["t"] == "p" \
                    and blocks[i + 1]["text"].startswith("**") and blocks[i + 1]["text"].endswith("**"):
                out.append(f'<p><strong>{inline(blocks[i + 1]["text"][2:-2])}</strong></p>')
                i += 1
            out.append("<hr>")
            i += 1
            continue

        if b["t"] == "h2":
            section = b["text"]
            out.append(f"<h3>{inline(section)}</h3>")
            i += 1
            continue

        if b["t"] == "h3":
            out.append(f"<h4>{inline(b['text'])}</h4>")
            i += 1
            continue

        if is_callout(b):
            out.append(f"<blockquote><p>{inline(b['text'])}</p></blockquote>")
            i += 1
            continue

        if b["t"] == "p" and section == "Compatibility":
            nxt = blocks[i + 1]["t"] if i + 1 < len(blocks) else "h2"
            if nxt == "h2":
                out.append(f"<blockquote><p>{inline(b['text'])}</p></blockquote>")
                i += 1
                continue

        out.append(plain_safe(b))
        i += 1

    return "\n".join(out)


def inline_bbcode(text: str) -> str:
    """Markdown inline formatting -> Nexus BBCode. Nexus has no inline-code
    tag, so a code span becomes [font=Courier New] - the same substitution
    the community's markdown->Nexus converters use."""
    spans: list[str] = []

    def stash(m: re.Match) -> str:
        spans.append(m.group(1))
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"[b]\1[/b]", text)
    text = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\*)", r"[i]\1[/i]", text)
    text = URL_RE.sub(lambda m: f"[url={m.group(0)}]{m.group(0)}[/url]", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"[font=Courier New]{spans[int(m.group(1))]}[/font]", text)


def bbcode_table(head: list[str], rows: list[list[str]]) -> str:
    """Nexus BBCode has no table tag at all - the standard workaround (used
    by every markdown->Nexus converter) is a plain aligned table in [code]."""
    cols = list(zip(*([head] + rows)))
    widths = [max(len(c) for c in col) for col in cols]

    def fmt(cells: list[str]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cells, widths))

    lines = [fmt(head), "  ".join("-" * w for w in widths)] + [fmt(r) for r in rows]
    return "[code]\n" + "\n".join(lines) + "\n[/code]"


def render_bbcode(blocks: list[dict]) -> str:
    """Render straight to Nexus BBCode text - not HTML. Nexus's description
    field is a plain-text/BBCode box, not a rich-text paste target, so this
    is meant to be copied as literal text, not copied as a DOM selection.
    Same heading-level shift as the DeadlyStream tab, for the same reason:
    the mod title is already Nexus's own page-title field."""
    out: list[str] = []
    i = 0
    section = ""

    def emit_list(items: list[str], ordered: bool) -> str:
        tag = "[list=1]" if ordered else "[list]"
        body = "\n".join(f"[*]{inline_bbcode(it)}" for it in items)
        return f"{tag}\n{body}\n[/list]"

    while i < len(blocks):
        b = blocks[i]

        if b["t"] == "h1":
            out.append(f"[size=5]{inline_bbcode(b['text'])}[/size]")
            if i + 1 < len(blocks) and blocks[i + 1]["t"] == "p" \
                    and blocks[i + 1]["text"].startswith("**") and blocks[i + 1]["text"].endswith("**"):
                out.append(f"[b]{inline_bbcode(blocks[i + 1]['text'][2:-2])}[/b]")
                i += 1
            out.append("[line]")
            i += 1
            continue

        if b["t"] == "h2":
            section = b["text"]
            out.append(f"[size=4]{inline_bbcode(section)}[/size]")
            i += 1
            continue

        if b["t"] == "h3":
            out.append(f"[size=3]{inline_bbcode(b['text'])}[/size]")
            i += 1
            continue

        if is_callout(b):
            out.append(f"[quote]{inline_bbcode(b['text'])}[/quote]")
            i += 1
            continue

        if b["t"] == "p" and section == "Compatibility":
            nxt = blocks[i + 1]["t"] if i + 1 < len(blocks) else "h2"
            if nxt == "h2":
                out.append(f"[quote]{inline_bbcode(b['text'])}[/quote]")
                i += 1
                continue

        if b["t"] == "p":
            out.append(inline_bbcode(b["text"]))
        elif b["t"] == "pre":
            out.append(f"[code]{b['text']}[/code]")
        elif b["t"] in ("ul", "ol"):
            out.append(emit_list(b["items"], ordered=(b["t"] == "ol")))
        elif b["t"] == "table":
            out.append(bbcode_table(b["head"], b["rows"]))
        i += 1

    return "\n\n".join(out)


def assemble(blocks: list[dict]) -> str:
    out: list[str] = []
    i = 0
    section = ""

    while i < len(blocks):
        b = blocks[i]

        if b["t"] == "h1":
            out.append(f"<h1>{inline(b['text'])}</h1>")
            # a bold-only paragraph straight after the title is the subtitle
            if i + 1 < len(blocks) and blocks[i + 1]["t"] == "p" \
                    and blocks[i + 1]["text"].startswith("**") and blocks[i + 1]["text"].endswith("**"):
                out.append(f'<p class="subtitle">{inline(blocks[i + 1]["text"][2:-2])}</p>')
                i += 1
            out.append('<hr class="rule">')
            i += 1
            continue

        if b["t"] == "h2":
            section = b["text"]
            out.append(f'<h2 id="{slug(section)}">{inline(section)}</h2>')
            i += 1

            # TL;DR: everything up to the next h2 sits in a tinted panel.
            if section.lower().startswith("tl;dr"):
                panel = []
                while i < len(blocks) and blocks[i]["t"] != "h2":
                    panel.append(plain(blocks[i]))
                    i += 1
                out.append('<div class="tldr">' + "".join(panel) + "</div>")
            continue

        if b["t"] == "h3":
            label = b["text"]

            # Compatibility tier -> coloured card wrapping its list.
            if section == "Compatibility" and label in TIERS:
                cls = TIERS[label]
                i += 1
                inner = []
                while i < len(blocks) and blocks[i]["t"] not in ("h2", "h3"):
                    # A closing paragraph that runs straight into the next h2
                    # belongs to the section, not to this tier.
                    nxt = blocks[i + 1]["t"] if i + 1 < len(blocks) else "h2"
                    if blocks[i]["t"] == "p" and nxt == "h2":
                        break
                    inner.append(plain(blocks[i]))
                    i += 1
                out.append(
                    f'<section class="cgroup {cls}">'
                    f'<header><span class="dot"></span><b>{inline(label)}</b></header>'
                    f'<div class="cbody">{"".join(inner)}</div>'
                    "</section>"
                )
                continue

            out.append(f"<h3>{inline(label)}</h3>")
            i += 1

            # Prerequisites -> numbered cards.
            if section == "Requirements" and label.lower().startswith("required"):
                while i < len(blocks) and blocks[i]["t"] not in ("h2", "h3"):
                    blk = blocks[i]
                    if blk["t"] == "p" and CARD_RE.match(blk["text"]):
                        i += 1
                        body = []
                        # A card keeps following paragraphs that are substantial
                        # or open with bold; short plain prose closes it.
                        while i < len(blocks) and blocks[i]["t"] == "p" \
                                and not CARD_RE.match(blocks[i]["text"]) \
                                and (len(blocks[i]["text"]) >= 120 or blocks[i]["text"].startswith("**")):
                            body.append(blocks[i])
                            i += 1
                        out.append(prereq_card(blk, body))
                    else:
                        out.append(plain(blk))
                        i += 1
            continue

        # Ticked list for the patcher's safety checks.
        if b["t"] == "ul" and section.lower().startswith("what the patcher"):
            body = "".join(f"<li>{inline(it)}</li>" for it in b["items"])
            out.append(f'<ul class="checks">{body}</ul>')
            i += 1
            continue

        if is_callout(b):
            out.append(f'<div class="note"><p>{inline(b["text"])}</p></div>')
            i += 1
            continue

        # The closing remark of Compatibility, after every tier, is a warning.
        if b["t"] == "p" and section == "Compatibility":
            nxt = blocks[i + 1]["t"] if i + 1 < len(blocks) else "h2"
            if nxt in ("h2",):
                out.append(f'<div class="note"><p>{inline(b["text"])}</p></div>')
                i += 1
                continue

        out.append(plain(b))
        i += 1

    return "\n".join(out)


def build() -> Path:
    md = SRC.read_text(encoding="utf-8")
    blocks = parse(md)
    body = assemble(blocks)
    ds_body = assemble_safe(blocks)
    bbcode = render_bbcode(blocks)
    nav = "".join(
        f'<li><a href="#{slug(t)}">{html.escape(t)}</a></li>'
        for t in re.findall(r"^## (.+)$", md, re.M)
    )
    raw = json.dumps(md).replace("</", "<\\/")
    bbcode_json = json.dumps(bbcode).replace("</", "<\\/")
    OUT.write_text(
        TEMPLATE.replace("{{NAV}}", nav).replace("{{BODY}}", body)
        .replace("{{DS_BODY}}", ds_body).replace("{{RAW}}", raw)
        .replace("{{BBCODE_HTML}}", html.escape(bbcode)).replace("{{BBCODE_RAW}}", bbcode_json),
        encoding="utf-8",
    )
    return OUT


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>K1 Area Map Fixes</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Saira:wght@500;600;700&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{
  --ground:#e9ecef; --surface:#fff; --surface-2:#f3f5f7;
  --ink:#131a20; --ink-2:#3d4a55; --muted:#697887;
  --line:#d2d9e0; --line-soft:#e2e7ec;
  --accent:#1c6b74; --accent-soft:#e0eef0; --accent-line:#9fc9ce;
  --amber:#8e5f1c; --amber-soft:#f8efdf; --amber-line:#dfc08a;
  --danger:#9c3128; --danger-soft:#f9e8e6; --danger-line:#e0b0ab;
  --code-bg:#f0f3f5;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ground:#0b1015; --surface:#121a21; --surface-2:#182129;
  --ink:#dde5eb; --ink-2:#b3c0cb; --muted:#8593a1;
  --line:#25313b; --line-soft:#1d272f;
  --accent:#5cb8c1; --accent-soft:#102d31; --accent-line:#27585e;
  --amber:#d6a256; --amber-soft:#2a2214; --amber-line:#5c4a28;
  --danger:#e08d84; --danger-soft:#2e1d1b; --danger-line:#5e3a35;
  --code-bg:#0e161c;
}}
:root[data-theme="dark"]{
  --ground:#0b1015; --surface:#121a21; --surface-2:#182129;
  --ink:#dde5eb; --ink-2:#b3c0cb; --muted:#8593a1;
  --line:#25313b; --line-soft:#1d272f;
  --accent:#5cb8c1; --accent-soft:#102d31; --accent-line:#27585e;
  --amber:#d6a256; --amber-soft:#2a2214; --amber-line:#5c4a28;
  --danger:#e08d84; --danger-soft:#2e1d1b; --danger-line:#5e3a35;
  --code-bg:#0e161c;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;color-scheme:light dark}
body{margin:0;background:var(--ground);color:var(--ink);
  font-family:"IBM Plex Sans","Segoe UI",system-ui,sans-serif;font-size:16px;line-height:1.62;
  -webkit-font-smoothing:antialiased}
img{max-width:100%}
[hidden]{display:none!important}

.bar{position:sticky;top:0;z-index:20;background:var(--surface);border-bottom:1px solid var(--line);
  display:flex;align-items:center;gap:16px;padding:12px 24px;flex-wrap:wrap}
.bar-id{display:flex;flex-direction:column;gap:1px;margin-right:auto;min-width:0}
.bar-id b{font-family:Saira,sans-serif;font-weight:600;font-size:15px}
.bar-id span{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.09em;font-weight:500}
.btn{font:inherit;font-size:13px;font-weight:500;font-family:Saira,sans-serif;letter-spacing:.02em;
  padding:7px 14px;border-radius:3px;border:1px solid var(--line);background:var(--surface-2);
  color:var(--ink-2);cursor:pointer;transition:border-color .14s,color .14s,background .14s}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.btn.on{background:var(--accent-soft);border-color:var(--accent);color:var(--accent)}

.shell{display:grid;grid-template-columns:minmax(0,1fr);max-width:1140px;margin:0 auto;padding:0 24px}
@media (min-width:1000px){.shell{grid-template-columns:216px minmax(0,1fr);gap:44px;padding:0 32px}}
nav{display:none}
@media (min-width:1000px){nav{display:block;position:sticky;top:78px;align-self:start;padding:44px 0;
  max-height:calc(100vh - 78px);overflow-y:auto}}
nav ol{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:1px}
nav a{display:block;padding:5px 0 5px 12px;border-left:2px solid var(--line-soft);color:var(--muted);
  text-decoration:none;font-size:13.5px;line-height:1.35;transition:color .14s,border-color .14s}
nav a:hover{color:var(--ink)}
nav a.active{color:var(--accent);border-left-color:var(--accent);font-weight:500}
nav a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.rail-label{font-family:Saira,sans-serif;font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--muted);font-weight:600;padding-bottom:10px}

main{padding:44px 0 96px;min-width:0}
.doc{background:var(--surface);border:1px solid var(--line);border-radius:4px;padding:44px 48px 52px}
@media (max-width:640px){.doc{padding:28px 22px 36px;border-radius:0;margin:0 -24px;border-left:0;border-right:0}}

.doc h1{font-family:Saira,sans-serif;font-weight:700;font-size:clamp(30px,4.6vw,42px);line-height:1.08;
  letter-spacing:-.015em;margin:0;text-wrap:balance}
.subtitle{font-family:Saira,sans-serif;font-weight:500;font-size:16px;color:var(--accent);margin:8px 0 0}
.rule{height:1px;background:var(--line);margin:30px 0 34px;border:0}
.doc h2{font-family:Saira,sans-serif;font-weight:600;font-size:23px;margin:52px 0 0;padding-top:26px;
  border-top:1px solid var(--line-soft);text-wrap:balance;scroll-margin-top:88px}
.doc h2:first-of-type{margin-top:0;border-top:0;padding-top:0}
.doc h3{font-family:Saira,sans-serif;font-weight:600;font-size:16px;margin:32px 0 0;color:var(--ink)}

.doc p{margin:14px 0 0;max-width:66ch;color:var(--ink-2)}
.doc h2 + p,.doc h3 + p{margin-top:12px}
.doc strong{color:var(--ink);font-weight:600}
.doc a{color:var(--accent);text-underline-offset:2px;word-break:break-word}
.doc a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.doc ul,.doc ol{margin:14px 0 0;padding-left:22px;max-width:66ch;color:var(--ink-2)}
.doc li{margin-top:8px}
.doc li::marker{color:var(--muted)}
.doc ol.steps{list-style:none;counter-reset:s;padding-left:0}
.doc ol.steps > li{counter-increment:s;position:relative;padding-left:40px;margin-top:14px}
.doc ol.steps > li::before{content:counter(s);position:absolute;left:0;top:1px;width:25px;height:25px;
  display:grid;place-items:center;border:1px solid var(--accent);border-radius:50%;color:var(--accent);
  font-family:Saira,sans-serif;font-weight:600;font-size:13px;font-variant-numeric:tabular-nums}

/* tinted TL;DR panel */
.tldr{background:var(--accent-soft);border:1px solid var(--accent-line);border-radius:4px;
  padding:22px 26px 26px;margin-top:14px;max-width:70ch}
.tldr p{color:var(--ink);max-width:64ch}
.tldr p:first-child{margin-top:0}

/* amber callout */
.note{margin:18px 0 0;max-width:66ch;background:var(--amber-soft);border:1px solid var(--amber-line);
  border-radius:4px;padding:14px 18px}
.note p{margin:0;color:var(--ink)}

/* numbered prerequisite card */
.prereq{margin-top:18px;border:1px solid var(--line);border-radius:4px;overflow:hidden;max-width:66ch}
.prereq-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;background:var(--surface-2);
  border-bottom:1px solid var(--line);padding:11px 16px}
.prereq-n{font-family:Saira,sans-serif;font-weight:700;font-size:12px;color:var(--accent);
  letter-spacing:.08em;font-variant-numeric:tabular-nums}
.prereq-name{font-family:Saira,sans-serif;font-weight:600;font-size:15.5px;color:var(--ink)}
.tag{font-family:Saira,sans-serif;font-size:10.5px;font-weight:600;letter-spacing:.09em;
  text-transform:uppercase;padding:2px 7px;border-radius:2px;background:var(--amber-soft);
  color:var(--amber);border:1px solid var(--amber-line)}
.prereq-body{padding:13px 16px 16px}
.prereq-body p{margin:0;max-width:60ch}
.prereq-body p + p{margin-top:10px}
.prereq-body .lnk{display:block;margin-bottom:10px;font-family:"IBM Plex Mono",monospace;font-size:12.5px}

/* compatibility tier cards */
.cgroup{margin-top:20px;border:1px solid var(--line);border-radius:4px;overflow:hidden;max-width:66ch}
.cgroup > header{display:flex;align-items:center;gap:9px;padding:9px 15px;border-bottom:1px solid var(--line)}
.cgroup > header b{font-family:Saira,sans-serif;font-weight:600;font-size:12px;letter-spacing:.1em;
  text-transform:uppercase}
.cbody{padding:4px 0 14px}
.cbody ul{margin-top:10px;padding-left:34px;padding-right:18px;max-width:none}
.dot{width:8px;height:8px;border-radius:50%;flex:none;background:var(--muted)}
.c-tested > header{background:var(--accent-soft);border-bottom-color:var(--accent-line)}
.c-tested > header b{color:var(--accent)} .c-tested .dot{background:var(--accent)}
.c-ok > header{background:var(--surface-2)}
.c-ok > header b{color:var(--ink-2)} .c-ok .dot{background:var(--accent);opacity:.55}
.c-partial > header{background:var(--amber-soft);border-bottom-color:var(--amber-line)}
.c-partial > header b{color:var(--amber)} .c-partial .dot{background:var(--amber)}
.c-maybe > header{background:var(--surface-2)}
.c-maybe > header b{color:var(--muted)} .c-maybe .dot{background:var(--muted)}
.c-untested > header{background:var(--surface-2)}
.c-untested > header b{color:var(--muted)} .c-untested .dot{background:var(--muted);opacity:.45}
.c-bad > header{background:var(--danger-soft);border-bottom-color:var(--danger-line)}
.c-bad > header b{color:var(--danger)} .c-bad .dot{background:var(--danger)}
.c-no > header{background:var(--surface-2)}
.c-no > header b{color:var(--danger);opacity:.85} .c-no .dot{background:var(--danger);opacity:.55}

/* ticked safety-check list */
ul.checks{list-style:none;padding-left:0}
ul.checks li{position:relative;padding-left:26px;margin-top:11px}
ul.checks li::before{content:"";position:absolute;left:3px;top:9px;width:7px;height:7px;
  border-left:1.5px solid var(--accent);border-bottom:1.5px solid var(--accent);transform:rotate(-45deg)}

code{font-family:"IBM Plex Mono",ui-monospace,Consolas,monospace;font-size:.875em;background:var(--code-bg);
  border:1px solid var(--line-soft);border-radius:3px;padding:1px 5px;color:var(--ink);word-break:break-word}
pre{margin:16px 0 0;max-width:66ch;background:var(--code-bg);border:1px solid var(--line-soft);
  border-left:2px solid var(--accent);border-radius:3px;padding:13px 16px;overflow-x:auto}
pre code{background:none;border:0;padding:0;font-size:13.5px}

.tw{overflow-x:auto;margin-top:16px;max-width:66ch}
table{border-collapse:collapse;width:100%;font-size:14.5px}
th,td{text-align:left;padding:9px 14px;border-bottom:1px solid var(--line-soft)}
th{font-family:Saira,sans-serif;font-weight:600;font-size:11px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--muted);border-bottom:1px solid var(--line)}
td{color:var(--ink-2);font-variant-numeric:tabular-nums}
td:first-child{font-family:"IBM Plex Mono",monospace;color:var(--ink);font-size:13.5px}
tr:last-child td{border-bottom:0}

#raw-pre,#nexus-pre{max-width:none;border-left-width:1px;max-height:74vh;overflow:auto;white-space:pre-wrap;
  font-size:13px;line-height:1.55}
.raw-hint{font-size:13px;color:var(--muted);margin:0 0 14px;max-width:66ch}

/* the DeadlyStream tab deliberately carries NO custom styling below this
   line - that plainness is what proves the copy is paste-safe */
#ds-content{max-width:66ch}
#ds-content :first-child{margin-top:0}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
</style>
</head>
<body>

<div class="bar">
  <div class="bar-id">
    <b>K1 Area Map Fixes</b>
    <span>DeadlyStream page copy &middot; local preview</span>
  </div>
  <button class="btn on" id="btn-view-rendered" type="button" aria-pressed="true">Page Preview</button>
  <button class="btn" id="btn-view-ds" type="button" aria-pressed="false">DeadlyStream Paste</button>
  <button class="btn" id="btn-view-nexus" type="button" aria-pressed="false">Nexus BBCode</button>
  <button class="btn" id="btn-view-raw" type="button" aria-pressed="false">Markdown</button>
  <button class="btn" id="btn-copy" type="button">Copy Rich Text</button>
</div>

<div class="shell">
  <nav aria-label="Sections">
    <div class="rail-label">On this page</div>
    <ol id="rail">{{NAV}}</ol>
  </nav>
  <main>
    <article class="doc" id="rendered">
{{BODY}}
    </article>
    <article class="doc" id="ds-view" hidden>
      <p class="raw-hint">This box uses your browser's default styling on purpose - no
      custom colours, cards or classes. That plainness is what survives DeadlyStream's
      paste filter: headings, bold, links, lists, tables and code blocks come through;
      anything fancier gets stripped anyway, so faking it here would be misleading.
      Click "Copy Rich Text" above, paste into the description field, and choose
      "keep formatting" if it asks.</p>
      <div id="ds-content">
{{DS_BODY}}
      </div>
    </article>
    <article class="doc" id="nexus-view" hidden>
      <p class="raw-hint">Nexus's description field is plain-text BBCode, not a rich-text
      paste target - so unlike the DeadlyStream tab, this is meant to be pasted as literal
      text. Nexus has no heading tag (shifted to [size=N]) and no table tag at all, so the
      Resolutions table below is a plain aligned table inside [code], the standard
      workaround. Click "Copy BBCode", then paste directly into the description box.</p>
      <pre id="nexus-pre"><code id="nexus-code">{{BBCODE_HTML}}</code></pre>
    </article>
    <article class="doc" id="raw-view" hidden>
      <p class="raw-hint">Raw Markdown - for reference only. Pasting this literally into
      DeadlyStream's editor will NOT render: it has no Markdown parser, so the # and **
      characters would show up as plain text. Use the "DeadlyStream Paste" tab instead.</p>
      <pre id="raw-pre"><code id="raw-code"></code></pre>
    </article>
  </main>
</div>

<script>
(function(){
  var md = {{RAW}};
  var bbcode = {{BBCODE_RAW}};
  document.getElementById('raw-code').textContent = md;
  var panels = {
    rendered: document.getElementById('rendered'),
    ds:       document.getElementById('ds-view'),
    nexus:    document.getElementById('nexus-view'),
    raw:      document.getElementById('raw-view')
  };
  var buttons = {
    rendered: document.getElementById('btn-view-rendered'),
    ds:       document.getElementById('btn-view-ds'),
    nexus:    document.getElementById('btn-view-nexus'),
    raw:      document.getElementById('btn-view-raw')
  };
  var copyLabels = { rendered: 'Copy Rich Text', ds: 'Copy Rich Text', nexus: 'Copy BBCode', raw: 'Copy Markdown' };
  var current = 'rendered';
  var btnCopy = document.getElementById('btn-copy'),
      nav     = document.querySelector('nav');

  function show(which){
    current = which;
    Object.keys(panels).forEach(function(k){
      panels[k].hidden = k !== which;
      buttons[k].classList.toggle('on', k === which);
      buttons[k].setAttribute('aria-pressed', String(k === which));
    });
    btnCopy.textContent = copyLabels[which];
    if (nav) nav.style.visibility = which === 'rendered' ? '' : 'hidden';
    window.scrollTo(0,0);
    sync();
  }
  buttons.rendered.addEventListener('click', function(){ show('rendered'); });
  buttons.ds.addEventListener('click', function(){ show('ds'); });
  buttons.nexus.addEventListener('click', function(){ show('nexus'); });
  buttons.raw.addEventListener('click', function(){ show('raw'); });

  btnCopy.addEventListener('click', function(){
    var done = function(ok){
      var label = copyLabels[current];
      btnCopy.textContent = ok ? 'Copied' : 'Press Ctrl+C';
      btnCopy.classList.add('on');
      setTimeout(function(){ btnCopy.textContent = label; btnCopy.classList.remove('on'); }, 1800);
    };

    if (current === 'raw' || current === 'nexus') {
      var text = current === 'raw' ? md : bbcode;
      var fallbackId = current === 'raw' ? 'raw-code' : 'nexus-code';
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function(){ done(true); }, function(){
          var r = document.createRange();
          r.selectNodeContents(document.getElementById(fallbackId));
          var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
          done(false);
        });
      }
      return;
    }

    if (current !== 'ds') show('ds');
    var el = document.getElementById('ds-content');
    var r = document.createRange();
    r.selectNodeContents(el);
    var s = window.getSelection();
    s.removeAllRanges(); s.addRange(r);
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    s.removeAllRanges();
    done(ok);
  });

  var links = [].slice.call(document.querySelectorAll('#rail a'));
  var targets = links.map(function(a){ return document.getElementById(a.getAttribute('href').slice(1)); });
  function sync(){
    if (panels.rendered.hidden) return;
    var best = 0;
    for (var i=0;i<targets.length;i++){
      if (targets[i] && targets[i].getBoundingClientRect().top <= 120) best = i;
    }
    links.forEach(function(a,i){ a.classList.toggle('active', i===best); });
  }
  var ticking = false;
  window.addEventListener('scroll', function(){
    if (!ticking){ ticking = true; requestAnimationFrame(function(){ sync(); ticking = false; }); }
  }, {passive:true});
  sync();
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(f"wrote {build().relative_to(ROOT)}")
