#!/usr/bin/env python3
"""
Envio de correio: Mailgun por HTTP por defeito; se não houver estado, cai para sendmail/msmtp.

Stdlib só; nada de shell=True.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Mapping, Sequence

from .mailgun_client import (
    MailgunHTTPError,
    build_mailgun_runtime_config,
    format_mailgun_failure,
    load_public_state,
    send_via_mailgun_api,
    state_path,
)

_DEFAULT_SENDMAIL = "/usr/sbin/sendmail"
_LOG = logging.getLogger("runv.mailer")


def _email_root() -> Path:
    env = os.environ.get("RUNV_EMAIL_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[1]


def templates_dir() -> Path:
    return _email_root() / "templates"


def render_template(name: str, **kwargs: object) -> str:
    """Lê ``templates/<name>.txt`` e faz ``.format``. Placeholder sem valor fica lá à mostra."""
    base = name.removesuffix(".txt")
    path = templates_dir() / f"{base}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"template de email não encontrado: {path}")
    text = path.read_text(encoding="utf-8")
    str_kw = {k: str(v) for k, v in kwargs.items()}
    try:
        return text.format(**str_kw)
    except KeyError as e:
        raise KeyError(f"placeholder em falta no template {name}: {e}") from e


def _resolve_backend(
    injected: dict | None,
    *,
    sendmail: str | None,
) -> tuple[str, dict]:
    """Tuple (mailgun|sendmail, dict lido de runv-email.json ou injectado)."""
    if injected is not None:
        state = injected
    else:
        sp = state_path()
        if not sp.is_file():
            return "sendmail", {}
        state = json.loads(sp.read_text(encoding="utf-8"))

    be = str(state.get("backend") or "").strip().lower()
    if be == "mailgun":
        return "mailgun", state
    if be == "sendmail":
        return "sendmail", state
    if state.get("smtp_host"):  # json velho do configure_msmtp
        return "sendmail", state
    if state.get("mailgun_domain") and state.get("mailgun_region"):  # mailgun sem campo backend
        return "mailgun", state
    return "sendmail", state


def send_mail(
    to_addrs: str | Sequence[str],
    subject: str,
    body: str,
    *,
    from_addr: str,
    sendmail: str | None = None,
    html: str | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: int = 120,
    _state: dict | None = None,
) -> None:
    """Mailgun se o estado pedir; senão ``sendmail -t -i``. ``html`` só interessa mesmo no ramo Mailgun."""
    sm_path = sendmail if sendmail is not None else _DEFAULT_SENDMAIL
    backend, st = _resolve_backend(_state, sendmail=sendmail)

    if backend == "mailgun":
        try:
            pub = st
            if not pub:
                pub = load_public_state()
            cfg = build_mailgun_runtime_config(pub)
        except FileNotFoundError:
            raise
        except Exception as e:
            raise RuntimeError(f"configuração Mailgun inválida: {e}") from e

        try:
            code, _raw = send_via_mailgun_api(
                base_url=cfg["api_base_url"],
                domain=cfg["domain"],
                api_key=cfg["api_key"],
                from_addr=from_addr,
                to_addrs=to_addrs,
                subject=subject,
                text=body,
                html=html,
                timeout=timeout,
            )
            _LOG.debug("mailgun envio OK status=%s", code)
        except MailgunHTTPError as e:
            msg = format_mailgun_failure(e.status, e.body_snippet)
            raise RuntimeError(msg) from e
        return

    # --- sendmail ---
    sm = Path(sm_path)
    if not sm.is_file():
        raise FileNotFoundError(
            f"sendmail não encontrado: {sm_path} "
            f"(modo legado). Configure Mailgun com configure_mailgun.py ou instale msmtp-mta.",
        )

    if isinstance(to_addrs, str):
        recipients: list[str] = [to_addrs.strip()]
    else:
        recipients = [a.strip() for a in to_addrs if a and str(a).strip()]

    if not recipients:
        raise ValueError("lista de destinatários vazia")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    if headers:
        for k, v in headers.items():
            if k.lower() in ("subject", "from", "to", "bcc", "cc"):
                continue
            msg[k] = v
    msg.set_content(body, subtype="plain", charset="utf-8")
    if html:
        msg.add_alternative(html, subtype="html", charset="utf-8")

    try:
        proc = subprocess.run(
            [str(sm), "-t", "-i"],
            input=msg.as_bytes(),
            capture_output=True,
            timeout=timeout,
        )
    except OSError as e:
        raise RuntimeError(f"erro ao executar sendmail: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("timeout ao executar sendmail") from e

    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"sendmail falhou (código {proc.returncode})" + (f": {err}" if err else "")
        )


def send_admin_notice(
    template_name: str,
    admin_email: str,
    *,
    subject: str,
    from_addr: str,
    sendmail: str | None = None,
    html_body: str | None = None,
    **kwargs: object,
) -> None:
    """Renderiza template administrativo e envia para admin_email."""
    body = render_template(template_name, **kwargs)
    send_mail(
        admin_email,
        subject,
        body,
        from_addr=from_addr,
        sendmail=sendmail,
        html=html_body,
    )


def send_user_notice(
    template_name: str,
    user_email: str,
    *,
    subject: str,
    from_addr: str,
    sendmail: str | None = None,
    html_body: str | None = None,
    **kwargs: object,
) -> None:
    """Renderiza template para utilizador e envia para user_email."""
    body = render_template(template_name, **kwargs)
    send_mail(
        user_email,
        subject,
        body,
        from_addr=from_addr,
        sendmail=sendmail,
        html=html_body,
    )


def format_from_display(name: str, addr: str) -> str:
    """Cabeçalho From com nome amigável (opcional)."""
    return formataddr((name, addr))
