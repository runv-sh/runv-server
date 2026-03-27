#!/usr/bin/env python3
"""
Gera ``config.toml`` a partir de ``config.example.toml`` (sem editar o example no git).

Uso típico no servidor após ``git pull`` (evita conflitos se ``config.toml`` não for versionado):

  sudo python3 /opt/runv/src/terminal/gen_config_toml.py --install-root /opt/runv/terminal

No clone local (ficheiro em ``terminal/config.toml``, ignorado pelo git):

  python3 terminal/gen_config_toml.py

O ``setup_entre.py`` chama a mesma função ao instalar o módulo.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Final, Literal

SCRIPT_DIR: Final[Path] = Path(__file__).resolve().parent
ADMIN_DIR: Final[Path] = SCRIPT_DIR.parent / "scripts" / "admin"
if str(ADMIN_DIR) not in sys.path:
    sys.path.insert(0, str(ADMIN_DIR))

from admin_guard import ensure_admin_cli

ADMIN_EMAIL_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r'^(?P<prefix>\s*admin_email\s*=\s*")(?P<value>.*?)(?P<suffix>"\s*)$',
    re.MULTILINE,
)


def preserve_admin_email(*, existing: Path, generated: Path) -> None:
    """Mantém admin_email do config.toml existente ao regenerar a partir do example."""
    if not existing.is_file() or not generated.is_file():
        return
    old_text = existing.read_text(encoding="utf-8")
    new_text = generated.read_text(encoding="utf-8")
    old_match = ADMIN_EMAIL_LINE_RE.search(old_text)
    new_match = ADMIN_EMAIL_LINE_RE.search(new_text)
    if old_match is None or new_match is None:
        return
    old_value = old_match.group("value")
    preserved_line = (
        f'{new_match.group("prefix")}{old_value}{new_match.group("suffix")}'
    )
    updated = ADMIN_EMAIL_LINE_RE.sub(preserved_line, new_text, count=1)
    if updated != new_text:
        generated.write_text(updated, encoding="utf-8")


def write_terminal_config_toml(
    *,
    example: Path,
    out: Path,
    force: bool,
    dry_run: bool,
) -> Literal["wrote", "skipped", "dry_run"]:
    """
    Copia ``example`` para ``out`` se ``out`` não existir ou ``force``.

    Returns:
        ``wrote``, ``skipped`` (já existia e não force), ou ``dry_run``.
    """
    if not example.is_file():
        raise FileNotFoundError(f"modelo em falta: {example}")
    if dry_run:
        return "dry_run"
    if out.is_file() and not force:
        return "skipped"
    previous = out.read_text(encoding="utf-8") if out.is_file() else None
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(example, out)
    if previous is not None:
        tmp_previous = out.with_suffix(out.suffix + ".previous")
        tmp_previous.write_text(previous, encoding="utf-8")
        try:
            preserve_admin_email(existing=tmp_previous, generated=out)
        finally:
            try:
                tmp_previous.unlink()
            except OSError:
                pass
    try:
        out.chmod(0o640)
    except OSError:
        pass
    return "wrote"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera config.toml do módulo entre a partir de config.example.toml.",
    )
    parser.add_argument(
        "--install-root",
        type=Path,
        default=SCRIPT_DIR,
        help="directório do módulo (default: pasta deste script)",
    )
    parser.add_argument(
        "--example",
        type=Path,
        default=None,
        help="caminho explícito do config.example.toml (default: <install-root>/config.example.toml)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="sobrescrever config.toml existente",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    ensure_admin_cli(
        script_name=Path(__file__).name,
        dry_run=bool(args.dry_run),
    )

    root = args.install_root.resolve()
    example = args.example.resolve() if args.example else root / "config.example.toml"
    out = root / "config.toml"

    try:
        result = write_terminal_config_toml(
            example=example,
            out=out,
            force=bool(args.force),
            dry_run=bool(args.dry_run),
        )
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1

    if result == "dry_run":
        print(f"[dry-run] escreveria {out} a partir de {example}")
        return 0
    if result == "skipped":
        print(f"Mantido {out} (use --force para substituir pelo example).")
        return 0
    print(f"Escrito {out} a partir de {example}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
