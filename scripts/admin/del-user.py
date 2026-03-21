#!/usr/bin/env python3
"""
Remove permanentemente uma conta Unix (banimento) no servidor runv.club (Debian).

Usa ``deluser`` com remoção da home. Opcionalmente remove o registro em
``/var/lib/runv/users.json`` se existir.

Executar como root. Não altera Apache nem SSH diretamente.

Versão 0.01 — runv.club
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import pwd
import shutil
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Final

# Com python3 -P ou PYTHONSAFEPATH=1 o diretório deste script não entra em sys.path.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

USERNAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")

# Contas de sistema / serviço — nunca remover por engano
RESERVED_USERNAMES: Final[frozenset[str]] = frozenset(
    {
        "root",
        "daemon",
        "bin",
        "sys",
        "sync",
        "games",
        "man",
        "lp",
        "mail",
        "news",
        "uucp",
        "proxy",
        "www-data",
        "backup",
        "list",
        "irc",
        "_apt",
        "nobody",
    }
)

DEFAULT_METADATA_PATH: Final[Path] = Path("/var/lib/runv/users.json")
DEFAULT_LOCK_PATH: Final[Path] = Path("/var/lib/runv/users.lock")

VERSION: Final[str] = "0.01"

EXIT_OK: Final[int] = 0
EXIT_VALIDATION: Final[int] = 1
EXIT_SYSTEM: Final[int] = 2

MIN_UID_NORMAL_USER: Final[int] = 1000


# ---------------------------------------------------------------------------
# Validação e privilégios
# ---------------------------------------------------------------------------


def validate_privileges() -> None:
    if os.geteuid() != 0:
        print(
            "Este script deve ser executado como root (ou com sudo).",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_VALIDATION)


def validate_username_syntax(username: str) -> str:
    if not username or not username.strip():
        print("Erro: username é obrigatório.", file=sys.stderr)
        raise SystemExit(EXIT_VALIDATION)
    u = username.strip()
    if u != username:
        print("Erro: username não pode ter espaços no início ou fim.", file=sys.stderr)
        raise SystemExit(EXIT_VALIDATION)
    if not USERNAME_PATTERN.fullmatch(u):
        print(
            "Erro: username inválido (use letras minúsculas, dígitos, _ e -; "
            "2–32 caracteres, começando com letra).",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_VALIDATION)
    return u


def check_user_exists(username: str) -> tuple[int, Path]:
    """Retorna (uid, home) ou encerra com erro."""
    try:
        pw = pwd.getpwnam(username)
    except KeyError:
        print(f"Erro: usuário {username!r} não existe neste sistema.", file=sys.stderr)
        raise SystemExit(EXIT_VALIDATION)
    return pw.pw_uid, Path(pw.pw_dir)


def enforce_safety_rules(
    username: str,
    uid: int,
    *,
    force: bool,
) -> None:
    """Impede remoção acidental de contas críticas."""
    if username == "root":
        print("Erro: remover 'root' não é permitido.", file=sys.stderr)
        raise SystemExit(EXIT_VALIDATION)

    if username in RESERVED_USERNAMES and not force:
        print(
            f"Erro: {username!r} é uma conta reservada do sistema. "
            "Se tem certeza absoluta, repita com --force (não recomendado).",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_VALIDATION)

    if uid < MIN_UID_NORMAL_USER and not force:
        print(
            f"Erro: UID {uid} < {MIN_UID_NORMAL_USER} (conta de sistema). "
            "Para remover, use --force (perigoso).",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_VALIDATION)


def confirm_interactive(username: str) -> bool:
    print()
    print("  ATENÇÃO: esta operação remove a conta, a home e o acesso SSH por chave")
    print("           (o utilizador deixa de existir no sistema).")
    print()
    typed = input(f"  Digite exatamente o username para confirmar [{username}]: ").strip()
    return typed == username


# ---------------------------------------------------------------------------
# deluser
# ---------------------------------------------------------------------------


def clear_user_quota_before_removal(
    username: str,
    home: Path,
    *,
    verbose: bool,
    dry_run: bool,
) -> None:
    """
    Se existir ext4+usrquota no mount da home, repõe limites a zero antes de apagar o utilizador
    (alinhado ao mount detetado por create_runv_user / runv_mount).
    """
    from runv_mount import MountLookupError, find_mount_triple, quota_opts_allow_user

    if not shutil.which("setquota"):
        if verbose:
            print("  [info] setquota ausente; não limpo quotas antes de deluser.")
        return
    try:
        tgt, fst, opts = find_mount_triple(home)
    except MountLookupError as e:
        if verbose:
            print(f"  [info] mount da home não resolvido ({e}); salto limpeza de quota.")
        return
    if fst != "ext4" or not quota_opts_allow_user(opts):
        if verbose:
            print("  [info] sem ext4+usrquota neste mount; salto limpeza de quota.")
        return
    cmd = ["setquota", "-u", username, "0", "0", "0", "0", tgt]
    if dry_run:
        print(f"  [dry-run] executaria: {' '.join(cmd)}")
        return
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        print(
            f"  [aviso] setquota para limpar quotas falhou (código {r.returncode}): {err}",
            file=sys.stderr,
        )
        print(
            "  Continuo com deluser; verifique repquota/edquota se necessário.",
            file=sys.stderr,
        )
    elif verbose:
        print(f"  [ok] quotas repostas a ilimitado para {username!r} em {tgt!r}")


def run_deluser(
    username: str,
    *,
    purge_all_files: bool,
    dry_run: bool,
    verbose: bool,
) -> None:
    if dry_run:
        cmd = ["deluser", username]
        if purge_all_files:
            cmd.insert(1, "--remove-all-files")
        else:
            cmd.insert(1, "--remove-home")
        print(f"  [dry-run] executaria: {' '.join(cmd)}")
        return

    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    env["LC_ALL"] = "C"

    cmd: list[str] = ["deluser"]
    if purge_all_files:
        cmd.append("--remove-all-files")
    else:
        cmd.append("--remove-home")
    cmd.append(username)

    if verbose:
        print(f"  [exec] {' '.join(cmd)}")

    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
    except FileNotFoundError:
        print(
            "Erro: comando 'deluser' não encontrado (pacote adduser no Debian).",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_SYSTEM) from None

    if r.returncode != 0:
        print(f"Erro: deluser falhou (código {r.returncode}).", file=sys.stderr)
        if r.stdout:
            print(r.stdout, file=sys.stderr)
        if r.stderr:
            print(r.stderr, file=sys.stderr)
        raise SystemExit(EXIT_SYSTEM)

    if verbose and r.stdout:
        print(r.stdout.rstrip())


# ---------------------------------------------------------------------------
# Metadados runv (users.json)
# ---------------------------------------------------------------------------


def remove_user_metadata(
    metadata_path: Path,
    lock_path: Path,
    username: str,
    *,
    dry_run: bool,
    verbose: bool,
) -> str:
    """
    Remove entrada com mesmo 'username' da lista JSON.
    Retorna: 'removed' | 'absent' | 'skipped' | 'dry-run'
    """
    if not metadata_path.is_file():
        if verbose:
            print(f"  [metadata] ficheiro inexistente, nada a fazer: {metadata_path}")
        return "skipped"

    if dry_run:
        raw = metadata_path.read_text(encoding="utf-8").strip()
        if not raw:
            return "dry-run"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            print(
                f"Aviso: {metadata_path} não é JSON válido; não alterado no dry-run.",
                file=sys.stderr,
            )
            return "dry-run"
        if isinstance(data, list) and any(
            isinstance(x, dict) and x.get("username") == username for x in data
        ):
            print(f"  [dry-run] removeria entrada de {username!r} em {metadata_path}")
        else:
            print(f"  [dry-run] sem entrada para {username!r} em {metadata_path}")
        return "dry-run"

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_f = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        raw = metadata_path.read_text(encoding="utf-8").strip()
        if not raw:
            return "absent"
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            print(
                f"Erro: formato inválido em {metadata_path} (esperada lista JSON).",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_SYSTEM)
        before = len(parsed)
        data = [x for x in parsed if not (isinstance(x, dict) and x.get("username") == username)]
        after = len(data)
        if before == after:
            if verbose:
                print(f"  [metadata] nenhum registo para {username!r} em {metadata_path}")
            return "absent"

        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix="users.",
            suffix=".tmp",
            dir=str(metadata_path.parent),
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as out:
                json.dump(data, out, indent=2, ensure_ascii=False)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp_path, metadata_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        print(f"  [metadata] removido registo de {username!r} em {metadata_path}")
        return "removed"
    finally:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
        lock_f.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove permanentemente um utilizador Unix (banimento, runv.club).",
    )
    parser.add_argument(
        "--username",
        "-u",
        required=True,
        metavar="USER",
        help="nome de utilizador Unix a remover",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="mostra o que seria feito sem remover nada (não exige root)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="mais detalhes na saída",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="não pedir confirmação interativa (para scripts)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="permite remover contas reservadas ou UID de sistema (muito perigoso)",
    )
    parser.add_argument(
        "--purge-all-files",
        action="store_true",
        help="usa deluser --remove-all-files em vez de só --remove-home",
    )
    parser.add_argument(
        "--skip-metadata",
        action="store_true",
        help="não altera /var/lib/runv/users.json",
    )
    parser.add_argument(
        "--metadata-file",
        type=Path,
        default=DEFAULT_METADATA_PATH,
        help=f"caminho do JSON de metadados (default: {DEFAULT_METADATA_PATH})",
    )
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=DEFAULT_LOCK_PATH,
        help=f"ficheiro de lock flock (default: {DEFAULT_LOCK_PATH})",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION} — runv.club",
    )
    args = parser.parse_args()

    username = validate_username_syntax(args.username)

    uid, home = check_user_exists(username)
    enforce_safety_rules(username, uid, force=args.force)

    if args.dry_run:
        print("del-user.py — modo dry-run (nenhuma alteração)\n")
        print(f"  utilizador: {username!r}")
        print(f"  UID:        {uid}")
        print(f"  home:       {home}")
        clear_user_quota_before_removal(
            username,
            home,
            verbose=args.verbose,
            dry_run=True,
        )
        run_deluser(
            username,
            purge_all_files=args.purge_all_files,
            dry_run=True,
            verbose=args.verbose,
        )
        if not args.skip_metadata:
            remove_user_metadata(
                args.metadata_file,
                args.lock_file,
                username,
                dry_run=True,
                verbose=args.verbose,
            )
        print("\nNada foi alterado. Execute sem --dry-run como root para aplicar.")
        return EXIT_OK

    if not args.yes:
        if not confirm_interactive(username):
            print("Cancelado: confirmação não coincide.")
            return EXIT_VALIDATION

    validate_privileges()

    print(f"\ndel-user.py — removendo {username!r} (UID {uid})\n")

    clear_user_quota_before_removal(
        username,
        home,
        verbose=args.verbose,
        dry_run=False,
    )

    run_deluser(
        username,
        purge_all_files=args.purge_all_files,
        dry_run=False,
        verbose=args.verbose,
    )
    print(f"  [ok] deluser concluído para {username!r}")

    if not args.skip_metadata:
        remove_user_metadata(
            args.metadata_file,
            args.lock_file,
            username,
            dry_run=False,
            verbose=args.verbose,
        )

    print("\n--- Resumo ---")
    print(f"  Conta removida: {username!r}")
    print("  Próximo passo: verificar se não restam processos desse UID e revogar acessos externos se aplicável.")

    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
