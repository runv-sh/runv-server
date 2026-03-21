#!/usr/bin/env python3
"""
Configurador de email runv — Mailgun HTTP API (predefinido).

Aviso: este script foi feito para Mailgun. Não pré-configura nenhuma credencial.

Executar como root. Ver email/docs/INSTALL.md.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from getpass import getpass
from pathlib import Path
from typing import Any

MODULE_ROOT = Path(__file__).resolve().parent
STATE_PATH = Path("/etc/runv-email.json")
SECRETS_PATH = Path("/etc/runv-email.secrets.json")

sys.path.insert(0, str(MODULE_ROOT))
from lib.mailgun_client import (  # noqa: E402
    MailgunHTTPError,
    build_mailgun_messages_url,
    mailgun_base_url,
    mask_secret,
    validate_mailgun_inputs,
)


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def log() -> logging.Logger:
    return logging.getLogger("runv-email-mailgun")


def require_root() -> None:
    if os.geteuid() != 0:
        print("Execute como root (sudo).", file=sys.stderr)
        raise SystemExit(1)


def prompt_line(msg: str, default: str = "") -> str:
    d = f" [{default}]" if default else ""
    r = input(f"{msg}{d}: ").strip()
    return r if r else default


def prompt_yes_no(msg: str, default_no: bool = True) -> bool:
    suf = " [s/N]: " if default_no else " [S/n]: "
    r = input(msg + suf).strip().lower()
    if not r:
        return not default_no
    return r in ("s", "sim", "y", "yes")


def interactive_config(*, email_package_root: str) -> tuple[dict[str, Any], dict[str, str]]:
    print()
    print("=== Configurador de email para Mailgun API ===")
    print()
    print("Aviso: este script foi feito para Mailgun. Não pré-configura nenhuma credencial.")
    print()

    print("Tipo de chave Mailgun (recomendado: domain sending key — menor privilégio):")
    print("  1) Domain sending key (recomendado)")
    print("  2) Primary account API key")
    choice = prompt_line("Escolha [1/2]", "1").strip()
    api_key_kind = "domain_sending" if choice != "2" else "primary"

    domain = prompt_line("Domínio de envio Mailgun (ex.: mg.exemplo.com ou exemplo.com)")
    region = prompt_line("Região da API (us ou eu)", "us").strip().lower()
    if region not in ("us", "eu"):
        raise ValueError("Região deve ser 'us' ou 'eu'.")

    key = getpass("Mailgun API key (não ecoa): ").strip()
    key2 = getpass("Repita a API key: ").strip()
    if key != key2:
        raise ValueError("As chaves não coincidem.")
    default_from = prompt_line("Remetente padrão (From)")
    admin_email = prompt_line("Email do administrador (notificações / teste)")

    validated = validate_mailgun_inputs(
        domain=domain,
        region=region,
        from_addr=default_from,
        admin_email=admin_email,
        api_key=key,
    )

    base = mailgun_base_url(validated["region"])
    public: dict[str, Any] = {
        "backend": "mailgun",
        "provider": "mailgun",
        "mailgun_domain": validated["domain"],
        "mailgun_region": validated["region"],
        "api_base_url": base,
        "default_from": validated["from_addr"],
        "admin_email": validated["admin_email"],
        "api_key_kind": api_key_kind,
        "api_key_source": "file",
        "secrets_path": str(SECRETS_PATH),
        "email_package_root": email_package_root,
    }
    secrets = {"mailgun_api_key": key}
    return public, secrets


def write_json_atomic(path: Path, data: dict[str, Any], *, mode: int, dry_run: bool) -> None:
    if dry_run:
        log().info("[dry-run] escreveria %s (modo %o)", path, mode)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{int(time.time())}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, mode)
    try:
        os.chown(tmp, 0, 0)
    except OSError:
        pass
    tmp.replace(path)
    log().info("Escrito %s (%o)", path, mode)


def run_test_send(*, dry_run: bool) -> None:
    pub = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    admin = str(pub.get("admin_email", "")).strip()
    from_addr = str(pub.get("default_from", "")).strip()
    if not admin or not from_addr:
        raise ValueError("admin_email ou default_from em falta no estado")

    from lib.mailer import render_template, send_mail

    body = render_template(
        "system_test",
        admin_email=admin,
        default_from=from_addr,
        host=pub.get("mailgun_domain", ""),
        api_base_url=pub.get("api_base_url", ""),
        timestamp=str(int(time.time())),
    )
    subj = "[runv.club] Email de teste do sistema (Mailgun API)"
    if dry_run:
        log().info("[dry-run] enviaria teste via Mailgun API para %s", admin)
        return
    try:
        send_mail(admin, subj, body, from_addr=from_addr, _state=pub)
    except MailgunHTTPError:
        raise
    except Exception as e:
        log().debug("detalhe (sem segredos): %s", type(e).__name__)
        raise
    log().info("Email de teste enviado para %s", admin)


def print_summary(public: dict[str, Any], *, dry_run: bool) -> None:
    print()
    print("=== Resumo ===")
    print(f"  provider:        Mailgun API")
    print(f"  domain:          {public.get('mailgun_domain', '')}")
    print(f"  region:          {public.get('mailgun_region', '')}")
    print(f"  api base URL:    {public.get('api_base_url', '')}")
    print(f"  messages URL:    {build_mailgun_messages_url(base_url=str(public.get('api_base_url','')), domain=str(public.get('mailgun_domain','')))}")
    print(f"  default from:    {public.get('default_from', '')}")
    print(f"  admin email:     {public.get('admin_email', '')}")
    print(f"  estado (meta):   {STATE_PATH}")
    print(f"  segredos:        {SECRETS_PATH} (API key — não partilhar; não impressa aqui)")
    print(f"  email_pkg_root:  {public.get('email_package_root', '')}")
    if dry_run:
        print("  (dry-run — ficheiros não gravados)")
    print()
    print("Documentação: email/docs/INSTALL.md")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Configura envio de email via Mailgun HTTP API (predefinido).",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--force", "-f", action="store_true", help="sobrescrever sem perguntar")
    parser.add_argument(
        "--test",
        action="store_true",
        help="enviar apenas email de teste (requer estado em /etc/runv-email.json)",
    )
    parser.add_argument(
        "--legacy-smtp",
        action="store_true",
        help="usar o configurador SMTP/msmtp legado (desativado por predefinição)",
    )
    args = parser.parse_args()

    if args.legacy_smtp:
        import configure_msmtp_legacy as leg

        argv = [sys.argv[0]] + [a for a in sys.argv[1:] if a != "--legacy-smtp"]
        sys.argv = argv
        return leg.main()

    setup_logging(args.verbose)
    require_root()

    print()
    print("Aviso: este script foi feito para Mailgun. Não pré-configura nenhuma credencial.")

    try:
        if args.test:
            if not STATE_PATH.is_file():
                log().error("Estado não encontrado: %s — execute o configurador primeiro.", STATE_PATH)
                return 1
            try:
                run_test_send(dry_run=args.dry_run)
            except Exception as e:
                log().error("%s", e)
                return 1
            print("Teste concluído.")
            return 0

        default_pkg = str(MODULE_ROOT)
        root_guess = prompt_line(
            "Caminho da pasta `email/` do repositório (importações, ex. entre)",
            default_pkg,
        ).strip()
        if not root_guess:
            root_guess = default_pkg
        ep_root = str(Path(root_guess).resolve())

        public, secrets = interactive_config(email_package_root=ep_root)

        if STATE_PATH.is_file() and not args.force and not args.dry_run:
            if not prompt_yes_no(f"Sobrescrever {STATE_PATH} e segredos?", default_no=True):
                print("Cancelado.")
                return 1

        write_json_atomic(STATE_PATH, public, mode=0o600, dry_run=args.dry_run)
        write_json_atomic(SECRETS_PATH, secrets, mode=0o600, dry_run=args.dry_run)

        if not args.dry_run:
            log().info("API key armazenada em %s (mascarado: %s)", SECRETS_PATH, mask_secret(secrets["mailgun_api_key"]))

        if not args.dry_run and prompt_yes_no("\nEnviar email de teste agora?", default_no=True):
            try:
                run_test_send(dry_run=False)
                log().info("Teste enviado.")
            except Exception as e:
                log().warning("Teste falhou: %s", e)

        print_summary(public, dry_run=args.dry_run)
        print("Teste posterior: sudo python3 email/configure_mailgun.py --test")
        return 0

    except (KeyboardInterrupt, EOFError):
        print("\nInterrompido.", file=sys.stderr)
        return 130
    except Exception as e:
        log().error("%s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
