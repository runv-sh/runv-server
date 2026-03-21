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
import shutil
import sys
from pathlib import Path
from typing import Final, Literal

SCRIPT_DIR: Final[Path] = Path(__file__).resolve().parent


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
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(example, out)
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
