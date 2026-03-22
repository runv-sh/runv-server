#!/usr/bin/env python3
"""
Lê ficheiros ``*.md`` nesta pasta (``site/news/``), gera entradas em
``site/public/news/data/news.json``, ``site/public/news/feed.rss`` e
actualiza ``lastmod`` da entrada ``/news/`` em ``site/public/sitemap.xml``.

Formato de cada ``.md``:
  - Linha 1: título
  - Linhas seguintes: corpo (Markdown leve: **negrito**, *itálico*, _itálico_, ++sublinhado++)

Os ``.md`` processados são **apagados**. Ficheiros cujo nome começa por ``_`` são ignorados
(ex.: ``_exemplo.md`` para documentação).

Não versionar notícias no HTML: os dados ficam em ``news.json`` (tipicamente ignorado pelo git
no servidor após gerar conteúdo local).

Após publicar (sem ``--dry-run``), tenta ``site/genlanding.py --sync-public-only`` quando o
DocumentRoot da landing existir (por omissão ``/var/www/runv.club/html``), para copiar
``site/public/`` para o Apache. Em produção use ``sudo``. ``--skip-genlanding`` omite esse passo.

Uso::
    sudo python3 site/news/publish_news.py [--dry-run] [--verbose] [--skip-genlanding]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import uuid
from xml.sax.saxutils import escape as xml_escape
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_SITE = SCRIPT_DIR.parent
_REPO_ROOT = REPO_SITE.parent

PUBLIC_NEWS = REPO_SITE / "public" / "news"
DATA_DIR = PUBLIC_NEWS / "data"
JSON_PATH = DATA_DIR / "news.json"
RSS_PATH = PUBLIC_NEWS / "feed.rss"
SITEMAP_PATH = REPO_SITE / "public" / "sitemap.xml"

TZ_BR: Final[str] = "America/Sao_Paulo"
# Brasil sem DST: fallback se ``tzdata`` não estiver instalado (ex.: Windows minimal).
BR_FALLBACK_TZ = timezone(timedelta(hours=-3))
SITE_URL: Final[str] = "https://runv.club"
DEFAULT_LANDING_DOCUMENT_ROOT: Final[Path] = Path("/var/www/runv.club/html")
DEFAULT_MEMBERS_USERS_JSON: Final[Path] = Path("/var/lib/runv/users.json")


def sync_landing_after_news(
    *,
    document_root: Path,
    members_users_json: Path,
    members_homes_root: Path | None,
    verbose: bool,
) -> int:
    """
    Copia site/public → DocumentRoot via genlanding --sync-public-only.
    Devolve 0 se omitido (sem script / sem DocumentRoot) ou sync OK; 1 se genlanding falhou.
    """
    gl = _REPO_ROOT / "site" / "genlanding.py"
    if not gl.is_file():
        print(
            f"AVISO: genlanding.py não encontrado em {gl}; não sincronizou DocumentRoot.",
            file=sys.stderr,
        )
        return 0
    root = document_root.resolve()
    if not root.is_dir():
        homes_opt = ""
        if members_homes_root is not None:
            homes_opt = f" --members-homes-root {members_homes_root.resolve()}"
        print(
            f"AVISO: DocumentRoot da landing inexistente ({root}) — site/public não foi copiado para Apache.\n"
            f"Manual: sudo python3 {_REPO_ROOT / 'site' / 'genlanding.py'} --sync-public-only "
            f"--document-root {root} --members-users-json {members_users_json}{homes_opt}",
            file=sys.stderr,
        )
        return 0
    admin = _REPO_ROOT / "scripts" / "admin"
    if str(admin) not in sys.path:
        sys.path.insert(0, str(admin))
    from runv_landing_sync import genlanding_sync_command

    cmd = genlanding_sync_command(
        document_root=root,
        users_json=members_users_json.resolve(),
        homes_root=members_homes_root.resolve() if members_homes_root else None,
    )
    if verbose:
        print(f"  $ {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode == 0:
        print(f"Landing sincronizada (public + members) → {root}")
        return 0
    combined = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
    print(
        f"Erro: genlanding --sync-public-only terminou com código {r.returncode}.",
        file=sys.stderr,
    )
    if combined:
        print(combined[:4000], file=sys.stderr)
    return 1


def _apply_underline(s: str) -> str:
    parts = s.split("++")
    out: list[str] = []
    for i, p in enumerate(parts):
        if i % 2 == 0:
            out.append(_apply_italic_underscore(p))
        else:
            out.append("<u>" + html.escape(p) + "</u>")
    return "".join(out)


def _apply_italic_underscore(s: str) -> str:
    parts = re.split(r"(?<!_)_([^_\n]+)_(?!_)", s)
    out: list[str] = []
    for i, p in enumerate(parts):
        if i % 2 == 0:
            out.append(_apply_italic_star(p))
        else:
            out.append("<em>" + html.escape(p) + "</em>")
    return "".join(out)


def _apply_italic_star(s: str) -> str:
    """Itálico com *simples* (não **)."""
    result: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] == "*":
            j = i + 1
            while j < n and s[j] != "*":
                j += 1
            if j < n and s[j] == "*" and j > i + 1:
                inner = s[i + 1 : j]
                result.append("<em>" + html.escape(inner) + "</em>")
                i = j + 1
                continue
        result.append(html.escape(s[i]))
        i += 1
    return "".join(result)


def _apply_bold(s: str) -> str:
    parts = s.split("**")
    out: list[str] = []
    for i, p in enumerate(parts):
        if i % 2 == 0:
            out.append(_apply_underline(p))
        else:
            out.append("<strong>" + html.escape(p) + "</strong>")
    return "".join(out)


def markdown_body_to_html(body: str) -> str:
    body = body.replace("\r\n", "\n").strip()
    if not body:
        return ""
    blocks = re.split(r"\n\s*\n+", body)
    paras: list[str] = []
    for block in blocks:
        lines = block.split("\n")
        inner = "<br>\n".join(_apply_bold(line) for line in lines)
        paras.append(f"<p>{inner}</p>")
    return "\n".join(paras)


def parse_md_file(path: Path) -> tuple[str, str]:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if not lines:
        raise ValueError(f"{path.name}: ficheiro vazio")
    title = lines[0].strip()
    if not title:
        raise ValueError(f"{path.name}: primeira linha (título) vazia")
    body = "\n".join(lines[1:]).lstrip("\n")
    return title, body


def load_articles() -> list[dict[str, Any]]:
    if not JSON_PATH.is_file():
        return []
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    arts = data.get("articles")
    if not isinstance(arts, list):
        return []
    return arts


def save_articles(articles: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(
        json.dumps({"articles": articles}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def br_date_display(now: datetime) -> str:
    return now.strftime("%d-%m-%Y")


def rfc822_date(now: datetime) -> str:
    """RFC 822 / RSS pubDate (locale inglês para dia da semana)."""
    return now.strftime("%a, %d %b %Y %H:%M:%S %z")


def w3c_date(now: datetime) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.isoformat(timespec="seconds")


def build_rss(articles: list[dict[str, Any]], now: datetime) -> str:
    """RSS 2.0; descriptions em CDATA com HTML seguro gerado pelo script."""
    channel_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        f"<title>Notícias — runv.club</title>",
        f"<link>{SITE_URL}/news/</link>",
        "<description>Comunicados e atualizações da comunidade runv.club</description>",
        f"<language>pt-BR</language>",
        f"<lastBuildDate>{rfc822_date(now)}</lastBuildDate>",
        f'<atom:link href="{SITE_URL}/news/feed.rss" rel="self" type="application/rss+xml"/>',
    ]
    for art in articles[:50]:
        title = xml_escape(str(art["title"]))
        aid = xml_escape(str(art["id"]))
        link = f"{SITE_URL}/news/#{aid}"
        pub = art.get("pub_rfc822") or rfc822_date(now)
        body = art.get("body_html") or ""
        desc = f"<![CDATA[{body}]]>"
        channel_parts.extend(
            [
                "<item>",
                f"<title>{title}</title>",
                f"<link>{link}</link>",
                f"<guid isPermaLink=\"false\">{SITE_URL}/news/item-{aid}</guid>",
                f"<pubDate>{pub}</pubDate>",
                f"<description>{desc}</description>",
                "</item>",
            ]
        )
    channel_parts.extend(["</channel>", "</rss>"])
    return "\n".join(channel_parts) + "\n"


def update_sitemap_lastmod(news_lastmod: str) -> None:
    """Actualiza ou insere ``<lastmod>`` só no URL ``/news/``, sem reescrever prefixos XML."""
    if not SITEMAP_PATH.is_file():
        return
    text = SITEMAP_PATH.read_text(encoding="utf-8")
    news_loc = f"<loc>{SITE_URL}/news/</loc>"
    if news_loc not in text:
        return
    lastmod_tag = f"<lastmod>{news_lastmod}</lastmod>"
    block_re = re.compile(
        rf"(\s*<url>\s*{re.escape(news_loc)})(\s*<lastmod>[^<]*</lastmod>)?(\s*</url>)",
        re.DOTALL,
    )

    def repl(m: re.Match[str]) -> str:
        return f"{m.group(1)}\n    {lastmod_tag}{m.group(3)}"

    new_text, n = block_re.subn(repl, text, count=1)
    if n:
        SITEMAP_PATH.write_text(new_text, encoding="utf-8")


def discover_md_files() -> list[Path]:
    out: list[Path] = []
    skip = frozenset({"readme.md", "readme.markdown"})
    for p in sorted(SCRIPT_DIR.glob("*.md")):
        if p.name.startswith("_"):
            continue
        if p.name.lower() in skip:
            continue
        out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Publica notícias a partir de .md em site/news/")
    ap.add_argument("--dry-run", action="store_true", help="Só mostra o que faria")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument(
        "--landing-document-root",
        type=Path,
        default=DEFAULT_LANDING_DOCUMENT_ROOT,
        help=(
            "DocumentRoot Apache; se existir como directório e não usar --skip-genlanding, "
            "corre site/genlanding.py --sync-public-only após publicar"
        ),
    )
    ap.add_argument(
        "--members-users-json",
        type=Path,
        default=DEFAULT_MEMBERS_USERS_JSON,
        help="Fonte para data/members.json no genlanding (default: /var/lib/runv/users.json)",
    )
    ap.add_argument(
        "--members-homes-root",
        type=Path,
        default=None,
        help="Opcional: --members-homes-root para genlanding (ex. /home)",
    )
    ap.add_argument(
        "--skip-genlanding",
        action="store_true",
        help="Não copiar site/public para DocumentRoot após publicar",
    )
    args = ap.parse_args()

    try:
        now = datetime.now(timezone.utc).astimezone(ZoneInfo(TZ_BR))
    except Exception:
        now = datetime.now(BR_FALLBACK_TZ)

    md_files = discover_md_files()
    if not md_files:
        print("Nenhum ficheiro .md para processar (ignore _*.md).", file=sys.stderr)
        return 0

    articles = load_articles()
    pub_rfc = rfc822_date(now)
    date_br = br_date_display(now)
    w3c = w3c_date(now)

    new_entries: list[dict[str, Any]] = []
    for path in md_files:
        try:
            title, body_md = parse_md_file(path)
        except ValueError as e:
            print(f"Erro em {path.name}: {e}", file=sys.stderr)
            return 1
        body_html = markdown_body_to_html(body_md)
        entry = {
            "id": uuid.uuid4().hex[:12],
            "title": title,
            "date": date_br,
            "body_html": body_html,
            "pub_rfc822": pub_rfc,
            "w3c_published": w3c,
        }
        new_entries.append((path, entry))
        if args.verbose:
            print(f"  + {path.name} -> {title!r}")

    if args.dry_run:
        print(f"[dry-run] {len(new_entries)} notícia(s); não gravou nem apagou ficheiros.")
        return 0

    for _path, entry in new_entries:
        articles.insert(0, entry)

    save_articles(articles)
    RSS_PATH.write_text(build_rss(articles, now), encoding="utf-8")

    update_sitemap_lastmod(w3c)

    for path, _entry in new_entries:
        path.unlink()
        if args.verbose:
            print(f"  removido {path.name}")

    print(f"Publicadas {len(new_entries)} notícia(s). Total: {len(articles)}.")

    if not args.skip_genlanding:
        rc = sync_landing_after_news(
            document_root=args.landing_document_root,
            members_users_json=args.members_users_json,
            members_homes_root=args.members_homes_root,
            verbose=args.verbose,
        )
        if rc != 0:
            return rc

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
