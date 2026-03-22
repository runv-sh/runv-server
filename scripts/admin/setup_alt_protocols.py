#!/usr/bin/env python3
"""
Infraestrutura Gopher (gophernicus) e Gemini (molly-brown) para runv.club.

- Gopher: raiz em /var/gopher, espaços de utilizador em ~/public_gopher (gophermap).
- Gemini: DocBase /var/gemini; **bind mount** ``/var/gemini/users/<user>`` <- ``~/public_gemini``
  (o Molly Debian recusa symlinks cujo destino fica fora do DocBase).

Idempotente, dry-run, subprocess sem shell. Executar como root no Debian.

Versão 0.14 — runv.club
"""

from __future__ import annotations

import argparse
import grp
import importlib.util
import logging
import shutil
import os
import pwd
import re
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

# constantes
VERSION: Final[str] = "0.14"

LETSENCRYPT_LIVE: Final[Path] = Path("/etc/letsencrypt/live")
LETSENCRYPT_ARCHIVE: Final[Path] = Path("/etc/letsencrypt/archive")
SSL_CERT_GROUP: Final[str] = "ssl-cert"

DEFAULT_USERS_JSON: Final[Path] = Path("/var/lib/runv/users.json")
DEFAULT_HOMES_ROOT: Final[Path] = Path("/home")
DEFAULT_GEMINI_HOSTNAME: Final[str] = "runv.club"
DEFAULT_LE_CERT: Final[Path] = Path("/etc/letsencrypt/live/runv.club/fullchain.pem")
DEFAULT_LE_KEY: Final[Path] = Path("/etc/letsencrypt/live/runv.club/privkey.pem")

GOPHER_ROOT: Final[Path] = Path("/var/gopher")
GEMINI_ROOT: Final[Path] = Path("/var/gemini")
GEMINI_USERS: Final[Path] = GEMINI_ROOT / "users"
FSTAB_PATH: Final[Path] = Path("/etc/fstab")

# Linha fstab: <source> <mountpoint> none bind 0 0 (paths sem espaços no 2.º campo)
_GEMINI_BIND_FSTAB_RE: Final[re.Pattern[str]] = re.compile(
    r"^(.+)\s+(/var/gemini/users/\S+)\s+none\s+bind\s+0\s+0\s*\Z"
)

GOPHER_DEFAULT_PATH: Final[Path] = Path("/etc/default/gophernicus")
GOPHER_SYSTEMD_SERVICE: Final[Path] = Path("/lib/systemd/system/gophernicus@.service")
MOLLY_CONF_DIR: Final[Path] = Path("/etc/molly-brown")
MOLLY_INSTANCE: Final[str] = "runv.club"  # molly-brown@runv.club.service
# StateDirectory=molly-brown no unit Debian — systemd cria /var/lib/molly-brown
# com o dono correcto (DynamicUser) antes do ExecStart; evita conflitos com
# LogsDirectory + directório pré-existente em /var/log.
MOLLY_LOG_DIR: Final[Path] = Path("/var/lib/molly-brown")
MOLLY_LOGS_DROPIN_PATH: Final[Path] = Path(
    "/etc/systemd/system/molly-brown@.service.d/50-runv-logs.conf"
)

PACKAGES_GOPHER: Final[tuple[str, ...]] = ("gophernicus",)
PACKAGES_GEMINI: Final[tuple[str, ...]] = ("molly-brown",)

DEFAULT_USER_GOPHERMAP: Final[str] = """iBem-vindo ao teu espaço Gopher no runv.club.	fake	NULL	0
iEdita este ficheiro em ~/public_gopher/gophermap.	fake	NULL	0
"""

DEFAULT_USER_INDEX_GMI: Final[str] = """# ~{username} — runv.club

Bem-vindo ao runv.club no **Gemini**. Este é o teu espaço — escreve em `.gmi`, cria subpáginas e liga-as como quiseres.

`gemini://runv.club/~{username}/`
"""


# utilitários
def _path_resolved(p: Path) -> Path:
    """Resolve o caminho; com symlinks (ex. Let's Encrypt) alinha com o canónico."""
    try:
        return p.resolve(strict=False)
    except TypeError:
        return p.resolve()


def setup_logging(verbose: bool) -> logging.Logger:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    return logging.getLogger("setup_alt_protocols")


def run_cmd(
    cmd: list[str],
    *,
    dry_run: bool,
    log: logging.Logger,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str] | None:
    log.debug("exec: %s", " ".join(cmd))
    if dry_run:
        log.info("[dry-run] %s", " ".join(cmd))
        return None
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def backup_if_exists(path: Path, log: logging.Logger, dry_run: bool) -> None:
    if not path.is_file():
        return
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak.{ts}")
    if dry_run:
        log.info("[dry-run] faria backup %s -> %s", path, bak)
        return
    shutil.copy2(path, bak)
    log.info("backup: %s -> %s", path, bak)


def infer_gopher_env_key(service_path: Path) -> str:
    if not service_path.is_file():
        return "OPTIONS"
    text = service_path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"ExecStart=.*?\$(\w+)", text, re.MULTILINE | re.DOTALL)
    if m:
        return m.group(1)
    return "OPTIONS"


def default_gopher_options(hostname: str) -> str:
    return f'-h {hostname} -r {GOPHER_ROOT} -u public_gopher -o UTF-8'


def infer_gophernicus_runtime_user(log: logging.Logger) -> str:
    """Lê User= do unit gophernicus@.service; fallback ``gophernicus``."""
    path = GOPHER_SYSTEMD_SERVICE
    if not path.is_file():
        log.debug("unit gophernicus inexistente (%s) — fallback User=gophernicus", path)
        return "gophernicus"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log.debug("ler %s: %s — fallback User=gophernicus", path, e)
        return "gophernicus"
    m = re.search(r"^User=(\S+)", text, re.MULTILINE)
    if not m:
        log.debug("User= não encontrado em %s — fallback gophernicus", path)
        return "gophernicus"
    u = m.group(1)
    if u.startswith("%") or "${" in u:
        log.debug("User= dinâmico (%s) em %s — fallback gophernicus", u, path)
        return "gophernicus"
    return u


def write_gophernicus_default(
    path: Path,
    options_value: str,
    *,
    env_key: str,
    dry_run: bool,
    log: logging.Logger,
    force: bool,
) -> None:
    lines: list[str] = []
    if path.is_file() and not force:
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
        replaced = False
        opt_re = re.compile(rf"^{re.escape(env_key)}=")
        for line in raw:
            if opt_re.match(line.strip()):
                lines.append(f'{env_key}="{options_value}"')
                replaced = True
            else:
                lines.append(line)
        if not replaced:
            lines.append(f'{env_key}="{options_value}"')
        content = "\n".join(lines).rstrip() + "\n"
    else:
        content = (
            f"# runv.club — gerido por setup_alt_protocols.py\n"
            f"# Ver: man gophernicus (8)\n\n"
            f'{env_key}="{options_value}"\n'
        )
    if dry_run:
        log.info("[dry-run] gravaria %s (%s=...)", path, env_key)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    os.chmod(path, 0o644)
    log.info("atualizado: %s", path)


def molly_log_paths(instance: str) -> tuple[Path, Path]:
    """Caminhos de access / error log para a instância (ex. runv.club)."""
    return (
        MOLLY_LOG_DIR / f"{instance}-access.log",
        MOLLY_LOG_DIR / f"{instance}-error.log",
    )


def retire_molly_brown_logs_dropin(
    *,
    dry_run: bool,
    log: logging.Logger,
    force: bool,
) -> None:
    """
    Remove 50-runv-logs.conf (LogsDirectory=molly-brown) se existir.

    Esse drop-in + directório /var/log/molly-brown criado antes do arranque faz o
    systemd migrar para /var/log/private/ e pode deixar o Molly a falhar. Os
    logs passam a usar só StateDirectory em /var/lib/molly-brown.
    """
    if not MOLLY_LOGS_DROPIN_PATH.is_file():
        return
    if dry_run:
        log.info("[dry-run] removeria drop-in obsoleto: %s", MOLLY_LOGS_DROPIN_PATH)
        return
    if force:
        backup_if_exists(MOLLY_LOGS_DROPIN_PATH, log, dry_run=False)
    MOLLY_LOGS_DROPIN_PATH.unlink()
    log.info("removido drop-in obsoleto (logs em StateDirectory): %s", MOLLY_LOGS_DROPIN_PATH)


def ensure_molly_log_files(
    instance: str,
    *,
    dry_run: bool,
    log: logging.Logger,
) -> tuple[Path, Path]:
    """
    Devolve caminhos AccessLog/ErrorLog sob StateDirectory (/var/lib/molly-brown).

    Não cria directório nem ficheiros: o unit Debian já define StateDirectory e o
    systemd prepara /var/lib/molly-brown antes do ExecStart. Molly-brown não
    aceita AccessLog/ErrorLog = \"-\" (interpreta como path /- e falha).
    """
    access_p, error_p = molly_log_paths(instance)
    if dry_run:
        log.info(
            "[dry-run] AccessLog/ErrorLog seriam %s, %s (StateDirectory systemd)",
            access_p,
            error_p,
        )
        return access_p, error_p

    log.info(
        "logs Molly (StateDirectory): %s, %s",
        access_p,
        error_p,
    )
    return access_p, error_p


def molly_brown_conf_text(
    *,
    hostname: str,
    cert: Path,
    key: Path,
    access_log: Path,
    error_log: Path,
) -> str:
    return f"""# runv.club — gerido por setup_alt_protocols.py
Hostname = "{hostname}"
Port = 1965
DocBase = "{GEMINI_ROOT.as_posix()}"
HomeDocBase = "users"
CertPath = "{cert.as_posix()}"
KeyPath = "{key.as_posix()}"
AccessLog = "{access_log.as_posix()}"
ErrorLog = "{error_log.as_posix()}"
GeminiExt = "gmi"
ReadMollyFiles = true

# Molly Brown (Go): resolvePath usa o *primeiro* segmento após / como ~NOME — ou seja
# path canónico /~username/… (tilde colado ao utilizador). O formato /~/username/
# deixa o nome vazio e devolve 51; redireccionamos /~/… -> /~… antes do Stat.
#
# Conteúdo por utilizador: bind mount (não symlink) de DocBase/users/<user> para
# ~/public_gemini — o pacote Debian recusa symlinks fora do DocBase.
[TempRedirects]
"^/~/([^/]+)(/.*)?$" = "/~$1$2"
"""


def repo_root() -> Path:
    """Raiz do repositório runv-server (scripts/admin/ → …/runv-server)."""
    return Path(__file__).resolve().parent.parent.parent


def load_patch_irc_module(log: logging.Logger) -> Any:
    path = repo_root() / "patches" / "patch_irc.py"
    if not path.is_file():
        log.error(
            "Ficheiro em falta: %s — clone completo do repo ou copie patches/patch_irc.py.",
            path,
        )
        raise FileNotFoundError(str(path))
    spec = importlib.util.spec_from_file_location("patch_irc_setup_alt", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"não foi possível carregar {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_IRC_PATCH_SKIP_USERS_CACHE: frozenset[str] | None = None


def irc_patch_skip_users(log: logging.Logger) -> frozenset[str]:
    """Contas em ``IRC_PATCH_SKIP_USERS`` (sem IRC / sem bind Gemini / fora dos índices raiz)."""
    global _IRC_PATCH_SKIP_USERS_CACHE
    if _IRC_PATCH_SKIP_USERS_CACHE is None:
        _IRC_PATCH_SKIP_USERS_CACHE = load_patch_irc_module(log).IRC_PATCH_SKIP_USERS
    return _IRC_PATCH_SKIP_USERS_CACHE


def resolve_backfill_users(
    users_json: Path,
    homes_root: Path,
    log: logging.Logger,
) -> list[str]:
    """União users.json + /home, mesma política que patches/patch_irc.py."""
    patch_irc = load_patch_irc_module(log)
    return patch_irc.resolve_all_users(users_json, homes_root, log)


def wait_for_unit_active(
    unit: str,
    *,
    log: logging.Logger,
    dry_run: bool,
    attempts: int = 5,
    delay_s: float = 1.0,
) -> bool:
    if dry_run:
        return True
    for i in range(attempts):
        r = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=30,
        )
        state = (r.stdout or "").strip()
        if state == "active":
            log.info("%s: active", unit)
            return True
        log.debug("%s: %s (tentativa %d/%d)", unit, state or r.returncode, i + 1, attempts)
        if i + 1 < attempts:
            time.sleep(delay_s)
    log.warning(
        "%s não ficou «active» após %d tentativas — veja: sudo journalctl -u %s -b --no-pager",
        unit,
        attempts,
        unit,
    )
    log_systemd_unit_failed_hint(unit, log)
    return False


def ensure_le_tls_readable_for_molly(
    cert_path: Path,
    key_path: Path,
    *,
    dry_run: bool,
    log: logging.Logger,
) -> None:
    """
    Ajusta /etc/letsencrypt/live, archive, live/<domínio>, archive/<domínio> para 755 e
    archive/<domínio>/privkey*.pem para grupo ssl-cert + 640, para o molly-brown ler a chave.

    Usa caminhos lógicos (sem resolver fullchain.pem → archive), porque o symlink típico do
    Let's Encrypt fazia falhar a detecção quando se aplicava resolve() ao certificado.
    """
    cert_p = Path(cert_path)
    key_p = Path(key_path)

    try:
        cert_rel = cert_p.relative_to(LETSENCRYPT_LIVE)
    except ValueError:
        log.debug(
            "LE TLS: cert_path não está sob %s (%s) — salto",
            LETSENCRYPT_LIVE,
            cert_p,
        )
        return

    cparts = cert_rel.parts
    if len(cparts) < 2:
        log.debug(
            "LE TLS: esperado %s/<domínio>/<ficheiro> — salto (%s)",
            LETSENCRYPT_LIVE,
            cert_p,
        )
        return
    domain = cparts[0]

    try:
        key_rel = key_p.relative_to(LETSENCRYPT_LIVE)
    except ValueError:
        log.debug(
            "LE TLS: key_path não está sob %s (%s) — salto",
            LETSENCRYPT_LIVE,
            key_p,
        )
        return
    if not key_rel.parts or key_rel.parts[0] != domain:
        log.debug(
            "LE TLS: key_path não está sob %s/%s/ — salto (%s)",
            LETSENCRYPT_LIVE,
            domain,
            key_p,
        )
        return

    live_domain_dir = LETSENCRYPT_LIVE / domain
    archive_domain_dir = LETSENCRYPT_ARCHIVE / domain

    try:
        ssl_gid = grp.getgrnam(SSL_CERT_GROUP).gr_gid
    except KeyError:
        log.warning(
            "LE TLS: grupo %r inexistente — não ajusto privkey*.pem (instale openssl/ssl-cert)",
            SSL_CERT_GROUP,
        )
        ssl_gid = None

    dirs_755: list[Path] = [
        LETSENCRYPT_LIVE,
        LETSENCRYPT_ARCHIVE,
        live_domain_dir,
    ]
    if archive_domain_dir.is_dir():
        dirs_755.append(archive_domain_dir)

    for d in dirs_755:
        if not d.is_dir():
            log.info("LE TLS: omito chmod 755 (não existe): %s", d)
            continue
        if dry_run:
            log.info("[dry-run] chmod 755 %s", d)
            continue
        try:
            before = stat.S_IMODE(os.stat(d).st_mode)
            os.chmod(d, 0o755)
            if before != 0o755:
                log.info("LE TLS: %s modo %04o -> 0755", d, before)
        except OSError as e:
            log.warning("LE TLS: chmod %s: %s", d, e)

    if not archive_domain_dir.is_dir():
        log.info("LE TLS: %s inexistente — sem privkey*.pem", archive_domain_dir)
        return

    privkeys = sorted(archive_domain_dir.glob("privkey*.pem"))
    if not privkeys:
        log.info("LE TLS: sem privkey*.pem em %s", archive_domain_dir)
        return

    if ssl_gid is None:
        log.warning("LE TLS: sem grupo ssl-cert — não altero privkey em %s", archive_domain_dir)
        return

    for pk in privkeys:
        if not pk.is_file():
            continue
        if dry_run:
            log.info("[dry-run] chgrp %s %s && chmod 640 %s", SSL_CERT_GROUP, pk, pk)
            continue
        try:
            st = os.stat(pk)
            os.chown(pk, st.st_uid, ssl_gid)
            before_m = stat.S_IMODE(st.st_mode)
            os.chmod(pk, 0o640)
            if before_m != 0o640:
                log.info("LE TLS: %s modo %04o -> 0640, grupo %s", pk, before_m, SSL_CERT_GROUP)
        except OSError as e:
            log.warning("LE TLS: ajuste %s: %s", pk, e)


def ensure_user_public_dirs(
    username: str,
    homes_root: Path,
    *,
    force: bool,
    dry_run: bool,
    log: logging.Logger,
) -> None:
    try:
        pw = pwd.getpwnam(username)
    except KeyError:
        log.warning("utilizador %s não existe no sistema — salto backfill", username)
        return
    home = Path(pw.pw_dir)
    uid, gid = pw.pw_uid, pw.pw_gid
    gdir = home / "public_gopher"
    gmap = gdir / "gophermap"
    xdir = home / "public_gemini"
    xidx = xdir / "index.gmi"

    if dry_run:
        log.info("[dry-run] garantiria ~/public_gopher e ~/public_gemini para %s", username)
        if home.is_dir():
            try:
                cur = stat.S_IMODE(os.stat(home).st_mode)
            except OSError as e:
                log.debug("[dry-run] stat home %s: %s", home, e)
            else:
                if cur != 0o755:
                    log.info("[dry-run] chmod 755 %s (era %04o)", home, cur)
        return

    gdir.mkdir(parents=True, exist_ok=True)
    xdir.mkdir(parents=True, exist_ok=True)
    os.chmod(gdir, 0o755)
    os.chmod(xdir, 0o755)
    os.chown(gdir, uid, gid)
    os.chown(xdir, uid, gid)

    if not gmap.exists() or force:
        if gmap.exists() and force:
            backup_if_exists(gmap, log, dry_run=False)
        gmap.write_text(DEFAULT_USER_GOPHERMAP, encoding="utf-8")
        os.chmod(gmap, 0o644)
        os.chown(gmap, uid, gid)
        log.info("gophermap: %s", gmap)
    else:
        log.debug("gophermap já existe, mantido: %s", gmap)

    # index.gmi: nunca sobrescrever se já existir (--force não aplica ao modelo Gemini).
    if not xidx.exists():
        xidx.write_text(
            DEFAULT_USER_INDEX_GMI.format(username=username),
            encoding="utf-8",
        )
        os.chmod(xidx, 0o644)
        os.chown(xidx, uid, gid)
        log.info("index.gmi: %s", xidx)
    else:
        log.debug("index.gmi já existe, mantido: %s", xidx)

    if home.is_dir():
        try:
            cur = stat.S_IMODE(os.stat(home).st_mode)
        except OSError as e:
            log.warning("stat home %s: %s", home, e)
        else:
            if cur != 0o755:
                os.chmod(home, 0o755)
                log.info("home %s: modo %04o -> 0755 (atravessável por serviços)", home, cur)


def _escape_fstab_path(s: str) -> str:
    return s.replace(" ", "\\040")


def _unescape_fstab_path(s: str) -> str:
    return s.replace("\\040", " ")


def _is_dir_mountpoint(path: Path) -> bool:
    r = subprocess.run(
        ["mountpoint", "-q", str(path)],
        capture_output=True,
        timeout=30,
    )
    return r.returncode == 0


def _bind_mount_source_resolved(mountpoint: Path) -> Path | None:
    r = subprocess.run(
        ["findmnt", "-n", "-o", "SOURCE", "--target", str(mountpoint)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if r.returncode != 0:
        return None
    raw = (r.stdout or "").strip()
    if not raw:
        return None
    src = raw.split()[0]
    if src.startswith("[") and "]" in src:
        src = src[1 : src.index("]")]
    try:
        return Path(src).resolve(strict=False)
    except OSError:
        return Path(src)


def _ensure_gemini_fstab_line(
    source: Path,
    mountpoint: Path,
    *,
    dry_run: bool,
    log: logging.Logger,
) -> None:
    src_s = str(_path_resolved(source))
    mp_s = str(_path_resolved(mountpoint))
    desired_line = f"{_escape_fstab_path(src_s)} {_escape_fstab_path(mp_s)} none bind 0 0\n"
    if dry_run:
        log.info("[dry-run] fstab (se necessário): %s", desired_line.rstrip())
        return
    if not FSTAB_PATH.is_file():
        log.warning("%s inexistente — bind não persistido após reboot", FSTAB_PATH)
        return
    try:
        text = FSTAB_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log.warning("ler fstab: %s", e)
        return
    mp_path = mountpoint
    src_res = Path(src_s).resolve()
    kept: list[str] = []
    found_exact = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            kept.append(line)
            continue
        m = _GEMINI_BIND_FSTAB_RE.match(stripped)
        if not m:
            kept.append(line)
            continue
        f2 = Path(_unescape_fstab_path(m.group(2)))
        if f2 != mp_path:
            kept.append(line)
            continue
        f1 = Path(_unescape_fstab_path(m.group(1))).resolve()
        if f1 == src_res:
            if not found_exact:
                found_exact = True
                kept.append(line)
            else:
                log.debug("fstab: duplicado ignorado para %s", mountpoint)
        else:
            log.debug("fstab: removida linha antiga para %s (origem diferente)", mountpoint)
    if not found_exact:
        if kept and not kept[-1].endswith("\n"):
            kept[-1] += "\n"
        kept.append(desired_line)
    new_content = "".join(kept)
    if new_content == text:
        log.debug("fstab inalterado para %s", mountpoint)
        return
    backup_if_exists(FSTAB_PATH, log, dry_run=False)
    FSTAB_PATH.write_text(new_content, encoding="utf-8")
    log.info("fstab: bind persistido %s -> %s", src_s, mp_s)


def _remove_gemini_fstab_lines_for_mountpoint(mountpoint: Path, log: logging.Logger) -> None:
    """Remove todas as linhas ``bind`` do fstab cujo segundo campo é ``mountpoint``."""
    if not FSTAB_PATH.is_file():
        return
    try:
        text = FSTAB_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log.warning("ler fstab: %s", e)
        return
    new_lines: list[str] = []
    removed = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            new_lines.append(line)
            continue
        m = _GEMINI_BIND_FSTAB_RE.match(stripped)
        if m and Path(_unescape_fstab_path(m.group(2))) == mountpoint:
            removed = True
            continue
        new_lines.append(line)
    if not removed:
        return
    new_content = "".join(new_lines)
    backup_if_exists(FSTAB_PATH, log, dry_run=False)
    FSTAB_PATH.write_text(new_content, encoding="utf-8")
    log.info("fstab: removida(s) linha(s) bind para %s", mountpoint)


def remove_gemini_bind_mount(
    username: str,
    *,
    dry_run: bool,
    log: logging.Logger,
) -> None:
    """Desmonta ``/var/gemini/users/<user>``, limpa fstab, symlink ou directório vazio."""
    mountpoint = GEMINI_USERS / username
    if dry_run:
        log.info("[dry-run] removeria bind Gemini / fstab em %s", mountpoint)
        return
    if _is_dir_mountpoint(mountpoint):
        ru = run_cmd(["umount", str(mountpoint)], dry_run=False, log=log)
        if ru is not None and ru.returncode != 0:
            log.warning(
                "umount %s: %s",
                mountpoint,
                (ru.stderr or ru.stdout or "").strip(),
            )
    _remove_gemini_fstab_lines_for_mountpoint(mountpoint, log)
    if mountpoint.is_symlink():
        try:
            mountpoint.unlink()
            log.info("symlink Gemini removido: %s", mountpoint)
        except OSError as e:
            log.warning("unlink %s: %s", mountpoint, e)
    if mountpoint.is_dir():
        try:
            if not any(mountpoint.iterdir()):
                mountpoint.rmdir()
                log.info("directório Gemini vazio removido: %s", mountpoint)
        except OSError as e:
            log.warning("%s: %s", mountpoint, e)


def build_root_gophermap_text(
    hostname: str,
    homes_root: Path,
    users: list[str],
) -> str:
    """Menu raiz com links ``1~user`` só para contas com ``~/public_gopher`` (exclui IRC_PATCH_SKIP)."""
    tab = "\t"
    lines: list[str] = [
        "!runv.club — Gopher",
        f"iBem-vindo ao Gopher em {hostname} — pubnix.{tab}fake{tab}NULL{tab}0",
        f"iMembros com espaço público (selector ~utilizador/).{tab}fake{tab}NULL{tab}0",
        "#",
    ]
    for u in sorted(users):
        if not (homes_root / u / "public_gopher").is_dir():
            continue
        lines.append(f"1~{u}{tab}~{u}/{tab}{hostname}{tab}70")
    return "\n".join(lines) + "\n"


def build_root_gemini_index_gmi(
    hostname: str,
    homes_root: Path,
    users: list[str],
) -> str:
    """Índice Gemtext na raiz do DocBase; mesmos membros que no menu Gopher raiz."""
    lines: list[str] = [
        f"# {hostname} — Gemini",
        "",
        f"Bem-vindo ao **Gemini** do **{hostname}**.",
        "",
        "## Capsules dos membros",
        "",
    ]
    for u in sorted(users):
        if not (homes_root / u / "public_gopher").is_dir():
            continue
        lines.append(f"=> gemini://{hostname}/~{u}/ Capsule ~{u}")
    lines.append("")
    return "\n".join(lines)


def ensure_gemini_bind_mount(
    username: str,
    homes_root: Path,
    *,
    force: bool,
    dry_run: bool,
    log: logging.Logger,
) -> None:
    """
    Expõe ~/public_gemini em /var/gemini/users/<user> com mount --bind + fstab.
    O Molly Debian recusa symlinks cujo destino fica fora de DocBase (/var/gemini).
    Contas em IRC_PATCH_SKIP_USERS não recebem bind; com force remove-se mount/fstab.
    """
    _ = homes_root  # API compatível com o backfill (getpwnam fornece a home)
    try:
        pw = pwd.getpwnam(username)
    except KeyError:
        return

    sk = irc_patch_skip_users(log)
    if username in sk:
        if dry_run:
            log.info("[dry-run] %s em IRC_PATCH_SKIP_USERS — bind Gemini omitido", username)
            return
        if force:
            remove_gemini_bind_mount(username, dry_run=False, log=log)
        else:
            mp = GEMINI_USERS / username
            if _is_dir_mountpoint(mp) or mp.is_symlink():
                log.warning(
                    "%s está em IRC_PATCH_SKIP_USERS mas há mount ou symlink em %s — "
                    "use --force para remover",
                    username,
                    mp,
                )
            else:
                log.debug("skip bind Gemini (IRC_PATCH_SKIP_USERS): %s", username)
        return

    home = Path(pw.pw_dir)
    target = home / "public_gemini"
    if not target.is_dir():
        log.debug("public_gemini inexistente para %s — bind não aplicado", username)
        return
    target_resolved = _path_resolved(target)
    mountpoint = GEMINI_USERS / username

    if not GEMINI_USERS.is_dir():
        log.warning("GEMINI_USERS inexistente: %s — bind não aplicado", GEMINI_USERS)
        return

    if dry_run:
        log.info("[dry-run] mount --bind %s %s + fstab", target_resolved, mountpoint)
        _ensure_gemini_fstab_line(target_resolved, mountpoint, dry_run=True, log=log)
        return

    if mountpoint.is_symlink():
        if not force:
            log.warning(
                "symlink %s -> %s: Molly Debian recusa symlinks fora do DocBase; "
                "corra com --force para substituir por bind mount",
                mountpoint,
                mountpoint.resolve(),
            )
            return
        mountpoint.unlink()
        log.info("symlink removido (migração bind): %s", mountpoint)

    if mountpoint.exists() and mountpoint.is_file():
        log.warning("%s é ficheiro; não aplico bind", mountpoint)
        return

    if _is_dir_mountpoint(mountpoint):
        src_now = _bind_mount_source_resolved(mountpoint)
        if src_now == target_resolved:
            log.debug("bind mount OK: %s <- %s", mountpoint, target_resolved)
            _ensure_gemini_fstab_line(target_resolved, mountpoint, dry_run=False, log=log)
            return
        if not force:
            log.warning(
                "mountpoint %s montado de %s; esperado %s — use --force",
                mountpoint,
                src_now,
                target_resolved,
            )
            return
        ru = run_cmd(["umount", str(mountpoint)], dry_run=False, log=log)
        if ru is not None and ru.returncode != 0:
            log.error(
                "umount %s falhou: %s",
                mountpoint,
                (ru.stderr or ru.stdout or "").strip(),
            )
            return
        log.info("umount antes de remount: %s", mountpoint)

    if mountpoint.exists() and mountpoint.is_dir():
        try:
            if any(mountpoint.iterdir()):
                log.warning(
                    "%s é directório com conteúdo (não é mountpoint); não aplico bind",
                    mountpoint,
                )
                return
        except OSError as e:
            log.warning("listar %s: %s", mountpoint, e)
            return

    mountpoint.mkdir(parents=True, exist_ok=True)
    os.chmod(mountpoint, 0o755)
    try:
        os.chown(mountpoint, 0, 0)
    except OSError as e:
        log.warning("chown %s: %s", mountpoint, e)

    rm = run_cmd(
        ["mount", "--bind", str(target_resolved), str(mountpoint)],
        dry_run=False,
        log=log,
    )
    if rm is None or rm.returncode != 0:
        log.error(
            "mount --bind falhou: %s -> %s (%s)",
            target_resolved,
            mountpoint,
            (rm.stderr or rm.stdout or "").strip() if rm else "",
        )
        return
    log.info("bind mount: %s -> %s", target_resolved, mountpoint)
    _ensure_gemini_fstab_line(target_resolved, mountpoint, dry_run=False, log=log)


# Alias legado (patches/yetgg.py e referências antigas)
ensure_gemini_symlink = ensure_gemini_bind_mount


def apt_install(
    packages: tuple[str, ...],
    *,
    dry_run: bool,
    log: logging.Logger,
) -> bool:
    env = {"DEBIAN_FRONTEND": "noninteractive", "LC_ALL": "C"}
    r1 = run_cmd(["apt-get", "update", "-qq"], dry_run=dry_run, log=log)
    if not dry_run and r1 is not None and r1.returncode != 0:
        log.error("apt-get update falhou: %s", (r1.stderr or r1.stdout or "").strip())
        return False
    cmd = ["apt-get", "install", "-y", "--no-install-recommends", *packages]
    r2 = run_cmd(cmd, dry_run=dry_run, log=log)
    if dry_run:
        return True
    if r2 is None or r2.returncode != 0:
        log.error("apt-get install falhou: %s", (r2.stderr or r2.stdout or "").strip() if r2 else "")
        return False
    return True


def log_ufw_suggested_commands(log: logging.Logger) -> None:
    """Comandos para copiar quando o script não aplicou regras UFW automaticamente."""
    log.info(
        "Se usar UFW, depois de «sudo ufw enable» (se ainda não estiver activo), execute:\n"
        "  sudo ufw allow 70/tcp comment 'gopher'\n"
        "  sudo ufw allow 1965/tcp comment 'gemini'\n"
        "  sudo ufw reload"
    )


def log_systemd_unit_failed_hint(unit: str, log: logging.Logger) -> None:
    """Se o unit estiver em estado failed, regista ERROR com ponteiro para journalctl."""
    r = subprocess.run(
        ["systemctl", "is-failed", unit],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if r.returncode != 0:
        return
    log.error(
        "%s está em estado «failed» — diagnóstico: sudo journalctl -u %s -b --no-pager -n 80",
        unit,
        unit,
    )


def dpkg_installed(package: str) -> bool:
    r = subprocess.run(
        ["dpkg", "-s", package],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return r.returncode == 0 and "Status: install ok installed" in (r.stdout or "")


def ufw_maybe_allow(
    ports: list[tuple[int, str]],
    *,
    dry_run: bool,
    log: logging.Logger,
    skip_firewall: bool,
) -> None:
    if skip_firewall:
        log.info("firewall ignorado (--skip-firewall)")
        log_ufw_suggested_commands(log)
        return
    r = subprocess.run(
        ["ufw", "status"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = (r.stdout or "").lower()
    if r.returncode != 0 or "status: active" not in out:
        log.warning(
            "UFW não está ativo (ou comando falhou). Não abro portas automaticamente. "
            "Abra 70/tcp (Gopher) e 1965/tcp (Gemini) se usar firewall."
        )
        log_ufw_suggested_commands(log)
        return
    for port, label in ports:
        cmd = ["ufw", "allow", f"{port}/tcp"]
        run_cmd(cmd, dry_run=dry_run, log=log)
        log.info("UFW: permitido %s/tcp (%s)", port, label)


def _runuser_can_read(
    path: Path,
    run_as: str,
    *,
    dry_run: bool,
    log: logging.Logger,
) -> bool | None:
    """None = skip (sem runuser), True/False = resultado de ``test -r`` como *run_as*."""
    if dry_run:
        if shutil.which("runuser"):
            log.info("[dry-run] runuser -u %s -- test -r %s", run_as, path)
        else:
            log.info("[dry-run] (runuser ausente) test -r como %s em %s", run_as, path)
        return None
    if not shutil.which("runuser"):
        log.debug("validação runuser: binário não encontrado — salto test -r")
        return None
    r = subprocess.run(
        ["runuser", "-u", run_as, "--", "test", "-r", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return r.returncode == 0


def _www_data_can_read(path: Path, *, dry_run: bool, log: logging.Logger) -> bool | None:
    """Heurística de leitura como ``www-data`` (ACL POSIX pode afectar o UID real do Molly)."""
    return _runuser_can_read(path, "www-data", dry_run=dry_run, log=log)


def validate_final(
    usernames: list[str],
    log: logging.Logger,
    *,
    dry_run: bool = False,
) -> None:
    log.info("--- validação final ---")
    for pkg, label in (("gophernicus", "Gopher"), ("molly-brown", "Gemini")):
        ok = dpkg_installed(pkg)
        log.info("pacote %s (%s): %s", pkg, label, "OK" if ok else "AUSENTE")

    r = subprocess.run(
        ["systemctl", "is-active", "gophernicus.socket"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    gopher_state = (r.stdout or "").strip()
    log.info("gophernicus.socket: %s", gopher_state or r.returncode)

    molly_unit = f"molly-brown@{MOLLY_INSTANCE}.service"
    r2 = subprocess.run(
        ["systemctl", "is-active", molly_unit],
        capture_output=True,
        text=True,
        timeout=30,
    )
    molly_state = (r2.stdout or "").strip() or str(r2.returncode)
    log.info("molly-brown@%s: %s", MOLLY_INSTANCE, molly_state)
    if molly_state != "active":
        log.warning(
            "molly-brown não está «active» (estado reportado: %s). "
            "«activating» durante o script não significa sucesso — confirme com "
            "«systemctl is-active %s» e «sudo ss -tlnp | grep 1965».",
            molly_state,
            molly_unit,
        )
        log_systemd_unit_failed_hint(molly_unit, log)

    if usernames:
        sk = irc_patch_skip_users(log)
        visible = [u for u in usernames if u not in sk]
        sample = visible[0] if visible else usernames[0]
        try:
            pw = pwd.getpwnam(sample)
            home = Path(pw.pw_dir)
            for p, label in (
                (home / "public_gopher" / "gophermap", "gophermap"),
                (home / "public_gemini" / "index.gmi", "index.gmi"),
            ):
                log.info("amostra %s %s: %s", sample, label, "OK" if p.is_file() else "FALTA")
            mp = GEMINI_USERS / sample
            pg = (home / "public_gemini").resolve()
            ok_mount = False
            if _is_dir_mountpoint(mp):
                src = _bind_mount_source_resolved(mp)
                ok_mount = src is not None and src == pg
            elif mp.is_symlink():
                log.warning(
                    "amostra %s: %s ainda é symlink (Molly Debian rejeita); "
                    "corra setup_alt_protocols com --force para bind mount",
                    sample,
                    mp,
                )
            log.info("amostra mount Gemini: %s", "OK" if ok_mount else "FALTA/INCORRETO")
            gophermap = home / "public_gopher" / "gophermap"
            if gopher_state == "active" and gophermap.is_file():
                guser = infer_gophernicus_runtime_user(log)
                gcan = _runuser_can_read(gophermap, guser, dry_run=dry_run, log=log)
                if gcan is False:
                    log.warning(
                        "amostra %s: utilizador %s (gophernicus) não consegue ler %s "
                        "(runuser … test -r falhou). Confirme home 755 (ou o+x), "
                        "public_gopher 755, gophermap 644.",
                        sample,
                        guser,
                        gophermap,
                    )
                elif gcan is True:
                    log.info(
                        "amostra %s: gophermap legível pelo utilizador do serviço (%s, test -r): OK",
                        sample,
                        guser,
                    )
            index_gmi = home / "public_gemini" / "index.gmi"
            if molly_state == "active" and index_gmi.is_file():
                can = _www_data_can_read(index_gmi, dry_run=dry_run, log=log)
                if can is False:
                    log.warning(
                        "amostra %s: www-data não consegue ler %s (runuser … test -r falhou). "
                        "Confirme home 755 (ou o+x), public_gemini 755, index.gmi 644, bind %s; "
                        "se `ls -l` mostrar +, veja getfacl no path (ACL).",
                        sample,
                        index_gmi,
                        mp,
                    )
                elif can is True:
                    log.info("amostra %s: index.gmi legível por www-data (test -r): OK", sample)
        except KeyError:
            log.info("amostra %s: utilizador não existe neste sistema", sample)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Instala/configura Gopher (gophernicus) e Gemini (molly-brown) para runv.club.",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument(
        "--force",
        action="store_true",
        help="sobrescreve configs e ficheiros modelo com backup (index.gmi existente nunca é substituído)",
    )
    p.add_argument("--skip-install", action="store_true")
    p.add_argument("--skip-gopher", action="store_true")
    p.add_argument("--skip-gemini", action="store_true")
    p.add_argument("--skip-firewall", action="store_true")
    p.add_argument("--skip-backfill", action="store_true")
    p.add_argument("--skip-services", action="store_true")
    p.add_argument("--skip-system-config", action="store_true")
    p.add_argument("--users-json", type=Path, default=DEFAULT_USERS_JSON)
    p.add_argument("--homes-root", type=Path, default=DEFAULT_HOMES_ROOT)
    p.add_argument("--gemini-hostname", default=DEFAULT_GEMINI_HOSTNAME)
    p.add_argument("--gemini-cert", type=Path, default=None)
    p.add_argument("--gemini-key", type=Path, default=None)
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log = setup_logging(args.verbose)

    if os.geteuid() != 0 and not args.dry_run:
        log.error("Execute como root (sudo).")
        return 1

    cert = args.gemini_cert or DEFAULT_LE_CERT
    key = args.gemini_key or DEFAULT_LE_KEY

    try:
        backfill_users = resolve_backfill_users(args.users_json, args.homes_root, log)
    except (FileNotFoundError, ImportError) as e:
        log.error("%s", e)
        return 1

    if not args.skip_gemini:
        ensure_le_tls_readable_for_molly(cert, key, dry_run=args.dry_run, log=log)

    pkgs: list[str] = []
    if not args.skip_install:
        if not args.skip_gopher:
            pkgs.extend(PACKAGES_GOPHER)
        if not args.skip_gemini:
            pkgs.extend(PACKAGES_GEMINI)
        pkgs = sorted(set(pkgs))
        if pkgs:
            log.info("instalação apt: %s", ", ".join(pkgs))
            if not apt_install(tuple(pkgs), dry_run=args.dry_run, log=log):
                return 1

    if not args.skip_system_config:
        env_key = infer_gopher_env_key(GOPHER_SYSTEMD_SERVICE)
        opts = default_gopher_options(args.gemini_hostname)

        if not args.skip_gopher:
            if args.force and GOPHER_DEFAULT_PATH.is_file():
                backup_if_exists(GOPHER_DEFAULT_PATH, log, args.dry_run)
            write_gophernicus_default(
                GOPHER_DEFAULT_PATH,
                opts,
                env_key=env_key,
                dry_run=args.dry_run,
                log=log,
                force=args.force,
            )
            if not args.dry_run:
                GOPHER_ROOT.mkdir(parents=True, exist_ok=True)
                os.chmod(GOPHER_ROOT, 0o755)
                root_map = GOPHER_ROOT / "gophermap"
                gmap_body = build_root_gophermap_text(
                    args.gemini_hostname,
                    args.homes_root,
                    backfill_users,
                )
                if not root_map.exists() or args.force:
                    if root_map.exists() and args.force:
                        backup_if_exists(root_map, log, dry_run=False)
                    root_map.write_text(gmap_body, encoding="utf-8")
                    os.chmod(root_map, 0o644)
                    n_menu = sum(1 for ln in gmap_body.splitlines() if ln.startswith("1~"))
                    log.info("gophermap raiz: %s (%d entradas ~user)", root_map, n_menu)

        if not args.dry_run:
            GEMINI_ROOT.mkdir(parents=True, exist_ok=True)
            GEMINI_USERS.mkdir(parents=True, exist_ok=True)
            os.chmod(GEMINI_ROOT, 0o755)
            os.chmod(GEMINI_USERS, 0o755)
            try:
                os.chown(GEMINI_ROOT, 0, 0)
                os.chown(GEMINI_USERS, 0, 0)
            except OSError as e:
                log.warning("chown /var/gemini: %s", e)

            if not args.skip_gemini:
                gemi_root = GEMINI_ROOT / "index.gmi"
                gemi_body = build_root_gemini_index_gmi(
                    args.gemini_hostname,
                    args.homes_root,
                    backfill_users,
                )
                if not gemi_root.exists() or args.force:
                    if gemi_root.exists() and args.force:
                        backup_if_exists(gemi_root, log, dry_run=False)
                    gemi_root.write_text(gemi_body, encoding="utf-8")
                    os.chmod(gemi_root, 0o644)
                    try:
                        os.chown(gemi_root, 0, 0)
                    except OSError as e:
                        log.warning("chown %s: %s", gemi_root, e)
                    log.info("index.gmi DocBase raiz: %s", gemi_root)

        if not args.skip_gemini:
            if not cert.is_file() or not key.is_file():
                log.error(
                    "Certificado ou chave TLS inexistentes (Gemini/molly-brown). "
                    "cert=%s key=%s — defina --gemini-cert / --gemini-key ou instale Let's Encrypt. "
                    "Pastas /var/gemini foram criadas; serviço Gemini não será ativado.",
                    cert,
                    key,
                )
            else:
                retire_molly_brown_logs_dropin(
                    dry_run=args.dry_run,
                    log=log,
                    force=args.force,
                )
                access_p, error_p = ensure_molly_log_files(
                    MOLLY_INSTANCE,
                    dry_run=args.dry_run,
                    log=log,
                )
                conf_path = MOLLY_CONF_DIR / f"{MOLLY_INSTANCE}.conf"
                body = molly_brown_conf_text(
                    hostname=args.gemini_hostname,
                    cert=cert,
                    key=key,
                    access_log=access_p,
                    error_log=error_p,
                )
                if args.dry_run:
                    log.info("[dry-run] gravaria %s", conf_path)
                else:
                    MOLLY_CONF_DIR.mkdir(parents=True, exist_ok=True)
                    if conf_path.is_file() and args.force:
                        backup_if_exists(conf_path, log, dry_run=False)
                    if not conf_path.is_file() or args.force:
                        conf_path.write_text(body, encoding="utf-8")
                        os.chmod(conf_path, 0o644)
                        log.info("molly-brown: %s", conf_path)

    ufw_maybe_allow(
        [(70, "gopher"), (1965, "gemini")],
        dry_run=args.dry_run,
        log=log,
        skip_firewall=args.skip_firewall,
    )

    if not args.skip_backfill:
        for u in backfill_users:
            ensure_user_public_dirs(
                u,
                args.homes_root,
                force=args.force,
                dry_run=args.dry_run,
                log=log,
            )
            ensure_gemini_bind_mount(
                u,
                args.homes_root,
                force=args.force,
                dry_run=args.dry_run,
                log=log,
            )

    if not args.skip_services:
        if not args.dry_run:
            run_cmd(["systemctl", "daemon-reload"], dry_run=False, log=log)
        if not args.skip_gopher:
            run_cmd(
                ["systemctl", "enable", "--now", "gophernicus.socket"],
                dry_run=args.dry_run,
                log=log,
            )
        if not args.skip_gemini and cert.is_file() and key.is_file():
            molly_unit = f"molly-brown@{MOLLY_INSTANCE}.service"
            run_cmd(
                ["systemctl", "enable", "--now", molly_unit],
                dry_run=args.dry_run,
                log=log,
            )
            wait_for_unit_active(
                molly_unit,
                log=log,
                dry_run=args.dry_run,
                attempts=15,
                delay_s=1.0,
            )

    validate_final(backfill_users, log, dry_run=args.dry_run)
    log.info("Concluído.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
