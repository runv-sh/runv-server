#!/usr/bin/env python3
"""
Ferramenta interna de administração: provisiona contas Unix no runv.club (Debian).

Contrato de provisionamento (ordem garantida após validação):

1. **Criar o usuário** — ``adduser --disabled-password``.
2. **Instalar a chave** — ``~/.ssh/authorized_keys`` com modos ``700`` / ``600``.
3. **Preparar public_html** — diretório ``755``, ``index.html`` estático ``644``.
4. **Preparar public_gopher / public_gemini** — ``gophermap`` modelo (não sobrescreve sem
   ``--force-gopher``); ``index.gmi`` só é criado se ainda não existir (nunca substituído);
   bind mount ``/var/gemini/users/<user>`` <- ``~/public_gemini`` quando o directório global existir
   (``--force-gemini`` força migração de symlink / remount).
5. **Skel Debian** — copiado no passo 1; o skel runv (``tools.py``) **não** inclui ``README.md`` por
   política. Opcionalmente ``--with-readme`` cria ``~/README.md`` (``--force-readme`` substitui se existir).
6. **Aplicar permissões** — ``apply_runv_permissions``: home, ``.ssh``, sites públicos e, se existir,
   ``README.md``, antes da **jail** (grupo ``runv-jailed``, Jailkit, bind, fstab), quota e verificação final.
7. **Jail SSH** — por omissão: ``usermod -aG runv-jailed``, ``/srv/jail/<user>``, ``jk_init``
   com perfil ``extendedshell`` (se ``bin/`` ainda não existir), bind de ``/home/<user>`` em
   ``/srv/jail/<user>/home/<user>``, fstab. Exclui ``entre`` e
   ``pmurad-admin``. ``--no-jail`` desliga.

Quota ext4, metadados JSON e logging seguem após estes passos.

É a **fonte principal** da política de provisionamento — sem depender de ``adduser.local``,
``QUOTAUSER`` ou regras espalhadas em ``/etc/adduser.conf``.

Garante na criação as permissões para **todos** os serviços runv expostos ao utilizador:
**HTTP** (``public_html``), **Gopher** (``public_gopher``) e **Gemini** (``public_gemini``) —
home ``755`` (atravessável por Apache, gophernicus e molly-brown), pastas públicas ``755``,
ficheiros servidos ``644``, mais ``.ssh``/``authorized_keys`` e bind mount Gemini quando aplicável.
Contas criadas **só** com ``adduser`` (sem este script) devem passar pelo backfill
``scripts/admin/setup_alt_protocols.py`` ou por nova execução deste script com as flags de reparo
adequadas (``--force-*``).

Não é signup público: executar manualmente como root/sudo no servidor.
Requer Linux (Debian). Quota: ext4 com ``usrquota``/``usrjquota`` via ``setquota`` (não altera fstab).

Versão 0.02 — desenvolvido por pmurad, 2026.
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
import stat as statmod
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final, NoReturn

# Com python3 -P ou PYTHONSAFEPATH=1 o diretório deste script não entra em sys.path;
# necessário para «from runv_mount» dentro das funções de quota/mount.
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import runv_jail

# constantes
USERNAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")

# Email pragmático (não RFC completo)
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

DEFAULT_METADATA_PATH: Final[Path] = Path("/var/lib/runv/users.json")
DEFAULT_LOCK_PATH: Final[Path] = Path("/var/lib/runv/users.lock")
DEFAULT_LOG_PATH: Final[Path] = Path("/var/log/runv-user-provision.log")
DEFAULT_BASE_URL: Final[str] = "http://runv.club"
DEFAULT_GEMINI_HOST_PUBLIC: Final[str] = "runv.club"
GEMINI_USERS_DIR: Final[Path] = Path("/var/gemini/users")

# Quota ext4 (valores padrão runv; limites em MiB = 1024² bytes → setquota usa kiB de 1024 B)
DEFAULT_QUOTA_SOFT_MIB: Final[int] = 450
DEFAULT_QUOTA_HARD_MIB: Final[int] = 500
DEFAULT_QUOTA_INODE_SOFT: Final[int] = 10_000
DEFAULT_QUOTA_INODE_HARD: Final[int] = 12_000

VERSION: Final[str] = "0.02"
AUTHOR: Final[str] = "pmurad"
COPYRIGHT_YEAR: Final[str] = "2026"

EXIT_OK: Final[int] = 0
EXIT_VALIDATION: Final[int] = 1
EXIT_SYSTEM: Final[int] = 2
EXIT_INCONSISTENT: Final[int] = 3


class ProvisionError(Exception):
    """Erro genérico de provisionamento."""


class ValidationError(ProvisionError):
    """Entrada ou estado inválido (exit 1)."""


class SystemProvisionError(ProvisionError):
    """Falha de sistema/subprocess (exit 2)."""


class QuotaNotAvailableError(ValidationError):
    """Sistema de quotas não preparado (ext4 usrquota ausente, ferramentas, etc.)."""


# validação username / email
def validate_username(username: str) -> str:
    """
    Valida username conservador; rejeita vazio, reservados e contas existentes.
    Retorna o username normalizado (sem espaços).
    """
    if username is None or username == "":
        raise ValidationError("username é obrigatório")
    if username != username.strip():
        raise ValidationError("username não pode ter espaços no início ou fim")
    u = username.strip()
    if not USERNAME_PATTERN.fullmatch(u):
        raise ValidationError(
            "username inválido: use apenas letras minúsculas, dígitos, _ e -; "
            "comece com letra; comprimento total 2–32 caracteres"
        )
    if u in RESERVED_USERNAMES:
        raise ValidationError(f"username reservado ou perigoso: {u!r}")
    try:
        pwd.getpwnam(u)
    except KeyError:
        pass
    else:
        raise ValidationError(f"usuário já existe no sistema: {u!r}")
    return u


def validate_email(email: str) -> str:
    if email is None or email == "":
        raise ValidationError("email é obrigatório")
    if email != email.strip():
        raise ValidationError("email não pode ter espaços no início ou fim")
    e = email.strip()
    at = e.count("@")
    if at == 0:
        raise ValidationError(
            "indica um endereço com @, por exemplo nome@exemplo.org."
        )
    if at != 1:
        raise ValidationError("o email deve ter um único @.")
    if not EMAIL_PATTERN.fullmatch(e):
        raise ValidationError("formato de email inválido")
    return e


# chave pública OpenSSH
def normalize_public_key(raw: str) -> str:
    """
    Aceita uma única linha OpenSSH authorized_keys.
    Rejeita newlines internos e normaliza espaços internos de forma segura.
    """
    if raw is None or raw == "":
        raise ValidationError("public_key é obrigatória")
    if "\n" in raw or "\r" in raw:
        raise ValidationError("public_key deve ser uma única linha (sem quebras de linha)")
    if raw != raw.strip():
        raise ValidationError("public_key não pode ter espaços extras no início ou fim")
    line = raw.strip()
    if not line or line.isspace():
        raise ValidationError("public_key vazia")
    parts = line.split()
    if len(parts) < 2:
        raise ValidationError("public_key malformada (esperado: tipo, dados-base64, [comentário])")
    key_type = parts[0]
    if key_type not in ALLOWED_KEY_TYPES:
        raise ValidationError(
            f"tipo de chave não permitido: {key_type!r}; permitidos: {', '.join(ALLOWED_KEY_TYPES)}"
        )
    # Uma linha: tipo + blob base64 + comentário opcional (pode conter espaços)
    blob = parts[1]
    comment = parts[2:] if len(parts) > 2 else []
    if not re.fullmatch(r"[A-Za-z0-9+/]+=*", blob):
        raise ValidationError("dados da chave pública (base64) inválidos")
    normalized = key_type + " " + blob
    if comment:
        normalized += " " + " ".join(comment)
    return normalized


def compute_public_key_fingerprint(public_key_line: str, tmp_dir: Path | None = None) -> str:
    """
    Calcula fingerprint no formato OpenSSH SHA256 (ex.: SHA256:...).
    Usa `ssh-keygen -lf -E sha256` (requer pacote openssh-client no Debian).
    """
    line = normalize_public_key(public_key_line)
    fd, tmppath = tempfile.mkstemp(prefix="runv-key-", suffix=".pub", dir=tmp_dir)
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
            raise ValidationError(f"chave pública rejeitada pelo ssh-keygen: {err}")
        out = (proc.stdout or "").strip().splitlines()
        if not out:
            raise SystemProvisionError("ssh-keygen não devolveu saída")
        first = out[0]
        m = FINGERPRINT_SHA256_RE.search(first)
        if not m:
            raise SystemProvisionError(f"não foi possível extrair SHA256 da saída: {first!r}")
        return m.group(1)
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def validate_public_key(public_key_line: str, tmp_dir: Path | None = None) -> tuple[str, str]:
    """
    Valida e normaliza a chave; retorna (linha_normalizada, fingerprint_sha256).
    """
    normalized = normalize_public_key(public_key_line)
    fp = compute_public_key_fingerprint(normalized, tmp_dir=tmp_dir)
    return normalized, fp


def read_public_key_from_args(pub: str | None, pub_file: Path | None) -> str:
    if pub and pub_file:
        raise ValidationError("use apenas --public-key ou --public-key-file, não ambos")
    if pub:
        return pub
    if pub_file:
        text = pub_file.read_text(encoding="utf-8")
        if len(text.splitlines()) > 1:
            raise ValidationError("arquivo de chave deve conter uma única linha")
        line = text.strip()
        return line
    raise ValidationError("forneça --public-key ou --public-key-file")


# caminhos sob /home (sem sair da árvore)
def home_directory(username: str) -> Path:
    p = Path(f"/home/{username}").resolve()
    home_root = Path("/home").resolve()
    try:
        p.relative_to(home_root)
    except ValueError as e:
        raise ValidationError("caminho home inválido") from e
    if p.name != username:
        raise ValidationError("inconsistência no nome do diretório home")
    return p


# authorized_keys
def install_authorized_keys(
    home: Path,
    uid: int,
    gid: int,
    public_key_line: str,
    log: logging.Logger,
) -> None:
    """Cria ~/.ssh/authorized_keys com permissões corretas."""
    ssh_dir = home / ".ssh"
    auth = ssh_dir / "authorized_keys"
    line = normalize_public_key(public_key_line)

    ssh_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(ssh_dir, 0o700)
    try:
        os.chown(ssh_dir, uid, gid)
    except PermissionError as e:
        raise SystemProvisionError(f"não foi possível ajustar dono de {ssh_dir}: {e}") from e

    if auth.exists():
        existing = auth.read_text(encoding="utf-8")
        if line in existing.splitlines():
            log.info("authorized_keys já continha esta chave; nada a acrescentar")
        else:
            with open(auth, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    else:
        auth.write_text(line + "\n", encoding="utf-8")

    os.chmod(auth, 0o600)
    try:
        os.chown(auth, uid, gid)
    except PermissionError as e:
        raise SystemProvisionError(f"não foi possível ajustar dono de {auth}: {e}") from e


# public_html
def default_index_html(username: str) -> str:
    """HTML estático: boas-vindas inspiradoras, sem caminhos de sistema nem comandos (só marcação)."""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>~{username} — runv.club</title>
  <style>
    :root {{
      --bg: #0e0c12;
      --fg: #e8e4f0;
      --accent: #c4a1ff;
      --muted: #9a90b0;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 2rem;
      font-family: Georgia, "Times New Roman", serif;
      background: radial-gradient(ellipse 120% 80% at 50% 0%, #1a1428 0%, var(--bg) 55%);
      color: var(--fg);
      line-height: 1.65;
    }}
    main {{
      max-width: 36rem;
      text-align: center;
    }}
    h1 {{
      font-weight: 400;
      font-size: clamp(1.75rem, 4vw, 2.25rem);
      letter-spacing: 0.02em;
      margin-bottom: 1.25rem;
      color: var(--accent);
    }}
    p {{
      margin: 0 0 1.15rem;
      font-size: 1.05rem;
    }}
    .lead {{
      font-size: 1.15rem;
      color: #f0ecf8;
    }}
    .soft {{
      color: var(--muted);
      font-size: 0.98rem;
    }}
  </style>
</head>
<body>
  <main>
    <h1>Bem-vindo ao runv.club</h1>
    <p class="lead">Este é o espaço de <strong>~{username}</strong> na nossa pubnix — um canto da rede para publicar ideias, texto e silêncio com intenção.</p>
    <p>A web ainda pode ser leve. Aqui vale experimentar, aprender em público e deixar a página crescer com o tempo, sem pressa de plataforma fechada.</p>
    <p class="soft">Faça deste sítio o que quiser: um blog, um cartão de visitas, um arquivo. O runv.club é o que cada pessoa constrói em conjunto.</p>
  </main>
</body>
</html>
"""


def default_readme_md(username: str, base_url: str) -> str:
    """Texto de ajuda inicial em português (política runv.club)."""
    base = base_url.rstrip("/")
    user_url = f"{base}/~{username}/"
    return f"""# Bem-vindo(a) ao runv.club

O **runv.club** é um servidor partilhado (pubnix): tens acesso por **SSH com chave**
e uma **página web pessoal** servida pelo Apache com `mod_userdir`.

## A tua página pessoal

- Ficheiros públicos ficam em **`~/public_html/`**.
- A página principal é **`~/public_html/index.html`** (HTML estático; sem PHP obrigatório nesta fase).
- A URL pública é:

  **{user_url}**

Edita o HTML com o teu editor na shell (ex.: `nano ~/public_html/index.html`).

## Permissões recomendadas

| Local | Modo | Notas |
|-------|------|--------|
| A tua home (`~`) | `755` | O Apache precisa de atravessar a home para chegar a `public_html`. |
| `~/public_html` | `755` | Diretório listável pelo servidor web. |
| Ficheiros do site | `644` | Ficheiros normais dentro de `public_html`. |
| `~/.ssh` | `700` | Só o teu utilizador deve aceder. |
| `~/.ssh/authorized_keys` | `600` | Chaves SSH autorizadas. |

Se alterares permissões e o site deixar de abrir, volta a `755` na home e em `public_html`,
e `644` nos ficheiros servidos.

## Ficheiros públicos

Tudo o que colocares em **`public_html`** pode ser lido pelo mundo via HTTP no endereço
`~{username}/...`. Não coloques aí segredos, chaves privadas nem dados sensíveis.

## Gopher e Gemini (protocolos alternativos)

- **Gopher:** edita `~/public_gopher/gophermap` (e outros ficheiros nessa pasta). URL típica:
  `gopher://{DEFAULT_GEMINI_HOST_PUBLIC}/1/~{username}` (o caminho exacto depende do servidor).
- **Gemini:** edita `~/public_gemini/index.gmi`. URL canónica: `gemini://{DEFAULT_GEMINI_HOST_PUBLIC}/~{username}/` (path **`/~{username}/`**, tilde colado ao nome); `gemini://{DEFAULT_GEMINI_HOST_PUBLIC}/~/{username}/` redirecciona no servidor (v0.11+). `gemini://{DEFAULT_GEMINI_HOST_PUBLIC}/{username}` **não** é o teu capsule.
- Mantém **755** nas pastas públicas e **644** nos ficheiros, para o servidor conseguir ler.

## Comandos úteis na shell

```bash
pwd                  # diretório atual
ls -la               # listar com detalhes
cd ~/public_html     # ir à pasta do site
mkdir -p ~/public_html/img   # criar subpastas
chmod 755 ~ ~/public_html
chmod 644 ~/public_html/index.html
```

Documentação do projeto (admin): repositório **runv-server**, script `create_runv_user.py`.

— Equipe runv.club
"""


def prepare_public_html(
    home: Path,
    username: str,
    uid: int,
    gid: int,
    force_index: bool,
    log: logging.Logger,
) -> None:
    pub = home / "public_html"
    pub.mkdir(parents=True, exist_ok=True)
    os.chmod(pub, 0o755)
    try:
        os.chown(pub, uid, gid)
    except PermissionError as e:
        raise SystemProvisionError(f"não foi possível ajustar dono de {pub}: {e}") from e

    index = pub / "index.html"
    if index.exists() and not force_index:
        log.info("%s já existe; não sobrescrevendo (use --force-index)", index)
        return
    if index.exists() and force_index:
        log.warning("sobrescrevendo %s (--force-index)", index)
    index.write_text(default_index_html(username), encoding="utf-8")
    os.chmod(index, 0o644)
    try:
        os.chown(index, uid, gid)
    except PermissionError as e:
        raise SystemProvisionError(f"não foi possível ajustar dono de {index}: {e}") from e


def default_gophermap_text(username: str) -> str:
    return f"""iBem-vindo ao runv.club — espaço Gopher de ~{username}.	fake	NULL	0
iGopher é linha a linha, menu e curiosidade: um protocolo simples para quem gosta de ir devagar.	fake	NULL	0
iExplore, publique texto e deixe este buraco crescer ao seu ritmo.	fake	NULL	0
"""


def default_gemini_index_gmi(username: str) -> str:
    return f"""# ~{username} — runv.club

Bem-vindo ao **Gemini**: um espaço em texto puro, sem rastreio nem barulho de anúncios.

Esta cápsula é sua. Pode contar histórias, listar leituras, partilhar notas — tudo em páginas leves que abrem com calma.

O runv.club acredita em protocolos abertos e em quem ainda gosta de ler no próprio ritmo. Boa estadia.
"""


def prepare_public_gopher(
    home: Path,
    username: str,
    uid: int,
    gid: int,
    force_gopher: bool,
    log: logging.Logger,
) -> None:
    d = home / "public_gopher"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o755)
    try:
        os.chown(d, uid, gid)
    except PermissionError as e:
        raise SystemProvisionError(f"não foi possível ajustar dono de {d}: {e}") from e
    gmap = d / "gophermap"
    if gmap.exists() and not force_gopher:
        log.info("%s já existe; não sobrescrevendo (use --force-gopher)", gmap)
        return
    if gmap.exists() and force_gopher:
        log.warning("sobrescrevendo %s (--force-gopher)", gmap)
    gmap.write_text(default_gophermap_text(username), encoding="utf-8")
    os.chmod(gmap, 0o644)
    try:
        os.chown(gmap, uid, gid)
    except PermissionError as e:
        raise SystemProvisionError(f"não foi possível ajustar dono de {gmap}: {e}") from e


def prepare_public_gemini(
    home: Path,
    username: str,
    uid: int,
    gid: int,
    log: logging.Logger,
) -> None:
    d = home / "public_gemini"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o755)
    try:
        os.chown(d, uid, gid)
    except PermissionError as e:
        raise SystemProvisionError(f"não foi possível ajustar dono de {d}: {e}") from e
    idx = d / "index.gmi"
    if idx.exists():
        log.info("%s já existe; modelo não aplicado", idx)
        return
    idx.write_text(default_gemini_index_gmi(username), encoding="utf-8")
    os.chmod(idx, 0o644)
    try:
        os.chown(idx, uid, gid)
    except PermissionError as e:
        raise SystemProvisionError(f"não foi possível ajustar dono de {idx}: {e}") from e


def ensure_gemini_user_symlink(
    username: str,
    home: Path,
    log: logging.Logger,
    *,
    force: bool,
) -> None:
    """
    Garante bind mount /var/gemini/users/<user> <- <home>/public_gemini (Molly Debian;
    symlinks fora do DocBase são rejeitados). Delega em setup_alt_protocols.
    """
    import setup_alt_protocols as alt

    if not GEMINI_USERS_DIR.is_dir():
        log.warning(
            "diretório %s inexistente — bind Gemini não aplicado. "
            "Execute scripts/admin/setup_alt_protocols.py no servidor.",
            GEMINI_USERS_DIR,
        )
        return
    if username in alt.irc_patch_skip_users(log):
        log.info("bind Gemini omitido (IRC_PATCH_SKIP_USERS): %s", username)
        return
    alt.ensure_gemini_bind_mount(
        username,
        home.parent,
        force=force,
        dry_run=False,
        log=log,
    )


def prepare_user_readme(
    home: Path,
    username: str,
    uid: int,
    gid: int,
    base_url: str,
    force_readme: bool,
    log: logging.Logger,
) -> None:
    """Garante ~/README.md com texto de ajuda em português (não sobrescreve sem --force-readme)."""
    readme = home / "README.md"
    if readme.exists() and not force_readme:
        log.info("%s já existe; não sobrescrevendo (use --force-readme)", readme)
        return
    if readme.exists() and force_readme:
        log.warning("sobrescrevendo %s (--force-readme)", readme)
    readme.write_text(default_readme_md(username, base_url), encoding="utf-8")
    os.chmod(readme, 0o644)
    try:
        os.chown(readme, uid, gid)
    except PermissionError as e:
        raise SystemProvisionError(f"não foi possível ajustar dono de {readme}: {e}") from e


# metadados JSON
@dataclass
class UserRecord:
    username: str
    email: str
    public_key_fingerprint: str
    created_at: str
    created_by: str
    home_directory: str
    status: str
    quota_enabled: bool
    quota_soft_mb: int | None
    quota_hard_mb: int | None
    quota_inode_soft: int | None
    quota_inode_hard: int | None
    quota_filesystem: str | None
    quota_mountpoint: str | None
    quota_applied_at: str | None
    quota_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "email": self.email,
            "public_key_fingerprint": self.public_key_fingerprint,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "home_directory": self.home_directory,
            "status": self.status,
            "quota_enabled": self.quota_enabled,
            "quota_soft_mb": self.quota_soft_mb,
            "quota_hard_mb": self.quota_hard_mb,
            "quota_inode_soft": self.quota_inode_soft,
            "quota_inode_hard": self.quota_inode_hard,
            "quota_filesystem": self.quota_filesystem,
            "quota_mountpoint": self.quota_mountpoint,
            "quota_applied_at": self.quota_applied_at,
            "quota_status": self.quota_status,
        }


def append_user_metadata(
    metadata_path: Path,
    lock_path: Path,
    record: UserRecord,
    log: logging.Logger,
) -> None:
    """
    Acrescenta registro a uma lista JSON com lock (flock) e escrita atômica.
    """
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    lock_f = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        data: list[dict[str, Any]]
        if metadata_path.exists():
            raw = metadata_path.read_text(encoding="utf-8").strip()
            if not raw:
                data = []
            else:
                parsed = json.loads(raw)
                if not isinstance(parsed, list):
                    raise SystemProvisionError(f"formato inválido em {metadata_path}: esperado lista JSON")
                data = parsed
        else:
            data = []
        for item in data:
            if isinstance(item, dict) and item.get("username") == record.username:
                raise ValidationError(f"username já registrado em metadados: {record.username!r}")
        data.append(record.to_dict())
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
        log.info("metadados gravados em %s", metadata_path)
    finally:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
        lock_f.close()


# adduser e rollback
def run_adduser(username: str, log: logging.Logger) -> None:
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    env["LC_ALL"] = "C"
    log.info("executando adduser --disabled-password para %r", username)
    try:
        proc = subprocess.run(
            ["adduser", "--disabled-password", "--gecos", "", username],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
    except FileNotFoundError as e:
        raise SystemProvisionError("comando adduser não encontrado (instale o pacote adduser)") from e
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        detail = f": {err}" if err else ""
        log.error("adduser stderr/stdout: %s", err or "(vazio)")
        raise SystemProvisionError(f"adduser falhou (código {proc.returncode}){detail}")


def run_deluser_remove_home(username: str, log: logging.Logger) -> bool:
    """Remove usuário e home. Retorna True se sucesso."""
    log.warning("rollback: removendo usuário %r com deluser --remove-home", username)
    try:
        r = subprocess.run(
            ["deluser", "--remove-home", username],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            log.error("deluser stderr: %s", r.stderr)
            return False
        return True
    except FileNotFoundError:
        log.error("deluser não encontrado")
        return False


def apply_runv_permissions(home: Path, uid: int, gid: int) -> None:
    """
    Aplica modos e donos esperados na home e nos artefactos runv.

    Deve ser chamado após criar o utilizador, chave SSH, ``public_html`` e opcionalmente ``README.md``,
    para garantir home ``755`` (Apache, Gophernicus e Molly-Brown atravessam até
    ``public_html`` / ``public_gopher`` / ``public_gemini``), ``.ssh`` ``700``,
    ``authorized_keys`` ``600``, site ``755``/``644``.
    """
    try:
        os.chmod(home, 0o755)
        os.chown(home, uid, gid)
    except PermissionError as e:
        raise SystemProvisionError(f"não foi possível ajustar permissões de {home}: {e}") from e

    ssh_dir = home / ".ssh"
    if ssh_dir.is_dir():
        try:
            os.chmod(ssh_dir, 0o700)
            os.chown(ssh_dir, uid, gid)
        except PermissionError as e:
            raise SystemProvisionError(f"não foi possível ajustar permissões de {ssh_dir}: {e}") from e
        auth = ssh_dir / "authorized_keys"
        if auth.is_file():
            try:
                os.chmod(auth, 0o600)
                os.chown(auth, uid, gid)
            except PermissionError as e:
                raise SystemProvisionError(f"não foi possível ajustar permissões de {auth}: {e}") from e

    pub = home / "public_html"
    if pub.is_dir():
        try:
            os.chmod(pub, 0o755)
            os.chown(pub, uid, gid)
        except PermissionError as e:
            raise SystemProvisionError(f"não foi possível ajustar permissões de {pub}: {e}") from e
        index = pub / "index.html"
        if index.is_file():
            try:
                os.chmod(index, 0o644)
                os.chown(index, uid, gid)
            except PermissionError as e:
                raise SystemProvisionError(f"não foi possível ajustar permissões de {index}: {e}") from e

    readme = home / "README.md"
    if readme.is_file():
        try:
            os.chmod(readme, 0o644)
            os.chown(readme, uid, gid)
        except PermissionError as e:
            raise SystemProvisionError(f"não foi possível ajustar permissões de {readme}: {e}") from e

    for label, path in (
        ("public_gopher", home / "public_gopher"),
        ("public_gemini", home / "public_gemini"),
    ):
        if path.is_dir():
            try:
                os.chmod(path, 0o755)
                os.chown(path, uid, gid)
            except PermissionError as e:
                raise SystemProvisionError(f"não foi possível ajustar permissões de {path}: {e}") from e
    gmap = home / "public_gopher" / "gophermap"
    if gmap.is_file():
        try:
            os.chmod(gmap, 0o644)
            os.chown(gmap, uid, gid)
        except PermissionError as e:
            raise SystemProvisionError(f"não foi possível ajustar permissões de {gmap}: {e}") from e
    gmi = home / "public_gemini" / "index.gmi"
    if gmi.is_file():
        try:
            os.chmod(gmi, 0o644)
            os.chown(gmi, uid, gid)
        except PermissionError as e:
            raise SystemProvisionError(f"não foi possível ajustar permissões de {gmi}: {e}") from e


def verify_user_artifact_permissions(
    home: Path,
    uid: int,
    gid: int,
    *,
    expect_readme: bool,
) -> None:
    checks: list[tuple[Path, int, str]] = [
        (home, 0o755, "home"),
        (home / ".ssh", 0o700, ".ssh"),
        (home / ".ssh" / "authorized_keys", 0o600, "authorized_keys"),
        (home / "public_html", 0o755, "public_html"),
        (home / "public_html" / "index.html", 0o644, "index.html"),
        (home / "public_gopher", 0o755, "public_gopher"),
        (home / "public_gopher" / "gophermap", 0o644, "gophermap"),
        (home / "public_gemini", 0o755, "public_gemini"),
        (home / "public_gemini" / "index.gmi", 0o644, "index.gmi"),
    ]
    if expect_readme:
        checks.append((home / "README.md", 0o644, "README.md"))
    for path, want_mode, label in checks:
        if not path.exists():
            raise SystemProvisionError(f"em falta após provisionamento ({label}): {path}")
        st = path.stat()
        if st.st_uid != uid or st.st_gid != gid:
            raise SystemProvisionError(
                f"donos incorretos em {path} ({label}): esperado uid/gid {uid}/{gid}, "
                f"obtido {st.st_uid}/{st.st_gid}"
            )
        got = statmod.S_IMODE(st.st_mode)
        if got != want_mode:
            raise SystemProvisionError(
                f"permissões incorretas em {path} ({label}): {oct(got)} (esperado {oct(want_mode)})"
            )


# quota ext4 (setquota / usrquota)
def quota_probe_path(home: Path) -> Path:
    """
    Caminho existente no disco para descobrir o mount (antes de adduser, /home/user pode não existir).
    Sobe até encontrar um diretório existente (tipicamente /home ou /).
    """
    p = home
    while True:
        try:
            if p.exists():
                return p.resolve()
        except OSError:
            pass
        if p == p.parent:
            return Path("/").resolve()
        p = p.parent


def mib_to_setquota_kib(mib: int) -> int:
    """
    Converte **MiB** (mebibytes = 1024² bytes) para as unidades de **blocos** do setquota
    em filesystems ext4 (vfsv0): cada unidade conta **1024 bytes** (1 KiB).

    Ex.: 450 MiB → 450 × 1024 = 460_800 (KiB de espaço contabilizado pelo quota).
    """
    if mib < 0:
        raise ValidationError("quota em MiB não pode ser negativa")
    return mib * 1024


def validate_quota_limits(
    soft_mib: int,
    hard_mib: int,
    inode_soft: int,
    inode_hard: int,
) -> None:
    if soft_mib > hard_mib:
        raise ValidationError(
            f"quota blocos: soft ({soft_mib} MiB) não pode exceder hard ({hard_mib} MiB)"
        )
    if inode_soft > inode_hard:
        raise ValidationError(
            f"quota inodes: soft ({inode_soft}) não pode exceder hard ({inode_hard})"
        )


def find_mount_for_path(path: Path) -> tuple[str, str, str]:
    """
    Retorna (target_canonical, fstype, options_csv) para o filesystem que contém path.
    Implementação partilhada: ``runv_mount.find_mount_triple``.
    """
    from runv_mount import MountLookupError, find_mount_triple

    try:
        return find_mount_triple(path)
    except MountLookupError as e:
        raise SystemProvisionError(str(e)) from e


def mount_options_allow_user_quota(options: str) -> bool:
    """True se usrquota ou usrjquota= (ext4 com quota em journal) está ativo."""
    from runv_mount import quota_opts_allow_user

    return quota_opts_allow_user(options)


def ensure_setquota_available() -> str:
    """Caminho do executável setquota ou levanta SystemProvisionError."""
    p = shutil.which("setquota")
    if not p:
        raise QuotaNotAvailableError(
            "comando 'setquota' não encontrado — instale o pacote Debian 'quota' "
            "(ex.: apt install quota)"
        )
    return p


def preflight_quota_for_home(
    home: Path,
    log: logging.Logger,
) -> tuple[str, str, str]:
    """
    Verifica ext4 + usrquota no mount da home (ou ascendente).
    Retorna (mountpoint, fstype, options).
    """
    log.info("quota: início da verificação (pré-voo)")
    probe = quota_probe_path(home)
    log.info("quota: path de sonda para findmnt: %s", probe)
    target, fstype, opts = find_mount_for_path(probe)
    log.info("quota: mountpoint=%s fstype=%s options=%s", target, fstype, opts)
    if fstype != "ext4":
        raise QuotaNotAvailableError(
            f"quota runv: só ext4 com quota tradicional é suportado neste script; "
            f"encontrado fstype={fstype!r} em {target!r}"
        )
    if not mount_options_allow_user_quota(opts):
        raise QuotaNotAvailableError(
            f"quota de utilizador não está ativa no mount {target!r}: "
            f"opções atuais não incluem usrquota nem usrjquota=. "
            f"Ajuste /etc/fstab (usrquota), remonte, quotacheck e quotaon — "
            f"o script não altera fstab nem montagens."
        )
    ensure_setquota_available()
    log.info("quota: pré-voo OK (ext4 + usrquota/usrjquota + setquota)")
    return target, fstype, opts


def run_setquota_user(
    username: str,
    mountpoint: str,
    block_soft_kib: int,
    block_hard_kib: int,
    inode_soft: int,
    inode_hard: int,
    log: logging.Logger,
) -> None:
    """Aplica limites com setquota -u (lista de argumentos, sem shell)."""
    cmd = [
        "setquota",
        "-u",
        username,
        str(block_soft_kib),
        str(block_hard_kib),
        str(inode_soft),
        str(inode_hard),
        mountpoint,
    ]
    log.info("quota: executando %s", " ".join(cmd))
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as e:
        raise SystemProvisionError("setquota desapareceu do PATH durante a execução") from e

    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise SystemProvisionError(
            f"setquota falhou (código {r.returncode})" + (f": {err}" if err else "")
        )
    log.info("quota: setquota concluído com sucesso para %r em %r", username, mountpoint)


@dataclass
class QuotaResult:
    """Estado da etapa de quota para metadados e saída."""

    enabled: bool
    soft_mib: int | None
    hard_mib: int | None
    inode_soft: int | None
    inode_hard: int | None
    filesystem: str | None
    mountpoint: str | None
    applied_at: str | None
    status: str  # skipped | applied | failed | not_configured


def try_apply_quota(
    username: str,
    home: Path,
    soft_mib: int,
    hard_mib: int,
    inode_soft: int,
    inode_hard: int,
    log: logging.Logger,
) -> QuotaResult:
    """
    Tenta aplicar quota após o utilizador existir. Não remove o utilizador em caso de falha.
    """
    try:
        target, fstype, _opts = preflight_quota_for_home(home, log)
    except QuotaNotAvailableError as e:
        log.error("quota indisponível: %s", e)
        return QuotaResult(
            enabled=True,
            soft_mib=soft_mib,
            hard_mib=hard_mib,
            inode_soft=inode_soft,
            inode_hard=inode_hard,
            filesystem=None,
            mountpoint=None,
            applied_at=None,
            status="not_configured",
        )

    try:
        bs = mib_to_setquota_kib(soft_mib)
        bh = mib_to_setquota_kib(hard_mib)
        run_setquota_user(username, target, bs, bh, inode_soft, inode_hard, log)
    except (SystemProvisionError, ValidationError) as e:
        log.error("quota falhou ao aplicar: %s", e)
        return QuotaResult(
            enabled=True,
            soft_mib=soft_mib,
            hard_mib=hard_mib,
            inode_soft=inode_soft,
            inode_hard=inode_hard,
            filesystem=fstype,
            mountpoint=target,
            applied_at=None,
            status="failed",
        )

    now = datetime.now(timezone.utc).isoformat()
    return QuotaResult(
        enabled=True,
        soft_mib=soft_mib,
        hard_mib=hard_mib,
        inode_soft=inode_soft,
        inode_hard=inode_hard,
        filesystem=fstype,
        mountpoint=target,
        applied_at=now,
        status="applied",
    )


# CLI
def try_refresh_landing_members_json(
    *,
    document_root: Path,
    users_json: Path,
    homes_root: Path | None,
    log: logging.Logger,
) -> tuple[bool, int | None]:
    """
    Regenera public/data/members.json no DocumentRoot da landing (build_directory.py).
    Falhas são apenas registadas — não aborta o provisionamento.
    Devolve (sucesso, número de membros no JSON público ou None se não foi possível contar).
    """
    script = _REPO_ROOT / "site" / "build_directory.py"
    if not script.is_file():
        log.warning(
            "build_directory.py não encontrado em %s; members.json da landing não atualizado",
            script,
        )
        return False, None
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
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        err_tail = (r.stderr or r.stdout or "").strip()
        if r.returncode != 0:
            log.warning(
                "build_directory terminou com código %s: %s",
                r.returncode,
                err_tail[:2000] if err_tail else "(sem saída)",
            )
            return False, None
        log.info("members.json da landing actualizado em %s", out)
        if r.stderr and r.stderr.strip():
            log.debug("build_directory stderr: %s", r.stderr.strip()[:1500])
        n_public: int | None = None
        try:
            raw = out.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                n_public = len(parsed)
                log.info("constelação: %s membro(s) no dataset público (%s)", n_public, out)
        except (OSError, json.JSONDecodeError, TypeError) as ex:
            log.warning("members.json escrito mas não foi possível validar a lista: %s", ex)
        return True, n_public
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("falha ao executar build_directory: %s", e)
        return False, None


def print_banner() -> None:
    print()
    print("  create_runv_user — provisionamento runv.club")
    print(f"  versão {VERSION}")
    print(f"  desenvolvido por {AUTHOR} — {COPYRIGHT_YEAR}")
    print()


def prompt_yes_no(pergunta: str, default_no: bool = True) -> bool:
    suf = " [s/N]: " if default_no else " [S/n]: "
    r = input(pergunta + suf).strip().lower()
    if not r:
        return not default_no
    return r in ("s", "sim", "y", "yes")


def interactive_fill(args: argparse.Namespace) -> None:
    """Preenche args a partir de perguntas no terminal."""
    print_banner()
    print("Modo interativo — responda às perguntas (Ctrl+C para cancelar).\n")

    while True:
        u = input("Nome de usuário Unix (minúsculas, ex.: maria): ").strip()
        if u:
            args.username = u
            break
        print("  (obrigatório)")

    while True:
        e = input("Email administrativo (metadado, ex.: maria@example.com): ").strip()
        if e:
            args.email = e
            break
        print("  (obrigatório)")

    print()
    print("Chave pública SSH (OpenSSH, uma linha).")
    modo = input("  (1) colar a linha agora  (2) ler de arquivo .pub [1]: ").strip() or "1"
    if modo == "2":
        while True:
            caminho = input("  Caminho absoluto do arquivo .pub: ").strip()
            if not caminho:
                print("  (obrigatório)")
                continue
            p = Path(caminho).expanduser()
            if not p.is_file():
                print(f"  Arquivo não encontrado: {p}")
                continue
            args.public_key = None
            args.public_key_file = p
            break
    else:
        while True:
            print("  Cole a linha completa (ssh-ed25519 AAAA... ou ssh-rsa ...):")
            linha = input("  > ").strip()
            if linha:
                args.public_key = linha
                args.public_key_file = None
                break
            print("  (obrigatório)")

    print()
    args.dry_run = prompt_yes_no("Apenas validar (dry-run), sem criar usuário?", default_no=True)
    if not args.dry_run:
        args.force_index = prompt_yes_no(
            "Se já existir ~/public_html/index.html, sobrescrever (--force-index)?",
            default_no=True,
        )
        args.force_gopher = prompt_yes_no(
            "Se já existir ~/public_gopher/gophermap, sobrescrever (--force-gopher)?",
            default_no=True,
        )
        args.force_gemini = prompt_yes_no(
            "Forçar correção do bind mount Gemini (/var/gemini/users) se estiver errado ou em conflito (--force-gemini)?",
            default_no=True,
        )
        args.with_readme = prompt_yes_no(
            "Criar ~/README.md com texto runv (--with-readme)?",
            default_no=True,
        )
        if args.with_readme:
            args.force_readme = prompt_yes_no(
                "Se já existir ~/README.md, sobrescrever (--force-readme)?",
                default_no=True,
            )
        else:
            args.force_readme = False
        args.no_jail = prompt_yes_no(
            "Omitir jail SSH (runv-jailed /srv/jail) (--no-jail)?",
            default_no=True,
        )
    else:
        args.force_index = False
        args.force_gopher = False
        args.force_gemini = False
        args.force_readme = False

    args.verbose = prompt_yes_no("Log verboso no terminal?", default_no=True)

    if not args.dry_run:
        if prompt_yes_no("Criar utilizador sem quota de disco (--no-quota)?", default_no=True):
            args.no_quota = True
        if not args.no_quota:
            if prompt_yes_no(
                "Abortar se quota ext4 não estiver pronta antes de criar (--require-quota)?",
                default_no=True,
            ):
                args.require_quota = True

    print()
    conf = input("Confirmar e continuar? [S/n]: ").strip().lower()
    if conf in ("n", "nao", "não", "no"):
        print("Cancelado.")
        raise SystemExit(EXIT_VALIDATION)


def setup_logging(log_path: Path, verbose: bool) -> logging.Logger:
    logger = logging.getLogger("runv")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError as e:
        print(f"Aviso: não foi possível gravar log em {log_path}: {e}", file=sys.stderr)
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.DEBUG if verbose else logging.WARNING)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def _resolve_email_package_root(state: dict[str, Any] | None) -> Path | None:
    """Pasta ``email/`` do repositório para importar ``lib.mailer``."""
    env = os.environ.get("RUNV_EMAIL_ROOT", "").strip()
    if env:
        p = Path(env)
        return p if p.is_dir() else None
    if state:
        er = str(state.get("email_package_root", "")).strip()
        if er:
            p = Path(er)
            if p.is_dir():
                return p
    cand = _REPO_ROOT / "email"
    return cand if cand.is_dir() else None


def try_send_welcome_email(
    *,
    username: str,
    user_email: str,
    fingerprint: str,
    base_url: str,
    welcome_ssh_host: str | None,
    no_welcome_email: bool,
    dry_run: bool,
    log: logging.Logger,
) -> None:
    """
    Envia ``user_account_created`` ao email do utilizador se existir configuração global
    (``/etc/runv-email.json``) e módulo ``email/`` acessível. Falhas são só registadas
    em log — a conta já foi criada.
    """
    if no_welcome_email:
        log.info("email de boas-vindas: omitido (--no-welcome-email)")
        return
    if dry_run:
        log.info("email de boas-vindas: omitido (--dry-run)")
        return

    state_file = Path("/etc/runv-email.json")
    if not state_file.is_file():
        log.info(
            "email de boas-vindas: %s ausente — defina email ou use --no-welcome-email",
            state_file,
        )
        return
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("email de boas-vindas: estado inválido (%s): %s", state_file, e)
        return

    email_root = _resolve_email_package_root(state)
    if email_root is None:
        log.warning(
            "email de boas-vindas: pasta email/ não encontrada "
            "(RUNV_EMAIL_ROOT, email_package_root no JSON ou repositório em %s)",
            _REPO_ROOT / "email",
        )
        return

    root_s = str(email_root.resolve())
    if root_s not in sys.path:
        sys.path.insert(0, root_s)

    try:
        from lib.mailer import send_user_notice
        from lib.templates import USER_ACCOUNT_CREATED
    except ImportError as e:
        log.warning("email de boas-vindas: import lib.mailer falhou: %s", e)
        return

    from_addr = str(state.get("default_from", "")).strip()
    if not from_addr:
        log.warning("email de boas-vindas: default_from ausente em %s", state_file)
        return

    member_url = f"{base_url.rstrip('/')}/~{username}/"
    host = (welcome_ssh_host or "").strip()
    if host:
        ssh_instructions = (
            f"Comando sugerido: ssh {username}@{host}\n"
            "Confirme no cliente SSH que está a usar a chave privada correta "
            "(a que corresponde à impressão digital acima)."
        )
    else:
        ssh_instructions = (
            f"Comando típico: ssh {username}@<hostname>\n"
            "Substitua <hostname> pelo endereço do servidor que o administrador lhe indicar. "
            "No cliente SSH, seleccione a **chave privada** que corresponde à chave pública registada."
        )

    try:
        send_user_notice(
            USER_ACCOUNT_CREATED,
            user_email,
            subject="[runv.club] Bem-vindo(a) — a sua conta foi criada",
            from_addr=from_addr,
            _state=state,
            username=username,
            email=user_email,
            fingerprint=fingerprint,
            member_url=member_url,
            ssh_instructions=ssh_instructions,
        )
        log.info("email de boas-vindas enviado para %s", user_email)
        print(f"  boas-vindas:        email enviado para {user_email}")
    except Exception as e:
        log.warning("email de boas-vindas falhou (conta já criada): %s", e)


def try_send_admin_user_created_email(
    *,
    username: str,
    user_email: str,
    operator_info: str,
    timestamp: str,
    no_admin_create_email: bool,
    dry_run: bool,
    log: logging.Logger,
) -> None:
    """
    Envia ``admin_user_created`` para ``admin_email`` em ``/etc/runv-email.json``.
    Falhas só em log — a conta já foi criada.
    """
    if no_admin_create_email:
        log.info("email admin (conta criada): omitido (--no-admin-create-email)")
        return
    if dry_run:
        log.info("email admin (conta criada): omitido (--dry-run)")
        return

    state_file = Path("/etc/runv-email.json")
    if not state_file.is_file():
        log.info(
            "email admin (conta criada): %s ausente — omitido",
            state_file,
        )
        return
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("email admin (conta criada): estado inválido (%s): %s", state_file, e)
        return

    admin = str(state.get("admin_email", "")).strip()
    if not admin:
        log.info(
            "email admin (conta criada): admin_email vazio em %s — omitido",
            state_file,
        )
        return

    email_root = _resolve_email_package_root(state)
    if email_root is None:
        log.warning(
            "email admin (conta criada): pasta email/ não encontrada "
            "(RUNV_EMAIL_ROOT, email_package_root no JSON ou repositório em %s)",
            _REPO_ROOT / "email",
        )
        return

    root_s = str(email_root.resolve())
    if root_s not in sys.path:
        sys.path.insert(0, root_s)

    try:
        from lib.mailer import send_admin_notice
        from lib.templates import ADMIN_USER_CREATED
    except ImportError as e:
        log.warning("email admin (conta criada): import lib.mailer falhou: %s", e)
        return

    from_addr = str(state.get("default_from", "")).strip()
    if not from_addr:
        log.warning("email admin (conta criada): default_from ausente em %s", state_file)
        return

    try:
        send_admin_notice(
            ADMIN_USER_CREATED,
            admin,
            subject=f"[runv.club] Conta criada — {username}",
            from_addr=from_addr,
            _state=state,
            username=username,
            email=user_email,
            operator_info=operator_info,
            timestamp=timestamp,
        )
        log.info("email admin (conta criada) enviado para %s", admin)
        print(f"  admin (conta):     email enviado para {admin}")
    except Exception as e:
        log.warning("email admin (conta criada) falhou (conta já criada): %s", e)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Provisiona conta Unix interna (runv.club). Executar como root no servidor. "
            "Aplica permissões completas para HTTP, Gopher e Gemini (home e public_*); "
            "contas só adduser precisam de setup_alt_protocols ou reparo aqui. "
            f"Versão {VERSION} — {AUTHOR} {COPYRIGHT_YEAR}."
        ),
    )
    p.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="modo interativo (perguntas no terminal); também é o padrão se não passar nenhum argumento",
    )
    p.add_argument("--username", default=None, help="nome de usuário Unix (minúsculas)")
    p.add_argument("--email", default=None, help="email administrativo (metadado)")
    g = p.add_mutually_exclusive_group(required=False)
    g.add_argument("--public-key", dest="public_key", default=None, help="linha authorized_keys (OpenSSH)")
    g.add_argument(
        "--public-key-file",
        type=Path,
        dest="public_key_file",
        default=None,
        help="arquivo com uma linha .pub",
    )
    p.add_argument("--dry-run", action="store_true", help="valida e mostra o plano sem alterar o sistema")
    p.add_argument("--verbose", action="store_true", help="log detalhado no stderr")
    p.add_argument(
        "--force-index",
        action="store_true",
        help="sobrescrever ~/public_html/index.html se já existir",
    )
    p.add_argument(
        "--with-readme",
        action="store_true",
        help="criar ~/README.md com texto runv (por omissão não cria)",
    )
    p.add_argument(
        "--force-readme",
        action="store_true",
        help="com --with-readme: sobrescrever ~/README.md se já existir",
    )
    p.add_argument(
        "--no-jail",
        action="store_true",
        help="não adicionar a runv-jailed nem criar jail em /srv/jail",
    )
    p.add_argument(
        "--force-gopher",
        action="store_true",
        help="sobrescrever ~/public_gopher/gophermap se já existir",
    )
    p.add_argument(
        "--force-gemini",
        action="store_true",
        help="corrigir bind mount em /var/gemini/users (migra symlink; remount se necessário); não sobrescreve index.gmi existente",
    )
    p.add_argument(
        "--metadata-file",
        type=Path,
        default=DEFAULT_METADATA_PATH,
        help=f"caminho do JSON de metadados (padrão: {DEFAULT_METADATA_PATH})",
    )
    p.add_argument(
        "--lock-file",
        type=Path,
        default=DEFAULT_LOCK_PATH,
        help=f"arquivo de lock flock (padrão: {DEFAULT_LOCK_PATH})",
    )
    p.add_argument(
        "--log-file",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help=f"log local (padrão: {DEFAULT_LOG_PATH})",
    )
    p.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"URL base para o resumo (padrão: {DEFAULT_BASE_URL})",
    )
    p.add_argument(
        "--landing-document-root",
        type=Path,
        default=Path("/var/www/runv.club/html"),
        help=(
            "DocumentRoot da landing Apache (directório existente para actualizar a constelação); "
            "após criar o utilizador, executa site/build_directory.py para gravar data/members.json. "
            "Se não existir, o refresh é omitido e é impresso um AVISO com o comando sugerido."
        ),
    )
    p.add_argument(
        "--no-refresh-landing-members",
        action="store_true",
        help="não regenerar data/members.json na landing após gravar metadados",
    )
    p.add_argument(
        "--members-homes-root",
        type=Path,
        default=None,
        help="se definido (ex. /home), passa --homes-root a build_directory.py (homepage_mtime)",
    )
    p.add_argument(
        "--no-quota",
        action="store_true",
        help="não aplica quota de disco (ignora setquota)",
    )
    p.add_argument(
        "--require-quota",
        action="store_true",
        help=(
            "exige sistema de quotas pronto (ext4 + usrquota + setquota) antes de criar o utilizador; "
            "aborta sem adduser se não estiver configurado"
        ),
    )
    p.add_argument(
        "--quota-soft-mb",
        type=int,
        default=DEFAULT_QUOTA_SOFT_MIB,
        metavar="MiB",
        help=f"limite soft de blocos em MiB (1024² B); padrão {DEFAULT_QUOTA_SOFT_MIB}",
    )
    p.add_argument(
        "--quota-hard-mb",
        type=int,
        default=DEFAULT_QUOTA_HARD_MIB,
        metavar="MiB",
        help=f"limite hard de blocos em MiB; padrão {DEFAULT_QUOTA_HARD_MIB}",
    )
    p.add_argument(
        "--quota-inode-soft",
        type=int,
        default=DEFAULT_QUOTA_INODE_SOFT,
        metavar="N",
        help=f"limite soft de inodes; padrão {DEFAULT_QUOTA_INODE_SOFT}",
    )
    p.add_argument(
        "--quota-inode-hard",
        type=int,
        default=DEFAULT_QUOTA_INODE_HARD,
        metavar="N",
        help=f"limite hard de inodes; padrão {DEFAULT_QUOTA_INODE_HARD}",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION} — desenvolvido por {AUTHOR}, {COPYRIGHT_YEAR}",
    )
    p.add_argument(
        "--no-welcome-email",
        action="store_true",
        help="não enviar email de boas-vindas ao utilizador após criar a conta",
    )
    p.add_argument(
        "--no-admin-create-email",
        action="store_true",
        help="não enviar email ao admin (template admin_user_created) após criar a conta",
    )
    p.add_argument(
        "--welcome-ssh-host",
        default=None,
        metavar="HOST",
        help=(
            "hostname SSH para incluir no email de boas-vindas (ex.: runv.club); "
            "alternativa: variável de ambiente RUNV_WELCOME_SSH_HOST"
        ),
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        argv = ["--interactive"]

    args = parse_args(argv)
    if args.interactive:
        try:
            interactive_fill(args)
        except KeyboardInterrupt:
            print("\nInterrompido (Ctrl+C).", file=sys.stderr)
            return EXIT_VALIDATION
        except SystemExit as e:
            code = e.code
            if code is None:
                return EXIT_VALIDATION
            if isinstance(code, int):
                return code
            return EXIT_VALIDATION

    if not args.username or not args.email:
        print(
            "Erro: informe --username e --email, ou use --interactive / execute sem argumentos.",
            file=sys.stderr,
        )
        return EXIT_VALIDATION
    if not args.public_key and not args.public_key_file:
        print(
            "Erro: informe --public-key ou --public-key-file, ou use modo interativo.",
            file=sys.stderr,
        )
        return EXIT_VALIDATION

    log = setup_logging(args.log_file, args.verbose)
    log.info(
        "=== início operação create_runv_user (versão %s) dry_run=%s interactive=%s",
        VERSION,
        args.dry_run,
        args.interactive,
    )

    if os.geteuid() != 0 and not args.dry_run:
        print("Erro: execute como root (ou sudo) para criar usuários.", file=sys.stderr)
        log.error("recusado: euid != 0 e não é dry-run")
        return EXIT_SYSTEM

    try:
        log.info("=== fase: validação de entrada (username, email, chave SSH)")
        raw_key = read_public_key_from_args(args.public_key, args.public_key_file)
        user = validate_username(args.username)
        email = validate_email(args.email)
        normalized_key, fingerprint = validate_public_key(raw_key)
        log.info(
            "=== validação OK: user=%s email=%s fingerprint=%s",
            user,
            email,
            fingerprint,
        )
    except ValidationError as e:
        log.error("validação falhou: %s", e)
        print(f"Validação: {e}", file=sys.stderr)
        return EXIT_VALIDATION

    home = home_directory(user)

    if args.no_quota and args.require_quota:
        print(
            "Erro: --no-quota e --require-quota não podem ser usados em conjunto.",
            file=sys.stderr,
        )
        return EXIT_VALIDATION

    if not args.no_quota:
        try:
            validate_quota_limits(
                args.quota_soft_mb,
                args.quota_hard_mb,
                args.quota_inode_soft,
                args.quota_inode_hard,
            )
        except ValidationError as e:
            print(f"Validação: {e}", file=sys.stderr)
            return EXIT_VALIDATION

    if args.dry_run:
        print("[dry-run] Nenhuma alteração será feita.")
        print(f"  username:     {user}")
        print(f"  email:        {email}")
        print(f"  home:         {home}")
        print(f"  fingerprint:  {fingerprint}")
        print(
            "  ações: (1) adduser + skel  (2) authorized_keys  (3) public_html  "
            "(4) public_gopher + public_gemini + bind Gemini  (5) README só com --with-readme  "
            "(6) permissões  (7) jail runv-jailed salvo --no-jail  "
            "(8) quota  (9) verificação + metadados JSON"
        )
        print(f"  with-readme: {getattr(args, 'with_readme', False)}  no-jail: {getattr(args, 'no_jail', False)}")
        if args.no_quota:
            print("  quota:        desativada (--no-quota)")
        else:
            print(
                f"  quota:        MiB soft/hard {args.quota_soft_mb}/{args.quota_hard_mb}; "
                f"inodes {args.quota_inode_soft}/{args.quota_inode_hard}"
            )
            print(
                "  quota:        tentará setquota após criar utilizador (ext4 + usrquota/usrjquota + pacote quota)"
            )
        if args.require_quota and not args.no_quota:
            print(
                "  quota:        --require-quota — aborta antes de adduser se o sistema de quotas não estiver pronto"
            )
        return EXIT_OK

    created_user = False
    try:
        if args.require_quota and not args.no_quota:
            log.info("=== fase: pré-voo de quota (require-quota)")
            preflight_quota_for_home(home, log)

        log.info("=== fase 1: criação de conta Unix (adduser; /etc/skel copiado pelo Debian)")
        run_adduser(user, log)
        created_user = True
        pw = pwd.getpwnam(user)
        uid, gid = pw.pw_uid, pw.pw_gid
        log.info("=== adduser concluído: uid=%s gid=%s home=%s", uid, gid, home)

        log.info("=== fase 2: SSH authorized_keys (~/.ssh 700, arquivo 600)")
        install_authorized_keys(home, uid, gid, normalized_key, log)

        log.info("=== fase 3: public_html e index.html estático")
        prepare_public_html(home, user, uid, gid, args.force_index, log)

        log.info("=== fase 3b: public_gopher (gophermap) e public_gemini (index.gmi)")
        prepare_public_gopher(home, user, uid, gid, args.force_gopher, log)
        prepare_public_gemini(home, user, uid, gid, log)
        ensure_gemini_user_symlink(user, home, log, force=args.force_gemini)

        if args.with_readme:
            log.info("=== fase 4: README.md runv (--with-readme)")
            prepare_user_readme(home, user, uid, gid, args.base_url, args.force_readme, log)
        else:
            log.info("=== fase 4: README.md omitido (use --with-readme para criar)")

        log.info("=== fase 5: permissões consolidadas (home, .ssh, sites públicos, README se existir)")
        apply_runv_permissions(home, uid, gid)

        log.info("=== fase 6: jail SSH (runv-jailed) salvo --no-jail")
        try:
            runv_jail.ensure_runv_jail_for_user(
                user,
                home,
                no_jail=bool(args.no_jail),
                log=log,
            )
        except RuntimeError as e:
            raise SystemProvisionError(str(e)) from e

        log.info("=== fase: quota (setquota em ext4 com usrquota)")
        if args.no_quota:
            qr = QuotaResult(
                enabled=False,
                soft_mib=None,
                hard_mib=None,
                inode_soft=None,
                inode_hard=None,
                filesystem=None,
                mountpoint=None,
                applied_at=None,
                status="skipped",
            )
            log.info("quota: ignorada (--no-quota)")
        else:
            qr = try_apply_quota(
                user,
                home,
                args.quota_soft_mb,
                args.quota_hard_mb,
                args.quota_inode_soft,
                args.quota_inode_hard,
                log,
            )
            log.info(
                "quota: estado final status=%s mount=%s fs=%s",
                qr.status,
                qr.mountpoint,
                qr.filesystem,
            )

        overall_status = "active"
        if not args.no_quota and qr.status in ("failed", "not_configured"):
            overall_status = "partial_quota"

        log.info("=== fase: verificação final de permissões e artefactos")
        verify_user_artifact_permissions(
            home,
            uid,
            gid,
            expect_readme=bool(args.with_readme),
        )

        record = UserRecord(
            username=user,
            email=email,
            public_key_fingerprint=fingerprint,
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by=os.environ.get("SUDO_USER") or getpass.getuser(),
            home_directory=str(home),
            status=overall_status,
            quota_enabled=qr.enabled,
            quota_soft_mb=qr.soft_mib,
            quota_hard_mb=qr.hard_mib,
            quota_inode_soft=qr.inode_soft,
            quota_inode_hard=qr.inode_hard,
            quota_filesystem=qr.filesystem,
            quota_mountpoint=qr.mountpoint,
            quota_applied_at=qr.applied_at,
            quota_status=qr.status,
        )
        log.info("=== fase: gravação de metadados JSON (%s)", args.metadata_file)
        append_user_metadata(args.metadata_file, args.lock_file, record, log)

        members_refreshed = False
        members_public_count: int | None = None
        if not args.no_refresh_landing_members and args.landing_document_root:
            root = args.landing_document_root.resolve()
            if root.is_dir():
                log.info("=== fase: actualizar members.json da landing (%s)", root)
                members_refreshed, members_public_count = try_refresh_landing_members_json(
                    document_root=root,
                    users_json=args.metadata_file,
                    homes_root=args.members_homes_root.resolve()
                    if args.members_homes_root
                    else None,
                    log=log,
                )
            else:
                log.warning(
                    "DocumentRoot da landing inexistente (%s); constelação/bolhas não actualizadas "
                    "(corra site/genlanding.py antes ou aponte --landing-document-root para o DocumentRoot real).",
                    root,
                )

        log.info(
            "=== resultado final: status=%s quota_status=%s (operação concluída)",
            overall_status,
            qr.status,
        )
        print("Usuário criado com sucesso.")
        print(f"  home:              {home}")
        print("  ssh:               authorized_keys instalado")
        print("  public_html:       pronto (index.html estático)")
        print("  public_gopher:     pronto (gophermap)")
        print("  public_gemini:     pronto (index.gmi)")
        print("  bind Gemini:       /var/gemini/users/<user> <- ~/public_gemini (se o diretório existir)")
        if args.with_readme:
            print("  README.md:         criado em ~/README.md (pt-BR)")
        else:
            print("  README.md:         omitido (use --with-readme para criar)")
        if args.no_jail:
            print("  jail SSH:          omitido (--no-jail)")
        else:
            print("  jail SSH:          runv-jailed + /srv/jail/<user> (bind home)")
        print(f"  URL prevista:      {args.base_url.rstrip('/')}/~{user}/")
        print(f"  fingerprint:       {fingerprint}")
        print(f"  metadados:         {args.metadata_file}")
        dr_resolved = (
            args.landing_document_root.resolve() if args.landing_document_root else None
        )
        out_members = (dr_resolved / "data" / "members.json") if dr_resolved else None
        if args.no_refresh_landing_members:
            print("  constelação (bolhas): omitida (--no-refresh-landing-members)")
        elif dr_resolved is not None:
            if not dr_resolved.is_dir():
                print(
                    f"  AVISO constelação: DocumentRoot inexistente ({dr_resolved}) — "
                    "bolhas não actualizadas. Depois de criar o site: "
                    f"python3 {_REPO_ROOT / 'site' / 'build_directory.py'} "
                    f"--users-json {args.metadata_file} -o {out_members}",
                    file=sys.stderr,
                )
            elif members_refreshed:
                cnt = (
                    f", {members_public_count} membro(s) público(s)"
                    if members_public_count is not None
                    else ""
                )
                print(f"  constelação (bolhas): actualizado{cnt} → {out_members}")
            else:
                print(
                    f"  AVISO constelação: falha ao regenerar members.json (ver log). "
                    f"Manual: python3 {_REPO_ROOT / 'site' / 'build_directory.py'} "
                    f"--users-json {args.metadata_file} -o {out_members}",
                    file=sys.stderr,
                )
        if args.no_quota:
            print("  quota:             omitida (--no-quota)")
        else:
            print(
                f"  quota:             status={qr.status} "
                f"(MiB {args.quota_soft_mb}/{args.quota_hard_mb}, "
                f"inodes {args.quota_inode_soft}/{args.quota_inode_hard})"
            )
            if qr.mountpoint:
                print(f"  quota mount:       {qr.mountpoint} ({qr.filesystem or '?'})")

        welcome_host = (args.welcome_ssh_host or os.environ.get("RUNV_WELCOME_SSH_HOST") or "").strip()
        welcome_host_opt: str | None = welcome_host if welcome_host else None
        try_send_welcome_email(
            username=user,
            user_email=email,
            fingerprint=fingerprint,
            base_url=args.base_url,
            welcome_ssh_host=welcome_host_opt,
            no_welcome_email=bool(args.no_welcome_email),
            dry_run=bool(args.dry_run),
            log=log,
        )
        try_send_admin_user_created_email(
            username=user,
            user_email=email,
            operator_info=record.created_by,
            timestamp=record.created_at,
            no_admin_create_email=bool(args.no_admin_create_email),
            dry_run=bool(args.dry_run),
            log=log,
        )

        if not args.no_quota and qr.status in ("failed", "not_configured"):
            print(
                "\n*** AVISO: conta criada mas quota NÃO aplicada ou sistema não configurado. "
                "Estado em metadados: partial_quota / quota_status. "
                "Corrija usrquota+quotaon e aplique setquota manualmente ou remova o utilizador se foi engano.",
                file=sys.stderr,
            )
            return EXIT_INCONSISTENT

        return EXIT_OK

    except ValidationError as e:
        log.error("validação: %s", e)
        print(f"Validação: {e}", file=sys.stderr)
        if created_user:
            if run_deluser_remove_home(user, log):
                print("Rollback: usuário removido após falha de validação tardia.", file=sys.stderr)
            else:
                print(
                    f"ERRO: estado parcial — usuário {user!r} pode existir; remova manualmente se necessário.",
                    file=sys.stderr,
                )
                return EXIT_INCONSISTENT
        return EXIT_VALIDATION

    except SystemProvisionError as e:
        log.exception("falha de sistema: %s", e)
        print(f"Erro de sistema: {e}", file=sys.stderr)
        if created_user:
            if run_deluser_remove_home(user, log):
                print("Rollback: usuário e home removidos.", file=sys.stderr)
            else:
                print(
                    f"FALHA NO ROLLBACK: revise o usuário {user!r} e o home em {home} manualmente.",
                    file=sys.stderr,
                )
                return EXIT_INCONSISTENT
        return EXIT_SYSTEM

    except Exception as e:
        log.exception("erro inesperado: %s", e)
        print(f"Erro inesperado: {e}", file=sys.stderr)
        if created_user:
            if run_deluser_remove_home(user, log):
                print("Rollback: usuário removido.", file=sys.stderr)
            else:
                print(
                    f"FALHA NO ROLLBACK: revise o usuário {user!r} manualmente.",
                    file=sys.stderr,
                )
                return EXIT_INCONSISTENT
        return EXIT_SYSTEM


def run() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":
    run()
