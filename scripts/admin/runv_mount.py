"""
Descoberta de montagens para quotas runv — partilhado por starthere, create_runv_user, del-user.

O ponto de verdade para «em que disco estão as homes» é o path físico (tipicamente /home):
o mesmo algoritmo deve usar findmnt/proc em todos os scripts.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


class MountLookupError(RuntimeError):
    """Não foi possível resolver o mount para um path."""


def find_mount_triple(path: Path) -> tuple[str, str, str]:
    """
    Retorna (target, fstype, options_csv) do filesystem que contém ``path``.

    ``target`` é o mountpoint canónico (ex.: ``/`` se /home está na raiz, ou ``/home``
    se /home é um ponto de montagem separado).
    """
    try:
        r = subprocess.run(
            ["findmnt", "-J", "-T", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0 and r.stdout.strip():
            data = json.loads(r.stdout)
            fss = data.get("filesystems") or []
            if fss:
                e = fss[0]
                tgt = str(e.get("target", ""))
                fst = str(e.get("fstype", ""))
                opts = str(e.get("options", ""))
                if tgt and fst:
                    return tgt, fst, opts
    except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired):
        pass

    try:
        resolved = path.resolve()
        rpath = str(resolved)
        best: tuple[str, str, str, int] = ("", "", "", -1)
        with open("/proc/mounts", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 4:
                    continue
                _dev, mountpoint, fstype, opts = parts[0], parts[1], parts[2], parts[3]
                mp = mountpoint.replace("\\040", " ")
                if rpath == mp or rpath.startswith(mp.rstrip("/") + "/") or rpath.startswith(mp + "/"):
                    ln = len(mp)
                    if ln > best[3]:
                        best = (mp, fstype, opts, ln)
        if best[3] >= 0:
            return best[0], best[1], best[2]
    except OSError:
        pass

    raise MountLookupError(
        f"não foi possível determinar o mountpoint do filesystem para {path} "
        "(findmnt e /proc/mounts falharam)"
    )


def quota_opts_allow_user(options: str) -> bool:
    """True se usrquota ou usrjquota= está ativo nas opções de mount."""
    if not options:
        return False
    for raw in options.split(","):
        opt = raw.strip()
        if opt == "usrquota":
            return True
        if opt.startswith("usrjquota="):
            return True
    return False
