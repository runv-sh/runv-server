#!/usr/bin/env python3
"""
LEGADO — Instalador/configurador runv.club: envio via msmtp + sendmail (Debian 13).

O caminho predefinido do projeto é Mailgun API (`configure_mailgun.py`).
Use este script apenas se precisar de SMTP local/msmtp.

Executar como root. Ver docs/08-email.md no repositório.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from getpass import getpass
from pathlib import Path
from typing import Any

# Caminhos no sistema
MSMPTRC_PATH = Path("/etc/msmtprc")
ALIASES_PATH = Path("/etc/msmtp_aliases")
NETRC_PATH = Path("/root/.netrc")
STATE_PATH = Path("/etc/runv-email.json")
PASS_SCRIPT_DIR = Path("/usr/local/lib/runv-email")
PASS_SCRIPT_DEST = PASS_SCRIPT_DIR / "netrc_password.py"
LOGFILE_MSMT = Path("/var/log/msmtp.log")

MODULE_ROOT = Path(__file__).resolve().parent
SOURCE_PASS_SCRIPT = MODULE_ROOT / "scripts" / "netrc_password.py"

APT_PACKAGES = ("msmtp", "msmtp-mta", "ca-certificates", "bsd-mailx")

ACCOUNT_NAME = "runv"


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def log() -> logging.Logger:
    return logging.getLogger("runv-email-legacy-smtp")


def require_root() -> None:
    if os.geteuid() != 0:
        print("Execute como root (sudo).", file=sys.stderr)
        raise SystemExit(1)


def run_cmd(
    cmd: list,
    *,
    dry_run: bool,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str] | None:
    log().debug("exec: %s", " ".join(cmd))
    if dry_run:
        log().info("[dry-run] %s", " ".join(cmd))
        return None
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def apt_install(dry_run: bool) -> None:
    r = run_cmd(["apt-get", "update", "-qq"], dry_run=dry_run)
    if r is not None and r.returncode != 0:
        log().warning("apt-get update: código %s — %s", r.returncode, r.stderr.strip())
    r2 = run_cmd(
        ["apt-get", "install", "-y", *APT_PACKAGES],
        dry_run=dry_run,
    )
    if r2 is not None and r2.returncode != 0:
        raise RuntimeError(f"apt-get install falhou: {r2.stderr or r2.stdout}")


def backup_if_exists(path: Path, *, dry_run: bool, force: bool) -> Path | None:
    if not path.is_file():
        return None
    bak = path.with_name(f"{path.name}.bak.{int(time.time())}")
    if dry_run:
        log().info("[dry-run] backup seria: %s -> %s", path, bak)
        return bak
    shutil.copy2(path, bak)
    log().info("Backup: %s", bak)
    return bak


def confirm_overwrite(path: Path, *, force: bool) -> bool:
    if force:
        return True
    if not path.is_file():
        return True
    r = input(f"O ficheiro {path} já existe. Sobrescrever? [s/N]: ").strip().lower()
    return r in ("s", "sim", "y", "yes")


def _remove_netrc_machine_block(text: str, host: str) -> str:
    """Remove o bloco que começa em 'machine <host>' até à linha antes do próximo 'machine '."""
    host_line = re.compile(rf"^machine\s+{re.escape(host)}\s*$", re.MULTILINE)
    next_machine = re.compile(r"^machine\s+", re.MULTILINE)
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        if host_line.match(lines[i]):
            i += 1
            while i < len(lines) and not next_machine.match(lines[i]):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def upsert_netrc_machine(host: str, login: str, password: str, *, dry_run: bool) -> None:
    """Atualiza ou acrescenta bloco machine HOST em /root/.netrc."""
    block = f"machine {host}\nlogin {login}\npassword {password}\n"
    if dry_run:
        log().info("[dry-run] atualizaria .netrc para machine %s", host)
        return

    existing = ""
    if NETRC_PATH.is_file():
        existing = NETRC_PATH.read_text(encoding="utf-8", errors="replace")

    stripped = _remove_netrc_machine_block(existing, host).rstrip()
    new_text = (stripped + "\n\n" + block if stripped else block).rstrip() + "\n"

    NETRC_PATH.parent.mkdir(parents=True, exist_ok=True)
    NETRC_PATH.write_text(new_text, encoding="utf-8")
    os.chmod(NETRC_PATH, 0o600)
    try:
        os.chown(NETRC_PATH, 0, 0)
    except OSError:
        pass
    log().info("Escrito %s (0600)", NETRC_PATH)


def install_passwordeval_script(*, dry_run: bool) -> None:
    if not SOURCE_PASS_SCRIPT.is_file():
        raise FileNotFoundError(f"script em falta no módulo: {SOURCE_PASS_SCRIPT}")
    if dry_run:
        log().info("[dry-run] copiaria netrc_password.py para %s", PASS_SCRIPT_DEST)
        return
    PASS_SCRIPT_DIR.mkdir(parents=True, mode=0o755, exist_ok=True)
    shutil.copy2(SOURCE_PASS_SCRIPT, PASS_SCRIPT_DEST)
    PASS_SCRIPT_DEST.chmod(0o755)
    try:
        os.chown(PASS_SCRIPT_DEST, 0, 0)
    except OSError:
        pass
    log().info("Instalado %s", PASS_SCRIPT_DEST)


def build_msmtprc(
    *,
    host: str,
    port: int,
    tls_on: bool,
    starttls_on: bool,
    auth_on: bool,
    user: str,
    default_from: str,
    use_aliases: bool,
) -> str:
    lines = [
        "# Gerido por runv.club configure_msmtp_legacy.py — não editar à mão sem cópia de segurança",
        "",
        "defaults",
        f"tls_trust_file /etc/ssl/certs/ca-certificates.crt",
        f"logfile {LOGFILE_MSMT}",
        "",
        f"account {ACCOUNT_NAME}",
        f"host {host}",
        f"port {port}",
        f"from {default_from}",
        "tls           " + ("on" if tls_on else "off"),
        "tls_starttls  " + ("on" if starttls_on else "off"),
    ]
    if auth_on and user:
        lines.append("auth on")
        lines.append(f"user {user}")
        lines.append(f"passwordeval {PASS_SCRIPT_DEST} {host}")
    else:
        lines.append("auth off")

    if use_aliases:
        lines.append(f"aliases {ALIASES_PATH}")

    lines.extend(
        [
            "",
            f"account default : {ACCOUNT_NAME}",
            "",
        ]
    )
    return "\n".join(lines)


def write_msmtprc(content: str, *, dry_run: bool) -> None:
    if dry_run:
        log().info("[dry-run] escreveria %s", MSMPTRC_PATH)
        log().debug("%s", content)
        return
    MSMPTRC_PATH.write_text(content, encoding="utf-8")
    os.chmod(MSMPTRC_PATH, 0o600)
    try:
        os.chown(MSMPTRC_PATH, 0, 0)
    except OSError:
        pass
    log().info("Escrito %s (0600)", MSMPTRC_PATH)


def write_aliases(admin_email: str, *, dry_run: bool) -> None:
    body = (
        f"# Gerido por runv.club configure_msmtp_legacy.py — formato msmtp (não Sendmail)\n"
        f"root: {admin_email}\n"
        f"cron: {admin_email}\n"
        f"default: {admin_email}\n"
    )
    if dry_run:
        log().info("[dry-run] escreveria %s", ALIASES_PATH)
        return
    backup_if_exists(ALIASES_PATH, dry_run=False, force=True)
    ALIASES_PATH.write_text(body, encoding="utf-8")
    os.chmod(ALIASES_PATH, 0o644)
    try:
        os.chown(ALIASES_PATH, 0, 0)
    except OSError:
        pass
    log().info("Escrito %s (0644)", ALIASES_PATH)


def write_state(data: dict[str, Any], *, dry_run: bool) -> None:
    if dry_run:
        log().info("[dry-run] escreveria %s", STATE_PATH)
        return
    STATE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.chmod(STATE_PATH, 0o600)
    try:
        os.chown(STATE_PATH, 0, 0)
    except OSError:
        pass
    log().info("Metadados em %s (sem segredos SMTP em texto claro — use .netrc)", STATE_PATH)


def touch_logfile(*, dry_run: bool) -> None:
    if dry_run:
        return
    LOGFILE_MSMT.parent.mkdir(parents=True, exist_ok=True)
    if not LOGFILE_MSMT.exists():
        LOGFILE_MSMT.touch(mode=0o640)
    try:
        os.chown(LOGFILE_MSMT, 0, 0)
    except OSError:
        pass


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        raise FileNotFoundError(
            f"Estado não encontrado: {STATE_PATH}. Execute configure_msmtp_legacy.py sem --test primeiro.",
        )
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def run_test_send(*, dry_run: bool) -> None:
    state = load_state()
    admin = str(state.get("admin_email", "")).strip()
    from_addr = str(state.get("default_from", "")).strip()
    if not admin or not from_addr:
        raise ValueError("admin_email ou default_from em falta no estado")

    sys.path.insert(0, str(MODULE_ROOT))
    from lib.mailer import render_template, send_mail  # type: ignore

    body = render_template(
        "system_test",
        admin_email=admin,
        default_from=from_addr,
        host=state.get("smtp_host", ""),
        api_base_url="(modo SMTP legado — não aplicável)",
        timestamp=str(int(time.time())),
    )
    subj = "[runv.club] Email de teste do sistema (SMTP legado)"
    if dry_run:
        log().info("[dry-run] enviaria teste para %s", admin)
        return
    send_mail(admin, subj, body, from_addr=from_addr, _state=state)
    log().info("Email de teste enviado para %s", admin)


def prompt_yes_no(msg: str, default_no: bool = True) -> bool:
    suf = " [s/N]: " if default_no else " [S/n]: "
    r = input(msg + suf).strip().lower()
    if not r:
        return not default_no
    return r in ("s", "sim", "y", "yes")


def prompt_line(msg: str, default: str = "") -> str:
    d = f" [{default}]" if default else ""
    r = input(f"{msg}{d}: ").strip()
    return r if r else default


def interactive_config() -> dict[str, Any]:
    print("\n=== LEGADO: Configuração SMTP (msmtp + sendmail) ===\n")
    print("Nota: o caminho recomendado é Mailgun API (configure_mailgun.py).\n")
    host = prompt_line("Host SMTP")
    if not host:
        raise ValueError("Host SMTP obrigatório.")

    port_s = prompt_line("Porta SMTP", "587")
    port = int(port_s) if port_s.isdigit() else 587

    tls_on = prompt_yes_no("Usar TLS (tls)?", default_no=False)
    starttls_on = prompt_yes_no("Usar STARTTLS (tls_starttls)?", default_no=False)
    auth_on = prompt_yes_no("Autenticação SMTP (usuário/senha)?", default_no=False)

    user = ""
    if auth_on:
        user = prompt_line("Utilizador SMTP (login)")
        if not user:
            raise ValueError("Com auth on, o utilizador SMTP é obrigatório.")

    default_from = prompt_line("Remetente padrão (From)")
    if not default_from or "@" not in default_from:
        raise ValueError("Remetente (From) deve ser um endereço de email válido.")

    admin_email = prompt_line("Email do administrador (notificações)")
    if not admin_email or "@" not in admin_email:
        raise ValueError("Email do admin inválido.")

    password = ""
    if auth_on:
        p1 = getpass("Senha ou token SMTP (não ecoa): ")
        p2 = getpass("Repita a senha: ")
        if p1 != p2:
            raise ValueError("Senhas não coincidem.")
        password = p1

    return {
        "smtp_host": host,
        "smtp_port": port,
        "tls_on": tls_on,
        "starttls_on": starttls_on,
        "auth_on": auth_on,
        "smtp_user": user,
        "smtp_password": password,
        "default_from": default_from,
        "admin_email": admin_email,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LEGADO: instala msmtp/sendmail e configura SMTP runv.club.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--force", "-f", action="store_true", help="sobrescrever sem perguntar")
    parser.add_argument(
        "--test",
        action="store_true",
        help="enviar apenas email de teste (requer config e %s)" % STATE_PATH,
    )
    parser.add_argument("--skip-apt", action="store_true", help="não executar apt-get")
    args = parser.parse_args()

    setup_logging(args.verbose)
    require_root()

    try:
        if args.test:
            run_test_send(dry_run=args.dry_run)
            print("Teste concluído.")
            return 0

        if not args.skip_apt:
            apt_install(args.dry_run)

        touch_logfile(dry_run=args.dry_run)
        install_passwordeval_script(dry_run=args.dry_run)

        cfg = interactive_config()

        if not confirm_overwrite(MSMPTRC_PATH, force=args.force):
            print("Cancelado.")
            return 1
        backup_if_exists(MSMPTRC_PATH, dry_run=args.dry_run, force=args.force)

        if cfg["auth_on"]:
            if not cfg.get("smtp_password"):
                raise ValueError("Com autenticação ligada, a senha/token é obrigatório.")
            if not confirm_overwrite(NETRC_PATH, force=args.force):
                print("Cancelado.")
                return 1
            backup_if_exists(NETRC_PATH, dry_run=args.dry_run, force=args.force)
            upsert_netrc_machine(
                cfg["smtp_host"],
                cfg["smtp_user"],
                cfg["smtp_password"],
                dry_run=args.dry_run,
            )

        mc = build_msmtprc(
            host=cfg["smtp_host"],
            port=int(cfg["smtp_port"]),
            tls_on=bool(cfg["tls_on"]),
            starttls_on=bool(cfg["starttls_on"]),
            auth_on=bool(cfg["auth_on"]),
            user=cfg["smtp_user"],
            default_from=cfg["default_from"],
            use_aliases=True,
        )
        write_msmtprc(mc, dry_run=args.dry_run)

        if not confirm_overwrite(ALIASES_PATH, force=args.force):
            print("Cancelado.")
            return 1
        write_aliases(cfg["admin_email"], dry_run=args.dry_run)

        state_public: dict[str, Any] = {
            "backend": "sendmail",
            "provider": "smtp_msmtp",
            "email_package_root": str(MODULE_ROOT),
            "admin_email": cfg["admin_email"],
            "default_from": cfg["default_from"],
            "smtp_host": cfg["smtp_host"],
            "smtp_port": cfg["smtp_port"],
        }
        write_state(state_public, dry_run=args.dry_run)

        if not args.dry_run and prompt_yes_no("\nEnviar email de teste agora?", default_no=True):
            try:
                run_test_send(dry_run=False)
                log().info("Teste enviado.")
            except Exception as e:
                log().warning("Teste falhou (config pode estar correta mesmo assim): %s", e)

        print("\n=== Resumo (backend legado: SMTP / sendmail) ===")
        print(f"  msmtp:     {MSMPTRC_PATH}")
        print(f"  aliases:   {ALIASES_PATH}")
        print(f"  netrc:     {NETRC_PATH} (credenciais — não partilhar)")
        print(f"  estado:    {STATE_PATH}")
        print(f"  sendmail:  /usr/sbin/sendmail (msmtp-mta)")
        print("\nDocumentação: docs/08-email.md (repositório)")
        print("Teste posterior: sudo python3 email/configure_msmtp_legacy.py --test")
        print("Mailgun (recomendado): sudo python3 email/configure_mailgun.py")
        return 0

    except (KeyboardInterrupt, EOFError):
        print("\nInterrompido.", file=sys.stderr)
        return 130
    except Exception as e:
        log().error("%s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
