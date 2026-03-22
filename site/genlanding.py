#!/usr/bin/env python3
"""
Configura o Apache (Debian) para servir a landing runv.club: VirtualHost,
mod_userdir + mod_rewrite, cópia de site/public para DocumentRoot, redirect
www → apex em HTTP. Produção ou modo --dev para testes locais.
Metadados SEO: editar site/public/. FAQ estático: public/faq/ (copiado com o resto).
Notícias: site/news/publish_news.py gera public/news/data/news.json e feed.rss —
depois volte a correr este script para copiar.

Executar como root (excepto --dry-run). Apenas biblioteca padrão Python 3.

Versão 0.04 — runv.club
"""

from __future__ import annotations

import argparse
import grp
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

VERSION: Final[str] = "0.04"
EXIT_OK: Final[int] = 0
EXIT_USAGE: Final[int] = 1
EXIT_ERROR: Final[int] = 2

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE: Final[Path] = SCRIPT_DIR / "public"
DEFAULT_MEMBERS_USERS_JSON: Final[Path] = Path("/var/lib/runv/users.json")

PROD_DOMAIN: Final[str] = "runv.club"
PROD_DOCUMENT_ROOT: Final[Path] = Path("/var/www/runv.club/html")
PROD_SITE_CONF: Final[str] = "runv.club.conf"

DEV_DOMAIN: Final[str] = "runv.local"
DEV_DOCUMENT_ROOT: Final[Path] = Path("/var/www/runv-dev/html")
DEV_SITE_CONF: Final[str] = "runv-dev.conf"

APACHE_SITES_AVAILABLE: Final[Path] = Path("/etc/apache2/sites-available")
APACHE_CTL: Final[str] = "/usr/sbin/apache2ctl"
DEFAULT_SITE: Final[str] = "000-default.conf"


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def require_root(*, dry_run: bool) -> None:
    if dry_run:
        return
    if os.geteuid() != 0:
        eprint("Erro: execute como root (sudo), excepto com --dry-run.")
        raise SystemExit(EXIT_USAGE)


def apache_installed() -> bool:
    return Path(APACHE_CTL).is_file()


def log_tag_from_domain(domain: str) -> str:
    """Nome seguro para ficheiros de log Apache."""
    return re.sub(r"[^\w.-]+", "-", domain).strip("-") or "runv"


def render_vhost(
    *,
    server_name: str,
    document_root: Path,
    log_tag: str,
) -> str:
    www_alias = f"www.{server_name}"
    return f"""# Gerado por genlanding.py v{VERSION} — runv.club
# Não editar à mão sem saber o que faz; volte a correr o script ou ajuste e recarregue o Apache.

<VirtualHost *:80>
    ServerName {server_name}
    ServerAlias {www_alias}
    DocumentRoot {document_root}

    # Redirect www → apex (HTTP; após Certbot o bloco :80 pode ser actualizado pelo certbot)
    RewriteEngine On
    RewriteCond %{{HTTP_HOST}} ^www\\.(.+)$ [NC]
    RewriteRule ^ http://%1%{{REQUEST_URI}} [R=301,L]

    <Directory {document_root}>
        Options FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>

    ErrorLog ${{APACHE_LOG_DIR}}/{log_tag}-error.log
    CustomLog ${{APACHE_LOG_DIR}}/{log_tag}-access.log combined
</VirtualHost>
"""


def run_cmd(
    cmd: list[str],
    *,
    dry_run: bool,
    verbose: bool = True,
) -> None:
    if verbose:
        print(f"  $ {' '.join(cmd)}")
    if dry_run:
        return
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(f"Comando falhou ({r.returncode}): {' '.join(cmd)}\n{err}")


def run_cmd_allow_fail(
    cmd: list[str],
    *,
    dry_run: bool,
    ok_hint: str = "",
) -> None:
    print(f"  $ {' '.join(cmd)}")
    if dry_run:
        return
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode == 0:
        print(f"  [ok] {' '.join(cmd)}")
    else:
        msg = (r.stderr or r.stdout or "").strip() or ok_hint
        print(f"  [info] {' '.join(cmd)} — {msg or 'ignorado (já inactivo?)'}")


def copy_landing(source: Path, dest: Path, *, dry_run: bool) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Pasta origem inexistente: {source}")
    if dry_run:
        print(f"  [dry-run] copiaria {source} -> {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest)


def refresh_members_json_in_document_root(
    document_root: Path,
    *,
    users_json: Path,
    homes_root: Path | None,
    dry_run: bool,
) -> None:
    """Regenera data/members.json no DocumentRoot após copiar site/public (stdlib)."""
    if dry_run:
        print(
            "  [dry-run] regeneraria data/members.json "
            f"({users_json} → {document_root / 'data' / 'members.json'})",
        )
        return
    if not document_root.is_dir():
        eprint(
            f"Erro: DocumentRoot inexistente ({document_root}); não é possível gravar data/members.json."
        )
        return
    script = SCRIPT_DIR / "build_directory.py"
    if not script.is_file():
        eprint(f"Aviso: {script} não encontrado; members.json não regenerado.")
        return
    out = document_root / "data" / "members.json"
    cmd = [
        sys.executable,
        str(script),
        "--users-json",
        str(users_json),
        "-o",
        str(out),
    ]
    if homes_root is not None:
        cmd.extend(["--homes-root", str(homes_root)])
    print(f"  $ {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip()
        eprint(
            f"Aviso: build_directory.py terminou com código {r.returncode}; "
            f"members.json pode estar desactualizado. {tail[:800]}"
        )
    else:
        print(f"  [ok] members.json em {out}")
        if r.stderr.strip():
            for line in r.stderr.strip().splitlines()[:5]:
                print(f"      {line}")
        try:
            data = json.loads(out.read_text(encoding="utf-8"))
            if isinstance(data, list):
                print(
                    f"  [ok] constelação (bolhas): {len(data)} membro(s) — "
                    "o index.html faz fetch a data/members.json (relativo ao DocumentRoot)."
                )
            else:
                eprint("Aviso: members.json não é uma lista JSON; verifique build_directory.py.")
        except (OSError, json.JSONDecodeError, TypeError) as e:
            eprint(f"Aviso: não foi possível confirmar o conteúdo de members.json: {e}")


def chown_www_data(path: Path, *, dry_run: bool) -> None:
    if dry_run:
        print(f"  [dry-run] chown -R www-data:www-data {path}")
        return
    try:
        u = pwd.getpwnam("www-data")
        g = grp.getgrnam("www-data")
    except KeyError as e:
        raise RuntimeError("Utilizador ou grupo 'www-data' não encontrado.") from e
    run_cmd(
        ["chown", "-R", f"{u.pw_uid}:{g.gr_gid}", str(path)],
        dry_run=False,
        verbose=True,
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Configura Apache para a landing runv (VirtualHost, userdir, cópia de public/).",
    )
    p.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"pasta com a landing (default: {DEFAULT_SOURCE})",
    )
    p.add_argument(
        "--document-root",
        type=Path,
        default=None,
        help="DocumentRoot do VirtualHost (default: prod ou dev conforme --dev)",
    )
    p.add_argument(
        "--domain",
        type=str,
        default=None,
        help="ServerName (default: runv.club ou runv.local com --dev)",
    )
    p.add_argument(
        "--dev",
        action="store_true",
        help="modo teste local: runv.local, runv-dev.conf, não desactiva 000-default",
    )
    p.add_argument("--dry-run", action="store_true", help="mostra acções sem alterar o sistema")
    p.add_argument(
        "--certbot",
        action="store_true",
        help="executa certbot --apache após configurar HTTP (incompatível com --dev)",
    )
    p.add_argument(
        "--keep-default-site",
        action="store_true",
        help="não desactiva 000-default.conf (produção e --dev: mantém página Debian; pedidos por IP não casam com ServerName)",
    )
    p.add_argument(
        "--no-refresh-members",
        action="store_true",
        help="não executar site/build_directory.py após copiar public/ (omitir data/members.json)",
    )
    p.add_argument(
        "--members-users-json",
        type=Path,
        default=DEFAULT_MEMBERS_USERS_JSON,
        help=f"fonte para build_directory.py (default: {DEFAULT_MEMBERS_USERS_JSON})",
    )
    p.add_argument(
        "--members-homes-root",
        type=Path,
        default=None,
        help="opcional: --homes-root para build_directory.py (ex. /home)",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION} — runv.club")
    return p.parse_args(argv)


def resolve_profile(args: argparse.Namespace) -> tuple[str, Path, str, bool]:
    """
    Retorna (domain, document_root, site_conf_filename, disable_default_site).
    """
    if args.dev:
        domain = (args.domain or DEV_DOMAIN).strip().lower()
        doc = args.document_root or DEV_DOCUMENT_ROOT
        conf = DEV_SITE_CONF
    else:
        domain = (args.domain or PROD_DOMAIN).strip().lower()
        doc = args.document_root or PROD_DOCUMENT_ROOT
        conf = PROD_SITE_CONF
    # Mesma regra em prod e --dev: sem --keep-default-site, desactiva 000-default para que
    # pedidos por IP (Host sem match) caiam no vhost runv em vez da página Debian.
    disable_default = not args.keep_default_site
    return domain, doc.resolve(), conf, disable_default


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.dev and args.certbot:
        eprint("Erro: --certbot não pode ser usado com --dev (Certbot não serve para domínios locais).")
        return EXIT_USAGE

    require_root(dry_run=args.dry_run)

    domain, document_root, site_conf_name, disable_default = resolve_profile(args)
    source = args.source.resolve()
    conf_path = APACHE_SITES_AVAILABLE / site_conf_name
    log_tag = log_tag_from_domain(domain)

    print(f"== genlanding.py v{VERSION} — runv.club ==")
    print(f"  modo: {'dev' if args.dev else 'produção'}")
    print(f"  ServerName: {domain}")
    print(f"  DocumentRoot: {document_root}")
    print(f"  ficheiro site: {conf_path}")
    print(f"  origem: {source}")
    print()

    if not apache_installed():
        eprint("Erro: Apache não parece instalado (falta /usr/sbin/apache2ctl).")
        eprint("       Instale com: sudo apt install -y apache2")
        eprint("       ou corra scripts/admin/starthere.py antes.")
        return EXIT_ERROR

    vhost_body = render_vhost(
        server_name=domain,
        document_root=document_root,
        log_tag=log_tag,
    )

    try:
        if args.dry_run:
            print("--- VirtualHost (pré-visualização) ---")
            print(vhost_body)

        run_cmd(["a2enmod", "userdir"], dry_run=args.dry_run)
        run_cmd(["a2enmod", "rewrite"], dry_run=args.dry_run)

        copy_landing(source, document_root, dry_run=args.dry_run)
        if not args.dry_run:
            chown_www_data(document_root, dry_run=False)

        if not args.no_refresh_members:
            refresh_members_json_in_document_root(
                document_root,
                users_json=args.members_users_json,
                homes_root=args.members_homes_root.resolve()
                if args.members_homes_root
                else None,
                dry_run=args.dry_run,
            )

        if args.dry_run:
            print(f"  [dry-run] escreveria {conf_path}")
        else:
            conf_path.write_text(vhost_body, encoding="utf-8")
            os.chmod(conf_path, 0o644)
        print(f"  [ok] VirtualHost em {conf_path}")

        if disable_default:
            run_cmd_allow_fail(
                ["a2dissite", DEFAULT_SITE],
                dry_run=args.dry_run,
                ok_hint="site por defeito já estava desactivado",
            )
        else:
            print("  [info] site por defeito 000-default mantido activo.")

        run_cmd(["a2ensite", site_conf_name], dry_run=args.dry_run)

        run_cmd([APACHE_CTL, "configtest"], dry_run=args.dry_run)

        if not args.dry_run:
            subprocess.run(
                ["systemctl", "reload", "apache2"],
                check=True,
                timeout=60,
            )
        else:
            print("  [dry-run] systemctl reload apache2")
        print("  [ok] Apache recarregado.")

        if args.certbot:
            www = f"www.{domain}"
            print()
            certbot_bin = shutil.which("certbot")
            if not certbot_bin:
                eprint("Erro: certbot não encontrado no PATH. Instale: sudo apt install -y certbot python3-certbot-apache")
                return EXIT_ERROR
            print("  A executar Certbot (interactivo se necessário)...")
            if args.dry_run:
                print(f"  [dry-run] {certbot_bin} --apache -d {domain} -d {www}")
            else:
                r = subprocess.run(
                    [certbot_bin, "--apache", "-d", domain, "-d", www],
                    check=False,
                )
                if r.returncode != 0:
                    eprint("Aviso: certbot terminou com código != 0; verifique TLS manualmente.")
                    return EXIT_ERROR
                print("  [ok] Certbot concluído.")

    except (FileNotFoundError, OSError, RuntimeError) as e:
        eprint(f"Erro: {e}")
        return EXIT_ERROR

    print()
    print("Próximos passos:")
    print(f"  - Testar: curl -sI http://{domain}/ | head -5")
    if args.dev:
        print("  - Em /etc/hosts (cliente ou VM): 127.0.0.1  runv.local  www.runv.local")
    print(
        "  - Membros na constelação: regenerado com build_directory após esta cópia "
        "(fonte: /var/lib/runv/users.json). Novas contas: create_runv_user.py também actualiza "
        "members.json se o DocumentRoot existir. Use --no-refresh-members para omitir."
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
