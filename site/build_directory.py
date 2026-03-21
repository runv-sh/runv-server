#!/usr/bin/env python3
"""
Gera dados públicos para a landing runv.club a partir de /var/lib/runv/users.json.

Expõe apenas: username, since (created_at ISO), path (~user/), e opcionalmente
homepage_mtime se --homes-root existir e public_html/index.html for legível.

Nunca escreve email, fingerprint de chave nem campos de quota detalhados.

Executar no servidor (cron) como root, ou localmente com --users-json apontando
para uma cópia de teste. Se users.json ainda não existir, assume lista vazia (aviso em stderr).

Python 3, só biblioteca padrão.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gera members.json público para site/")
    here = Path(__file__).resolve().parent
    default_out = here / "public" / "data" / "members.json"
    p.add_argument(
        "--users-json",
        type=Path,
        default=Path("/var/lib/runv/users.json"),
        help="Caminho para users.json do provisionador",
    )
    p.add_argument(
        "--output",
        "-o",
        type=Path,
        default=default_out,
        help="Ficheiro JSON de saída (pasta criada se necessário)",
    )
    p.add_argument(
        "--homes-root",
        type=Path,
        default=None,
        help="Se definido (ex. /home), tenta ler mtime de <root>/<user>/public_html/index.html",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Imprime JSON para stdout em vez de gravar ficheiro",
    )
    return p.parse_args()


def homepage_mtime_iso(homes_root: Path, username: str) -> str | None:
    idx = homes_root / username / "public_html" / "index.html"
    try:
        st = idx.stat()
        ts = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
        return ts.isoformat()
    except OSError:
        return None


def load_users(path: Path) -> list[dict]:
    if not path.exists():
        print(
            f"Aviso: {path} ainda não existe; a assumir lista vazia (0 membros).",
            file=sys.stderr,
        )
        return []
    if not path.is_file():
        raise SystemExit(f"Não é um ficheiro: {path}")
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise SystemExit(f"Formato inválido: esperado lista JSON em {path}")
    return data


def main() -> None:
    args = parse_args()
    users = load_users(args.users_json)
    members: list[dict] = []
    for row in users:
        if not isinstance(row, dict):
            continue
        username = row.get("username")
        if not isinstance(username, str) or not username:
            continue
        created = row.get("created_at")
        since = created if isinstance(created, str) else ""
        entry: dict = {
            "username": username,
            "since": since,
            "path": f"/~{username}/",
        }
        if args.homes_root is not None:
            mt = homepage_mtime_iso(args.homes_root, username)
            if mt:
                entry["homepage_mtime"] = mt
        members.append(entry)

    members.sort(key=lambda x: x["username"].lower())

    out_json = json.dumps(members, ensure_ascii=False, indent=2) + "\n"
    if args.dry_run:
        sys.stdout.write(out_json)
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(out_json, encoding="utf-8")
    out_abs = args.output.resolve()
    print(f"Escritos {len(members)} membros em {out_abs}", file=sys.stderr)
    # O browser faz fetch a data/members.json relativo ao index — tem de ser o mesmo ficheiro
    # que o HTTP serve (DocumentRoot), não só a cópia em site/public do repositório.
    norm = str(out_abs).replace("\\", "/")
    if members and "/var/www/" not in norm:
        print(
            "Nota: com membros > 0, confirme que este path é o servido pelo HTTP "
            "(<DocumentRoot>/data/members.json). Se a landing em produção não mostrar os pontos, "
            "use -o ex.: /var/www/runv.club/html/data/members.json ou copie o ficheiro para lá "
            "(ou genlanding.py). Ver site/build_directory.md.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
