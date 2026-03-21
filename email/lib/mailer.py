#!/usr/bin/env python3
"""
Envio de email via interface sendmail compatível (msmtp-mta).

Sem shell=True. Sem dependências PyPI — apenas stdlib.
"""

from __future__ import annotations

import os
import subprocess
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Mapping, Sequence

from . import templates as T

_DEFAULT_SENDMAIL = "/usr/sbin/sendmail"


def _email_root() -> Path:
    env = os.environ.get("RUNV_EMAIL_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[1]


def templates_dir() -> Path:
    return _email_root() / "templates"


def render_template(name: str, **kwargs: object) -> str:
    """
    Lê templates/<name>.txt e substitui {chaves} pelos kwargs.
    Chaves em falta deixam o placeholder visível (não falha silenciosamente).
    """
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


def send_mail(
    to_addrs: str | Sequence[str],
    subject: str,
    body: str,
    *,
    from_addr: str,
    sendmail: str = _DEFAULT_SENDMAIL,
    headers: Mapping[str, str] | None = None,
    timeout: int = 120,
) -> None:
    """
    Envia mensagem texto puro via sendmail -t -i.

    :param to_addrs: um endereço ou lista de endereços (cabeçalho To).
    :raises FileNotFoundError: sendmail inexistente.
    :raises RuntimeError: sendmail devolveu código != 0.
    """
    sm = Path(sendmail)
    if not sm.is_file():
        raise FileNotFoundError(f"sendmail não encontrado: {sendmail}")

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
    sendmail: str = _DEFAULT_SENDMAIL,
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
    )


def send_user_notice(
    template_name: str,
    user_email: str,
    *,
    subject: str,
    from_addr: str,
    sendmail: str = _DEFAULT_SENDMAIL,
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
    )


def format_from_display(name: str, addr: str) -> str:
    """Cabeçalho From com nome amigável (opcional)."""
    return formataddr((name, addr))
