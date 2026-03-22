"""
Sincronização da landing pública após alterações a ``users.json``.

Invoca ``site/genlanding.py --sync-public-only`` (cópia de ``site/public/`` +
``data/members.json``). Partilhado por create_runv_user, update_user e del-user.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent


def genlanding_sync_command(
    *,
    document_root: Path,
    users_json: Path,
    homes_root: Path | None = None,
) -> list[str]:
    """Comando completo para ``site/genlanding.py --sync-public-only`` (lista para subprocess)."""
    script = _REPO_ROOT / "site" / "genlanding.py"
    cmd: list[str] = [
        sys.executable,
        str(script),
        "--sync-public-only",
        "--document-root",
        str(document_root),
        "--members-users-json",
        str(users_json),
    ]
    if homes_root is not None:
        cmd.extend(["--members-homes-root", str(homes_root)])
    return cmd


def try_sync_landing_via_genlanding(
    *,
    document_root: Path,
    users_json: Path,
    homes_root: Path | None,
    log: logging.Logger,
) -> tuple[bool, int | None]:
    """
    Copia site/public → DocumentRoot e regenera data/members.json (genlanding.py --sync-public-only).
    Falhas são apenas registadas — não aborta o chamador.
    Devolve (sucesso, número de membros no JSON público ou None se não foi possível contar).
    """
    script = _REPO_ROOT / "site" / "genlanding.py"
    if not script.is_file():
        log.warning(
            "genlanding.py não encontrado em %s; landing não sincronizada",
            script,
        )
        return False, None
    cmd = genlanding_sync_command(
        document_root=document_root,
        users_json=users_json,
        homes_root=homes_root,
    )
    out = document_root / "data" / "members.json"
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        combined = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        if r.returncode != 0:
            log.warning(
                "genlanding --sync-public-only terminou com código %s: %s",
                r.returncode,
                combined[:2000] if combined else "(sem saída)",
            )
            return False, None
        log.info("landing sincronizada (site/public + members.json) em %s", document_root)
        if combined:
            log.debug("genlanding sync: %s", combined[:1500])
        n_public: int | None = None
        try:
            raw = out.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                n_public = len(parsed)
                log.info("constelação: %s membro(s) no dataset público (%s)", n_public, out)
        except (OSError, json.JSONDecodeError, TypeError) as ex:
            log.warning("members.json após sync não foi possível validar: %s", ex)
        return True, n_public
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("falha ao executar genlanding --sync-public-only: %s", e)
        return False, None
