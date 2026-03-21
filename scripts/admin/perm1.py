#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import os
import pwd
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import runv_jail as rj

EXCLUDE_NAMES = frozenset({"nobody", "pmurad-admin", "entre"})


def setup_logging(verbose: bool) -> logging.Logger:
    log = logging.getLogger("perm1")
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    log.handlers.clear()
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    log.addHandler(h)
    return log


def iter_targets(only_user: str | None):
    if only_user:
        yield pwd.getpwnam(only_user)
        return
    for pw in pwd.getpwall():
        if pw.pw_uid < 1000:
            continue
        if pw.pw_name in EXCLUDE_NAMES or rj.jail_skip_username(pw.pw_name):
            continue
        yield pw


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Aplica runv-jailed + jail /srv/jail/<user> a contas existentes (uid>=1000).",
    )
    p.add_argument("--dry-run", action="store_true", help="só listar utilizadores e ações previstas")
    p.add_argument("--verbose", "-v", action="store_true", help="log detalhado")
    p.add_argument(
        "--only-user",
        metavar="U",
        default=None,
        help="processar apenas este utilizador (ainda sujeito a exclusões)",
    )
    p.add_argument(
        "--jk-profile",
        default="extendedshell",
        metavar="P",
        choices=("extendedshell", "basicshell"),
        help="perfil Jailkit para jk_init quando o jail ainda não tem bin/ (default: extendedshell)",
    )
    p.add_argument(
        "--no-jk-init",
        action="store_true",
        help="não executar jk_init; exige jail já com bin/ (só grupo + home no jail + bind + fstab)",
    )
    args = p.parse_args(argv)

    log = setup_logging(args.verbose)

    if os.geteuid() != 0 and not args.dry_run:
        log.error("execute como root (ou use --dry-run)")
        return 2

    if args.only_user:
        u = args.only_user.strip()
        if u in EXCLUDE_NAMES or rj.jail_skip_username(u):
            log.error("utilizador %r está excluído desta ferramenta", u)
            return 1

    try:
        targets = list(iter_targets(args.only_user))
    except KeyError as e:
        log.error("utilizador desconhecido: %s", e)
        return 1

    if not targets:
        log.warning("nenhum utilizador corresponde aos critérios")
        return 0

    for pw in targets:
        home = Path(pw.pw_dir)
        log.info("--- %s (uid=%s) home=%s", pw.pw_name, pw.pw_uid, home)
        if args.dry_run:
            if rj.jail_skip_username(pw.pw_name):
                log.info("[dry-run] omitir (exclusão)")
            else:
                log.info(
                    "[dry-run] usermod -aG runv-jailed + jail em /srv/jail/%s "
                    "(jk_profile=%s, no_jk_init=%s)",
                    pw.pw_name,
                    args.jk_profile,
                    args.no_jk_init,
                )
            continue
        try:
            rj.ensure_runv_jail_for_user(
                pw.pw_name,
                home,
                no_jail=False,
                log=log,
                jk_profile=args.jk_profile,
                no_jk_init=args.no_jk_init,
            )
        except Exception as e:
            log.error("falha para %s: %s", pw.pw_name, e)
            return 3

    log.info("concluído (%d utilizador(es))", len(targets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
