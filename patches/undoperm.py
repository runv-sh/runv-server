#!/usr/bin/env python3
"""
Reverte o efeito típico de ``scripts/admin/perm1.py`` para utilizadores uid>=1000:

- remove o utilizador do grupo ``runv-jailed``;
- desmonta o bind em ``/srv/jail/<user>/home/<user>`` se estiver montado;
- remove a linha correspondente em ``/etc/fstab``;
- opcionalmente ``--purge-jail-dir`` apaga ``/srv/jail/<user>`` (perigoso).

**Não** restaura ficheiros alterados por ``jk_init``. Executar como root (salvo ``--dry-run``).

Versão 0.01 — runv.club (patch na raiz do repositório)
"""

from __future__ import annotations

import argparse
import logging
import os
import pwd
import shutil
import sys
from pathlib import Path

_PATCHES_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PATCHES_DIR.parent
_ADMIN_DIR = _REPO_ROOT / "scripts" / "admin"
if str(_ADMIN_DIR) not in sys.path:
    sys.path.insert(0, str(_ADMIN_DIR))

import runv_jail as rj

EXCLUDE_NAMES = frozenset({"nobody", "pmurad-admin", "entre"})
VERSION = "0.01"


def setup_logging(verbose: bool) -> logging.Logger:
    log = logging.getLogger("undoperm")
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
        description="Reverte runv-jailed + bind + fstab aplicados por perm1 (uid>=1000).",
    )
    p.add_argument("--dry-run", action="store_true", help="só listar ações previstas")
    p.add_argument("--verbose", "-v", action="store_true", help="log detalhado")
    p.add_argument(
        "--only-user",
        metavar="U",
        default=None,
        help="processar apenas este utilizador (ainda sujeito a exclusões)",
    )
    p.add_argument(
        "--purge-jail-dir",
        action="store_true",
        help="apaga /srv/jail/<user> após umount (DESTRUTIVO; default: não apagar)",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION} — runv.club",
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
        username = pw.pw_name
        real_home = Path(pw.pw_dir).resolve()
        jail_home = rj.jail_bind_mountpoint(username)
        jail_root = rj.JAIL_ROOT / username
        log.info("--- %s (uid=%s) home=%s", username, pw.pw_uid, real_home)

        if args.dry_run:
            log.info(
                "[dry-run] gpasswd -d %s runv-jailed; umount %s; remover bind fstab; purge_jail=%s",
                username,
                jail_home,
                args.purge_jail_dir,
            )
            continue

        try:
            rj.remove_user_from_jailed_group(username, log)
            rj.unbind_jail_home(jail_home, log)
            rj.remove_fstab_bind(real_home, jail_home, log)
            if args.purge_jail_dir:
                if jail_root.is_dir():
                    shutil.rmtree(jail_root)
                    log.info("jail: removido diretório %s", jail_root)
                else:
                    log.debug("jail: %s não existe — purge ignorado", jail_root)
        except Exception as e:
            log.error("falha para %s: %s", username, e)
            return 3

    log.info("concluído (%d utilizador(es))", len(targets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
