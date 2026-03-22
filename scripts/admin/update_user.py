#!/usr/bin/env python3
"""
Atualiza utilizador Unix existente no runv.club: email do utilizador (users.json), chave SSH,
palavra-passe de login (chpasswd) e quotas ext4 (setquota).

Executar como root. Alinha-se a create_runv_user / del-user / runv_mount.

Modo interativo no terminal (sem argumentos ou -i) ou flags CLI.

Após gravar ``users.json``, pode sincronizar a landing pública com
``site/genlanding.py --sync-public-only`` (como ``create_runv_user`` / ``del-user``).

Versão 0.03 — runv.club
"""

from __future__ import annotations

import argparse
import fcntl
import getpass
import json
import logging
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any, Final

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from runv_landing_sync import try_sync_landing_via_genlanding

USERNAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)
ALLOWED_KEY_TYPES: Final[tuple[str, ...]] = (
    "ssh-ed25519",
    "sk-ssh-ed25519@openssh.com",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "ssh-rsa",
)
FINGERPRINT_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"\b(SHA256:[+A-Za-z0-9/_=-]+)\b")

DEFAULT_METADATA_PATH: Final[Path] = Path("/var/lib/runv/users.json")
DEFAULT_LOCK_PATH: Final[Path] = Path("/var/lib/runv/users.lock")

DEFAULT_QUOTA_SOFT_MIB: Final[int] = 450
DEFAULT_QUOTA_HARD_MIB: Final[int] = 500
DEFAULT_QUOTA_INODE_SOFT: Final[int] = 10_000
DEFAULT_QUOTA_INODE_HARD: Final[int] = 12_000

VERSION: Final[str] = "0.03"
EXIT_OK: Final[int] = 0
EXIT_VALIDATION: Final[int] = 1
EXIT_SYSTEM: Final[int] = 2

MIN_UID_NORMAL_USER: Final[int] = 1000


def setup_update_user_log() -> logging.Logger:
    log = logging.getLogger("runv.update_user")
    log.setLevel(logging.INFO)
    log.propagate = False
    if not log.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        log.addHandler(h)
    return log


def maybe_sync_landing_after_metadata(
    *,
    skip_metadata: bool,
    no_refresh_landing_members: bool,
    landing_document_root: Path | None,
    metadata_file: Path,
    members_homes_root: Path | None,
    dry_run: bool,
    log: logging.Logger,
) -> None:
    if dry_run or skip_metadata or no_refresh_landing_members or landing_document_root is None:
        return
    root = landing_document_root.resolve()
    if not root.is_dir():
        log.warning("DocumentRoot da landing inexistente (%s); sync omitido", root)
        return
    log.info("sincronizar landing (public + members) em %s", root)
    try_sync_landing_via_genlanding(
        document_root=root,
        users_json=metadata_file,
        homes_root=members_homes_root.resolve() if members_homes_root else None,
        log=log,
    )


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def require_root(*, dry_run: bool) -> None:
    if not dry_run and os.geteuid() != 0:
        eprint("Erro: execute como root (sudo).")
        raise SystemExit(EXIT_VALIDATION)


def validate_username_syntax(username: str) -> str:
    if not username or not username.strip():
        eprint("Erro: username é obrigatório.")
        raise SystemExit(EXIT_VALIDATION)
    u = username.strip()
    if not USERNAME_PATTERN.fullmatch(u):
        eprint(
            "Erro: username inválido (letras minúsculas, dígitos, _ e -; 2–32 chars, começa com letra)."
        )
        raise SystemExit(EXIT_VALIDATION)
    return u


def validate_email(email: str) -> str:
    e = email.strip()
    if not EMAIL_PATTERN.fullmatch(e):
        raise ValueError("formato de email inválido")
    return e


def check_user_exists(username: str) -> tuple[int, int, Path]:
    try:
        pw = pwd.getpwnam(username)
    except KeyError:
        eprint(f"Erro: utilizador {username!r} não existe no sistema.")
        raise SystemExit(EXIT_VALIDATION)
    if pw.pw_uid < MIN_UID_NORMAL_USER:
        eprint(f"Erro: UID {pw.pw_uid} < {MIN_UID_NORMAL_USER} (conta de sistema).")
        raise SystemExit(EXIT_VALIDATION)
    return pw.pw_uid, pw.pw_gid, Path(pw.pw_dir)


def normalize_public_key(raw: str) -> str:
    if "\n" in raw or "\r" in raw:
        raise ValueError("chave deve ser uma única linha")
    line = raw.strip()
    if not line:
        raise ValueError("chave vazia")
    parts = line.split()
    if len(parts) < 2:
        raise ValueError("chave malformada")
    if parts[0] not in ALLOWED_KEY_TYPES:
        raise ValueError(f"tipo de chave não permitido: {parts[0]!r}")
    blob = parts[1]
    if not re.fullmatch(r"[A-Za-z0-9+/]+=*", blob):
        raise ValueError("dados base64 inválidos")
    out = parts[0] + " " + blob
    if len(parts) > 2:
        out += " " + " ".join(parts[2:])
    return out


def compute_public_key_fingerprint(public_key_line: str) -> str:
    line = normalize_public_key(public_key_line)
    fd, tmppath = tempfile.mkstemp(prefix="runv-upd-key-", suffix=".pub")
    path = Path(tmppath)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(line + "\n")
        proc = subprocess.run(
            ["ssh-keygen", "-l", "-E", "sha256", "-f", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise ValueError(f"ssh-keygen: {err}")
        first = (proc.stdout or "").strip().splitlines()[0]
        m = FINGERPRINT_SHA256_RE.search(first)
        if not m:
            raise ValueError(f"fingerprint não encontrado: {first!r}")
        return m.group(1)
    finally:
        path.unlink(missing_ok=True)


def mib_to_setquota_kib(mib: int) -> int:
    if mib < 0:
        raise ValueError("MiB negativo")
    return mib * 1024


def quota_probe_path(home: Path) -> Path:
    p = home.resolve()
    if p.is_dir():
        return p
    return p.parent if p.parent != p else Path("/").resolve()


def apply_setquota(
    username: str,
    home: Path,
    soft_mib: int,
    hard_mib: int,
    inode_soft: int,
    inode_hard: int,
    *,
    dry_run: bool,
) -> tuple[str, str]:
    from runv_mount import MountLookupError, find_mount_triple, quota_opts_allow_user

    if soft_mib > hard_mib or inode_soft > inode_hard:
        raise ValueError("soft não pode exceder hard (blocos ou inodes)")
    probe = quota_probe_path(home)
    try:
        target, fstype, opts = find_mount_triple(probe)
    except MountLookupError as e:
        raise RuntimeError(str(e)) from e
    if fstype != "ext4" or not quota_opts_allow_user(opts):
        raise RuntimeError(f"sem ext4+usrquota em {target!r}")
    if not shutil.which("setquota"):
        raise RuntimeError("comando setquota não encontrado (apt install quota)")
    bs = mib_to_setquota_kib(soft_mib)
    bh = mib_to_setquota_kib(hard_mib)
    cmd = ["setquota", "-u", username, str(bs), str(bh), str(inode_soft), str(inode_hard), target]
    if dry_run:
        print(f"  [dry-run] {' '.join(cmd)}")
        return target, fstype
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(f"setquota falhou: {err}")
    return target, fstype


def write_authorized_keys_replace(
    home: Path,
    uid: int,
    gid: int,
    public_key_line: str,
    *,
    dry_run: bool,
) -> None:
    line = normalize_public_key(public_key_line)
    ssh_dir = home / ".ssh"
    auth = ssh_dir / "authorized_keys"
    if dry_run:
        print(f"  [dry-run] escreveria {auth} com uma linha")
        return
    ssh_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(ssh_dir, 0o700)
    os.chown(ssh_dir, uid, gid)
    auth.write_text(line + "\n", encoding="utf-8")
    os.chmod(auth, 0o600)
    os.chown(auth, uid, gid)


def write_authorized_keys_append(
    home: Path,
    uid: int,
    gid: int,
    public_key_line: str,
    *,
    dry_run: bool,
) -> None:
    line = normalize_public_key(public_key_line)
    ssh_dir = home / ".ssh"
    auth = ssh_dir / "authorized_keys"
    if dry_run:
        print(f"  [dry-run] acrescentaria chave em {auth}")
        return
    ssh_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(ssh_dir, 0o700)
    os.chown(ssh_dir, uid, gid)
    if auth.exists():
        existing = auth.read_text(encoding="utf-8")
        if line in existing.splitlines():
            print("  [info] authorized_keys já continha esta chave.")
        else:
            with open(auth, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    else:
        auth.write_text(line + "\n", encoding="utf-8")
    os.chmod(auth, 0o600)
    os.chown(auth, uid, gid)


def set_password_chpasswd(username: str, password: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"  [dry-run] chpasswd para {username!r}")
        return
    r = subprocess.run(
        ["chpasswd"],
        input=f"{username}:{password}\n",
        text=True,
        capture_output=True,
        timeout=60,
    )
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(f"chpasswd falhou: {err}")


def mutate_metadata(
    metadata_path: Path,
    lock_path: Path,
    *,
    dry_run: bool,
    mutator: Callable[[list[dict[str, Any]]], bool],
) -> bool:
    """
    Lê lista JSON sob flock, chama mutator(data) -> True se deve gravar.
    Gravação atómica na mesma secção crítica.
    """
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_f = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        if not metadata_path.is_file():
            data: list[dict[str, Any]] = []
        else:
            raw = metadata_path.read_text(encoding="utf-8").strip()
            if not raw:
                data = []
            else:
                parsed = json.loads(raw)
                if not isinstance(parsed, list):
                    raise ValueError("users.json: esperada lista JSON")
                data = parsed
        if not mutator(data):
            return False
        if dry_run:
            print(f"  [dry-run] gravaria {len(data)} entradas em {metadata_path}")
            return True
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
        return True
    finally:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
        lock_f.close()


def find_metadata_index(data: list[dict[str, Any]], username: str) -> int | None:
    for i, row in enumerate(data):
        if isinstance(row, dict) and row.get("username") == username:
            return i
    return None


def update_metadata_email(
    metadata_path: Path,
    lock_path: Path,
    username: str,
    email: str,
    *,
    dry_run: bool,
) -> bool:
    def m(data: list[dict[str, Any]]) -> bool:
        idx = find_metadata_index(data, username)
        if idx is None:
            eprint(
                f"Aviso: sem entrada em {metadata_path} para {username!r}; email não gravado em JSON."
            )
            return False
        data[idx]["email"] = email
        return True

    ok = mutate_metadata(metadata_path, lock_path, dry_run=dry_run, mutator=m)
    if ok:
        print(f"  [ok] email em metadados atualizado para {email!r}")
    return ok


def update_metadata_after_key(
    metadata_path: Path,
    lock_path: Path,
    username: str,
    fingerprint: str,
    *,
    dry_run: bool,
) -> bool:
    def m(data: list[dict[str, Any]]) -> bool:
        idx = find_metadata_index(data, username)
        if idx is None:
            eprint(f"Aviso: sem entrada em metadados para {username!r}; fingerprint não gravado.")
            return False
        data[idx]["public_key_fingerprint"] = fingerprint
        return True

    if mutate_metadata(metadata_path, lock_path, dry_run=dry_run, mutator=m):
        print(f"  [ok] fingerprint em metadados: {fingerprint}")
        return True
    return False


def update_metadata_after_quota(
    metadata_path: Path,
    lock_path: Path,
    username: str,
    soft_mib: int,
    hard_mib: int,
    inode_soft: int,
    inode_hard: int,
    mountpoint: str,
    fstype: str,
    *,
    dry_run: bool,
) -> None:
    def m(data: list[dict[str, Any]]) -> bool:
        idx = find_metadata_index(data, username)
        if idx is None:
            eprint(
                f"Aviso: sem entrada em metadados para {username!r}; quotas não reflectidas no JSON."
            )
            return False
        now = datetime.now(timezone.utc).isoformat()
        row = data[idx]
        row["quota_enabled"] = True
        row["quota_soft_mb"] = soft_mib
        row["quota_hard_mb"] = hard_mib
        row["quota_inode_soft"] = inode_soft
        row["quota_inode_hard"] = inode_hard
        row["quota_mountpoint"] = mountpoint
        row["quota_filesystem"] = fstype
        row["quota_applied_at"] = now
        row["quota_status"] = "applied"
        if row.get("status") == "partial_quota":
            row["status"] = "active"
        return True

    if mutate_metadata(metadata_path, lock_path, dry_run=dry_run, mutator=m):
        print("  [ok] campos de quota actualizados em metadados")


def prompt_line(msg: str, default: str | None = None) -> str:
    if default is not None:
        s = input(f"{msg} [{default}]: ").strip()
        return s if s else default
    return input(f"{msg}: ").strip()


def interactive_loop(
    username: str,
    uid: int,
    gid: int,
    home: Path,
    metadata_path: Path,
    lock_path: Path,
    *,
    dry_run: bool,
    skip_metadata: bool,
) -> None:
    print()
    print(f"Utilizador: {username}  (uid={uid}, home={home})")
    print("Escolha o que alterar (número). Repita até terminar.")
    print("  1) Email do utilizador (users.json)")
    print("  2) Substituir ~/.ssh/authorized_keys por UMA chave (política runv típica)")
    print("  3) Acrescentar chave a authorized_keys")
    print("  4) Definir palavra-passe de login (chpasswd) — o runv costuma usar só SSH por chave")
    print("  5) Aplicar quota (MiB soft/hard + inodes, como create_runv_user)")
    print("  0) Sair")
    print()
    while True:
        choice = input("Opção [0]: ").strip() or "0"
        if choice == "0":
            break
        if choice == "1":
            if skip_metadata:
                print("  [skip] --skip-metadata activo.")
                continue
            em = prompt_line("Novo email do utilizador")
            if not em:
                continue
            try:
                em = validate_email(em)
            except ValueError as e:
                eprint(f"Erro: {e}")
                continue
            update_metadata_email(metadata_path, lock_path, username, em, dry_run=dry_run)
        elif choice == "2":
            print("Cole UMA linha de chave pública OpenSSH (Enter para cancelar):")
            line = input().strip()
            if not line:
                continue
            try:
                fp = compute_public_key_fingerprint(line)
                write_authorized_keys_replace(home, uid, gid, line, dry_run=dry_run)
                if not skip_metadata:
                    update_metadata_after_key(
                        metadata_path, lock_path, username, fp, dry_run=dry_run
                    )
            except ValueError as e:
                eprint(f"Erro: {e}")
        elif choice == "3":
            print("Cole linha de chave a acrescentar:")
            line = input().strip()
            if not line:
                continue
            try:
                write_authorized_keys_append(home, uid, gid, line, dry_run=dry_run)
                print("  [ok] chave acrescentada (metadados: use opção 2 ou edite JSON se quiser fingerprint único)")
            except ValueError as e:
                eprint(f"Erro: {e}")
        elif choice == "4":
            if not sys.stdin.isatty():
                eprint("Palavra-passe: use terminal interactivo ou não use esta opção.")
                continue
            p1 = getpass.getpass("Nova palavra-passe: ")
            p2 = getpass.getpass("Repita: ")
            if p1 != p2:
                eprint("As palavras-passe não coincidem.")
                continue
            if not p1:
                eprint("Palavra-passe vazia recusada.")
                continue
            try:
                set_password_chpasswd(username, p1, dry_run=dry_run)
                print("  [ok] palavra-passe alterada (login shell / chpasswd)")
            except RuntimeError as e:
                eprint(str(e))
        elif choice == "5":
            try:
                sm = int(prompt_line("MiB soft", str(DEFAULT_QUOTA_SOFT_MIB)))
                hm = int(prompt_line("MiB hard", str(DEFAULT_QUOTA_HARD_MIB)))
                isoft = int(prompt_line("Inode soft", str(DEFAULT_QUOTA_INODE_SOFT)))
                ihard = int(prompt_line("Inode hard", str(DEFAULT_QUOTA_INODE_HARD)))
            except ValueError:
                eprint("Números inválidos.")
                continue
            try:
                mp, fs = apply_setquota(
                    username, home, sm, hm, isoft, ihard, dry_run=dry_run
                )
                if not skip_metadata:
                    update_metadata_after_quota(
                        metadata_path,
                        lock_path,
                        username,
                        sm,
                        hm,
                        isoft,
                        ihard,
                        mp,
                        fs,
                        dry_run=dry_run,
                    )
            except (ValueError, RuntimeError) as e:
                eprint(str(e))
        else:
            print("Opção desconhecida.")
        print()


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Atualiza utilizador runv: email (JSON), SSH, palavra-passe, quota.",
    )
    p.add_argument("--username", "-u", metavar="USER", help="utilizador Unix existente")
    p.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="menu interactivo (também é o padrão se não houver flags de alteração)",
    )
    p.add_argument("--email", metavar="ADDR", help="email do utilizador (users.json)")
    p.add_argument(
        "--replace-public-key",
        metavar="LINE",
        help="substitui authorized_keys por esta linha OpenSSH",
    )
    p.add_argument(
        "--append-public-key",
        metavar="LINE",
        help="acrescenta linha a authorized_keys",
    )
    p.add_argument(
        "--ssh-replace-file",
        type=Path,
        metavar="PATH",
        help="ficheiro com uma linha OpenSSH (substitui authorized_keys)",
    )
    p.add_argument(
        "--ssh-append-file",
        type=Path,
        metavar="PATH",
        help="ficheiro com uma linha OpenSSH (acrescenta a authorized_keys)",
    )
    p.add_argument(
        "--set-password",
        action="store_true",
        help="pede nova palavra-passe (getpass); requer TTY",
    )
    p.add_argument("--quota-soft-mb", type=int, metavar="MiB", default=None)
    p.add_argument("--quota-hard-mb", type=int, metavar="MiB", default=None)
    p.add_argument("--quota-inode-soft", type=int, default=None)
    p.add_argument("--quota-inode-hard", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--skip-metadata",
        action="store_true",
        help="não lê nem grava users.json",
    )
    p.add_argument("--metadata-file", type=Path, default=DEFAULT_METADATA_PATH)
    p.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK_PATH)
    p.add_argument(
        "--landing-document-root",
        type=Path,
        default=Path("/var/www/runv.club/html"),
        help=(
            "DocumentRoot da landing; após gravar users.json, executa genlanding --sync-public-only "
            "(omitido com --skip-metadata ou --no-refresh-landing-members)"
        ),
    )
    p.add_argument(
        "--no-refresh-landing-members",
        action="store_true",
        help="não copiar site/public nem regenerar data/members.json após alterar metadados",
    )
    p.add_argument(
        "--members-homes-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="opcional: --members-homes-root para genlanding (ex. /home)",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION} — runv.club")
    return p.parse_args(argv)


def read_key_file(path: Path) -> str:
    raw = path.read_text(encoding="utf-8").strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if len(lines) != 1:
        raise ValueError("ficheiro deve conter exactamente uma linha de chave (sem comentários)")
    return lines[0]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dry_run = args.dry_run
    log = setup_update_user_log()
    require_root(dry_run=dry_run)

    has_quota_flag = any(
        [
            args.quota_soft_mb is not None,
            args.quota_hard_mb is not None,
            args.quota_inode_soft is not None,
            args.quota_inode_hard is not None,
        ]
    )
    has_cli_change = any(
        [
            args.email,
            args.replace_public_key,
            args.append_public_key,
            args.ssh_replace_file is not None,
            args.ssh_append_file is not None,
            args.set_password,
            has_quota_flag,
        ]
    )

    if not args.username:
        if not sys.stdin.isatty():
            eprint("Erro: indique --username ou execute em modo interactivo com TTY.")
            return EXIT_VALIDATION
        u = prompt_line("Username Unix a atualizar")
        username = validate_username_syntax(u)
    else:
        username = validate_username_syntax(args.username)

    uid, gid, home = check_user_exists(username)

    if args.interactive or not has_cli_change:
        if args.interactive and has_cli_change:
            eprint("Aviso: com -i/--interactive o menu ignora outras flags de alteração nesta execução.")
        if args.set_password and not sys.stdin.isatty():
            eprint("Erro: --set-password requer TTY.")
            return EXIT_VALIDATION
        print(f"== update_user.py v{VERSION} — runv.club ==")
        interactive_loop(
            username,
            uid,
            gid,
            home,
            args.metadata_file,
            args.lock_file,
            dry_run=dry_run,
            skip_metadata=args.skip_metadata,
        )
        maybe_sync_landing_after_metadata(
            skip_metadata=args.skip_metadata,
            no_refresh_landing_members=args.no_refresh_landing_members,
            landing_document_root=args.landing_document_root,
            metadata_file=args.metadata_file,
            members_homes_root=args.members_homes_root,
            dry_run=dry_run,
            log=log,
        )
        return EXIT_OK

    pk_replace: str | None = args.replace_public_key
    if args.ssh_replace_file is not None:
        if pk_replace is not None:
            eprint("Erro: use só uma de --replace-public-key ou --ssh-replace-file.")
            return EXIT_VALIDATION
        try:
            pk_replace = read_key_file(args.ssh_replace_file)
        except (OSError, ValueError) as e:
            eprint(f"Erro: {e}")
            return EXIT_VALIDATION

    pk_append: str | None = args.append_public_key
    if args.ssh_append_file is not None:
        if pk_append is not None:
            eprint("Erro: use só uma de --append-public-key ou --ssh-append-file.")
            return EXIT_VALIDATION
        try:
            pk_append = read_key_file(args.ssh_append_file)
        except (OSError, ValueError) as e:
            eprint(f"Erro: {e}")
            return EXIT_VALIDATION

    if pk_replace is not None and pk_append is not None:
        eprint("Erro: numa só execução use substituir chave OU acrescentar, não ambos.")
        return EXIT_VALIDATION

    try:
        if args.email:
            if args.skip_metadata:
                eprint("Erro: --email requer metadados; não use --skip-metadata.")
                return EXIT_VALIDATION
            em = validate_email(args.email)
            update_metadata_email(
                args.metadata_file, args.lock_file, username, em, dry_run=dry_run
            )

        if pk_replace:
            fp = compute_public_key_fingerprint(pk_replace)
            write_authorized_keys_replace(home, uid, gid, pk_replace, dry_run=dry_run)
            if not args.skip_metadata:
                update_metadata_after_key(
                    args.metadata_file, args.lock_file, username, fp, dry_run=dry_run
                )

        if pk_append:
            write_authorized_keys_append(home, uid, gid, pk_append, dry_run=dry_run)

        if args.set_password:
            if not sys.stdin.isatty():
                eprint("Erro: --set-password requer TTY (use modo interactivo).")
                return EXIT_VALIDATION
            p1 = getpass.getpass("Nova palavra-passe: ")
            p2 = getpass.getpass("Repita: ")
            if p1 != p2 or not p1:
                eprint("Palavra-passe inválida ou não coincide.")
                return EXIT_VALIDATION
            set_password_chpasswd(username, p1, dry_run=dry_run)
            print("  [ok] palavra-passe alterada")

        if (
            args.quota_soft_mb is not None
            or args.quota_hard_mb is not None
            or args.quota_inode_soft is not None
            or args.quota_inode_hard is not None
        ):
            sm = args.quota_soft_mb if args.quota_soft_mb is not None else DEFAULT_QUOTA_SOFT_MIB
            hm = args.quota_hard_mb if args.quota_hard_mb is not None else DEFAULT_QUOTA_HARD_MIB
            iso = (
                args.quota_inode_soft
                if args.quota_inode_soft is not None
                else DEFAULT_QUOTA_INODE_SOFT
            )
            ihd = (
                args.quota_inode_hard
                if args.quota_inode_hard is not None
                else DEFAULT_QUOTA_INODE_HARD
            )
            mp, fs = apply_setquota(username, home, sm, hm, iso, ihd, dry_run=dry_run)
            if not args.skip_metadata:
                update_metadata_after_quota(
                    args.metadata_file,
                    args.lock_file,
                    username,
                    sm,
                    hm,
                    iso,
                    ihd,
                    mp,
                    fs,
                    dry_run=dry_run,
                )
    except ValueError as e:
        eprint(f"Erro: {e}")
        return EXIT_VALIDATION
    except RuntimeError as e:
        eprint(str(e))
        return EXIT_SYSTEM

    maybe_sync_landing_after_metadata(
        skip_metadata=args.skip_metadata,
        no_refresh_landing_members=args.no_refresh_landing_members,
        landing_document_root=args.landing_document_root,
        metadata_file=args.metadata_file,
        members_homes_root=args.members_homes_root,
        dry_run=dry_run,
        log=log,
    )

    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
