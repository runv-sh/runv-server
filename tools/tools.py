#!/usr/bin/env python3
"""
runv.club — ferramentas globais, MOTD, comandos em /usr/local/bin e /etc/skel.

Debian 13 · Python 3 stdlib apenas · sem shell=True.
Execute como root. Ver tools/README.md e tools/docs/INSTALL.md.
"""

from __future__ import annotations

import argparse
import filecmp
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

TOOL_ROOT: Path = Path(__file__).resolve().parent
MANIFEST_PATH: Path = TOOL_ROOT / "manifests" / "apt_packages.txt"
BIN_DIR: Path = TOOL_ROOT / "bin"
MOTD_SRC: Path = TOOL_ROOT / "motd" / "60-runv"
SKEL_DIR: Path = TOOL_ROOT / "skel"

DEST_BIN_DIR: Path = Path("/usr/local/bin")
DEST_MOTD: Path = Path("/etc/update-motd.d/60-runv")
DEST_SKEL: Path = Path("/etc/skel")


@dataclass
class RunSummary:
    """Acumula ações para o resumo final."""

    dry_run: bool = False
    apt_updated: bool = False
    apt_install_attempted: bool = False
    packages_requested: list[str] = field(default_factory=list)
    copied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def setup_logging(verbose: bool) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )
    return logging.getLogger("runv-tools")


def require_root(log: logging.Logger) -> None:
    if os.geteuid() != 0:
        log.error("Este script precisa ser executado como root (sudo).")
        sys.exit(1)


def run_subprocess(
    cmd: list[str],
    *,
    dry_run: bool,
    log: logging.Logger,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str] | None:
    """Executa comando sem shell; em dry-run apenas registra."""
    log.debug("exec: %s", " ".join(cmd))
    if dry_run:
        log.info("[dry-run] %s", " ".join(cmd))
        return None
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        env=e,
        timeout=3600,
    )


def read_apt_manifest(path: Path, log: logging.Logger) -> list[str]:
    if not path.is_file():
        log.error("Manifesto não encontrado: %s", path)
        sys.exit(1)
    packages: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        packages.append(line)
    return packages


def install_apt_packages(
    packages: list[str],
    *,
    dry_run: bool,
    log: logging.Logger,
    summary: RunSummary,
) -> None:
    if not packages:
        log.info("Nenhum pacote listado no manifesto; etapa apt ignorada.")
        return
    summary.packages_requested = list(packages)
    env_apt = {
        "DEBIAN_FRONTEND": "noninteractive",
        "LC_ALL": "C",
    }
    log.info("Atualizando índice apt (apt-get update)...")
    r = run_subprocess(
        ["apt-get", "update", "-qq"],
        dry_run=dry_run,
        log=log,
        env=env_apt,
    )
    if dry_run:
        summary.apt_updated = True
    elif r is not None:
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            msg = f"apt-get update falhou (código {r.returncode})" + (f": {err}" if err else "")
            summary.errors.append(msg)
            log.error("%s", msg)
            return
        summary.apt_updated = True

    log.info("Instalando pacotes: %s", ", ".join(packages))
    summary.apt_install_attempted = True
    cmd = ["apt-get", "install", "-y", "--no-install-recommends", *packages]
    r = run_subprocess(cmd, dry_run=dry_run, log=log, env=env_apt)
    if dry_run:
        return
    if r is None:
        return
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        msg = f"apt-get install falhou (código {r.returncode})" + (f": {err}" if err else "")
        summary.errors.append(msg)
        log.error("%s", msg)
    else:
        log.info("Pacotes instalados ou já presentes (apt idempotente).")


def ensure_parent(path: Path, log: logging.Logger) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def copy_one(
    src: Path,
    dst: Path,
    mode: int,
    *,
    force: bool,
    dry_run: bool,
    log: logging.Logger,
    summary: RunSummary,
) -> None:
    if not src.is_file():
        summary.errors.append(f"origem inexistente: {src}")
        log.error("Origem inexistente: %s", src)
        return

    def same_content() -> bool:
        if not dst.is_file():
            return False
        try:
            return filecmp.cmp(src, dst, shallow=False)
        except OSError:
            return False

    # Sem --force: só pula se o ficheiro já for byte-a-byte igual à origem (reexecução actualiza mudanças do repo).
    if not force and dst.exists() and same_content():
        log.info("Destino já coincide com a origem, pulando: %s", dst)
        summary.skipped.append(str(dst))
        return
    if dry_run:
        log.info("[dry-run] copiaria %s -> %s (modo %o)", src, dst, mode)
        summary.copied.append(f"{src} -> {dst} (simulado)")
        return
    ensure_parent(dst, log)
    shutil.copy2(src, dst)
    os.chmod(dst, mode)
    try:
        os.chown(dst, 0, 0)
    except OSError as e:
        log.warning("chown root:root em %s: %s", dst, e)
    log.info("Instalado: %s", dst)
    summary.copied.append(str(dst))


def install_bin_scripts(
    *,
    force: bool,
    dry_run: bool,
    log: logging.Logger,
    summary: RunSummary,
) -> None:
    if not dry_run:
        DEST_BIN_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("runv-help", "runv-links", "runv-status"):
        copy_one(
            BIN_DIR / name,
            DEST_BIN_DIR / name,
            0o755,
            force=force,
            dry_run=dry_run,
            log=log,
            summary=summary,
        )


def install_motd(
    *,
    force: bool,
    dry_run: bool,
    log: logging.Logger,
    summary: RunSummary,
) -> None:
    copy_one(
        MOTD_SRC,
        DEST_MOTD,
        0o755,
        force=force,
        dry_run=dry_run,
        log=log,
        summary=summary,
    )


def install_skel(
    *,
    force: bool,
    dry_run: bool,
    log: logging.Logger,
    summary: RunSummary,
) -> None:
    """Copia apenas arquivos modelo; não instala pacotes."""
    if not dry_run:
        DEST_SKEL.mkdir(parents=True, exist_ok=True)

    skel_files: list[tuple[Path, Path, int]] = [
        (SKEL_DIR / "README.md", DEST_SKEL / "README.md", 0o644),
        (SKEL_DIR / ".bash_aliases", DEST_SKEL / ".bash_aliases", 0o644),
    ]
    for src, dst, mode in skel_files:
        copy_one(src, dst, mode, force=force, dry_run=dry_run, log=log, summary=summary)

    pub_dir = DEST_SKEL / "public_html"
    index_src = SKEL_DIR / "public_html" / "index.html"
    index_dst = pub_dir / "index.html"

    if not index_src.is_file():
        summary.errors.append(f"origem inexistente: {index_src}")
        log.error("Origem inexistente: %s", index_src)
        return

    if not dry_run:
        pub_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(pub_dir, 0o755)
        try:
            os.chown(pub_dir, 0, 0)
        except OSError as e:
            log.warning("chown em %s: %s", pub_dir, e)
    elif not pub_dir.exists() and dry_run:
        log.info("[dry-run] criaria diretório %s (755)", pub_dir)

    copy_one(
        index_src,
        index_dst,
        0o644,
        force=force,
        dry_run=dry_run,
        log=log,
        summary=summary,
    )

    if not dry_run and pub_dir.is_dir():
        os.chmod(pub_dir, 0o755)
        try:
            os.chown(pub_dir, 0, 0)
        except OSError:
            pass


def print_summary(summary: RunSummary, log: logging.Logger) -> None:
    print()
    print("========== runv-tools — resumo ==========")
    if summary.dry_run:
        print("Modo: DRY-RUN (nenhuma alteração no sistema)")
    print(f"apt-get update executado/simulado: {summary.apt_updated}")
    if summary.packages_requested:
        print(f"Pacotes (manifesto): {', '.join(summary.packages_requested)}")
    print(f"Instalação apt tentada/simulada: {summary.apt_install_attempted}")
    if summary.copied:
        print("Copiados / simulados:")
        for c in summary.copied:
            print(f"  + {c}")
    if summary.skipped:
        print("Sem alteração (destino já idêntico à origem no repositório):")
        for s in summary.skipped:
            print(f"  = {s}")
    if summary.errors:
        print("Erros:")
        for e in summary.errors:
            print(f"  ! {e}")
        print("==========================================")
        sys.exit(1)
    print("Concluído sem erros fatais registrados pelo script.")
    print("==========================================")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Instala pacotes globais, comandos runv, MOTD e arquivos em /etc/skel.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="não altera o sistema; mostra o que seria feito",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="log detalhado",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="sobrescreve sempre (mesmo conteúdo idêntico); sem isto, só copia se origem e destino diferirem",
    )
    p.add_argument(
        "--skip-apt",
        action="store_true",
        help="não executa apt-get (útil para reaplicar só arquivos/MOTD/skel)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log = setup_logging(args.verbose)
    summary = RunSummary(dry_run=args.dry_run)

    if not args.dry_run:
        require_root(log)
    else:
        log.info("Dry-run: validação de root ignorada (nada será gravado).")

    if not args.skip_apt:
        pkgs = read_apt_manifest(MANIFEST_PATH, log)
        install_apt_packages(pkgs, dry_run=args.dry_run, log=log, summary=summary)
    else:
        log.info("Etapa apt ignorada (--skip-apt).")

    log.info("Instalando scripts em %s", DEST_BIN_DIR)
    install_bin_scripts(force=args.force, dry_run=args.dry_run, log=log, summary=summary)

    log.info("Instalando MOTD em %s", DEST_MOTD)
    install_motd(force=args.force, dry_run=args.dry_run, log=log, summary=summary)

    log.info("Sincronizando skel em %s", DEST_SKEL)
    install_skel(force=args.force, dry_run=args.dry_run, log=log, summary=summary)

    print_summary(summary, log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
