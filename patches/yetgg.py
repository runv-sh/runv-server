#!/usr/bin/env python3
"""
runv.club — backfill Gopher/Gemini para utilizadores já registados.

Cria ``~/public_gopher``, ``~/public_gemini`` (modelos) e symlinks em
``/var/gemini/users/<user>``, usando a **mesma lista de contas** que o IRC
(união ``users.json`` + ``/home``, filtro ``IRC_PATCH_SKIP_USERS``).

Não instala pacotes nem serviços; ver ``scripts/admin/setup_alt_protocols.py``.

Executar como root em produção. Ver ``--help``.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any, Final

VERSION: Final[str] = "0.01"

GEMINI_ROOT: Final[Path] = Path("/var/gemini")
GEMINI_USERS: Final[Path] = GEMINI_ROOT / "users"


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_script_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"não foi possível carregar {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def setup_logging(verbose: bool) -> logging.Logger:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    return logging.getLogger("yetgg")


def require_root(log: logging.Logger) -> None:
    if os.geteuid() != 0:
        log.error("Execute como root (sudo).")
        raise SystemExit(1)


def ensure_gemini_users_tree(*, dry_run: bool, log: logging.Logger) -> None:
    if GEMINI_USERS.is_dir():
        return
    log.warning("%s inexistente — criar antes dos symlinks Gemini", GEMINI_USERS)
    if dry_run:
        log.info("[dry-run] mkdir -p %s %s (755 root:root)", GEMINI_ROOT, GEMINI_USERS)
        return
    GEMINI_ROOT.mkdir(parents=True, exist_ok=True)
    GEMINI_USERS.mkdir(parents=True, exist_ok=True)
    os.chmod(GEMINI_ROOT, 0o755)
    os.chmod(GEMINI_USERS, 0o755)
    try:
        os.chown(GEMINI_ROOT, 0, 0)
        os.chown(GEMINI_USERS, 0, 0)
    except OSError as e:
        log.warning("chown em %s / %s: %s", GEMINI_ROOT, GEMINI_USERS, e)
    log.info("criado: %s e %s", GEMINI_ROOT, GEMINI_USERS)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill Gopher/Gemini por utilizador (lista como patch_irc).",
    )
    p.add_argument("--dry-run", action="store_true", help="só simular")
    p.add_argument("--verbose", action="store_true", help="log detalhado")
    p.add_argument("--force", action="store_true", help="sobrescrever modelos / symlinks (como setup_alt_protocols)")
    p.add_argument(
        "--users-json",
        type=Path,
        default=Path("/var/lib/runv/users.json"),
        metavar="PATH",
    )
    p.add_argument(
        "--homes-root",
        type=Path,
        default=Path("/home"),
        metavar="PATH",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log = setup_logging(args.verbose)

    if not args.dry_run:
        require_root(log)
    else:
        log.info("dry-run: não grava alterações.")

    root = repo_root()
    patch_irc_path = root / "patches" / "patch_irc.py"
    alt_path = root / "scripts" / "admin" / "setup_alt_protocols.py"
    if not patch_irc_path.is_file():
        log.error("ficheiro em falta: %s", patch_irc_path)
        return 1
    if not alt_path.is_file():
        log.error("ficheiro em falta: %s", alt_path)
        return 1

    patch_irc = load_script_module("patch_irc_dynamic", patch_irc_path)
    setup_alt = load_script_module("setup_alt_protocols_dynamic", alt_path)

    resolve_all_users = patch_irc.resolve_all_users
    ensure_user_public_dirs = setup_alt.ensure_user_public_dirs
    ensure_gemini_symlink = setup_alt.ensure_gemini_symlink

    users = resolve_all_users(args.users_json, args.homes_root, log)
    ensure_gemini_users_tree(dry_run=args.dry_run, log=log)

    failures = 0
    for username in users:
        try:
            ensure_user_public_dirs(
                username,
                args.homes_root,
                force=args.force,
                dry_run=args.dry_run,
                log=log,
            )
            ensure_gemini_symlink(
                username,
                args.homes_root,
                force=args.force,
                dry_run=args.dry_run,
                log=log,
            )
        except OSError as e:
            log.error("%s: %s", username, e)
            failures += 1

    print()
    print("========== yetgg — resumo ==========")
    print(f"Modo: {'DRY-RUN' if args.dry_run else 'aplicação'}")
    print(f"Utilizadores na lista: {len(users)}  falhas: {failures}")
    print(f"JSON: {args.users_json}  homes: {args.homes_root}")
    print("====================================")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
