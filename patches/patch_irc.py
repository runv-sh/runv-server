#!/usr/bin/env python3
"""
Provisiona a rede IRC da casa (estilo tilde.club) e o comando «chat» para utilizadores.

O conjunto ``IRC_PATCH_SKIP_USERS`` também é usado por ``resolve_all_users`` para o
backfill Gopher/Gemini (``setup_alt_protocols.py``): contas listadas não recebem
bind mount em ``/var/gemini/users/<user>`` nem entram no menu Gopher/Gemini raiz.

- Config em ~/.config/weechat (XDG), servidor interno «runv», TLS, autoconnect só nele.
- Outros servidores existentes mantêm-se; apenas ``irc.server.<outro>.autoconnect`` fica ``off``.
- Aplicação **só** via ``weechat-headless`` (-a, -r, --stdout) no patch; o launcher ``chat`` não usa -a.
- Instala /usr/local/bin/chat (launcher) salvo --skip-launcher.

MOTD e runv-help referem apenas **chat** (sem expor outros nomes de comando ao utilizador).

Executar como root no Debian; detalhes em docs/05-tools-and-system-experience.md.
SASL/NickServ: ver constante ``SASL_WEECHAT_SNIPPETS`` e https://weechat.org/doc/

Versão 0.04 — runv.club
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import pwd
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

_PATCHES_DIR = Path(__file__).resolve().parent
_ADMIN_DIR = _PATCHES_DIR.parent / "scripts" / "admin"
if str(_ADMIN_DIR) not in sys.path:
    sys.path.insert(0, str(_ADMIN_DIR))

from admin_guard import ensure_admin_cli

# SASL ainda não entra no patch; quando entrar, é na mão no WeeChat com sec.data (nada de
# password em claro neste repo). Isto é só o boneco dos comandos, para não ir buscar à memória.
SASL_WEECHAT_SNIPPETS: Final[tuple[str, ...]] = (
    "/set irc.server.<name>.sasl_mechanism plain",
    "/secure set runv_irc_senha ...",
    '/set irc.server.<name>.sasl_password "${sec.data.runv_irc_senha}"',
)

VERSION: Final[str] = "0.04"

DEFAULT_USERS_JSON: Final[Path] = Path("/var/lib/runv/users.json")
DEFAULT_HOMES_ROOT: Final[Path] = Path("/home")
DEFAULT_HOST: Final[str] = "irc.tilde.chat"
DEFAULT_PORT_TLS: Final[int] = 6697
DEFAULT_SERVER_NAME: Final[str] = "runv"
DEFAULT_AUTOJOIN: Final[str] = "#runv"

MIN_UID_USER: Final[int] = 1000

IRC_PATCH_SKIP_USERS: Final[frozenset[str]] = frozenset(
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
        "entre",
        "pmurad-admin",
        "admin",
        "postmaster",
    }
)

CHAT_DEST: Final[Path] = Path("/usr/local/bin/chat")


def setup_logging(verbose: bool) -> logging.Logger:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    return logging.getLogger("patch_irc")


def require_root(log: logging.Logger) -> None:
    if os.geteuid() != 0:
        log.error("Execute como root (sudo).")
        sys.exit(1)


def run_cmd(
    cmd: list[str],
    *,
    dry_run: bool,
    log: logging.Logger,
    timeout: int = 180,
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


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def launcher_source_path() -> Path:
    return repo_root() / "tools" / "bin" / "chat"


def embedded_launcher_text() -> str:
    return """#!/bin/sh
# runv.club — fallback mínimo (preferir tools/bin/chat do repositório)
IRC_UI=""
for c in weechat weechat-curses; do
  command -v "$c" >/dev/null 2>&1 && IRC_UI=$c && break
done
if [ -z "$IRC_UI" ]; then
  for p in /usr/bin/weechat-curses /usr/bin/weechat; do
    [ -x "$p" ] && IRC_UI=$p && break
  done
fi
if [ -z "$IRC_UI" ]; then
  echo "runv: instale weechat-curses (apt) ou corra tools/tools.py." >&2
  exit 127
fi
CONFIG_DIR="${WEECHAT_HOME:-$HOME/.config/weechat}"
exec "$IRC_UI" -d "$CONFIG_DIR" "$@"
"""


def install_chat_launcher(*, dry_run: bool, log: logging.Logger) -> bool:
    src = launcher_source_path()
    if dry_run:
        log.info("[dry-run] instalaria %s -> %s", src if src.is_file() else "(embutido)", CHAT_DEST)
        return True
    CHAT_DEST.parent.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        shutil.copy2(src, CHAT_DEST)
    else:
        log.warning("origem %s inexistente; escrevo launcher mínimo embutido", src)
        CHAT_DEST.write_text(embedded_launcher_text(), encoding="utf-8")
    os.chmod(CHAT_DEST, 0o755)
    try:
        os.chown(CHAT_DEST, 0, 0)
    except OSError as e:
        log.warning("chown em %s: %s", CHAT_DEST, e)
    log.info("launcher: %s", CHAT_DEST)
    return True


def find_weechat_headless(log: logging.Logger) -> str | None:
    """Apenas weechat-headless — o patch não usa cliente interactivo."""
    p = shutil.which("weechat-headless")
    if p:
        log.debug("binário de provisionamento IRC: %s", p)
    return p


def load_usernames_from_json(path: Path, log: logging.Logger) -> list[str] | None:
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        data = json.loads(raw)
        if not isinstance(data, list):
            log.warning("%s: JSON não é lista; ignoro.", path)
            return None
        names: list[str] = []
        for item in data:
            if isinstance(item, dict):
                u = item.get("username")
                if isinstance(u, str) and u:
                    names.append(u)
        return sorted(set(names))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("falha ao ler %s: %s — uso fallback /home", path, e)
        return None


def usernames_from_homes(homes_root: Path, log: logging.Logger) -> list[str]:
    names: list[str] = []
    if not homes_root.is_dir():
        log.warning("homes_root inexistente: %s", homes_root)
        return []
    for entry in sorted(homes_root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        try:
            pw = pwd.getpwnam(entry.name)
        except KeyError:
            continue
        if pw.pw_uid < MIN_UID_USER:
            continue
        if entry.name in IRC_PATCH_SKIP_USERS:
            continue
        names.append(entry.name)
    return sorted(set(names))


def resolve_all_users(users_json: Path, homes_root: Path, log: logging.Logger) -> list[str]:
    from_json = load_usernames_from_json(users_json, log)
    from_homes = usernames_from_homes(homes_root, log)

    if from_json is None:
        log.info("utilizadores a partir de %s (%d); JSON indisponível", homes_root, len(from_homes))
        return from_homes

    if not from_json:
        log.info("%s vazio — só homes em %s (%d)", users_json, homes_root, len(from_homes))
        return from_homes

    merged = sorted(set(from_json) | set(from_homes))
    log.info(
        "utilizadores: união %s (%d) + %s (%d) → %d contas",
        users_json,
        len(from_json),
        homes_root,
        len(from_homes),
        len(merged),
    )
    return [u for u in merged if u not in IRC_PATCH_SKIP_USERS]


def weechat_config_dir(home: Path) -> Path:
    return home / ".config" / "weechat"


def parse_all_server_names(irc_conf_text: str) -> set[str]:
    """Nomes de servidor na secção [server] (prefixos antes do primeiro '.' na chave)."""
    names: set[str] = set()
    in_server = False
    for raw in irc_conf_text.splitlines():
        line = raw.strip()
        if line == "[server]":
            in_server = True
            continue
        if line.startswith("[") and line.endswith("]"):
            in_server = False
            continue
        if not in_server or not line or line.startswith("#") or "=" not in line:
            continue
        key_part = line.split("=", 1)[0].strip()
        if "." not in key_part:
            continue
        srv, _sub = key_part.split(".", 1)
        if srv:
            names.add(srv)
    return names


def parse_server_options(irc_conf_text: str, server: str) -> dict[str, str]:
    opts: dict[str, str] = {}
    in_server = False
    prefix = f"{server}."
    for raw in irc_conf_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "[server]":
            in_server = True
            continue
        if line.startswith("[") and line.endswith("]"):
            in_server = False
            continue
        if not in_server:
            continue
        if not line.startswith(prefix):
            continue
        key_part, _, rest = line.partition("=")
        key_part = key_part.strip()
        val = rest.strip()
        if len(key_part) <= len(prefix):
            continue
        sub = key_part[len(prefix) :]
        if val.startswith('"') and val.endswith('"') and len(val) >= 2:
            val = val[1:-1]
        opts[sub] = val
    return opts


def tls_effective(opts: dict[str, str]) -> bool:
    v = (opts.get("tls") or opts.get("ssl") or "off").lower()
    return v in ("on", "true", "yes", "1")


def autoconnect_enabled(opts: dict[str, str]) -> bool:
    ac = (opts.get("autoconnect") or "off").lower()
    return ac in ("on", "true", "yes", "1")


def expected_nicks(username: str) -> str:
    return f"{username},{username}_,{username}__,{username}|away"


def runv_server_options_match(
    opts: dict[str, str],
    *,
    host: str,
    port: int,
    tls: bool,
    unix_username: str,
    autojoin: str,
    log: logging.Logger,
) -> bool:
    if "addresses" not in opts:
        return False
    addr = opts["addresses"].lower()
    expect_addr = f"{host.lower()}/{port}"
    if addr != expect_addr:
        log.debug("addresses %r != %r", addr, expect_addr)
        return False
    if tls_effective(opts) != tls:
        log.debug("tls/ssl diverge")
        return False
    if opts.get("nicks") != expected_nicks(unix_username):
        log.debug("nicks divergem")
        return False
    if (opts.get("username") or "") != unix_username:
        return False
    if (opts.get("realname") or "") != unix_username:
        return False
    if not autoconnect_enabled(opts):
        return False
    aj = opts.get("autojoin") or ""
    if aj != autojoin:
        log.debug("autojoin %r != %r", aj, autojoin)
        return False
    return True


def non_primary_servers_autoconnect_all_off(
    irc_conf_text: str,
    primary: str,
    log: logging.Logger,
) -> bool:
    for name in parse_all_server_names(irc_conf_text):
        if name == primary:
            continue
        o = parse_server_options(irc_conf_text, name)
        if not o.get("addresses"):
            continue
        if autoconnect_enabled(o):
            log.debug("servidor %r tem autoconnect on (deveria off)", name)
            return False
    return True


def config_matches(
    irc_conf: Path,
    *,
    server: str,
    host: str,
    port: int,
    tls: bool,
    unix_username: str,
    autojoin: str,
    log: logging.Logger,
) -> bool:
    if not irc_conf.is_file():
        return False
    try:
        text = irc_conf.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log.debug("ler %s: %s", irc_conf, e)
        return False
    opts = parse_server_options(text, server)
    if not runv_server_options_match(
        opts,
        host=host,
        port=port,
        tls=tls,
        unix_username=unix_username,
        autojoin=autojoin,
        log=log,
    ):
        return False
    return non_primary_servers_autoconnect_all_off(text, server, log)


def build_disable_other_autoconnect_chain(irc_conf_text: str, primary: str) -> str:
    """Comandos /set para desligar autoconnect em servidores != primary (só onde está on)."""
    parts: list[str] = []
    for name in sorted(parse_all_server_names(irc_conf_text)):
        if name == primary:
            continue
        o = parse_server_options(irc_conf_text, name)
        if not o.get("addresses"):
            continue
        if not autoconnect_enabled(o):
            continue
        parts.append(f"/set irc.server.{name}.autoconnect off")
    return " ; ".join(parts)


def build_apply_command_chain(
    *,
    server: str,
    host: str,
    port: int,
    tls: bool,
    unix_username: str,
    autojoin: str,
) -> str:
    # Sem -autoconnect no /server add: autoconnect via /set (requisito runv).
    add_cmd = f"/server add {server} {host}/{port}"
    if tls:
        add_cmd += " -tls"
    parts: list[str] = [add_cmd]
    nicks = expected_nicks(unix_username)
    parts.append(f'/set irc.server.{server}.nicks "{nicks}"')
    parts.append(f'/set irc.server.{server}.username "{unix_username}"')
    parts.append(f'/set irc.server.{server}.realname "{unix_username}"')
    parts.append(f"/set irc.server.{server}.autoconnect on")
    if autojoin:
        parts.append(f'/set irc.server.{server}.autojoin "{autojoin}"')
    else:
        parts.append(f'/set irc.server.{server}.autojoin ""')
    parts.append("/set irc.look.buffer_switch_join on")
    parts.append("/set irc.look.server_buffer independent")
    parts.append(
        '/set buflist.look.display_conditions "${buffer.plugin} == irc && ${type} == channel"'
    )
    parts.append("/save")
    parts.append("/quit")
    return " ; ".join(parts)


def chain_with_save_quit(prefix_chain: str) -> str:
    p = prefix_chain.strip()
    if p:
        return f"{p} ; /save ; /quit"
    return "/save ; /quit"


def merge_command_chains(*parts: str) -> str:
    return " ; ".join(s.strip() for s in parts if s and s.strip())


def ensure_xdg_weechat_dir(home: Path, uid: int, gid: int, log: logging.Logger, dry_run: bool) -> Path:
    xdg = home / ".config"
    weechat_d = weechat_config_dir(home)
    if dry_run:
        log.info("[dry-run] garantiria dirs %s e %s (700, dono %d:%d)", xdg, weechat_d, uid, gid)
        return weechat_d
    if not home.is_dir():
        raise FileNotFoundError(f"home inexistente: {home}")
    if not xdg.is_dir():
        xdg.mkdir(parents=True, exist_ok=True)
        os.chmod(xdg, 0o700)
        os.chown(xdg, uid, gid)
    elif xdg.stat().st_uid != uid:
        log.warning("%s não pertence a uid %d; não altero dono do .config inteiro", xdg, uid)
    if not weechat_d.is_dir():
        weechat_d.mkdir(parents=True, exist_ok=True)
        os.chmod(weechat_d, 0o700)
        os.chown(weechat_d, uid, gid)
    else:
        os.chmod(weechat_d, 0o700)
        try:
            os.chown(weechat_d, uid, gid)
        except OSError as e:
            log.warning("chown %s: %s", weechat_d, e)
    return weechat_d


def run_weechat_script(
    *,
    username: str,
    home: Path,
    weechat_bin: str,
    command_chain: str,
    dry_run: bool,
    log: logging.Logger,
    allow_failure: bool = False,
) -> bool:
    runuser = shutil.which("runuser")
    if not runuser:
        log.error("runuser não encontrado (pacote util-linux).")
        return False
    weechat_dir = weechat_config_dir(home)
    cmd: list[str] = [
        runuser,
        "-u",
        username,
        "--",
        weechat_bin,
        "-d",
        str(weechat_dir),
        "-a",
        "--stdout",
        "-r",
        command_chain,
    ]
    r = run_cmd(cmd, dry_run=dry_run, log=log)
    if dry_run:
        return True
    assert r is not None
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        msg = f"weechat-headless código {r.returncode} para {username}: {out.strip() or '(sem saída)'}"
        if allow_failure:
            log.debug("%s (ignorado)", msg)
            return True
        log.error("%s", msg)
        return False
    if out.strip():
        log.debug("weechat-headless saída (%s): %s", username, out.strip()[:2000])
    return True


def patch_user(
    username: str,
    *,
    host: str,
    port: int,
    tls: bool,
    server: str,
    autojoin: str,
    force: bool,
    weechat_bin: str,
    dry_run: bool,
    log: logging.Logger,
) -> bool:
    try:
        pw = pwd.getpwnam(username)
    except KeyError:
        log.error("utilizador inexistente: %s", username)
        return False
    if username in IRC_PATCH_SKIP_USERS:
        log.warning("utilizador reservado, ignorado: %s", username)
        return False
    if pw.pw_uid < MIN_UID_USER:
        log.warning("UID < %d, ignorado: %s", MIN_UID_USER, username)
        return False

    home = Path(pw.pw_dir)
    uid, gid = pw.pw_uid, pw.pw_gid
    try:
        ensure_xdg_weechat_dir(home, uid, gid, log, dry_run)
    except OSError as e:
        log.error("%s: %s", username, e)
        return False

    irc_conf = weechat_config_dir(home) / "irc.conf"
    conf_text = ""
    if irc_conf.is_file():
        try:
            conf_text = irc_conf.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            log.debug("%s: ler %s: %s", username, irc_conf, e)

    if not force and config_matches(
        irc_conf,
        server=server,
        host=host,
        port=port,
        tls=tls,
        unix_username=username,
        autojoin=autojoin,
        log=log,
    ):
        log.info("%s: IRC já conforme (runv + sem autoconnect noutros) — no-op", username)
        return True

    opts_runv = parse_server_options(conf_text, server)
    runv_ok = runv_server_options_match(
        opts_runv,
        host=host,
        port=port,
        tls=tls,
        unix_username=username,
        autojoin=autojoin,
        log=log,
    )
    others_ok = non_primary_servers_autoconnect_all_off(conf_text, server, log)

    disable_others = build_disable_other_autoconnect_chain(conf_text, server)

    if not force and runv_ok and not others_ok:
        log.info("%s: só desligar autoconnect noutros servidores", username)
        chain = chain_with_save_quit(disable_others)
        ok = run_weechat_script(
            username=username,
            home=home,
            weechat_bin=weechat_bin,
            command_chain=chain,
            dry_run=dry_run,
            log=log,
        )
        if ok and not dry_run and irc_conf.is_file():
            try:
                os.chown(irc_conf, uid, gid)
            except OSError:
                pass
        return ok

    server_exists = bool(opts_runv.get("addresses"))

    if server_exists and (force or not runv_ok):
        del_chain = f"/server del {server} ; /quit"
        if force:
            log.info("%s: remover servidor %s existente (--force)", username, server)
        else:
            log.info("%s: realinhar servidor «%s» (remove e volta a criar)", username, server)
        run_weechat_script(
            username=username,
            home=home,
            weechat_bin=weechat_bin,
            command_chain=del_chain,
            dry_run=dry_run,
            log=log,
            allow_failure=True,
        )
        if not dry_run and irc_conf.is_file():
            try:
                conf_text = irc_conf.read_text(encoding="utf-8", errors="replace")
            except OSError:
                conf_text = ""
        disable_others = build_disable_other_autoconnect_chain(conf_text, server)

    apply_chain = build_apply_command_chain(
        server=server,
        host=host,
        port=port,
        tls=tls,
        unix_username=username,
        autojoin=autojoin,
    )
    # apply_chain já termina em /save;/quit — prefixar desligar outros antes do /server add.
    full_chain = merge_command_chains(disable_others, apply_chain)
    log.info("%s: aplicar configuração IRC — servidor «%s» (weechat-headless)", username, server)
    ok = run_weechat_script(
        username=username,
        home=home,
        weechat_bin=weechat_bin,
        command_chain=full_chain,
        dry_run=dry_run,
        log=log,
    )
    if not ok:
        return False
    if not dry_run and irc_conf.is_file():
        try:
            os.chown(irc_conf, uid, gid)
        except OSError:
            pass
    return True


def validate_post(
    sample_user: str | None,
    *,
    host: str,
    port: int,
    tls: bool,
    server: str,
    autojoin: str,
    log: logging.Logger,
) -> None:
    if not CHAT_DEST.is_file() or not os.access(CHAT_DEST, os.X_OK):
        log.warning("validação: %s em falta ou não executável", CHAT_DEST)
    else:
        log.info("validação: launcher %s OK", CHAT_DEST)
    if not sample_user:
        return
    try:
        pw = pwd.getpwnam(sample_user)
    except KeyError:
        return
    irc_conf = weechat_config_dir(Path(pw.pw_dir)) / "irc.conf"
    if not irc_conf.is_file():
        log.warning("validação: %s sem %s", sample_user, irc_conf)
        return
    if config_matches(
        irc_conf,
        server=server,
        host=host,
        port=port,
        tls=tls,
        unix_username=sample_user,
        autojoin=autojoin,
        log=log,
    ):
        log.info("validação: %s — runv=%s/%s TLS=%s autoconnect+autojoin OK; outros sem autoconnect", sample_user, host, port, tls)
        return
    log.warning("validação: %s — config não passa em todas as verificações (ver patch / irc.conf)", sample_user)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Provisiona IRC (servidor runv, weechat-headless) e instala o comando chat.",
    )
    p.add_argument("--dry-run", action="store_true", help="só mostrar o plano")
    p.add_argument("--verbose", action="store_true", help="log detalhado")
    p.add_argument("--force", action="store_true", help="reconfigurar mesmo se existir servidor divergente")
    p.add_argument("--skip-launcher", action="store_true", help="não instalar /usr/local/bin/chat")
    p.add_argument("--skip-backfill", action="store_true", help="não aplicar config por utilizador")
    p.add_argument("--users-json", type=Path, default=DEFAULT_USERS_JSON, metavar="PATH")
    p.add_argument("--homes-root", type=Path, default=DEFAULT_HOMES_ROOT, metavar="PATH")
    p.add_argument("--host", default=DEFAULT_HOST, help="hostname IRC")
    p.add_argument(
        "--port",
        type=int,
        default=None,
        metavar="PORT",
        help=f"porta (omissão: {DEFAULT_PORT_TLS} com TLS, 6667 sem TLS)",
    )
    tls_g = p.add_mutually_exclusive_group()
    tls_g.add_argument("--tls", dest="tls", action="store_true", help="usar TLS (padrão)")
    tls_g.add_argument("--no-tls", dest="tls", action="store_false", help="IRC sem TLS")
    p.set_defaults(tls=True)
    p.add_argument(
        "--server-name",
        default=DEFAULT_SERVER_NAME,
        metavar="NAME",
        help="nome interno na config IRC (equivalente a /server add …)",
    )
    p.add_argument(
        "--autojoin",
        default=DEFAULT_AUTOJOIN,
        metavar="CHANNEL",
        help=(
            f'canal único por omissão ({DEFAULT_AUTOJOIN!r}); '
            'use --autojoin "" para não autoentrar em canais'
        ),
    )
    ug = p.add_mutually_exclusive_group(required=True)
    ug.add_argument("--user", metavar="USER", help="apenas este utilizador Unix")
    ug.add_argument("--all-users", action="store_true", help="todos os utilizadores válidos")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ensure_admin_cli(
        script_name=Path(__file__).name,
        dry_run=bool(args.dry_run),
    )
    log = setup_logging(args.verbose)

    if args.port is None:
        port = DEFAULT_PORT_TLS if args.tls else 6667
    else:
        port = args.port

    if not args.dry_run:
        require_root(log)
    else:
        log.info("dry-run: não grava alterações.")

    if not args.skip_launcher:
        install_chat_launcher(dry_run=args.dry_run, log=log)

    weechat_bin = find_weechat_headless(log)
    if not args.skip_backfill and not weechat_bin:
        log.error(
            "weechat-headless não encontrado no PATH; instale o pacote Debian «weechat-headless» (ex.: apt).",
        )
        return 1

    if args.all_users:
        users = resolve_all_users(args.users_json, args.homes_root, log)
    else:
        assert args.user is not None
        users = [args.user]

    failures = 0
    autojoin = args.autojoin.strip()
    if not args.skip_backfill:
        assert weechat_bin is not None
        for u in users:
            if u in IRC_PATCH_SKIP_USERS:
                log.warning("ignorado (reservado): %s", u)
                continue
            ok = patch_user(
                u,
                host=args.host,
                port=port,
                tls=args.tls,
                server=args.server_name,
                autojoin=autojoin,
                force=args.force,
                weechat_bin=weechat_bin,
                dry_run=args.dry_run,
                log=log,
            )
            if not ok:
                failures += 1
    else:
        log.info("backfill ignorado (--skip-backfill).")

    sample = users[0] if users else None
    validate_post(
        sample,
        host=args.host,
        port=port,
        tls=args.tls,
        server=args.server_name,
        autojoin=autojoin,
        log=log,
    )

    print()
    print("========== patch_irc — resumo ==========")
    print(f"Modo: {'DRY-RUN' if args.dry_run else 'aplicação'}")
    print(f"Host: {args.host}:{port}  TLS: {args.tls}  servidor na config: {args.server_name}")
    print(f"Autojoin (só runv): {autojoin if autojoin else '(nenhum)'}")
    if not args.skip_backfill:
        print(f"Utilizadores processados: {len(users)}  falhas: {failures}")
    print("Comando para utilizadores: chat")
    print("========================================")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
