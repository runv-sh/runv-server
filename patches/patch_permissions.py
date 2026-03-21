#!/usr/bin/env python3
"""
runv.club — privacidade em /home e drop-in SSH para confinamento (ChrootDirectory).

Dois níveis (resumo do modelo POSIX/OpenSSH):

1. **Privacidade entre utilizadores** — não impede «cd ..»; apenas impede listar/entrar nas
   homes alheias: ``chmod 711 /home`` e ``chmod 700`` em cada ``/home/<user>``.

2. **Confinamento real** — ``Match Group`` + ``ChrootDirectory /srv/jail/%u``; o caminho do
   chroot e ascendentes devem ser **root-owned** e não graváveis por outros (requisito do
   sshd). ``rbash`` sozinho não substitui jail/container.

Este script **não** constrói um jail completo (libs, /dev, etc.); aplica ou documenta o
drop-in e as permissões de /home. Debian 13 · Python 3 stdlib · sem shell=True.

Executar como root em produção. Ver ``--help``.
"""

from __future__ import annotations

import argparse
import grp
import os
import pwd
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Final

VERSION: Final[str] = "0.01"

GROUP_NAME: Final[str] = "runv-jailed"
SSHD_DROPIN: Final[str] = "/etc/ssh/sshd_config.d/runv-jailed.conf"
HOME_ROOT: Final[str] = "/home"
JAIL_ROOT: Final[str] = "/srv/jail"

SSHD_BLOCK: Final[str] = f"""# runv.club — grupo {GROUP_NAME}: shell dentro de ChrootDirectory
# Requisitos sshd: {JAIL_ROOT}/<user> e todos os ascendentes owned por root, sem escrita
# para grupo/outros; dentro do jail é preciso árvore mínima executável (ex. /bin/sh).
# Validar: sshd -t && systemctl reload ssh

Match Group {GROUP_NAME}
    ChrootDirectory {JAIL_ROOT}/%u
    ForceCommand /bin/sh
    X11Forwarding no
    AllowTcpForwarding no
    AllowAgentForwarding no
    PermitTunnel no
    DisableForwarding yes
"""

CHROOT_NOTES: Final[str] = """
=== ChrootDirectory (OpenSSH) — notas ===

- «cd ..» com permissões Unix normais não se «proíbe»; ou restringe-se visibilidade
  (r/x em diretórios) ou usa-se confinamento real (chroot, container, zone).

- ChrootDirectory exige que o directório do chroot e **todos** os componentes do caminho
  até à raiz sejam propriedade de root e **não** graváveis por grupo nem outros.

- Não use ChrootDirectory apontando para a home do próprio utilizador se essa home for
  dele e gravável — o sshd rejeita ou quebra o modelo de segurança.

- Layout típico para utilizador «alice»:

    /srv/jail/alice           root:root   0755   (raiz do chroot)
    /srv/jail/alice/home      alice:alice 0700   (área gravável; cd ~)

  O utilizador em passwd pode continuar a ter home «/home/alice» no sistema real, mas
  dentro do chroot o shell vê a raiz em /srv/jail/alice; costuma montar-se ou replicar-se
  binários, libs e dispositivos mínimos sob /srv/jail/alice (ou usar abordagem com
  container em vez de chroot «manual»).

- Quem **não** estiver no grupo runv-jailed não recebe este Match e mantém sessão normal
  (ex.: administrador com conta fora do grupo).

- rbash não é substituto de jail; ver manual do Bash (restricted shell).
"""


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def require_root() -> None:
    if os.geteuid() != 0:
        eprint("Execute como root (sudo).")
        raise SystemExit(1)


def run(cmd: list[str], *, timeout: int = 120) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(f"Falhou: {' '.join(cmd)}\n{err}")


def sshd_main_config_mentions_dropin() -> bool:
    main = Path("/etc/ssh/sshd_config")
    if not main.is_file():
        return False
    try:
        text = main.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "sshd_config.d" in text and "Include" in text


def apply_sshd_dropin(*, dry_run: bool, no_reload: bool) -> None:
    path = Path(SSHD_DROPIN)
    if dry_run:
        print(f"[dry-run] escreveria {path}")
        print(SSHD_BLOCK)
        print("[dry-run] sshd -t && systemctl reload ssh")
        return

    if not sshd_main_config_mentions_dropin():
        eprint(
            "AVISO: /etc/ssh/sshd_config pode não incluir /etc/ssh/sshd_config.d/*.conf.\n"
            "  Confirme uma linha «Include … sshd_config.d»."
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if path.is_file():
        backup = path.with_name(f"{path.name}.bak.{int(time.time())}")
        shutil.copy2(path, backup)
        print(f"Backup: {backup}")

    path.write_text(SSHD_BLOCK, encoding="utf-8")
    path.chmod(0o644)
    print(f"Escrito {path}")

    def revert() -> None:
        if backup is not None:
            shutil.copy2(backup, path)
            eprint(f"Revertido {path}")
        else:
            path.unlink(missing_ok=True)
            eprint(f"Removido {path}")

    try:
        run(["sshd", "-t"])
    except RuntimeError as e:
        revert()
        raise SystemExit(f"sshd -t falhou; configuração revertida.\n{e}") from e
    print("sshd -t: OK.")

    if no_reload:
        print("Saltado reload; execute: systemctl reload ssh")
        return
    try:
        run(["systemctl", "reload", "ssh"], timeout=60)
    except RuntimeError:
        try:
            run(["systemctl", "reload", "sshd"], timeout=60)
        except RuntimeError as e2:
            raise SystemExit(
                "sshd -t OK mas falhou systemctl reload ssh/sshd; recarregue manualmente."
            ) from e2
    print("Serviço SSH recarregado.")


def ensure_group(*, dry_run: bool) -> None:
    try:
        grp.getgrnam(GROUP_NAME)
        print(f"Grupo «{GROUP_NAME}» já existe.")
        return
    except KeyError:
        pass
    if dry_run:
        print(f"[dry-run] groupadd {GROUP_NAME}")
        return
    run(["groupadd", GROUP_NAME])
    print(f"Criado grupo «{GROUP_NAME}».")


def apply_home_privacy(
    *,
    dry_run: bool,
    home_path: Path,
    exclude: frozenset[str],
) -> None:
    if not home_path.is_dir():
        raise SystemExit(f"Não é directório: {home_path}")

    if dry_run:
        print(f"[dry-run] chmod 711 {home_path}")
    else:
        os.chmod(home_path, 0o711)
        print(f"chmod 711 {home_path}")

    for child in sorted(home_path.iterdir(), key=lambda p: p.name):
        if child.name in exclude:
            print(f"Omitido (—exclude): {child}")
            continue
        if not child.is_dir():
            continue
        if dry_run:
            print(f"[dry-run] chmod 700 {child}")
        else:
            os.chmod(child, 0o700)
            print(f"chmod 700 {child}")

    print()
    print("Verificação sugerida: ls -ld /home /home/*")


def scaffold_jail_tree(username: str, *, dry_run: bool) -> None:
    """Cria apenas a árvore mínima de directórios e donos; não copia binários/libs."""
    try:
        pw = pwd.getpwnam(username)
    except KeyError as e:
        raise SystemExit(f"Utilizador «{username}» não existe em passwd.") from e

    jail = Path(JAIL_ROOT) / username
    jail_home = jail / "home"

    if dry_run:
        print(f"[dry-run] mkdir -p {jail_home}")
        print(f"[dry-run] chown root:root {jail} && chmod 755 {jail}")
        print(
            f"[dry-run] chown {pw.pw_uid}:{pw.pw_gid} {jail_home} && chmod 700 {jail_home}"
        )
        return

    jail_home.parent.mkdir(parents=True, exist_ok=True)
    jail_home.mkdir(parents=True, exist_ok=True)
    os.chown(jail, 0, 0)
    os.chmod(jail, 0o755)
    os.chown(jail_home, pw.pw_uid, pw.pw_gid)
    os.chmod(jail_home, 0o700)
    print(f"Criado {jail} (root:root 755) e {jail_home} ({username}, 700).")
    eprint(
        "Aviso: para shell interactivo no chroot ainda precisa de /bin/sh, libs e "
        "normalmente /dev dentro do jail — este comando só cria directórios vazios."
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Permissões /home + drop-in SSH Match Group runv-jailed (ChrootDirectory)."
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra acções sem escrever no sistema (exceto --print-chroot-notes).",
    )
    p.add_argument(
        "--apply-ssh",
        action="store_true",
        help=f"Instala {SSHD_DROPIN} com Match Group {GROUP_NAME}.",
    )
    p.add_argument(
        "--apply-home",
        action="store_true",
        help=f"chmod 711 {HOME_ROOT} e 700 em cada subdirectório (privacidade básica).",
    )
    p.add_argument(
        "--ensure-group",
        action="store_true",
        help=f"Cria o grupo {GROUP_NAME} se não existir (groupadd).",
    )
    p.add_argument(
        "--no-reload",
        action="store_true",
        help="Após sshd -t, não executa systemctl reload ssh.",
    )
    p.add_argument(
        "--home-root",
        type=Path,
        default=Path(HOME_ROOT),
        help=f"Raiz das homes (omissão: {HOME_ROOT}).",
    )
    p.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="NAME",
        help="Nome de entrada em /home a omitir no chmod 700 (repetível).",
    )
    p.add_argument(
        "--print-chroot-notes",
        action="store_true",
        help="Imprime notas sobre ChrootDirectory e layout /srv/jail.",
    )
    p.add_argument(
        "--scaffold-jail",
        metavar="USER",
        default=None,
        help=f"Cria {JAIL_ROOT}/USER e .../home com donos mínimos (sem binários).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.print_chroot_notes:
        print(CHROOT_NOTES.strip())
        if not any(
            [
                args.apply_ssh,
                args.apply_home,
                args.ensure_group,
                args.scaffold_jail,
            ]
        ):
            return

    want_any = (
        args.apply_ssh
        or args.apply_home
        or args.ensure_group
        or args.scaffold_jail is not None
    )
    if not want_any and not args.print_chroot_notes:
        eprint(
            "Indique pelo menos uma acção: --apply-ssh, --apply-home, --ensure-group, "
            "--scaffold-jail USER, ou --print-chroot-notes."
        )
        raise SystemExit(2)

    if want_any and not args.dry_run:
        require_root()

    excl = frozenset(args.exclude) if args.exclude else frozenset()

    if args.ensure_group:
        ensure_group(dry_run=args.dry_run)

    if args.apply_ssh:
        apply_sshd_dropin(dry_run=args.dry_run, no_reload=args.no_reload)

    if args.apply_home:
        apply_home_privacy(
            dry_run=args.dry_run,
            home_path=args.home_root,
            exclude=excl,
        )

    if args.scaffold_jail is not None:
        scaffold_jail_tree(args.scaffold_jail.strip(), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
