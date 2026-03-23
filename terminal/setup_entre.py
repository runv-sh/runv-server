#!/usr/bin/env python3
"""
Prepara infraestrutura do utilizador «entre» e instala o módulo terminal em
/opt/runv/terminal.

Onboarding estilo tilde.town (join@tilde.town):
  O padrão documentado por tilde.town usa utilizador especial + Match User + SSH com
  PasswordAuthentication, PermitEmptyPasswords yes, PubkeyAuthentication no, e muitas vezes
  uma linha em /etc/pam.d/sshd com pam_succeed_if (ex.: user ingroup join) para que a
  autenticação PAM não exija palavra-passe para esse grupo. Não é «sem autenticação» no
  protocolo: é aceitar palavra-passe vazia / sucesso PAM antecipado só para essa conta
  e políticas explícitas. Deliberadamente menos seguro — usar só para onboarding público,
  não para contas normais.

Modo recomendado (default): --auth-mode shared-password
  Palavra-passe Unix partilhada + ForceCommand.

Modo --auth-mode empty-password (primeira classe):
  Replica o espírito tilde.town para «entre»: senha vazia (passwd -d), grupo suplementar
  (omissão: entre-open), e por omissão drop-in com AuthenticationMethods keyboard-interactive
  + KbdInteractiveAuthentication yes (PAM pam_succeed_if sem prompts) — compatível com
  OpenSSH do Windows, que em geral não envia palavra-passe vazia no método password.
  Por omissão altera /etc/pam.d/sshd (pam_succeed_if user ingroup …) com backup — no Debian,
  sem isto o PAM recusa o fluxo e a sessão pode fechar. Use --skip-pam-empty-password-rule
  só se configurar PAM à mão.
  Para o esquema README tilde (password + PermitEmptyPasswords yes), use
  --empty-password-tilde-password-auth (Linux/Git Bash).

Porque /bin/sh e não nologin:
  O OpenSSH usa o shell de passwd no contexto do login; nologin impede o fluxo até ao
  ForceCommand. Use /bin/sh; o visitante não fica com shell interactivo normal.

Por defeito (sem --skip-sshd):
  - cria «entre» com /bin/sh; chsh se já existir com outro shell;
  - em empty-password: grupo onboarding, membro, passwd -d, validação NP, regra PAM (por omissão);
  - escreve runv-entre.conf; sshd -t; sshd -T -C …; reload ssh.

Use --skip-sshd / --no-reload / --dry-run conforme necessário.

Executar como root no servidor Debian.

Reexecução: com instalação existente, em TTY pede confirmação antes de actualizar o módulo
  e (em separado) antes de substituir config.toml; use --yes / --force-config para automatizar.

Versão 0.11 — runv.club
"""

from __future__ import annotations

import argparse
import grp
import os
import pwd
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Final

from gen_config_toml import write_terminal_config_toml  # type: ignore

VERSION: Final[str] = "0.11"
ENTRE_USER: Final[str] = "entre"
INSTALL_ROOT: Final[Path] = Path("/opt/runv/terminal")
QUEUE_DIR: Final[Path] = Path("/var/lib/runv/entre-queue")
LOG_DIR: Final[Path] = Path("/var/log/runv")
SSHD_DROPIN: Final[Path] = Path("/etc/ssh/sshd_config.d/runv-entre.conf")
PAM_SSHD: Final[Path] = Path("/etc/pam.d/sshd")
MODULE_SRC: Final[Path] = Path(__file__).resolve().parent

AUTH_SHARED: Final[str] = "shared-password"
AUTH_KEY: Final[str] = "key-only"
AUTH_EMPTY: Final[str] = "empty-password"

# Grupo suplementar para PAM pam_succeed_if (tilde.town usa «join»; aqui «entre-open»).
ENTRE_EMPTY_PASSWORD_GROUP_DEFAULT: Final[str] = "entre-open"

INSECURE_EMPTY_BANNER: Final[str] = """
******************************************************************************
* AVISO: modo empty-password — onboarding estilo tilde.town / join@tilde.town   *
* Não é «SSH sem autenticação»: é palavra-passe vazia + políticas só para «entre». *
* Qualquer cliente que alcance o porto SSH pode entrar nesta conta.            *
* Não use para contas normais nem exponha sem firewall / política consciente.   *
******************************************************************************
"""


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def prompt_yes(question: str, *, default: bool) -> bool:
    """Confirmação em TTY; fora de TTY devolve ``default``."""
    if not sys.stdin.isatty():
        return default
    suffix = "[S/n]" if default else "[s/N]"
    try:
        raw = input(f"{question}{suffix} ").strip().lower()
    except EOFError:
        return default
    if not raw:
        return default
    return raw in ("s", "sim", "y", "yes")


def require_root() -> None:
    if os.geteuid() != 0:
        eprint("Execute como root (sudo).")
        raise SystemExit(1)


def run(cmd: list[str], *, timeout: int = 120) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(f"Falhou: {' '.join(cmd)}\n{err}")


def run_capture(cmd: list[str], *, timeout: int = 120) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(f"Falhou: {' '.join(cmd)}\n{err}")
    return (r.stdout or "").strip()


def user_exists(name: str) -> bool:
    try:
        pwd.getpwnam(name)
    except KeyError:
        return False
    return True


def group_exists(name: str) -> bool:
    try:
        grp.getgrnam(name)
    except KeyError:
        return False
    return True


def user_in_group(username: str, group_name: str) -> bool:
    try:
        g = grp.getgrnam(group_name)
    except KeyError:
        return False
    if username in g.gr_mem:
        return True
    try:
        pw = pwd.getpwnam(username)
    except KeyError:
        return False
    return pw.pw_gid == g.gr_gid


def ensure_onboarding_group(
    group_name: str,
    *,
    dry_run: bool,
) -> None:
    if dry_run:
        print(f"[dry-run] groupadd -f {group_name!r} (se não existir)")
        return
    if not group_exists(group_name):
        run(["groupadd", group_name])
        print(f"Criado grupo {group_name!r}.")
    else:
        print(f"Grupo {group_name!r} já existe.")


def ensure_user_in_onboarding_group(group_name: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] usermod -aG {group_name} {ENTRE_USER}")
        return
    if user_in_group(ENTRE_USER, group_name):
        print(f"{ENTRE_USER!r} já está no grupo {group_name!r}.")
        return
    run(["usermod", "-aG", group_name, ENTRE_USER])
    print(f"Adicionado {ENTRE_USER!r} ao grupo {group_name!r}.")


def pam_line_for_onboarding_group(group_name: str) -> str:
    return (
        "auth [success=done default=ignore] pam_succeed_if.so "
        f"user ingroup {group_name}"
    )


def install_pam_empty_password_rule(
    group_name: str,
    *,
    dry_run: bool,
) -> None:
    """
    Insere regra tilde.town-style antes da autenticação PAM padrão (ex.: @include common-auth).
    Backup: /etc/pam.d/sshd.bak.<timestamp>
    """
    line = pam_line_for_onboarding_group(group_name)
    marker = f"runv.club setup_entre.py — onboarding {group_name}"
    block = (
        f"# {marker}\n"
        f"{line}\n"
    )

    if dry_run:
        print(f"[dry-run] backup + inserir em {PAM_SSHD}:\n{line}")
        return

    if not PAM_SSHD.is_file():
        raise RuntimeError(f"{PAM_SSHD} não existe; não é possível instalar regra PAM.")

    current = PAM_SSHD.read_text(encoding="utf-8", errors="replace")
    if line in current:
        print(f"Regra PAM já presente em {PAM_SSHD} (saltar).")
        return

    backup = PAM_SSHD.with_name(f"{PAM_SSHD.name}.bak.{int(time.time())}")
    shutil.copy2(PAM_SSHD, backup)
    print(f"Backup PAM: {backup}")

    lines = current.splitlines(keepends=True)
    insert_at = 0
    for i, raw in enumerate(lines):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("@include") or re.match(r"^auth\s", s):
            insert_at = i
            break
        insert_at = i + 1

    part1 = [lines[j] for j in range(insert_at)]
    part2 = [lines[j] for j in range(insert_at, len(lines))]
    new_body = "".join(part1) + block + "".join(part2)
    PAM_SSHD.write_text(new_body, encoding="utf-8")
    print(f"Inserida regra PAM em {PAM_SSHD} (antes da auth padrão).")


def ensure_user_entre(*, home: Path, shell: str) -> None:
    if user_exists(ENTRE_USER):
        print(f"Utilizador {ENTRE_USER!r} já existe.")
        return
    run(
        [
            "useradd",
            "--create-home",
            "--home-dir",
            str(home),
            "--shell",
            shell,
            "--user-group",
            ENTRE_USER,
        ]
    )
    print(f"Criado utilizador {ENTRE_USER!r} (shell {shell!r}).")


def ensure_entre_shell(shell: str, *, dry_run: bool) -> None:
    """Garante shell em passwd (ex.: migração de contas antigas com nologin)."""
    if dry_run:
        return
    pw = pwd.getpwnam(ENTRE_USER)
    if pw.pw_shell == shell:
        return
    run(["chsh", "-s", shell, ENTRE_USER])
    print(f"Shell de {ENTRE_USER!r} actualizado de {pw.pw_shell!r} para {shell!r}.")


def ensure_entre_dot_ssh(home: Path, uid: int, gid: int, *, dry_run: bool) -> None:
    """Garante ~/.ssh/authorized_keys com modos correctos (ficheiro pode ficar vazio)."""
    if dry_run:
        print(f"[dry-run] garantiria {home}/.ssh e authorized_keys")
        return
    home.mkdir(parents=True, exist_ok=True)
    try:
        os.chown(home, uid, gid)
    except OSError:
        pass
    ssh = home / ".ssh"
    ssh.mkdir(mode=0o700, exist_ok=True)
    os.chmod(ssh, 0o700)
    os.chown(ssh, uid, gid)
    auth = ssh / "authorized_keys"
    if not auth.exists():
        auth.write_text("", encoding="utf-8")
    os.chmod(auth, 0o600)
    os.chown(auth, uid, gid)
    print(f"Garantido {ssh} e {auth} (dono {ENTRE_USER}).")


def clear_entre_password(*, dry_run: bool) -> None:
    """Palavra-passe vazia (modo empty-password)."""
    if dry_run:
        print("[dry-run] passwd -d entre (palavra-passe vazia)")
        return
    run(["passwd", "-d", ENTRE_USER])
    print(f"Palavra-passe de {ENTRE_USER!r} removida (passwd -d).")


def assert_entre_password_empty(*, dry_run: bool) -> None:
    """Estado NP em passwd -S (sem palavra-passe utilizável)."""
    if dry_run:
        print("[dry-run] validaria passwd -S entre (esperado NP)")
        return
    out = run_capture(["passwd", "-S", ENTRE_USER], timeout=30)
    parts = out.split()
    if len(parts) < 2:
        raise RuntimeError(f"passwd -S inesperado: {out!r}")
    status = parts[1]
    if status != "NP":
        raise RuntimeError(
            f"Esperava estado NP (sem palavra-passe) após passwd -d; obtido {status!r} "
            f"em «{out}». Verifique bloqueios (usermod -U) ou política de palavras-passe."
        )
    print(f"passwd -S: {ENTRE_USER!r} está NP (sem palavra-passe utilizável).")


def build_sshd_dropin_content(
    python_path: str,
    app_path: Path,
    auth_mode: str,
    *,
    empty_ssh_auth: str | None = None,
) -> str:
    cmd = f"{python_path} {app_path}"
    header = (
        f"# Instalado por runv.club setup_entre.py — auth_mode={auth_mode}\n"
        f"# Validar: sshd -t\n"
    )
    if auth_mode == AUTH_EMPTY:
        header += "# Onboarding tilde.town-style: PAM pam_succeed_if + conta especial entre.\n"

    lines = [
        header.rstrip(),
        f"Match User {ENTRE_USER}",
    ]

    if auth_mode == AUTH_SHARED:
        lines.extend(
            [
                "    AuthenticationMethods password",
                "    PasswordAuthentication yes",
                "    KbdInteractiveAuthentication no",
                "    PubkeyAuthentication no",
                "    PermitEmptyPasswords no",
            ]
        )
    elif auth_mode == AUTH_KEY:
        lines.extend(
            [
                "    AuthenticationMethods publickey",
                "    PasswordAuthentication no",
                "    KbdInteractiveAuthentication no",
                "    PubkeyAuthentication yes",
                "    PermitEmptyPasswords no",
            ]
        )
    elif auth_mode == AUTH_EMPTY:
        # Omissão: keyboard-interactive + PAM (compatível com OpenSSH Windows; sem senha vazia no wire).
        # tilde-password: como README tilde (password + PermitEmptyPasswords); Linux/Git Bash.
        if empty_ssh_auth == "password":
            lines.extend(
                [
                    "    AuthenticationMethods password",
                    "    PasswordAuthentication yes",
                    "    KbdInteractiveAuthentication no",
                    "    PubkeyAuthentication no",
                    "    PermitEmptyPasswords yes",
                ]
            )
        else:
            lines.extend(
                [
                    "    AuthenticationMethods keyboard-interactive",
                    "    PasswordAuthentication no",
                    "    KbdInteractiveAuthentication yes",
                    "    PubkeyAuthentication no",
                    "    PermitEmptyPasswords no",
                ]
            )
    else:
        raise ValueError(f"auth_mode desconhecido: {auth_mode!r}")

    lines.extend(
        [
            f"    ForceCommand {cmd}",
            "    PermitTTY yes",
            "    PermitUserRC no",
            "    X11Forwarding no",
            "    AllowAgentForwarding no",
            "    AllowTcpForwarding no",
            "    PermitTunnel no",
            "    DisableForwarding yes",
            "",
        ]
    )
    return "\n".join(lines)


def parse_sshd_t(output: str) -> dict[str, str]:
    cfg: dict[str, str] = {}
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 1:
            cfg[parts[0].lower()] = ""
        else:
            cfg[parts[0].lower()] = parts[1].strip()
    return cfg


def _norm_ws(s: str) -> str:
    return " ".join(s.split())


def validate_effective_sshd(
    *,
    conn: str,
    force_command: str,
    auth_mode: str,
    empty_ssh_auth: str | None = None,
) -> None:
    """Confirma opções efectivas para Match User entre via sshd -T -C."""
    try:
        out = run_capture(["sshd", "-T", "-C", conn], timeout=60)
    except RuntimeError as e:
        raise RuntimeError(
            "Validação sshd -T -C falhou (sshd inacessível ou -C inválido?). "
            f"Detalhe: {e}"
        ) from e

    cfg = parse_sshd_t(out)
    errs: list[str] = []

    fc_eff = _norm_ws(cfg.get("forcecommand", ""))
    fc_exp = _norm_ws(force_command)
    if not fc_eff or (fc_eff != fc_exp and fc_exp not in fc_eff and fc_eff not in fc_exp):
        errs.append(f"forcecommand: esperado «{fc_exp}», efectivo «{fc_eff}»")

    if cfg.get("permittty", "").lower() != "yes":
        errs.append(f"permittty: esperado yes, efectivo «{cfg.get('permittty', '')}»")

    if cfg.get("disableforwarding", "").lower() != "yes":
        errs.append(
            f"disableforwarding: esperado yes, efectivo «{cfg.get('disableforwarding', '')}»"
        )

    if "permituserrc" in cfg and cfg.get("permituserrc", "").lower() != "no":
        errs.append(f"permituserrc: esperado no, efectivo «{cfg.get('permituserrc', '')}»")

    am = cfg.get("authenticationmethods", "").lower().replace(",", " ")
    pw = cfg.get("passwordauthentication", "").lower()
    pk = cfg.get("pubkeyauthentication", "").lower()
    kbd = cfg.get("kbdinteractiveauthentication", "").lower()
    empty = cfg.get("permitemptypasswords", "").lower()

    if auth_mode == AUTH_SHARED:
        if "password" not in am.split():
            errs.append(f"authenticationmethods: esperado incluir password, efectivo «{am}»")
        if pw != "yes":
            errs.append(f"passwordauthentication: esperado yes, efectivo «{pw}»")
        if pk != "no":
            errs.append(f"pubkeyauthentication: esperado no, efectivo «{pk}»")
        if kbd != "no":
            errs.append(f"kbdinteractiveauthentication: esperado no, efectivo «{kbd}»")
        if empty != "no":
            errs.append(f"permitemptypasswords: esperado no, efectivo «{empty}»")
    elif auth_mode == AUTH_KEY:
        if "publickey" not in am.split():
            errs.append(f"authenticationmethods: esperado incluir publickey, efectivo «{am}»")
        if pw != "no":
            errs.append(f"passwordauthentication: esperado no, efectivo «{pw}»")
        if pk != "yes":
            errs.append(f"pubkeyauthentication: esperado yes, efectivo «{pk}»")
        if empty != "no":
            errs.append(f"permitemptypasswords: esperado no, efectivo «{empty}»")
    elif auth_mode == AUTH_EMPTY:
        if empty_ssh_auth == "password":
            if "password" not in am.split():
                errs.append(f"authenticationmethods: esperado incluir password, efectivo «{am}»")
            if pw != "yes":
                errs.append(f"passwordauthentication: esperado yes, efectivo «{pw}»")
            if pk != "no":
                errs.append(f"pubkeyauthentication: esperado no, efectivo «{pk}»")
            if kbd != "no":
                errs.append(f"kbdinteractiveauthentication: esperado no, efectivo «{kbd}»")
            if empty != "yes":
                errs.append(f"permitemptypasswords: esperado yes, efectivo «{empty}»")
        else:
            if "keyboard-interactive" not in am.split():
                errs.append(
                    f"authenticationmethods: esperado incluir keyboard-interactive, efectivo «{am}»"
                )
            if pw != "no":
                errs.append(f"passwordauthentication: esperado no, efectivo «{pw}»")
            if kbd != "yes":
                errs.append(
                    f"kbdinteractiveauthentication: esperado yes, efectivo «{kbd}»"
                )
            if pk != "no":
                errs.append(f"pubkeyauthentication: esperado no, efectivo «{pk}»")
            if empty != "no":
                errs.append(f"permitemptypasswords: esperado no, efectivo «{empty}»")

    if errs:
        raise RuntimeError(
            "Validação pós-configuração (sshd -T -C) falhou:\n  - "
            + "\n  - ".join(errs)
        )


def sshd_main_config_mentions_dropin() -> bool:
    main = Path("/etc/ssh/sshd_config")
    if not main.is_file():
        return False
    try:
        text = main.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "sshd_config.d" in text and "Include" in text


def apply_sshd_configuration(
    python_path: str,
    app_path: Path,
    *,
    install_root: Path,
    auth_mode: str,
    sshd_test_connection: str,
    empty_ssh_auth: str | None,
    dry_run: bool,
    skip_sshd: bool,
    no_reload: bool,
) -> None:
    force_cmd = f"{python_path} {app_path}"
    content = build_sshd_dropin_content(
        python_path, app_path, auth_mode, empty_ssh_auth=empty_ssh_auth
    )

    if skip_sshd:
        print()
        print("== Modo --skip-sshd: configure o SSH manualmente ==")
        print(
            "1. Opcional: editar",
            install_root / "config.toml",
            "— admin_email pode ficar vazio se /etc/runv-email.json já tiver admin_email; From padrão noreply@runv.club.",
        )
        print("2. Criar /etc/ssh/sshd_config.d/… com o bloco abaixo.")
        print("3. sshd -t && systemctl reload ssh")
        print("4. empty-password: regra PAM por omissão (ou --skip-pam-empty-password-rule).")
        print("5. Testar conforme --auth-mode.")
        print()
        print(content)
        return

    if dry_run:
        print(f"[dry-run] escreveria {SSHD_DROPIN} e correria sshd -t + validação -T")
        print("--- conteúdo ---")
        print(content)
        return

    if not sshd_main_config_mentions_dropin():
        print(
            "AVISO: /etc/ssh/sshd_config pode não incluir /etc/ssh/sshd_config.d/*.conf.\n"
            "  Confirme uma linha «Include … sshd_config.d» ou o drop-in não será lido.",
            file=sys.stderr,
        )

    SSHD_DROPIN.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if SSHD_DROPIN.is_file():
        backup = SSHD_DROPIN.with_name(f"{SSHD_DROPIN.name}.bak.{int(time.time())}")
        shutil.copy2(SSHD_DROPIN, backup)
        print(f"Backup do drop-in anterior: {backup}")

    SSHD_DROPIN.write_text(content, encoding="utf-8")
    SSHD_DROPIN.chmod(0o644)
    print(f"Escrito {SSHD_DROPIN}")

    def revert() -> None:
        if backup is not None:
            shutil.copy2(backup, SSHD_DROPIN)
            print(f"Revertido {SSHD_DROPIN} a partir de {backup}.", file=sys.stderr)
        else:
            try:
                SSHD_DROPIN.unlink()
            except OSError:
                pass
            print(f"Removido {SSHD_DROPIN}.", file=sys.stderr)

    try:
        run(["sshd", "-t"])
    except RuntimeError as e:
        revert()
        raise RuntimeError("sshd -t falhou após instalar drop-in; configuração revertida.") from e

    print("sshd -t: OK.")

    try:
        validate_effective_sshd(
            conn=sshd_test_connection,
            force_command=force_cmd,
            auth_mode=auth_mode,
            empty_ssh_auth=empty_ssh_auth,
        )
    except RuntimeError as e:
        revert()
        raise RuntimeError(
            f"{e}\nConfiguração revertida; corrija o Match User ou a string -C de teste."
        ) from e

    print(f"Validação efectiva sshd -T -C {sshd_test_connection!r}: OK.")

    if no_reload:
        print("Saltado reload (--no-reload). Execute: systemctl reload ssh")
        return

    try:
        run(["systemctl", "reload", "ssh"], timeout=60)
    except RuntimeError:
        try:
            run(["systemctl", "reload", "sshd"], timeout=60)
        except RuntimeError as e2:
            raise RuntimeError(
                "sshd -t e validação passaram mas falhou systemctl reload ssh/sshd; "
                "recarregue o serviço SSH manualmente."
            ) from e2
    print("Serviço SSH recarregado (reload).")


def copy_module(dest: Path, *, dry_run: bool) -> None:
    files = [
        "entre_app.py",
        "entre_core.py",
        "closed_app.py",
        "close_entre.py",
        "config.example.toml",
        "gen_config_toml.py",
        "README.md",
    ]
    subdirs = ["templates", "docs", "systemd", "scripts", "data", "examples"]
    if dry_run:
        print(f"[dry-run] copiaria para {dest}")
        return
    dest.mkdir(parents=True, exist_ok=True)
    for name in files:
        src = MODULE_SRC / name
        if src.is_file():
            shutil.copy2(src, dest / name)
    for sd in subdirs:
        s = MODULE_SRC / sd
        if s.is_dir():
            d = dest / sd
            if d.exists():
                shutil.rmtree(d)
            shutil.copytree(s, d)
    print(f"Módulo copiado para {dest}")


def install_config(dest: Path, *, dry_run: bool, force: bool) -> None:
    cfg = dest / "config.toml"
    example = dest / "config.example.toml"
    if dry_run:
        print(f"[dry-run] config em {cfg} (gen_config_toml)")
        return
    if not example.is_file():
        eprint(f"Aviso: {example} não encontrado.")
        return
    try:
        result = write_terminal_config_toml(
            example=example, out=cfg, force=force, dry_run=False
        )
    except FileNotFoundError as e:
        eprint(str(e))
        return
    if result == "skipped":
        print(f"Mantido {cfg} existente (use --force-config para regenerar do example).")
    else:
        print(f"Instalado {cfg} (gen_config_toml a partir do example).")


def chmod_tree_templates(root: Path) -> None:
    t = root / "templates"
    if not t.is_dir():
        return
    for p in t.rglob("*"):
        if p.is_file():
            p.chmod(0o644)


def print_final_instructions(
    *,
    auth_mode: str,
    install_root: Path,
    empty_group: str,
    pam_installed: bool,
    empty_ssh_auth: str | None,
) -> None:
    print()
    print("== Concluído ==")
    print(
        f"1. Opcional: {install_root / 'config.toml'} — regenere com "
        f"python3 {install_root / 'gen_config_toml.py'} --install-root {install_root} "
        "(ou --force para repor o example). Com /etc/runv-email.json, admin_email pode ficar vazio no TOML."
    )

    if auth_mode == AUTH_SHARED:
        print("2. Acesso por palavra-passe Unix partilhada (definida só pelo root):")
        print(f"      sudo passwd {ENTRE_USER}")
        print("   ou: echo 'entre:A_SENHA' | sudo chpasswd")
        print("3. Testar:")
        print("      ssh entre@runv.club")
    elif auth_mode == AUTH_KEY:
        auth_keys = Path(pwd.getpwnam(ENTRE_USER).pw_dir) / ".ssh" / "authorized_keys"
        print("2. Colocar chaves públicas em (uma linha por chave):")
        print(f"      {auth_keys}")
        print("3. Testar:")
        print("      ssh entre@runv.club")
    elif auth_mode == AUTH_EMPTY:
        print(INSECURE_EMPTY_BANNER)
        print("2. Onboarding estilo join@tilde.town:")
        print(f"   - Conta {ENTRE_USER!r} sem palavra-passe utilizável (passwd -d; estado NP).")
        print(f"   - Grupo suplementar {empty_group!r} (para alinhar com PAM pam_succeed_if).")
        if pam_installed:
            print(f"   - PAM: linha ingroup {empty_group!r} em /etc/pam.d/sshd (com backup .bak.*).")
        else:
            print("   - PAM: saltado (--skip-pam-empty-password-rule). No Debian o login com")
            print("     senha vazia falha sem pam_succeed_if antes de common-auth; volte a correr")
            print("     o setup sem --skip-pam ou edite /etc/pam.d/sshd à mão.")
        if empty_ssh_auth == "password":
            print("3. Testar (Enter em branco no prompt de palavra-passe):")
            print("      ssh entre@runv.club")
            print("   Nota: OpenSSH do Windows em geral não envia palavra-passe vazia neste modo.")
            print("   Use WSL/Git Bash, ou volte a correr o setup sem --empty-password-tilde-password-auth")
            print("   (omissão: keyboard-interactive, mais compatível com Windows).")
        else:
            print("3. Testar (omissão: keyboard-interactive + PAM; pode não pedir palavra-passe):")
            print("      ssh entre@runv.club")
            print("   Se aparecer prompt, tente Enter em branco; em Windows este modo costuma funcionar.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Setup utilizador entre + /opt/runv/terminal + OpenSSH (automatizado).",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="não perguntar em reinstalação; combinar com --force-config para repor config.toml sem prompt",
    )
    parser.add_argument("--force-config", action="store_true", help="sobrescrever config.toml com example")
    parser.add_argument("--home", type=Path, default=Path(f"/home/{ENTRE_USER}"))
    parser.add_argument(
        "--shell",
        default="/bin/sh",
        help="shell em passwd (ForceCommand precisa de shell funcional; não use nologin)",
    )
    parser.add_argument(
        "--auth-mode",
        choices=[AUTH_SHARED, AUTH_KEY, AUTH_EMPTY],
        default=AUTH_SHARED,
        help="método SSH para «entre» (empty-password = onboarding tilde.town-style)",
    )
    parser.add_argument(
        "--empty-password-group",
        default=ENTRE_EMPTY_PASSWORD_GROUP_DEFAULT,
        metavar="GRUPO",
        help=f"grupo suplementar em empty-password + PAM ingroup (default: {ENTRE_EMPTY_PASSWORD_GROUP_DEFAULT})",
    )
    parser.add_argument(
        "--empty-password-tilde-password-auth",
        action="store_true",
        help="empty-password: password + PermitEmptyPasswords (README tilde); omissão usa "
        "keyboard-interactive (melhor no OpenSSH do Windows)",
    )
    parser.add_argument(
        "--skip-pam-empty-password-rule",
        action="store_true",
        help="não alterar /etc/pam.d/sshd (empty-password: sem PAM, Debian costuma fechar a sessão)",
    )
    parser.add_argument(
        "--install-pam-empty-password-rule",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--sshd-test-connection",
        default="user=entre,host=runv.club,addr=127.0.0.1",
        help="argumento -C para sshd -T na validação pós-config (user/host/addr do Match)",
    )
    parser.add_argument("--install-root", type=Path, default=INSTALL_ROOT)
    parser.add_argument("--queue-dir", type=Path, default=QUEUE_DIR)
    parser.add_argument("--skip-copy", action="store_true", help="não copiar ficheiros do módulo")
    parser.add_argument(
        "--skip-sshd",
        action="store_true",
        help="não escrever drop-in nem recarregar SSH; imprime bloco para cópia manual",
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="após sshd -t e validação -T, não executar systemctl reload",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    args = parser.parse_args()

    if args.empty_password_tilde_password_auth and args.auth_mode != AUTH_EMPTY:
        eprint("--empty-password-tilde-password-auth só com --auth-mode empty-password.")
        return 2

    empty_ssh_auth: str | None
    if args.auth_mode == AUTH_EMPTY:
        empty_ssh_auth = (
            "password" if args.empty_password_tilde_password_auth else "keyboard-interactive"
        )
    else:
        empty_ssh_auth = None

    if args.auth_mode == AUTH_EMPTY:
        print(INSECURE_EMPTY_BANNER, file=sys.stderr)
        if args.skip_pam_empty_password_rule:
            eprint(
                "AVISO: --skip-pam-empty-password-rule — em Debian/Ubuntu o stack PAM em "
                "sshd recusa palavra-passe vazia sem pam_succeed_if; espere «Connection closed» "
                "após o prompt se não configurar PAM à mão."
            )

    require_root()

    ir = args.install_root
    qd = args.queue_dir
    empty_group = args.empty_password_group.strip()
    if not empty_group:
        eprint("--empty-password-group não pode ser vazio.")
        return 2

    existing_module = (ir / "entre_app.py").is_file()
    if (
        existing_module
        and not args.skip_copy
        and not args.dry_run
        and not args.yes
    ):
        if sys.stdin.isatty():
            if not prompt_yes(
                f"Já existe instalação em {ir} (ficheiros do módulo serão actualizados; "
                f"config.toml só se pedir abaixo ou usar --force-config). Continuar? ",
                default=True,
            ):
                print("Operação cancelada.")
                return 0
        else:
            print(
                f"Aviso: instalação existente em {ir}; a actualizar sem prompt "
                f"(TTY ausente). Use --dry-run para simular ou --yes para suprimir avisos."
            )

    pam_done = False
    apply_pam_empty = (
        args.auth_mode == AUTH_EMPTY
        and not args.skip_pam_empty_password_rule
    )

    if not args.skip_copy:
        copy_module(ir, dry_run=args.dry_run)
        force_cfg = bool(args.force_config)
        cfg_path = ir / "config.toml"
        if (
            cfg_path.is_file()
            and not force_cfg
            and not args.dry_run
            and not args.yes
            and sys.stdin.isatty()
        ):
            if prompt_yes(
                f"Manter {cfg_path} com as suas definições (recomendado) ou substituir "
                f"por config.example.toml (repor mail_from noreply@runv.club, etc.)? Substituir? ",
                default=False,
            ):
                force_cfg = True
        install_config(ir, dry_run=args.dry_run, force=force_cfg)
        if not args.dry_run:
            chmod_tree_templates(ir)

    if not args.dry_run:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        qd.mkdir(parents=True, mode=0o750, exist_ok=True)
        ensure_user_entre(home=args.home, shell=args.shell)
        ensure_entre_shell(args.shell, dry_run=False)

        pw = pwd.getpwnam(ENTRE_USER)
        uid, gid = pw.pw_uid, pw.pw_gid
        entre_home = Path(pw.pw_dir)
        ensure_entre_dot_ssh(entre_home, uid, gid, dry_run=False)

        if args.auth_mode == AUTH_EMPTY:
            ensure_onboarding_group(empty_group, dry_run=False)
            ensure_user_in_onboarding_group(empty_group, dry_run=False)
            clear_entre_password(dry_run=False)
            assert_entre_password_empty(dry_run=False)
            if apply_pam_empty:
                install_pam_empty_password_rule(empty_group, dry_run=False)
                pam_done = True

        os.chown(qd, uid, gid)
        qd.chmod(0o700)

        log_path = LOG_DIR / "entre.log"
        if not log_path.exists():
            log_path.touch(mode=0o640)
        os.chown(log_path, uid, gid)
        log_path.chmod(0o640)

        if ir.exists():
            for root, dirs, files in os.walk(ir, followlinks=False):
                for name in dirs + files:
                    p = Path(root) / name
                    try:
                        os.chown(p, uid, gid, follow_symlinks=False)
                    except OSError:
                        pass
            try:
                os.chown(ir, uid, gid)
            except OSError:
                pass
            ir.chmod(0o750)
    else:
        print("[dry-run] utilizador entre, fila, log e .ssh seriam garantidos (sem alterar sistema).")
        if args.auth_mode == AUTH_EMPTY:
            ensure_onboarding_group(empty_group, dry_run=True)
            ensure_user_in_onboarding_group(empty_group, dry_run=True)
            clear_entre_password(dry_run=True)
            assert_entre_password_empty(dry_run=True)
            if apply_pam_empty:
                install_pam_empty_password_rule(empty_group, dry_run=True)

    py = shutil.which("python3") or "/usr/bin/python3"
    app = ir / "entre_app.py"

    try:
        apply_sshd_configuration(
            py,
            app,
            install_root=ir,
            auth_mode=args.auth_mode,
            sshd_test_connection=args.sshd_test_connection,
            empty_ssh_auth=empty_ssh_auth,
            dry_run=args.dry_run,
            skip_sshd=args.skip_sshd,
            no_reload=args.no_reload,
        )
    except RuntimeError as e:
        eprint(str(e))
        return 1

    if not args.skip_sshd and not args.dry_run:
        print_final_instructions(
            auth_mode=args.auth_mode,
            install_root=ir,
            empty_group=empty_group,
            pam_installed=pam_done,
            empty_ssh_auth=empty_ssh_auth,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
