#!/usr/bin/env python3
"""
Gera HTML estático em site/public/wiki/ a partir dos .txt em site/wiki/.
Executar localmente antes de site/genlanding.py. Não copia para o servidor
por si — só o conteúdo de site/public/ é implantado.

Apenas biblioteca padrão Python 3.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SITE_DIR = SCRIPT_DIR.parent
OUT_DIR = SITE_DIR / "public" / "wiki"
SITEMAP_PATH = SITE_DIR / "public" / "sitemap.xml"

TXT_GLOB = "[0-9][0-9]_*.txt"
SLUG_RE = re.compile(r"^(\d+)_(.+)\.txt$")


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def is_heading_line(s: str) -> bool:
    s = s.strip()
    if not s or len(s) > 120:
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    return all(c.isupper() for c in letters)


def paragraph_blocks(text: str) -> list[list[str]]:
    lines = text.strip().splitlines()
    blocks: list[list[str]] = []
    cur: list[str] = []
    for line in lines:
        if not line.strip():
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(line.rstrip())
    if cur:
        blocks.append(cur)
    return blocks


def block_to_html(block: list[str], *, is_first: bool) -> str:
    if len(block) == 1:
        line = block[0].strip()
        if is_first:
            return f'<h1 class="hero-title subpage-title wiki-page-title">{html.escape(line)}</h1>'
        if is_heading_line(line):
            return f"<h2>{html.escape(line)}</h2>"
        return f"<p>{html.escape(line)}</p>"

    stripped = [l.strip() for l in block if l.strip()]
    if stripped and all(
        s.startswith("- ") or s.startswith("– ") or s.startswith("— ") for s in stripped
    ):
        items = []
        for s in stripped:
            for prefix in ("- ", "– ", "— "):
                if s.startswith(prefix):
                    items.append(s[len(prefix) :])
                    break
        lis = "".join(f"<li>{html.escape(i)}</li>" for i in items)
        return f"<ul>{lis}</ul>"

    inner = "<br>\n".join(html.escape(l) for l in block)
    return f"<p>{inner}</p>"


def txt_to_article_body(raw: str) -> str:
    blocks = paragraph_blocks(raw)
    parts: list[str] = []
    for i, b in enumerate(blocks):
        parts.append(block_to_html(b, is_first=(i == 0)))
    return "\n\n".join(parts)


def page_shell(
    *,
    title: str,
    description: str,
    body_main: str,
    nav_pages: list[tuple[str, str]],
    current_slug: str | None,
) -> str:
    nav_items = []
    for slug, label in nav_pages:
        if current_slug is not None and slug == current_slug:
            nav_items.append(
                f'<span class="hero-nav-current" aria-current="page">{html.escape(label)}</span>'
            )
        else:
            href = "/wiki/" if slug == "index" else f"/wiki/{slug}.html"
            nav_items.append(f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>')
    nav_inner = '\n        <span class="hero-nav-sep" aria-hidden="true">·</span>\n        '.join(
        nav_items
    )
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(description)}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&family=IBM+Plex+Mono:wght@400;600&family=Syne:wght@600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../assets/style.css">
</head>
<body>
  <div class="wrap">
    <nav class="top-nav"><a href="/">← runv.club</a></nav>

    <header>
      <p class="eyebrow">runv.club</p>
      <nav class="hero-nav wiki-hero-nav" aria-label="Páginas da wiki">
        <a href="/news/">Notícias</a>
        <span class="hero-nav-sep" aria-hidden="true">·</span>
        {nav_inner}
        <span class="hero-nav-sep" aria-hidden="true">·</span>
        <a href="/junte-se/">Junte-se</a>
      </nav>
    </header>

    <main class="section prose-block subpage-main wiki-main">
{body_main}
    </main>

    <footer class="site-footer">
      <p>Administração: <a href="mailto:admin@runv.club">admin@runv.club</a><span class="footer-sep" aria-hidden="true"> · </span><a href="/faq/" class="footer-link-discrete">FAQ</a></p>
    </footer>
  </div>
</body>
</html>
"""


LABELS: dict[str, str] = {
    "index": "Índice",
    "visao-geral": "Visão geral",
    "contas-e-acesso": "Contas e acesso",
    "regras-da-comunidade": "Regras",
    "punicoes-e-moderacao": "Punições",
    "privacidade-e-seguranca": "Privacidade",
    "faq": "FAQ wiki",
}


def slug_and_label(path: Path) -> tuple[str, str] | None:
    m = SLUG_RE.match(path.name)
    if not m:
        return None
    slug = m.group(2)
    label = LABELS.get(slug, slug.replace("-", " ").title())
    return slug, label


def first_line_title(raw: str) -> str:
    for line in raw.strip().splitlines():
        t = line.strip()
        if t:
            return t[:70] + ("…" if len(t) > 70 else "")
    return "Wiki"


def build_nav_order(paths: list[Path]) -> list[tuple[str, str]]:
    ordered: list[tuple[str, str]] = []
    for p in sorted(paths):
        sl = slug_and_label(p)
        if sl:
            ordered.append(sl)
    # Índice primeiro na nav
    idx = next((i for i, (s, _) in enumerate(ordered) if s == "index"), None)
    if idx is not None and idx > 0:
        ordered.insert(0, ordered.pop(idx))
    return ordered


def patch_sitemap(wiki_urls: list[str]) -> None:
    if not SITEMAP_PATH.is_file():
        return
    text = SITEMAP_PATH.read_text(encoding="utf-8")
    marker_start = "  <!-- wiki:gerado -->"
    marker_end = "  <!-- /wiki:gerado -->"
    block_lines = [marker_start]
    for url in wiki_urls:
        block_lines.append("  <url>")
        block_lines.append(f"    <loc>{html.escape(url)}</loc>")
        block_lines.append("  </url>")
    block_lines.append(marker_end)
    new_block = "\n".join(block_lines) + "\n"

    if marker_start in text and marker_end in text:
        before, rest = text.split(marker_start, 1)
        _, after = rest.split(marker_end, 1)
        text = before + new_block + after.lstrip("\n")
    else:
        text = text.replace(
            "</urlset>",
            new_block + "</urlset>",
            1,
        )
    SITEMAP_PATH.write_text(text, encoding="utf-8")


def main() -> int:
    txt_files = sorted(SCRIPT_DIR.glob(TXT_GLOB))
    if not txt_files:
        eprint("Nenhum ficheiro", TXT_GLOB, "em", SCRIPT_DIR)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    nav_pages = build_nav_order(txt_files)

    base_url = "https://runv.club"
    wiki_urls: list[str] = [f"{base_url}/wiki/"]

    for path in txt_files:
        sl = slug_and_label(path)
        if not sl:
            continue
        slug, _label = sl
        raw = path.read_text(encoding="utf-8")
        title_line = first_line_title(raw)
        article = txt_to_article_body(raw)

        if slug == "index":
            toc = ['<nav class="wiki-toc" aria-label="Nesta wiki"><p class="wiki-toc-title">Páginas</p><ul>']
            for s, lab in nav_pages:
                if s == "index":
                    continue
                toc.append(
                    f'<li><a href="/wiki/{html.escape(s, quote=True)}.html">{html.escape(lab)}</a></li>'
                )
            toc.append("</ul></nav>")
            body_main = "\n".join(toc) + "\n" + article
            out_name = "index.html"
            current = "index"
            desc = "Mapa e índice da wiki runv.club."
        else:
            body_main = article
            out_name = f"{slug}.html"
            current = slug
            desc = f"{title_line} — wiki runv.club."
            wiki_urls.append(f"{base_url}/wiki/{slug}.html")

        full_title = f"{title_line} — Wiki runv.club" if slug != "index" else "Wiki — runv.club"
        html_out = page_shell(
            title=full_title,
            description=desc,
            body_main=body_main,
            nav_pages=nav_pages,
            current_slug=current,
        )
        (OUT_DIR / out_name).write_text(html_out, encoding="utf-8")
        print("Wrote", OUT_DIR / out_name)

    wiki_urls = sorted(set(wiki_urls))
    patch_sitemap(wiki_urls)
    print("Updated", SITEMAP_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
