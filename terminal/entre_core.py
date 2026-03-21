#!/usr/bin/env python3
"""
Lógica partilhada do fluxo SSH «entre» (runv.club): validação, fila, log, email.

Mantido alinhado com as regras de ``scripts/admin/create_runv_user.py`` (username,
email, tipos de chave). Campo ``online_presence`` é texto livre na fila (não duplicado
em ``create_runv_user``). Sem dependências PyPI.

Versão 0.02 — runv.club
"""

from __future__ import annotations

import json
import logging
import os
import time
import pwd
import re
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Final

import tomllib

# --- Alinhado a create_runv_user.py (não importar em runtime) ----------------

USERNAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)

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
        "admin",
        "postmaster",
        "entre",
        "join",
        "welcome",
    }
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

PRIVATE_KEY_MARKERS: Final[tuple[str, ...]] = (
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN EC PRIVATE KEY-----",
    "-----BEGIN DSA PRIVATE KEY-----",
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN ENCRYPTED PRIVATE KEY-----",
    "PuTTY-User-Key-File",
)

MAX_USERNAME_LEN: Final[int] = 32
MAX_EMAIL_LEN: Final[int] = 254
MAX_PUBKEY_LEN: Final[int] = 16_384
MIN_ONLINE_PRESENCE_LEN: Final[int] = 16
MAX_ONLINE_PRESENCE_LEN: Final[int] = 4000

APP_VERSION: Final[str] = "0.02"
SOURCE_TAG: Final[str] = "entre-ssh"
# Remetente por omissão das notificações sendmail do fluxo «entre» (cabeçalho From).
DEFAULT_MAIL_FROM: Final[str] = "entre@runv.club"


class ValidationError(ValueError):
    """Entrada inválida (mensagem para o utilizador)."""


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"config não encontrado: {path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config TOML inválido: raiz deve ser tabela")
    return data


def validate_username(username: str) -> str:
    if not username or not username.strip():
        raise ValidationError("o nome de utilizador desejado é obrigatório.")
    u = username.strip()
    if len(u) > MAX_USERNAME_LEN:
        raise ValidationError("nome de utilizador demasiado longo.")
    if not USERNAME_PATTERN.fullmatch(u):
        raise ValidationError(
            "use apenas letras minúsculas, dígitos, _ e -; comece com letra; "
            "entre 2 e 32 caracteres."
        )
    if u in RESERVED_USERNAMES:
        raise ValidationError("esse nome está reservado ou não é permitido.")
    try:
        pwd.getpwnam(u)
    except KeyError:
        pass
    else:
        raise ValidationError("esse nome já existe neste servidor.")
    return u


def validate_online_presence(raw: str) -> str:
    """Texto livre: URLs, perfis, uma linha por sítio — sem mencionar moderação ao utilizador."""
    if raw is None or not str(raw).strip():
        raise ValidationError(
            "indica sítios ou perfis onde possamos ver o teu trabalho ou o que publicas online "
            f"(mínimo {MIN_ONLINE_PRESENCE_LEN} caracteres). Podes usar várias linhas no passo anterior."
        )
    t = str(raw).strip()
    if len(t) < MIN_ONLINE_PRESENCE_LEN:
        raise ValidationError(
            "esse campo ainda é curto demais — adiciona um link, perfil ou página onde apareças online."
        )
    if len(t) > MAX_ONLINE_PRESENCE_LEN:
        raise ValidationError(
            "texto demasiado longo; resume ou escolhe os links mais importantes."
        )
    if "\x00" in t:
        raise ValidationError("caracteres inválidos no texto.")
    return t


def validate_email(email: str) -> str:
    if not email or not email.strip():
        raise ValidationError("o email é obrigatório.")
    if email != email.strip():
        raise ValidationError("o email não pode ter espaços no início ou fim.")
    e = email.strip()
    if len(e) > MAX_EMAIL_LEN:
        raise ValidationError("email demasiado longo.")
    at = e.count("@")
    if at == 0:
        raise ValidationError(
            "indica um endereço com @, por exemplo nome@exemplo.org."
        )
    if at != 1:
        raise ValidationError("o email deve ter um único @.")
    if not EMAIL_PATTERN.fullmatch(e):
        raise ValidationError("formato de email inválido.")
    return e


def _reject_private_key_blob(raw: str) -> None:
    s = raw.strip()
    low = s.lower()
    for marker in PRIVATE_KEY_MARKERS:
        if marker.lower() in low:
            raise ValidationError(
                "isto parece uma chave **privada**. Nunca a cole aqui. "
                "Cole apenas a linha da chave **pública** (.pub)."
            )


def normalize_public_key(raw: str) -> str:
    if raw is None or raw == "":
        raise ValidationError("a chave pública é obrigatória.")
    if len(raw) > MAX_PUBKEY_LEN:
        raise ValidationError("linha da chave demasiado longa.")
    _reject_private_key_blob(raw)
    if "\n" in raw or "\r" in raw:
        raise ValidationError("cole uma única linha, sem quebras.")
    line = raw.strip()
    if not line:
        raise ValidationError("chave pública vazia.")
    parts = line.split()
    if len(parts) < 2:
        raise ValidationError("formato inválido: esperado tipo, dados base64 e comentário opcional.")
    key_type = parts[0]
    if key_type not in ALLOWED_KEY_TYPES:
        raise ValidationError(
            f"tipo de chave não aceite ({key_type!r}). "
            f"Exemplos: ssh-ed25519, ecdsa-sha2-nistp256, ssh-rsa."
        )
    blob = parts[1]
    if not re.fullmatch(r"[A-Za-z0-9+/]+=*", blob):
        raise ValidationError("dados da chave (base64) inválidos.")
    normalized = key_type + " " + blob
    if len(parts) > 2:
        normalized += " " + " ".join(parts[2:])
    return normalized


def compute_public_key_fingerprint(public_key_line: str, tmp_dir: Path | None = None) -> str:
    line = normalize_public_key(public_key_line)
    fd, tmppath = tempfile.mkstemp(prefix="runv-entre-key-", suffix=".pub", dir=tmp_dir)
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
            raise ValidationError(f"a chave foi rejeitada pelo ssh-keygen: {err}")
        out = (proc.stdout or "").strip().splitlines()
        if not out:
            raise RuntimeError("ssh-keygen não devolveu saída")
        m = FINGERPRINT_SHA256_RE.search(out[0])
        if not m:
            raise RuntimeError(f"não foi possível ler o fingerprint: {out[0]!r}")
        return m.group(1)
    finally:
        path.unlink(missing_ok=True)


def validate_public_key_line(raw: str) -> tuple[str, str]:
    normalized = normalize_public_key(raw)
    fp = compute_public_key_fingerprint(normalized)
    return normalized, fp


def ssh_remote_context() -> dict[str, str | None]:
    return {
        "remote_addr": os.environ.get("SSH_CONNECTION", "").split()[0]
        if os.environ.get("SSH_CONNECTION")
        else (
            os.environ.get("SSH_CLIENT", "").split()[0]
            if os.environ.get("SSH_CLIENT")
            else None
        ),
        "ssh_connection": os.environ.get("SSH_CONNECTION"),
        "ssh_client": os.environ.get("SSH_CLIENT"),
        "tty": os.environ.get("SSH_TTY"),
    }


@dataclass
class EntrePaths:
    install_root: Path
    templates_dir: Path
    queue_dir: Path
    log_file: Path
    config_path: Path


def resolve_paths(cfg: dict[str, Any], install_root: Path) -> EntrePaths:
    q = os.environ.get("RUNV_ENTRE_QUEUE_DIR", "").strip()
    queue = Path(q) if q else Path(cfg.get("queue_dir", "/var/lib/runv/entre-queue"))
    lf_e = os.environ.get("RUNV_ENTRE_LOG_FILE", "").strip()
    logf = Path(lf_e) if lf_e else Path(cfg.get("log_file", "/var/log/runv/entre.log"))
    td_e = os.environ.get("RUNV_ENTRE_TEMPLATES_DIR", "").strip()
    td = Path(td_e) if td_e else Path(cfg.get("templates_dir", str(install_root / "templates")))
    return EntrePaths(
        install_root=install_root,
        templates_dir=td,
        queue_dir=queue,
        log_file=logf,
        config_path=install_root / "config.toml",
    )


def setup_file_logger(log_path: Path) -> logging.Logger:
    log = logging.getLogger("runv.entre")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s")
    fmt.converter = time.gmtime
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError:
        sh = logging.StreamHandler()
        fmt_err = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s")
        fmt_err.converter = time.gmtime
        sh.setFormatter(fmt_err)
        log.addHandler(sh)
    return log


def log_session(logger: logging.Logger, msg: str, *, level: int = logging.INFO) -> None:
    logger.log(level, msg)


def sendmail_notify(
    *,
    admin_email: str,
    mail_from: str,
    subject: str,
    body: str,
    sendmail_path: str,
    logger: logging.Logger,
) -> None:
    if not admin_email.strip():
        logger.info("notificação por email: admin_email vazio, ignorado.")
        return
    if not Path(sendmail_path).is_file():
        logger.warning(
            "notificação por email: sendmail não encontrado em %s — pedido continua gravado.",
            sendmail_path,
        )
        return
    from_addr = mail_from.strip() or DEFAULT_MAIL_FROM
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = admin_email
    msg.set_content(body)
    try:
        proc = subprocess.run(
            [sendmail_path, "-t", "-i"],
            input=msg.as_bytes(),
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
            logger.warning("sendmail falhou (código %s): %s", proc.returncode, err)
        else:
            logger.info("notificação por email enviada para %s", admin_email)
    except OSError as e:
        logger.warning("notificação por email: erro ao executar sendmail: %s", e)
    except subprocess.TimeoutExpired:
        logger.warning("notificação por email: timeout ao executar sendmail.")


def save_request_json(
    *,
    queue_dir: Path,
    request_id: str,
    payload: dict[str, Any],
    logger: logging.Logger,
) -> Path:
    queue_dir.mkdir(parents=True, exist_ok=True)
    path = queue_dir / f"{request_id}.json"
    fd = os.open(
        str(path),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o640,
    )
    try:
        data = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        os.write(fd, data.encode("utf-8"))
    finally:
        os.close(fd)
    logger.info("pedido gravado: %s", path)
    return path


def build_request_payload(
    *,
    request_id: str,
    username: str,
    email: str,
    online_presence: str,
    public_key: str,
    fingerprint: str,
    remote_addr: str | None,
    tty: str | None,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "username": username,
        "email": email,
        "online_presence": online_presence,
        "public_key": public_key,
        "public_key_fingerprint": fingerprint,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "remote_addr": remote_addr,
        "tty": tty,
        "source": SOURCE_TAG,
        "status": "pending",
        "app_version": APP_VERSION,
    }


def new_request_id() -> str:
    return str(uuid.uuid4())


def render_template(path: Path, mapping: dict[str, str]) -> str:
    text = path.read_text(encoding="utf-8")
    for k, v in mapping.items():
        text = text.replace("{" + k + "}", v)
    return text


def find_install_root() -> Path:
    env = os.environ.get("RUNV_ENTRE_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parent


def find_config_path(install_root: Path) -> Path:
    env = os.environ.get("RUNV_ENTRE_CONFIG", "").strip()
    if env:
        return Path(env).resolve()
    p = install_root / "config.toml"
    if p.is_file():
        return p
    example = install_root / "config.example.toml"
    if example.is_file():
        return example
    return p
