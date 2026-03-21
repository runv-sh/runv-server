#!/usr/bin/env python3
"""
Ferramenta interna de administração: provisiona contas Unix no runv.club (Debian).

Contrato de provisionamento (ordem garantida após validação):

1. **Criar o usuário** — ``adduser --disabled-password``.
2. **Instalar a chave** — ``~/.ssh/authorized_keys`` com modos ``700`` / ``600``.
3. **Preparar public_html** — diretório ``755``, ``index.html`` estático ``644``.
4. **Preparar public_gopher / public_gemini** — ``gophermap`` e ``index.gmi`` modelo (não
   sobrescreve sem ``--force-gopher`` / ``--force-gemini``); symlink Gemini em
   ``/var/gemini/users/<user>`` quando o diretório existir.
5. **Copiar o skel** — o Debian copia ``/etc/skel`` para a home **durante** o passo 1; depois,
   após os diretórios públicos, o script acrescenta ``README.md`` runv (português), sem apagar o que
   veio do skel (use ``--force-readme`` para substituir). Prepare ``/etc/skel`` com ``tools.py``
   antes das contas, se for política do servidor.
6. **Aplicar permissões** — ``apply_runv_permissions``: home, ``.ssh``, sites públicos e README com modos
   e donos corretos, antes da quota e da verificação final.

Quota ext4, metadados JSON e logging seguem após estes passos.

É a **fonte principal** da política de provisionamento — sem depender de ``adduser.local``,
``QUOTAUSER`` ou regras espalhadas em ``/etc/adduser.conf``.

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
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Validação de username / email
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Chave pública OpenSSH
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Caminhos seguros sob /home
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# SSH authorized_keys
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# public_html
# ---------------------------------------------------------------------------


def default_index_html(username: str) -> str:
    """HTML estático mínimo: sem JavaScript, sem CDN, sem conteúdo dinâmico."""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>~{username} no runv.club</title>
</head>
<body>
  <h1>Olá, ~{username}</h1>
  <p>Bem-vindo(a) ao runv.club — espaço pubnix com shell e site pessoal.</p>
  <p>Edite este ficheiro em <code>~/public_html/index.html</code> (ficheiros estáticos apenas).</p>
  <p>Leia também <code>~/README.md</code> na shell para instruções e permissões.</p>
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
- **Gemini:** edita `~/public_gemini/index.gmi`. URL típica: `gemini://{DEFAULT_GEMINI_HOST_PUBLIC}/~{username}/`
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

— Equipa runv.club
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
    return f"""iBem-vindo ao teu espaço Gopher no runv.club.	fake	NULL	0
iEdita este ficheiro em ~/public_gopher/gophermap para personalizares o menu.	fake	NULL	0
iDocumentação: man gophermap (no pacote gophernicus).	fake	NULL	0
"""


def default_gemini_index_gmi(username: str) -> str:
    return f"""# ~{username} — runv.club (Gemini)

Bem-vindo ao teu capsule em `gemini://{DEFAULT_GEMINI_HOST_PUBLIC}/~{username}/`.

Edita este ficheiro em `~/public_gemini/index.gmi`. Mantém pastas **755** e ficheiros **644**.

## Dicas

* Ficheiros `.gmi` são Texto Gemini.
* Não coloques segredos em diretórios públicos.
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
    force_gemini: bool,
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
    if idx.exists() and not force_gemini:
        log.info("%s já existe; não sobrescrevendo (use --force-gemini)", idx)
        return
    if idx.exists() and force_gemini:
        log.warning("sobrescrevendo %s (--force-gemini)", idx)
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
    """Cria /var/gemini/users/<user> -> <home>/public_gemini se o diretório global existir."""
    target = (home / "public_gemini").resolve()
    if not GEMINI_USERS_DIR.is_dir():
        log.warning(
            "diretório %s inexistente — symlink Gemini não criado. "
            "Execute scripts/admin/setup_alt_protocols.py no servidor.",
            GEMINI_USERS_DIR,
        )
        return
    link = GEMINI_USERS_DIR / username
    if link.is_symlink():
        if link.resolve() == target:
            log.info("symlink Gemini já correto: %s", link)
            return
        if force:
            link.unlink()
            log.info("symlink Gemini antigo removido: %s", link)
        else:
            log.warning(
                "symlink %s aponta para %s (esperado %s); não altero sem --force-gemini",
                link,
                link.resolve(),
                target,
            )
            return
    elif link.exists():
        if not force:
            log.warning("%s existe e não é symlink; não sobrescrevo sem --force-gemini", link)
            return
        if link.is_dir():
            shutil.rmtree(link)
        else:
            link.unlink()
        log.info("removido destino em conflito para symlink Gemini: %s", link)
    link.symlink_to(target, target_is_directory=True)
    log.info("symlink Gemini: %s -> %s", link, target)


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


# ---------------------------------------------------------------------------
# Metadados JSON
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# adduser / rollback
# ---------------------------------------------------------------------------


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
    Aplica modos e donos esperados na home e nos artefactos runv (passo 5 do contrato).

    Deve ser chamado após criar o utilizador, chave SSH, ``public_html`` e ``README.md``,
    para garantir home ``755`` (Apache atravessa até ``public_html``), ``.ssh`` ``700``,
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


def verify_user_artifact_permissions(home: Path, uid: int, gid: int) -> None:
    """
    Confirma existência, dono e modos esperados após o provisionamento (falha explícita se algo estiver errado).
    """
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
        (home / "README.md", 0o644, "README.md"),
    ]
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


# ---------------------------------------------------------------------------
# Quota ext4 (setquota, usrquota)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# CLI e main
# ---------------------------------------------------------------------------


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
            "Se já existir ~/public_gemini/index.gmi, sobrescrever (--force-gemini)?",
            default_no=True,
        )
        args.force_readme = prompt_yes_no(
            "Se já existir ~/README.md, sobrescrever (--force-readme)?",
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Provisiona conta Unix interna (runv.club). Executar como root no servidor. "
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
        "--force-readme",
        action="store_true",
        help="sobrescrever ~/README.md se já existir",
    )
    p.add_argument(
        "--force-gopher",
        action="store_true",
        help="sobrescrever ~/public_gopher/gophermap se já existir",
    )
    p.add_argument(
        "--force-gemini",
        action="store_true",
        help="sobrescrever ~/public_gemini/index.gmi e corrigir symlink em /var/gemini/users se necessário",
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
            "  ações: (1) adduser + /etc/skel  (2) authorized_keys  (3) public_html  "
            "(4) public_gopher + public_gemini + symlink Gemini  (5) README.md  "
            "(6) permissões consolidadas  + quota (se ativa) + metadados JSON"
        )
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
        prepare_public_gemini(home, user, uid, gid, args.force_gemini, log)
        ensure_gemini_user_symlink(user, home, log, force=args.force_gemini)

        log.info("=== fase 4: README.md runv (após skel /etc/skel do adduser; texto em português)")
        prepare_user_readme(home, user, uid, gid, args.base_url, args.force_readme, log)

        log.info("=== fase 5: permissões consolidadas (home, .ssh, sites públicos, README)")
        apply_runv_permissions(home, uid, gid)

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
        verify_user_artifact_permissions(home, uid, gid)

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
        print("  symlink Gemini:    /var/gemini/users/<user> (se o diretório existir)")
        print("  README.md:         criado em ~/README.md (pt-BR)")
        print(f"  URL prevista:      {args.base_url.rstrip('/')}/~{user}/")
        print(f"  fingerprint:       {fingerprint}")
        print(f"  metadados:         {args.metadata_file}")
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
