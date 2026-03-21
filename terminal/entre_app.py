#!/usr/bin/env python3
"""
Experiência SSH guiada para pedidos de entrada na runv.club (utilizador «entre»).

Executado via ForceCommand no OpenSSH. Não cria contas Linux; apenas fila + log
+ notificação opcional.

Versão 0.01 — runv.club
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Arte ASCII da landing (site/public/index.html) — manter alinhado ao <pre class="ascii">.
RUNV_ASCII_ART: str = """██████╗ ██╗   ██╗███╗   ██╗██╗   ██╗
██╔══██╗██║   ██║████╗  ██║██║   ██║
██████╔╝██║   ██║██╔██╗ ██║██║   ██║
██╔══██╗╚██╗ ██╔╝██║╚██╗██║╚██╗ ██╔╝
██║  ██║ ╚████╔╝ ██║ ╚████║ ╚████╔╝
╚═╝  ╚═╝  ╚═══╝  ╚═╝  ╚═══╝  ╚═══╝"""

ASCII_TAGLINE: str = ".club — um computador para compartilhar"

# Em intro.txt: linha só com este marcador separa ecrãs da narrativa.
INTRO_PAGE_BREAK: str = "%%PAGE%%"

from entre_core import (
    APP_VERSION,
    DEFAULT_MAIL_FROM,
    MAX_ONLINE_PRESENCE_LEN,
    ValidationError,
    build_request_payload,
    find_config_path,
    find_install_root,
    load_config,
    log_session,
    new_request_id,
    render_template,
    resolve_paths,
    save_request_json,
    sendmail_notify,
    setup_file_logger,
    ssh_remote_context,
    validate_email,
    validate_online_presence,
    validate_public_key_line,
    validate_username,
)


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def pause(stdin, stdout) -> None:
    stdout.write("\n[Enter] continuar  ·  [q] sair\n")
    stdout.flush()
    line = stdin.readline()
    if not line:
        raise SystemExit(0)
    if line.strip().lower() in ("q", "quit", "sair"):
        print("\nAté logo.\n")
        raise SystemExit(0)


def read_line(prompt: str, stdin, stdout) -> str:
    stdout.write(prompt)
    stdout.flush()
    line = stdin.readline()
    if not line:
        raise SystemExit(0)
    return line.rstrip("\r\n")


def write_data_step_header(stdout, step: int, total: int, title: str) -> None:
    """Cabeçalho visível antes de cada campo do formulário."""
    clear_screen(stdout)
    g = "\033[92m" if _use_ansi_color(stdout) else ""
    c = "\033[96m" if _use_ansi_color(stdout) else ""
    b = "\033[1m" if _use_ansi_color(stdout) else ""
    r = "\033[0m" if g else ""
    bar = "━" * 52
    stdout.write(f"\n  {g}{bar}{r}\n")
    stdout.write(f"  {b}{c}Dados · passo {step}/{total}{r}\n")
    stdout.write(f"  {b}{g}{title}{r}\n")
    stdout.write(f"  {g}{bar}{r}\n\n")


def read_multiline_until_dot(stdin, stdout, *, max_lines: int = 48) -> str:
    """Várias linhas; termina com uma linha só com '.' (como no SMTP clássico)."""
    d = "\033[2m" if _use_ansi_color(stdout) else ""
    r = "\033[0m" if d else ""
    stdout.write(
        f"{d}  (podes usar várias linhas; para terminar, uma linha só com . e Enter){r}\n\n"
    )
    stdout.flush()
    lines: list[str] = []
    for _ in range(max_lines):
        line = stdin.readline()
        if not line:
            raise SystemExit(0)
        s = line.rstrip("\r\n")
        if s == ".":
            if lines:
                break
            continue
        lines.append(s)
        if len("\n".join(lines)) > MAX_ONLINE_PRESENCE_LEN:
            stdout.write(
                f"\n  {d}(limite de tamanho atingido — campo fechado aqui.){r}\n"
            )
            break
    return "\n".join(lines).strip()


def clear_screen(stdout) -> None:
    stdout.write("\033[2J\033[H")
    stdout.flush()


def _use_ansi_color(stdout) -> bool:
    if not getattr(stdout, "isatty", lambda: False)():
        return False
    term = (os.environ.get("TERM") or "").strip().lower()
    if term in ("", "dumb"):
        return False
    if os.environ.get("NO_COLOR", "").strip():
        return False
    return True


RUNV_CLUB_MARK: str = "runv.club"


def style_runv_club(text: str, stdout) -> str:
    """Destaca runv.club a verde no terminal (todas as ocorrências)."""
    if not _use_ansi_color(stdout) or RUNV_CLUB_MARK not in text:
        return text
    g, r = "\033[92m", "\033[0m"
    return text.replace(RUNV_CLUB_MARK, f"{g}{RUNV_CLUB_MARK}{r}")


def wait_any_key(stdin, stdout) -> None:
    """Lê uma tecla em modo cru (POSIX); senão, uma linha (Enter)."""
    if sys.platform != "win32" and stdin.isatty():
        try:
            import termios
            import tty

            fd = stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                ch = stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            if ch == "\x03":
                raise KeyboardInterrupt
            if ch == "\x04" or ch == "":
                raise SystemExit(0)
            return
        except (ImportError, OSError, termios.error):
            pass
    stdout.write("  (tecla Enter para continuar)\n")
    stdout.flush()
    line = stdin.readline()
    if not line:
        raise SystemExit(0)


def show_opening_splash(stdin, stdout) -> None:
    clear_screen(stdout)
    green = "\033[92m" if _use_ansi_color(stdout) else ""
    reset = "\033[0m" if green else ""
    stdout.write("\n")
    for line in RUNV_ASCII_ART.splitlines():
        stdout.write(f"  {green}{line}{reset}\n")
    stdout.write(f"\n  {green}{ASCII_TAGLINE}{reset}\n\n")
    stdout.write(f"  {green}Aperte qualquer tecla para continuar...{reset}\n")
    stdout.flush()
    wait_any_key(stdin, stdout)


def show_paged_template(stdin, stdout, template_path: Path) -> None:
    raw = template_path.read_text(encoding="utf-8")
    pages = [p.strip("\n") for p in raw.split(INTRO_PAGE_BREAK)]
    pages = [p for p in pages if p.strip()]
    total = len(pages)
    for i, page in enumerate(pages, start=1):
        clear_screen(stdout)
        if total > 1:
            stdout.write(f"  ({i}/{total})\n\n")
        page = style_runv_club(page, stdout)
        stdout.write(page)
        if not page.endswith("\n"):
            stdout.write("\n")
        stdout.flush()
        pause(stdin, stdout)


def collect_loop(stdin, stdout, templates: Path) -> tuple[str, str, str, str, str]:
    username = email = online_presence = pubkey = ""
    fp = ""
    total = 4
    while True:
        write_data_step_header(stdout, 1, total, "Nome de utilizador Unix desejado")
        stdout.write(
            style_runv_club(
                "Letras minúsculas, dígitos, _ ou -; começa com letra. "
                "Deixa em branco só se ainda não tiveres escolhido.\n",
                stdout,
            )
        )
        b = "\033[1m" if _use_ansi_color(stdout) else ""
        r = "\033[0m" if b else ""
        stdout.write(f"\n  {b}» Escreve abaixo e prima Enter:{r}\n\n  ")
        stdout.flush()
        u = read_line("", stdin, stdout).strip()
        if u:
            username = u

        write_data_step_header(stdout, 2, total, "Email de contacto")
        stdout.write(
            "Endereço para a equipa te responder sobre este pedido.\n"
        )
        stdout.write(f"\n  {b}» Escreve abaixo e prima Enter:{r}\n\n  ")
        stdout.flush()
        e = read_line("", stdin, stdout).strip()
        if e:
            email = e

        write_data_step_header(stdout, 3, total, "Onde te encontramos online?")
        stdout.write(
            style_runv_club(
                "Links, perfis ou páginas onde aparece o teu trabalho, código ou participação "
                "— por exemplo site, GitHub, Mastodon, itch.io, etc. "
                "Uma sugestão por linha.\n",
                stdout,
            )
        )
        stdout.write(f"\n  {b}» A tua resposta (várias linhas):{r}\n")
        stdout.flush()
        raw_on = read_multiline_until_dot(stdin, stdout)
        if raw_on:
            online_presence = raw_on

        write_data_step_header(stdout, 4, total, "Chave pública SSH")
        stdout.write(
            "Uma única linha, a mesma que irias pôr em authorized_keys. "
            "Só a pública.\n"
        )
        stdout.write(f"\n  {b}» Cola a linha abaixo e prima Enter:{r}\n\n  ")
        stdout.flush()
        pk = stdin.readline()
        if not pk:
            raise SystemExit(0)
        pk = pk.rstrip("\r\n")
        if pk.strip():
            pubkey = pk.strip()

        errors: list[str] = []
        try:
            vu = validate_username(username)
        except ValidationError as ex:
            errors.append(str(ex))
            vu = ""
        try:
            ve = validate_email(email)
        except ValidationError as ex:
            errors.append(str(ex))
            ve = ""
        try:
            v_on = validate_online_presence(online_presence)
        except ValidationError as ex:
            errors.append(str(ex))
            v_on = ""
        try:
            if not pubkey:
                raise ValidationError("a chave pública é obrigatória.")
            nkey, fp = validate_public_key_line(pubkey)
        except ValidationError as ex:
            errors.append(str(ex))
            nkey, fp = "", ""

        if errors:
            clear_screen(stdout)
            stdout.write("— Corrige os dados —\n\n")
            for err in errors:
                stdout.write(f"  • {err}\n")
            stdout.write("\n[Enter] para voltar ao início do formulário\n")
            stdout.flush()
            stdin.readline()
            continue
        return vu, ve, v_on, nkey, fp


def confirm_loop(
    stdin,
    stdout,
    *,
    username: str,
    email: str,
    online_presence: str,
    fingerprint: str,
    templates: Path,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = render_template(
        templates / "confirm.txt",
        {
            "username": username,
            "email": email,
            "online_presence": online_presence,
            "fingerprint": fingerprint,
            "submitted_preview": now,
        },
    )
    while True:
        clear_screen(stdout)
        stdout.write(style_runv_club(body, stdout))
        stdout.write("\n  [c] confirmar envio\n")
        stdout.write("  [e] editar dados\n")
        stdout.write("  [x] cancelar e sair\n\n")
        stdout.write("Opção: ")
        stdout.flush()
        line = stdin.readline()
        if not line:
            raise SystemExit(0)
        c = line.strip().lower()
        if c in ("c", "confirmar", "s", "sim", "y", "yes"):
            return "confirm"
        if c in ("e", "editar"):
            return "edit"
        if c in ("x", "cancelar", "n", "nao", "não"):
            return "cancel"
        stdout.write("Opção inválida.\n")
        stdout.write("[Enter]")
        stdin.readline()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fluxo SSH entre@runv.club (runv.club)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    args = parser.parse_args()
    del args

    stdin, stdout = sys.stdin, sys.stdout

    install_root = find_install_root()
    config_path = find_config_path(install_root)
    try:
        cfg = load_config(config_path)
    except (OSError, ValueError) as e:
        eprint(f"Erro de configuração: {e}")
        return 2

    paths = resolve_paths(cfg, install_root)
    logger = setup_file_logger(paths.log_file)

    ctx = ssh_remote_context()
    log_session(
        logger,
        f"sessão iniciada remote_addr={ctx.get('remote_addr')!r} tty={ctx.get('tty')!r}",
    )

    templates = paths.templates_dir
    if not templates.is_dir():
        eprint(f"Templates em falta: {templates}")
        log_session(logger, f"ERRO templates em falta: {templates}", level=40)
        return 2

    try:
        # --- Abertura: arte ASCII da landing (verde) + qualquer tecla
        show_opening_splash(stdin, stdout)

        # --- Etapa 1: narrativa (%%PAGE%% em intro.txt)
        show_paged_template(stdin, stdout, templates / "intro.txt")

        # --- Etapa 2: aviso chave (pode ter %%PAGE%% como intro.txt)
        show_paged_template(stdin, stdout, templates / "warning_public_key.txt")

        # --- Etapa 3–4: coleta e confirmação (com edição repetível)
        username, email, online_presence, pubkey, fingerprint = collect_loop(
            stdin, stdout, templates
        )
        while True:
            action = confirm_loop(
                stdin,
                stdout,
                username=username,
                email=email,
                online_presence=online_presence,
                fingerprint=fingerprint,
                templates=templates,
            )
            if action == "cancel":
                log_session(logger, "utilizador cancelou antes de gravar")
                stdout.write("\nPedido cancelado. Até logo.\n\n")
                return 0
            if action == "edit":
                username, email, online_presence, pubkey, fingerprint = collect_loop(
                    stdin, stdout, templates
                )
                continue
            break

        request_id = ""
        path_saved = None
        for attempt in range(8):
            request_id = new_request_id()
            payload = build_request_payload(
                request_id=request_id,
                username=username,
                email=email,
                online_presence=online_presence,
                public_key=pubkey,
                fingerprint=fingerprint,
                remote_addr=ctx.get("remote_addr"),
                tty=ctx.get("tty"),
            )
            try:
                path_saved = save_request_json(
                    queue_dir=paths.queue_dir,
                    request_id=request_id,
                    payload=payload,
                    logger=logger,
                )
                break
            except FileExistsError:
                log_session(logger, f"colisão request_id, a gerar outro (tentativa {attempt + 1})")
                continue
            except OSError as e:
                log_session(logger, f"ERRO ao gravar pedido: {e}", level=40)
                eprint("Não foi possível gravar o pedido. Contacte a administração.")
                return 2
        else:
            log_session(logger, "ERRO: não foi possível obter request_id único", level=40)
            eprint("Erro interno: tente novamente.")
            return 2

        submitted_at = payload["submitted_at"]
        _ = path_saved

        # Aviso em consola ao admin (template curto)
        try:
            oneline = online_presence.replace("\n", " ").strip()
            if len(oneline) > 100:
                oneline = oneline[:97] + "..."
            notice = render_template(
                templates / "admin_console_notice.txt",
                {
                    "request_id": request_id,
                    "username": username,
                    "email": email,
                    "fingerprint": fingerprint,
                    "submitted_at": submitted_at,
                    "online_presence_line": oneline,
                },
            )
            log_session(logger, "admin_console_notice:\n" + notice.strip())
        except OSError:
            pass

        admin_email = str(cfg.get("admin_email", "")).strip()
        mail_raw = str(cfg.get("mail_from", DEFAULT_MAIL_FROM)).strip()
        mail_from = mail_raw or DEFAULT_MAIL_FROM
        sendmail_path = str(cfg.get("sendmail_path", "/usr/sbin/sendmail")).strip()
        if admin_email:
            try:
                subject = f"[runv] Novo pedido: {username}"
                body = render_template(
                    templates / "admin_mail.txt",
                    {
                        "request_id": request_id,
                        "username": username,
                        "email": email,
                        "online_presence": online_presence,
                        "public_key": pubkey,
                        "fingerprint": fingerprint,
                        "submitted_at": submitted_at,
                        "remote_addr": ctx.get("remote_addr") or "",
                        "tty": ctx.get("tty") or "",
                    },
                )
                sendmail_notify(
                    admin_email=admin_email,
                    mail_from=mail_from,
                    subject=subject,
                    body=body,
                    sendmail_path=sendmail_path,
                    logger=logger,
                )
            except OSError as e:
                log_session(logger, f"template admin_mail falhou: {e}", level=40)

        # --- Etapa 7: despedida
        clear_screen(stdout)
        goodbye = render_template(
            templates / "goodbye.txt",
            {"request_id": request_id},
        )
        stdout.write(style_runv_club(goodbye, stdout))
        stdout.flush()
        log_session(logger, f"sessão concluída request_id={request_id}")
    except ValidationError as e:
        log_session(logger, f"validação: {e}", level=40)
        stdout.write(style_runv_club(f"\n{e}\n\n", stdout))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
