#!/usr/bin/env python3
"""
Proteção comum para scripts administrativos do runv.club.

Regra:
- só operadores administrativos autorizados podem executar os entrypoints protegidos
- a conta root directa também é aceite
- a lista de operadores pode ser ajustada com RUNV_ADMIN_USERS=nome1,nome2
"""

from __future__ import annotations

import getpass
import os
import sys
from typing import Final

DEFAULT_ALLOWED_ADMIN_USERS: Final[tuple[str, ...]] = ("pmurad-admin",)


def resolve_allowed_admin_users() -> set[str]:
    raw = os.environ.get("RUNV_ADMIN_USERS", "").strip()
    if not raw:
        return set(DEFAULT_ALLOWED_ADMIN_USERS)
    names = {part.strip() for part in raw.split(",") if part.strip()}
    return names or set(DEFAULT_ALLOWED_ADMIN_USERS)


def resolve_operator_user() -> str:
    sudo_user = os.environ.get("SUDO_USER", "").strip()
    if sudo_user:
        return sudo_user
    user = os.environ.get("USER", "").strip()
    if user:
        return user
    return getpass.getuser().strip()


def ensure_admin_cli(*, script_name: str, dry_run: bool = False) -> str:
    operator = resolve_operator_user() or "root"
    if operator == "root":
        return operator
    allowed = resolve_allowed_admin_users()
    if operator in allowed:
        return operator
    allowed_list = ", ".join(sorted(allowed))
    print(
        f"Acesso negado em {script_name}: operador {operator!r} não está autorizado. "
        f"Permitidos: root, {allowed_list}.",
        file=sys.stderr,
    )
    raise SystemExit(1)
