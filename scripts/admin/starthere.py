#!/usr/bin/env python3
"""
starthere.py - bootstrap seguro para runv.club em Debian/ext4

O que faz:
- atualiza índices APT
- instala um conjunto conservador de pacotes úteis para o projeto
- faz limpeza segura (autoremove + autoclean)
- enable/start apache2; UFW inativo → allow SSH/80/443 e enable
- descobre automaticamente o filesystem que contém /home (pode ser / ou /home, etc.)
- habilita usrquota nesse mountpoint ext4 no /etc/fstab
- remount + quotacheck + quotaon nesse mesmo ponto
- roda quotacheck (-cu, depois -cuM, depois variantes com -f se quotas já ativas no mount)
- quotaon -vu trata EBUSY (quotas já ativas após remount) como sucesso com aviso
- ativa quotas de usuário

O que NÃO faz:
- não purga pacotes arbitrariamente
- não mexe em SSH
- não mexe no Apache além de instalar o pacote se faltar
- não cria usuários
- não instala stack de email
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

# Com python3 -P ou PYTHONSAFEPATH=1 o diretório deste script deixa de ir para sys.path;
# sem isto, «from runv_mount» falha mesmo com runv_mount.py ao lado.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    from runv_mount import MountLookupError, find_mount_triple
except ModuleNotFoundError:
    print(
        "Erro: módulo 'runv_mount' não encontrado. "
        "O ficheiro runv_mount.py tem de estar no mesmo diretório que starthere.py.\n"
        f"  Esperado: {_SCRIPT_DIR / 'runv_mount.py'}",
        file=sys.stderr,
    )
    raise SystemExit(1) from None

DEFAULT_QUOTA_PROBE: Final[Path] = Path("/home")

VERSION: Final[str] = "0.01"

FSTAB = Path("/etc/fstab")
BACKUP_DIR = Path("/root/runv-fstab-backups")

BASE_PACKAGES = [
    "apache2",
    "openssh-server",
    "sudo",
    "ufw",
    "quota",
    "curl",
    "wget",
    "git",
    "rsync",
    "tmux",
    "htop",
    "vim",
    "nano",
    "tree",
    "jq",
    "acl",
    "zip",
    "unzip",
    "less",
    "ca-certificates",
    "man-db",
    "build-essential",
    "python3-venv",
    "python3-pip",
    "ripgrep",
    "shellcheck",
    "e2fsprogs",
]

@dataclass
class CmdResult:
    cmd: list[str]
    returncode: int
    stdout: str
    stderr: str


class BootstrapError(RuntimeError):
    pass


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def require_root() -> None:
    if os.geteuid() != 0:
        raise BootstrapError("Este script precisa rodar como root (use sudo).")


def run(
    cmd: list[str],
    *,
    dry_run: bool = False,
    verbose: bool = False,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> CmdResult:
    if verbose or dry_run:
        eprint("$ " + " ".join(shlex.quote(part) for part in cmd))
    if dry_run:
        return CmdResult(cmd, 0, "", "")
    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if verbose and proc.stdout:
        eprint(proc.stdout.rstrip())
    if verbose and proc.stderr:
        eprint(proc.stderr.rstrip())
    if check and proc.returncode != 0:
        raise BootstrapError(
            f"Comando falhou ({proc.returncode}): {' '.join(cmd)}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return CmdResult(cmd, proc.returncode, proc.stdout, proc.stderr)


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def apt_env() -> dict[str, str]:
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    return env


def apt_update(verbose: bool, dry_run: bool) -> None:
    run(["apt-get", "update"], verbose=verbose, dry_run=dry_run, env=apt_env())


def apt_install(packages: list[str], verbose: bool, dry_run: bool) -> None:
    run(
        ["apt-get", "install", "-y", *packages],
        verbose=verbose,
        dry_run=dry_run,
        env=apt_env(),
    )


def apt_cleanup(verbose: bool, dry_run: bool) -> None:
    run(["apt-get", "autoremove", "-y"], verbose=verbose, dry_run=dry_run, env=apt_env())
    run(["apt-get", "autoclean", "-y"], verbose=verbose, dry_run=dry_run, env=apt_env())


def get_mount_kernel_view(mountpoint: str, *, verbose: bool) -> tuple[str, str, list[str]]:
    """Lê TARGET,FSTYPE,OPTIONS do kernel para um mountpoint (ex. ``/`` ou ``/home``)."""
    res = run(
        ["findmnt", "-no", "TARGET,FSTYPE,OPTIONS", mountpoint],
        verbose=verbose,
        dry_run=False,
    )
    line = res.stdout.strip()
    if not line:
        raise BootstrapError(
            f"Não consegui obter informações do mount {mountpoint!r} com findmnt."
        )
    parts = line.split(maxsplit=2)
    if len(parts) != 3:
        raise BootstrapError(f"Saída inesperada do findmnt: {line!r}")
    target, fstype, options = parts
    opts_list = [opt.strip() for opt in options.split(",") if opt.strip()]
    return target, fstype, opts_list


def mount_options_indicate_user_quota(options: list[str]) -> bool:
    """usrquota explícito ou journaled (usrjquota=...)."""
    blob = ",".join(options)
    return "usrquota" in blob or "usrjquota" in blob


def discover_quota_mountpoint(home_probe: Path, verbose: bool) -> str:
    """
    O mesmo critério que create_runv_user / setquota: filesystem que contém o path de sonda
    (por omissão ``/home``). Pode ser ``/`` ou ``/home`` (volume dedicado), etc.
    """
    try:
        tgt, fst, opts_csv = find_mount_triple(home_probe)
    except MountLookupError as e:
        raise BootstrapError(
            f"Não foi possível descobrir em que filesystem {home_probe} está montado. "
            f"Detalhe: {e}"
        ) from e
    if verbose:
        eprint(
            f"Deteção automática: {home_probe} → mount {tgt!r}, fstype {fst}, opções {opts_csv!r}"
        )
    if fst != "ext4":
        raise BootstrapError(
            f"O filesystem que contém {home_probe} está em {tgt!r} com tipo {fst!r}. "
            "Só configuramos quotas automaticamente para ext4 (alinhado a create_runv_user.py). "
            "Noutro tipo de FS, configure quotas manualmente ou use uma VPS com /home em ext4."
        )
    return tgt


def backup_fstab(verbose: bool, dry_run: bool) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"fstab.{timestamp}.bak"
    if verbose or dry_run:
        eprint(f"Backup do fstab: {backup_path}")
    if not dry_run:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FSTAB, backup_path)
    return backup_path


def ensure_usrquota_in_fstab(mountpoint: str, *, dry_run: bool, verbose: bool) -> bool:
    """
    Garante usrquota na linha do fstab que monta ``mountpoint`` como ext4.
    Retorna True se o arquivo foi alterado.
    """
    content = FSTAB.read_text(encoding="utf-8").splitlines(keepends=True)
    changed = False
    new_lines: list[str] = []

    for line in content:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        parts = line.split()
        if len(parts) < 4:
            new_lines.append(line)
            continue

        _device, mp, fstype, options = parts[:4]
        if mp == mountpoint and fstype == "ext4":
            opts = [o for o in options.split(",") if o]
            if "usrquota" not in opts:
                opts.append("usrquota")
                parts[3] = ",".join(opts)
                newline = "\t".join(parts)
                if not newline.endswith("\n"):
                    newline += "\n"
                new_lines.append(newline)
                changed = True
                continue
        new_lines.append(line)

    if changed:
        backup_fstab(verbose, dry_run)
        if verbose or dry_run:
            eprint(f"Atualizando /etc/fstab para incluir usrquota em {mountpoint!r}")
        if not dry_run:
            FSTAB.write_text("".join(new_lines), encoding="utf-8")
    else:
        if verbose:
            eprint(f"/etc/fstab já contém usrquota para {mountpoint!r} (ext4)")
    return changed


def remount_with_usrquota(mountpoint: str, verbose: bool, dry_run: bool) -> None:
    run(
        ["mount", "-o", "remount,usrquota", mountpoint],
        verbose=verbose,
        dry_run=dry_run,
    )
    if dry_run or mount_has_user_quota(mountpoint, verbose):
        return
    if verbose:
        eprint(
            f"Aviso: usrquota ainda não aparece em {mountpoint!r}; "
            "tentando remount genérico..."
        )
    run(["mount", "-o", "remount", mountpoint], verbose=verbose, dry_run=dry_run)


def mount_has_user_quota(mountpoint: str, verbose: bool = False) -> bool:
    _, _, options = get_mount_kernel_view(mountpoint, verbose=verbose)
    return mount_options_indicate_user_quota(options)


def dry_run_assume_quota_active(
    *,
    dry_run: bool,
    fstab_changed: bool,
    skip_remount: bool,
) -> bool:
    """
    Em --dry-run não escrevemos fstab nem remontamos de verdade; o findmnt
    continua sem usrquota. Assumimos sucesso só para completar o plano de quotas.
    """
    if not dry_run:
        return False
    if skip_remount and fstab_changed:
        eprint(
            "AVISO (dry-run): com --skip-remount e fstab a alterar, "
            "em execução real seria preciso remount ou reboot antes de quotacheck."
        )
    return True


def quota_mount_ready(
    mountpoint: str,
    verbose: bool,
    *,
    dry_run: bool,
    dry_run_trust: bool,
) -> bool:
    if dry_run_trust:
        return True
    return mount_has_user_quota(mountpoint, verbose)


def quota_tools_present() -> list[str]:
    required = ["quotacheck", "quotaon", "setquota", "quota"]
    return [tool for tool in required if command_exists(tool)]


def run_quotacheck_escalation(
    mountpoint: str,
    *,
    verbose: bool,
    dry_run: bool,
    allow_live_scan: bool,
) -> None:
    """
    Cria/atualiza aquota.* com quotacheck.

    Após ``remount,usrquota``, o kernel pode já reportar quotas de utilizador
    ativas; nesse caso o quotacheck recusa-se sem ``-f`` («use -f to force»).
    Tentamos primeiro varreduras normais e só depois variantes com ``-f``.
    """
    if allow_live_scan:
        sequences: list[tuple[list[str], str]] = [
            (["quotacheck", "-cuM", mountpoint], "quotacheck -cuM"),
            (["quotacheck", "-cuM", "-f", mountpoint], "quotacheck -cuM -f"),
        ]
    else:
        sequences = [
            (["quotacheck", "-cu", mountpoint], "quotacheck -cu"),
            (["quotacheck", "-cuM", mountpoint], "quotacheck -cuM"),
            (["quotacheck", "-cuM", "-f", mountpoint], "quotacheck -cuM -f"),
            (["quotacheck", "-cu", "-f", mountpoint], "quotacheck -cu -f"),
        ]

    last_exc: BootstrapError | None = None
    for i, (cmd, label) in enumerate(sequences):
        try:
            run(cmd, verbose=verbose, dry_run=dry_run)
            return
        except BootstrapError as exc:
            last_exc = exc
            if dry_run:
                raise
            if i + 1 < len(sequences):
                eprint(f"{label} falhou; a tentar método seguinte...")

    assert last_exc is not None
    tried = ", ".join(label for _cmd, label in sequences)
    raise BootstrapError(
        f"quotacheck falhou após tentar: {tried}.\nÚltimo erro:\n{last_exc}\n"
        "Se a mensagem falar de quotas nativas ext4 (tune2fs -O quota) vs ficheiros "
        "aquota.*, veja a secção de quotas em starthere.md; em muitos casos "
        "-f resolve após remount com usrquota já ativo."
    ) from last_exc


def _quotaon_stderr_implies_already_active(text: str) -> bool:
    """EBUSY típico quando usrquota já ficou ativo no remount e aquota.* está em uso."""
    t = text.lower()
    return "device or resource busy" in t or (
        "resource busy" in t and "quotaon" in t
    )


def run_quotaon_user_vu(mountpoint: str, *, verbose: bool, dry_run: bool) -> None:
    """
    Executa ``quotaon -vu``. Se falhar com EBUSY, assume quotas de utilizador
    já ativas (comum após ``remount,usrquota`` + quotacheck) e continua.
    """
    res = run(
        ["quotaon", "-vu", mountpoint],
        verbose=verbose,
        dry_run=dry_run,
        check=False,
    )
    if dry_run:
        return
    if res.returncode == 0:
        return
    combined = (res.stderr or "") + (res.stdout or "")
    if _quotaon_stderr_implies_already_active(combined):
        qmp = shlex.quote(mountpoint)
        eprint(
            "quotaon: quotas de utilizador já ativas neste mount (Device or resource busy); "
            f"a continuar. Confirme com «quota -vs» ou «sudo repquota -s {qmp}»."
        )
        return
    raise BootstrapError(
        f"Comando falhou ({res.returncode}): quotaon -vu {shlex.quote(mountpoint)}\n"
        f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    )


def init_quotas(
    mountpoint: str,
    verbose: bool,
    dry_run: bool,
    *,
    allow_live_scan: bool,
) -> None:
    present = quota_tools_present()
    missing = [tool for tool in ["quotacheck", "quotaon", "setquota", "quota"] if tool not in present]
    if missing:
        raise BootstrapError(
            "Ferramentas de quota ausentes mesmo após instalar o pacote quota: "
            + ", ".join(missing)
        )

    if not dry_run and not mount_has_user_quota(mountpoint, False):
        raise BootstrapError(
            f"O mount {mountpoint!r} ainda não mostra usrquota ativo. "
            "Reinicie a VM ou confirme o remount antes de prosseguir."
        )

    run_quotacheck_escalation(
        mountpoint,
        verbose=verbose,
        dry_run=dry_run,
        allow_live_scan=allow_live_scan,
    )

    run_quotaon_user_vu(mountpoint, verbose=verbose, dry_run=dry_run)


def block_device_for_mount(mountpoint: str) -> str | None:
    res = run(
        ["findmnt", "-no", "SOURCE", mountpoint],
        verbose=False,
        dry_run=False,
        check=False,
    )
    if res.returncode != 0:
        return None
    dev = res.stdout.strip()
    if not dev or dev == "none":
        return None
    return dev


def ext4_has_internal_quota_feature(device: str) -> bool | None:
    """True se `tune2fs -l` lista a feature «quota» (quotas nativas ext4)."""
    proc = subprocess.run(
        ["tune2fs", "-l", device],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        if line.startswith("Filesystem features:"):
            _label, _, rest = line.partition(":")
            parts = rest.split()
            return "quota" in parts
    return False


def note_ext4_quota_deprecation_context(mountpoint: str) -> None:
    """
    Explica os avisos «external quota files» / tune2fs -O quota após sucesso.
    """
    dev = block_device_for_mount(mountpoint)
    if not dev:
        return
    internal = ext4_has_internal_quota_feature(dev)
    if internal is True:
        return
    eprint(
        "Nota (ext4): os avisos de quotacheck/quotaon sobre «external quota files» "
        "e «tune2fs -O quota» aparecem quando a feature interna «quota» do ext4 "
        "ainda não está ligada no dispositivo — o script usa o modo clássico "
        "(usrquota + aquota.*), que continua válido; confirme com «quota -vs». "
        "Migrar para o modo recomendado pelo kernel exige janela de manutenção "
        f"(desmontar {dev}, «tune2fs -O quota», remontar); ver starthere.md."
    )


def ufw_status_text() -> str:
    proc = subprocess.run(
        ["ufw", "status"],
        text=True,
        capture_output=True,
        check=False,
    )
    return (proc.stdout or "") + (proc.stderr or "")


def configure_ufw(verbose: bool, dry_run: bool) -> None:
    """Habilita UFW só se estiver inativo; preserva SSH antes de fechar."""
    if not command_exists("ufw"):
        eprint("AVISO: comando ufw ausente; instale o pacote ufw ou não use --no-install.")
        return
    txt = ufw_status_text().lower()
    if "inactive" not in txt:
        if verbose:
            eprint("UFW já está ativo ou estado não reconhecido; não altero regras.")
        return
    if verbose or dry_run:
        eprint("UFW inativo: permitindo SSH, HTTP, HTTPS e ativando.")
    run(["ufw", "allow", "OpenSSH"], verbose=verbose, dry_run=dry_run)
    run(["ufw", "allow", "80/tcp"], verbose=verbose, dry_run=dry_run)
    run(["ufw", "allow", "443/tcp"], verbose=verbose, dry_run=dry_run)
    run(["ufw", "--force", "enable"], verbose=verbose, dry_run=dry_run)


def configure_apache(verbose: bool, dry_run: bool) -> None:
    if not command_exists("systemctl"):
        eprint("AVISO: systemctl ausente; não configurei Apache.")
        return
    run(["systemctl", "enable", "apache2"], verbose=verbose, dry_run=dry_run)
    run(["systemctl", "start", "apache2"], verbose=verbose, dry_run=dry_run)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Bootstrap seguro do servidor runv.club (Debian/ext4 + quotas)."
    )
    p.add_argument("--dry-run", action="store_true", help="Mostra o plano sem executar.")
    p.add_argument("--verbose", action="store_true", help="Mostra mais detalhes.")
    p.add_argument(
        "--packages",
        nargs="*",
        default=BASE_PACKAGES,
        help="Lista de pacotes a instalar (padrão conservador incluído).",
    )
    p.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Pula apt autoremove/autoclean.",
    )
    p.add_argument(
        "--no-install",
        action="store_true",
        help="Não instala pacotes; só verifica/configura quotas.",
    )
    p.add_argument(
        "--no-quota",
        action="store_true",
        help="Não mexe em quotas; só instala pacotes e faz limpeza segura.",
    )
    p.add_argument(
        "--quota-probe",
        type=Path,
        default=DEFAULT_QUOTA_PROBE,
        metavar="PATH",
        help=(
            "Caminho para descobrir o filesystem de quotas (deve refletir onde ficam as homes "
            f"runv; predefinido: {DEFAULT_QUOTA_PROBE})."
        ),
    )
    p.add_argument(
        "--skip-remount",
        action="store_true",
        help="Não tenta remount após editar /etc/fstab.",
    )
    p.add_argument(
        "--allow-live-scan",
        action="store_true",
        help=(
            "Usa só quotacheck -cuM (sem tentar antes -cu). "
            "Por omissão o script já tenta -cu e cai para -cuM se necessário."
        ),
    )
    p.add_argument(
        "--no-services",
        action="store_true",
        help="Não ativa Apache nem configura/ativa UFW (pacotes podem ser instalados).",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION} — runv.club",
    )
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        require_root()

        quota_mp: str | None = None
        if not args.no_quota:
            quota_mp = discover_quota_mountpoint(args.quota_probe, args.verbose)

        print(f"== runv.club / starthere.py v{VERSION} ==")
        print("Bootstrap conservador para Debian/ext4.")
        if quota_mp is not None:
            print(
                f"Quotas: mount detetado para {args.quota_probe} → {quota_mp!r} (ext4, alinhado a create_runv_user)."
            )
        print()

        print("[1/6] Atualizando índices APT...")
        if not args.no_install:
            apt_update(args.verbose, args.dry_run)

        print("[2/6] Instalando pacotes-base...")
        if not args.no_install:
            apt_install(args.packages, args.verbose, args.dry_run)

        print("[3/6] Limpeza segura...")
        if not args.no_cleanup and not args.no_install:
            apt_cleanup(args.verbose, args.dry_run)
        else:
            print("Pulando limpeza segura.")

        print("[4/6] Serviços (Apache, UFW)...")
        if not args.no_services:
            configure_apache(args.verbose, args.dry_run)
            configure_ufw(args.verbose, args.dry_run)
        else:
            print("Pulado por --no-services.")

        if not args.no_quota:
            assert quota_mp is not None
            print(f"[5/6] Ajustando /etc/fstab para usrquota em {quota_mp!r} ...")
            changed = ensure_usrquota_in_fstab(
                quota_mp,
                dry_run=args.dry_run,
                verbose=args.verbose,
            )

            if changed and not args.skip_remount:
                print(f"Tentando remount de {quota_mp!r} com usrquota ...")
                try:
                    remount_with_usrquota(quota_mp, args.verbose, args.dry_run)
                except BootstrapError as exc:
                    raise BootstrapError(
                        f"Não consegui remount de {quota_mp!r} com usrquota.\n{exc}\n"
                        "Caminho recomendado: reinicie a VM e rode o script novamente."
                    ) from exc

            dry_trust = dry_run_assume_quota_active(
                dry_run=args.dry_run,
                fstab_changed=changed,
                skip_remount=args.skip_remount,
            )

            if quota_mount_ready(
                quota_mp,
                args.verbose,
                dry_run=args.dry_run,
                dry_run_trust=dry_trust,
            ):
                print("[6/6] Inicializando e ativando quotas...")
                init_quotas(
                    quota_mp,
                    args.verbose,
                    args.dry_run,
                    allow_live_scan=args.allow_live_scan,
                )
                print(f"Quotas de usuário ativadas em {quota_mp!r}.")
                if not args.dry_run:
                    note_ext4_quota_deprecation_context(quota_mp)
            else:
                raise BootstrapError(
                    f"usrquota ainda não aparece ativo em {quota_mp!r}. "
                    "Reinicie a VM e rode o script novamente."
                )
        else:
            print("[5/6] Quotas puladas por --no-quota")
            print("[6/6] Nada a fazer em quotas")

        print()
        print("Concluído.")
        print("Próximos passos:")
        if quota_mp is not None:
            print(f"- Confirmar mount de quotas:  mount | grep ' on {quota_mp} '")
        else:
            print("- Confirmar mounts e usrquota conforme a sua configuração")
        print("- Checar quotas:    quota -vs")
        print("- Contas: usar create_runv_user.py (setquota) conforme create_runv_user.md")
        print("- Reinício (se precisar):  sudo reboot   ou   /sbin/reboot")
        return 0

    except BootstrapError as exc:
        eprint(f"ERRO: {exc}")
        return 2
    except KeyboardInterrupt:
        eprint("Interrompido pelo usuário.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
