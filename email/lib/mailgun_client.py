#!/usr/bin/env python3
"""
Cliente HTTP Mailgun (API de envio) — stdlib apenas.

Basic Auth: utilizador fixo ``api``, palavra-passe = API key.
Documentação: https://documentation.mailgun.com/en/latest/api-sending.html
"""

from __future__ import annotations

import base64
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

DEFAULT_STATE_PATH = Path("/etc/runv-email.json")
DEFAULT_SECRETS_PATH = Path("/etc/runv-email.secrets.json")

# Placeholder neutro para testes/documentação — nunca credenciais reais.
EXAMPLE_DOMAIN: Final[str] = "example.com"

_REGIONS: Final[frozenset[str]] = frozenset({"us", "eu"})

# Domínio verificável: hostname ou subdomínio típico Mailgun (mg.example.com)
_DOMAIN_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
)


class MailgunConfigError(ValueError):
    """Configuração inválida ou incompleta."""


class MailgunHTTPError(RuntimeError):
    """Resposta HTTP não-sucesso da API Mailgun."""

    def __init__(self, message: str, *, status: int, body_snippet: str) -> None:
        super().__init__(message)
        self.status = status
        self.body_snippet = body_snippet


def mailgun_base_url(region: str) -> str:
    """
    URL base da API (sem ``/v3/...``) para a região escolhida.
    ``region`` deve ser ``us`` ou ``eu`` (minúsculas).
    """
    r = region.strip().lower()
    if r not in _REGIONS:
        raise MailgunConfigError(f"região inválida: {region!r} (use 'us' ou 'eu')")
    if r == "eu":
        return "https://api.eu.mailgun.net"
    return "https://api.mailgun.net"


def build_mailgun_messages_url(*, base_url: str, domain: str) -> str:
    """URL completa ``POST .../v3/{domain}/messages``."""
    b = base_url.rstrip("/")
    d = domain.strip().lower()
    if not d:
        raise MailgunConfigError("domínio Mailgun vazio")
    return f"{b}/v3/{urllib.parse.quote(d, safe='.')}/messages"


def mask_secret(value: str | None, *, visible_tail: int = 4) -> str:
    """Mascara segredos para logs ou mensagens de diagnóstico."""
    if value is None:
        return "(não definido)"
    s = value.strip()
    if not s:
        return "(vazio)"
    if len(s) <= visible_tail + 3:
        return "***"
    return s[:3] + "…" + s[-visible_tail:]  # type: ignore


def validate_mailgun_inputs(
    *,
    domain: str,
    region: str,
    from_addr: str,
    admin_email: str,
    api_key: str,
) -> dict[str, str]:
    """
    Valida entradas interactivas / ficheiro. Devolve dict normalizado
    (domain, region, from_addr, admin_email) — não devolve a key.
    """
    core = validate_mailgun_send_fields(
        domain=domain,
        region=region,
        from_addr=from_addr,
        api_key=api_key,
    )
    ad = admin_email.strip()
    if not ad or "@" not in ad:
        raise MailgunConfigError("email do administrador inválido.")
    return {**core, "admin_email": ad}


def validate_mailgun_send_fields(
    *,
    domain: str,
    region: str,
    from_addr: str,
    api_key: str,
) -> dict[str, str]:
    """Valida domínio, região, From e API key (envio em tempo de execução)."""
    d = domain.strip().lower()
    if not d:
        raise MailgunConfigError("domínio de envio obrigatório (não pode estar vazio).")
    if not _DOMAIN_RE.match(d):
        raise MailgunConfigError(
            f"domínio inválido: {domain!r} — use um hostname FQDN (ex.: {EXAMPLE_DOMAIN}).",
        )

    r = region.strip().lower()
    mailgun_base_url(r)  # valida região

    fa = from_addr.strip()
    if not fa or "@" not in fa:
        raise MailgunConfigError("remetente (From) deve ser um endereço de email válido.")

    key = api_key.strip()
    if not key:
        raise MailgunConfigError("API key Mailgun obrigatória (não pode estar vazia).")

    return {
        "domain": d,
        "region": r,
        "from_addr": fa,
    }


def state_path() -> Path:
    raw = os.environ.get("RUNV_EMAIL_STATE_PATH", "").strip()
    return Path(raw) if raw else DEFAULT_STATE_PATH


def secrets_path_from_state(public: Mapping[str, Any]) -> Path:
    raw = str(public.get("secrets_path") or "").strip()
    if raw:
        return Path(raw)
    raw_env = os.environ.get("RUNV_EMAIL_SECRETS_PATH", "").strip()
    if raw_env:
        return Path(raw_env)
    return DEFAULT_SECRETS_PATH


def load_public_state(path: Path | None = None) -> dict[str, Any]:
    p = path or state_path()
    if not p.is_file():
        raise FileNotFoundError(
            f"Estado de email não encontrado: {p}. Execute o configurador Mailgun.",
        )
    return json.loads(p.read_text(encoding="utf-8"))


def load_mailgun_api_key(public: Mapping[str, Any]) -> tuple[str, str]:
    """
    Carrega API key. Ordem: ``RUNV_MAILGUN_API_KEY``, depois ficheiro de segredos.
    Devolve (api_key, fonte_descritiva) — fonte nunca contém a key.
    """
    env_key = os.environ.get("RUNV_MAILGUN_API_KEY", "").strip()
    if env_key:
        return env_key, "environment"

    sp = secrets_path_from_state(public)
    if not sp.is_file():
        raise MailgunConfigError(
            f"API key em falta: defina RUNV_MAILGUN_API_KEY ou crie {sp} (0600) com mailgun_api_key.",
        )
    try:
        sec = json.loads(sp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise MailgunConfigError(f"ficheiro de segredos JSON inválido: {sp}: {e}") from e
    key = str(sec.get("mailgun_api_key", "")).strip()
    if not key:
        raise MailgunConfigError(f"mailgun_api_key vazio em {sp}")
    return key, f"file:{sp}"


def build_mailgun_runtime_config(public: Mapping[str, Any]) -> dict[str, Any]:
    """Junta estado público + key (em memória) para envio."""
    if public.get("backend") == "sendmail":
        raise MailgunConfigError("estado explícito backend=sendmail — não usar Mailgun")
    domain = str(public.get("mailgun_domain", "")).strip()
    region = str(public.get("mailgun_region", "")).strip().lower()
    default_from = str(public.get("default_from", "")).strip()
    api_key, _src = load_mailgun_api_key(public)
    base = str(public.get("api_base_url") or mailgun_base_url(region))
    validate_mailgun_send_fields(
        domain=domain,
        region=region,
        from_addr=default_from,
        api_key=api_key,
    )
    return {
        "domain": domain,
        "region": region,
        "api_base_url": base,
        "default_from": default_from,
        "api_key": api_key,
    }


def send_via_mailgun_api(
    *,
    base_url: str,
    domain: str,
    api_key: str,
    from_addr: str,
    to_addrs: str | Sequence[str],
    subject: str,
    text: str,
    html: str | None = None,
    timeout: int = 120,
) -> tuple[int, str]:
    """
    POST application/x-www-form-urlencoded para ``/v3/{domain}/messages``.

    :return: (status_code, body_text) em sucesso 200.
    :raises MailgunHTTPError: status não 2xx.
    :raises MailgunConfigError: destinatários vazios.
    """
    if isinstance(to_addrs, str):
        recipients = [to_addrs.strip()]
    else:
        recipients = [a.strip() for a in to_addrs if a and str(a).strip()]
    if not recipients:
        raise MailgunConfigError("lista de destinatários vazia")

    url = build_mailgun_messages_url(base_url=base_url, domain=domain)
    pairs: list[tuple[str, str]] = [
        ("from", from_addr),
        ("subject", subject),
        ("text", text),
    ]
    for a in recipients:
        pairs.append(("to", a))
    if html:
        pairs.append(("html", html))

    body = urllib.parse.urlencode(pairs).encode("utf-8")
    token = base64.b64encode(f"api:{api_key}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded; charset=utf-8")

    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.getcode() or 200, raw
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        snippet = err_body[:500].strip()  # type: ignore
        raise MailgunHTTPError(
            f"Mailgun HTTP {e.code}",
            status=e.code,
            body_snippet=snippet,
        ) from None
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        raise MailgunConfigError(f"rede/SSL ao contactar Mailgun: {reason}") from e
    except TimeoutError as e:
        raise MailgunConfigError("timeout ao contactar API Mailgun") from e


def format_mailgun_failure(status: int, body_snippet: str) -> str:
    """Mensagem legível para operadores (sem expor segredos)."""
    base = f"HTTP {status}"
    if status in (401, 403):
        return (
            f"{base}: API key inválida, domínio/região incorrectos, ou **IP allowlist** no "
            f"painel Mailgun a bloquear este servidor. Confirme chave HTTP (não password SMTP), "
            f"domínio na URL, e em Security/API a lista de IPs permitidos."
        )
    if status == 400:
        return f"{base}: pedido inválido — verifique domínio, From autorizado e campos obrigatórios. Resposta: {body_snippet[:200]}"  # type: ignore
    if status == 404:
        return f"{base}: domínio ou URL/região incorretos (confirme US vs EU e o domínio no painel Mailgun). Resposta: {body_snippet[:200]}"  # type: ignore
    if status >= 500:
        return f"{base}: erro no serviço Mailgun. Tente mais tarde. Resposta: {body_snippet[:200]}"  # type: ignore
    return f"{base}: {body_snippet[:300]}"  # type: ignore
