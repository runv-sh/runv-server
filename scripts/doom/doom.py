#!/usr/bin/env python3
"""
Apaga todas as contas runv listadas em users.json, excepto o conjunto protegido.

Nunca apaga quem está ligado ao processo: ``SUDO_USER``, real UID e effective UID
(cobre ``sudo -u bob``). O ``--keep USER`` define
a conta runv de referência; mesmo assim, quem rodou nunca entra na lista de
remoção. Em sessão root pura (sem SUDO_USER), é obrigatório ``--keep USER``.

Para cada utilizador a remover, delega em ``scripts/admin/del-user.py`` (-y),
para manter o mesmo fluxo (deluser, quotas, users.json).

Executar como root. Operação irreversível.

Versão 0.02 — runv.club
"""

from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import subprocess
import sys
from pathlib import Path
from typing import Final

VERSION: Final[str] = "0.02"
EXIT_OK: Final[int] = 0
EXIT_VALIDATION: Final[int] = 1
EXIT_SYSTEM: Final[int] = 2

USERNAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")

DEFAULT_METADATA_PATH: Final[Path] = Path("/var/lib/runv/users.json")

_DOOM_DIR = Path(__file__).resolve().parent
_REPO_SCRIPTS = _DOOM_DIR.parent
_DEL_USER_PY: Final[Path] = _REPO_SCRIPTS / "admin" / "del-user.py"


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def validate_privileges() -> None:
    if os.geteuid() != 0:
        eprint("Erro: execute como root (ex.: sudo python3 doom.py …).")
        raise SystemExit(EXIT_VALIDATION)


def validate_username_syntax(username: str) -> str:
    if not username or not username.strip():
        eprint("Erro: username vazio.")
        raise SystemExit(EXIT_VALIDATION)
    u = username.strip()
    if not USERNAME_PATTERN.fullmatch(u):
        eprint(
            "Erro: username inválido (minúsculas, dígitos, _ e -; "
            "2–32 caracteres, começando com letra).",
        )
        raise SystemExit(EXIT_VALIDATION)
    return u


def username_for_metadata_match(raw: str) -> str:
    """Forma canónica para comparar com entradas de users.json (runv em minúsculas)."""
    u = raw.strip()
    if not u:
        return u
    if USERNAME_PATTERN.fullmatch(u):
        return u
    low = u.lower()
    if USERNAME_PATTERN.fullmatch(low):
        return low
    return u


def collect_runners_who_must_survive() -> set[str]:
    """
    Contas que não podem ser apagadas em relação a quem corre o processo.

    - SUDO_USER: quem invocou ``sudo`` (quando definido).
    - Real UID e effective UID: cobre ``sudo -u bob`` (RUID ainda pode ser alice,
      EUID é bob — ambos ficam protegidos).
    - Root sem SUDO_USER: também protege ``root`` se existir no JSON.
    """
    out: set[str] = set()
    su = os.environ.get("SUDO_USER", "").strip()
    if su:
        out.add(username_for_metadata_match(su))
    for uid in (os.getuid(), os.geteuid()):
        try:
            login = pwd.getpwuid(uid).pw_name
            if login:
                out.add(username_for_metadata_match(login))
        except KeyError:
            pass
    if os.geteuid() == 0 and not su:
        out.add("root")
    return {x for x in out if x}


def resolve_keeper(args: argparse.Namespace) -> str:
    if args.keep:
        return validate_username_syntax(args.keep)
    if os.geteuid() == 0:
        su = os.environ.get("SUDO_USER", "").strip()
        if su:
            return validate_username_syntax(username_for_metadata_match(su))
        eprint(
            "Erro: sessão root sem SUDO_USER. Indique explicitamente a conta a preservar:\n"
            "       --keep alice\n"
            "       ou execute a partir da conta desejada, ex.: sudo -u alice python3 …/doom.py",
        )
        raise SystemExit(EXIT_VALIDATION)
    return validate_username_syntax(
        username_for_metadata_match(pwd.getpwuid(os.getuid()).pw_name),
    )


def load_runv_usernames(metadata_path: Path) -> list[str]:
    if not metadata_path.is_file():
        return []
    raw = metadata_path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        eprint(f"Erro: JSON inválido em {metadata_path}: {e}")
        raise SystemExit(EXIT_SYSTEM) from e
    if not isinstance(data, list):
        eprint(f"Erro: {metadata_path} deve ser uma lista JSON.")
        raise SystemExit(EXIT_SYSTEM)
    out: list[str] = []
    for item in data:
        if isinstance(item, dict) and item.get("username"):
            u = str(item["username"]).strip()
            if u:
                out.append(u)
    return out


def confirm_doom(keeper: str, protected: set[str], victims: list[str]) -> bool:
    print()
    print("  ═══════════════════════════════════════════════════════════")
    print("  DOOM — remoção em massa de contas runv")
    print("  ═══════════════════════════════════════════════════════════")
    print(f"  Conta runv alvo (referência):  {keeper!r}")
    extra = sorted(protected - {keeper})
    if extra:
        print(f"  Nunca apagar (quem invocou / efectivo):  {', '.join(repr(x) for x in extra)}")
    print(f"  Contas a apagar:   {len(victims)}")
    if victims:
        preview = ", ".join(sorted(victims)[:20])
        if len(victims) > 20:
            preview += ", …"
        print(f"                     {preview}")
    print()
    typed = input("  Digite DOOM em maiúsculas para confirmar: ").strip()
    return typed == "DOOM"


def run_del_user(
    username: str,
    *,
    metadata_path: Path,
    lock_path: Path,
    purge_all_files: bool,
    verbose: bool,
    dry_run: bool,
) -> None:
    if not _DEL_USER_PY.is_file():
        eprint(f"Erro: não encontrei del-user.py em {_DEL_USER_PY}")
        raise SystemExit(EXIT_SYSTEM)

    cmd: list[str] = [
        sys.executable,
        str(_DEL_USER_PY),
        "--username",
        username,
        "--yes",
        "--metadata-file",
        str(metadata_path),
        "--lock-file",
        str(lock_path),
    ]
    if purge_all_files:
        cmd.append("--purge-all-files")
    if verbose:
        cmd.append("--verbose")
    if dry_run:
        cmd.append("--dry-run")

    r = subprocess.run(cmd, timeout=600)
    if r.returncode != 0:
        eprint(f"Erro: del-user.py falhou para {username!r} (código {r.returncode}).")
        raise SystemExit(EXIT_SYSTEM)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Remove todas as contas em users.json excepto a conta indicada (runv.club).",
    )
    p.add_argument(
        "--keep",
        metavar="USER",
        help="conta Unix a preservar (obrigatório se root sem SUDO_USER)",
    )
    p.add_argument(
        "--metadata-file",
        type=Path,
        default=DEFAULT_METADATA_PATH,
        help=f"caminho users.json (default: {DEFAULT_METADATA_PATH})",
    )
    p.add_argument(
        "--lock-file",
        type=Path,
        default=Path("/var/lib/runv/users.lock"),
        help="ficheiro de lock (default: /var/lib/runv/users.lock)",
    )
    p.add_argument(
        "--purge-all-files",
        action="store_true",
        help="repassa --purge-all-files ao del-user (além de --remove-home)",
    )
    p.add_argument("--dry-run", action="store_true", help="só simula (del-user em dry-run)")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="não pedir confirmação DOOM (perigoso)",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION} — runv.club")
    args = p.parse_args()

    keeper = resolve_keeper(args)
    keeper = validate_username_syntax(keeper)

    runners = collect_runners_who_must_survive()
    protected = runners | {keeper}

    all_names = load_runv_usernames(args.metadata_file)
    victims = sorted({u for u in all_names if u not in protected})

    if not victims:
        print(
            f"doom.py — nada a fazer (entradas em users.json já só dentro do conjunto protegido; "
            f"referência {keeper!r}).",
        )
        return EXIT_OK

    if args.dry_run:
        print("doom.py — dry-run\n")
        print(f"  protegidos (nunca apagar): {', '.join(sorted(protected))}")
        for u in victims:
            print(f"  removia:   {u!r}")
        for u in victims:
            run_del_user(
                u,
                metadata_path=args.metadata_file,
                lock_path=args.lock_file,
                purge_all_files=args.purge_all_files,
                verbose=args.verbose,
                dry_run=True,
            )
        return EXIT_OK

    if not args.yes:
        if not confirm_doom(keeper, protected, victims):
            eprint("Cancelado.")
            return EXIT_VALIDATION

    validate_privileges()

    overlap = protected & set(victims)
    if overlap:
        eprint(f"Erro: utilizador(es) protegido(s) na lista de vítimas: {sorted(overlap)!r}")
        return EXIT_SYSTEM

    print(
        f"\ndoom.py — a remover {len(victims)} conta(s); "
        f"protegidos: {', '.join(sorted(protected))}\n",
    )

    for u in victims:
        print(f"--- {u!r} ---")
        run_del_user(
            u,
            metadata_path=args.metadata_file,
            lock_path=args.lock_file,
            purge_all_files=args.purge_all_files,
            verbose=args.verbose,
            dry_run=False,
        )

    print("\n--- Resumo ---")
    print(f"  Protegidos (não removidos): {', '.join(sorted(protected))}")
    print(f"  Removidos:  {len(victims)} utilizador(es) runv.")
    print(f"  Verifique {args.metadata_file} e repquota se necessário.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
