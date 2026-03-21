from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

RUNV_JAILED_GROUP = "runv-jailed"
JAIL_SKIP_USERNAMES = frozenset({"entre", "pmurad-admin"})
JAIL_ROOT = Path("/srv/jail")
FSTAB_PATH = Path("/etc/fstab")


def jail_skip_username(username: str) -> bool:
    return username in JAIL_SKIP_USERNAMES


def _run(cmd: list[str], *, log: logging.Logger) -> subprocess.CompletedProcess[str]:
    log.debug("exec: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600)


def ensure_runv_jailed_group(log: logging.Logger) -> None:
    r = _run(["groupadd", "-f", RUNV_JAILED_GROUP], log=log)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(f"groupadd -f {RUNV_JAILED_GROUP} falhou: {err}")


def ensure_user_in_jailed_group(username: str, log: logging.Logger) -> None:
    ensure_runv_jailed_group(log)
    r = _run(["getent", "group", RUNV_JAILED_GROUP], log=log)
    if r.returncode != 0 or not (r.stdout or "").strip():
        raise RuntimeError("grupo runv-jailed não existe após groupadd")
    line = (r.stdout or "").strip()
    members_field = line.split(":")[-1] if ":" in line else ""
    members = {m.strip() for m in members_field.split(",") if m.strip()}
    if username in members:
        log.debug("jail: %s já está em %s", username, RUNV_JAILED_GROUP)
        return
    r2 = _run(["usermod", "-aG", RUNV_JAILED_GROUP, username], log=log)
    if r2.returncode != 0:
        err = (r2.stderr or r2.stdout or "").strip()
        raise RuntimeError(f"usermod -aG {RUNV_JAILED_GROUP} {username}: {err}")
    log.info("jail: utilizador %s adicionado ao grupo %s", username, RUNV_JAILED_GROUP)


def fstab_bind_line(real_home: Path, jail_mount_point: Path) -> str:
    src = str(real_home.resolve())
    dst = str(jail_mount_point.resolve())
    return f"{src}\t{dst}\tnone\tbind,nofail\t0\t0\n"


def fstab_has_bind(real_home: Path, jail_mount_point: Path) -> bool:
    if not FSTAB_PATH.is_file():
        return False
    text = FSTAB_PATH.read_text(encoding="utf-8", errors="replace")
    src = str(real_home.resolve())
    dst = str(jail_mount_point.resolve())
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0] == src and parts[1] == dst:
            return True
    return False


def append_fstab_bind(real_home: Path, jail_mount_point: Path, log: logging.Logger) -> None:
    if fstab_has_bind(real_home, jail_mount_point):
        log.debug("jail: fstab já contém bind %s -> %s", real_home, jail_mount_point)
        return
    with open(FSTAB_PATH, "a", encoding="utf-8") as f:
        f.write(fstab_bind_line(real_home, jail_mount_point))
    log.info("jail: fstab atualizado (bind %s)", real_home.name)


def remove_fstab_bind(real_home: Path, jail_mount_point: Path, log: logging.Logger) -> bool:
    """Remove a linha de bind correspondente de ``/etc/fstab``. Devolve True se alterou o ficheiro."""
    if not FSTAB_PATH.is_file():
        return False
    src = str(real_home.resolve())
    dst = str(jail_mount_point.resolve())
    text = FSTAB_PATH.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    removed = False
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            out.append(line)
            continue
        parts = s.split()
        if len(parts) >= 2 and parts[0] == src and parts[1] == dst:
            removed = True
            log.info("jail: removida linha fstab bind %s -> %s", src, dst)
            continue
        out.append(line)
    if not removed:
        return False
    new_body = "".join(out)
    fd, tmp_name = tempfile.mkstemp(
        prefix="fstab.",
        suffix=".tmp",
        dir=str(FSTAB_PATH.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, FSTAB_PATH)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return True


def jail_bind_mountpoint(username: str) -> Path:
    """Caminho dentro do chroot onde a home real é montada (bind)."""
    return JAIL_ROOT / username / "home" / username


def remove_user_from_jailed_group(username: str, log: logging.Logger) -> None:
    """Remove o utilizador do grupo ``runv-jailed`` (idempotente)."""
    r = _run(["getent", "group", RUNV_JAILED_GROUP], log=log)
    if r.returncode != 0 or not (r.stdout or "").strip():
        log.debug("jail: grupo %s inexistente — nada a remover", RUNV_JAILED_GROUP)
        return
    line = (r.stdout or "").strip()
    members_field = line.split(":")[-1] if ":" in line else ""
    members = {m.strip() for m in members_field.split(",") if m.strip()}
    if username not in members:
        log.debug("jail: %s já não está em %s", username, RUNV_JAILED_GROUP)
        return
    r2 = _run(["gpasswd", "-d", username, RUNV_JAILED_GROUP], log=log)
    if r2.returncode != 0:
        err = (r2.stderr or r2.stdout or "").strip()
        raise RuntimeError(f"gpasswd -d {username} {RUNV_JAILED_GROUP}: {err}")
    log.info("jail: %s removido do grupo %s", username, RUNV_JAILED_GROUP)


def unbind_jail_home(jail_home: Path, log: logging.Logger) -> None:
    """Desmonta o bind em ``jail_home`` se estiver montado."""
    if not os.path.ismount(jail_home):
        log.debug("jail: %s não está montado", jail_home)
        return
    r = _run(["umount", str(jail_home.resolve())], log=log)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(f"umount {jail_home}: {err}")
    log.info("jail: desmontado bind em %s", jail_home)


def ensure_jail_layout(
    username: str,
    home: Path,
    log: logging.Logger,
    *,
    jk_profile: str = "extendedshell",
    no_jk_init: bool = False,
) -> Path:
    """
    Cria ``/srv/jail/user``, opcionalmente ``jk_init`` (perfil Jailkit), ``home/user``.
    Devolve o caminho do mountpoint do bind.
    """
    jail_root = JAIL_ROOT / username
    jail_root.mkdir(parents=True, exist_ok=True)
    os.chmod(jail_root, 0o755)
    try:
        os.chown(jail_root, 0, 0)
    except OSError as e:
        log.warning("jail: chown root em %s: %s", jail_root, e)
    marker = jail_root / "bin"
    if not marker.exists():
        if no_jk_init:
            raise RuntimeError(
                f"jail: {jail_root} sem layout Jailkit (falta bin/) e --no-jk-init foi pedido — "
                "crie o jail manualmente ou execute sem --no-jk-init."
            )
        if shutil.which("jk_init") is None:
            raise RuntimeError("jk_init não encontrado — instale jailkit e corra tools/tools.py")
        prof = (jk_profile or "extendedshell").strip()
        r = _run(["jk_init", "-j", str(jail_root), prof], log=log)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            raise RuntimeError(f"jk_init {prof!r} falhou: {err}")
        log.info("jail: jk_init %s em %s", prof, jail_root)
    else:
        log.debug("jail: %s já tem layout jk (bin presente)", jail_root)
    inner = jail_root / "home" / username
    inner.mkdir(parents=True, exist_ok=True)
    hp = inner.parent
    try:
        os.chmod(hp, 0o755)
        os.chown(hp, 0, 0)
        os.chown(inner, 0, 0)
    except OSError as e:
        log.warning("jail: permissões em %s: %s", inner, e)
    return inner


def ensure_bind_mount(real_home: Path, jail_home: Path, log: logging.Logger) -> None:
    if os.path.ismount(jail_home):
        log.debug("jail: %s já montado", jail_home)
        return
    r = _run(
        ["mount", "--bind", str(real_home.resolve()), str(jail_home.resolve())],
        log=log,
    )
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(f"mount --bind falhou: {err}")
    log.info("jail: bind mount %s -> %s", real_home, jail_home)


def ensure_runv_jail_for_user(
    username: str,
    home: Path,
    *,
    no_jail: bool,
    log: logging.Logger,
    jk_profile: str = "extendedshell",
    no_jk_init: bool = False,
) -> None:
    if no_jail:
        log.info("jail: omitido (--no-jail)")
        return
    if jail_skip_username(username):
        log.info("jail: omitido (conta excluída: %s)", username)
        return
    home = home.resolve()
    ensure_user_in_jailed_group(username, log)
    jail_home = ensure_jail_layout(
        username,
        home,
        log,
        jk_profile=jk_profile,
        no_jk_init=no_jk_init,
    )
    ensure_bind_mount(home, jail_home, log)
    append_fstab_bind(home, jail_home, log)
