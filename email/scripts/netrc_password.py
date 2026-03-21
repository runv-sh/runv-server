#!/usr/bin/env python3
"""
Lê a palavra-passe SMTP de /root/.netrc para a máquina indicada (argv[1]).

Usado por msmtp passwordeval. Executar apenas como root; saída só na stdout.
Código de saída != 0 se não encontrar entrada.
"""
from __future__ import annotations

import netrc
import sys
from pathlib import Path

NETRC_PATH = Path("/root/.netrc")


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    host = sys.argv[1].strip()
    if not host:
        return 2
    if not NETRC_PATH.is_file():
        return 1
    try:
        n = netrc.netrc(str(NETRC_PATH))
        tup = n.authenticators(host)
        if not tup:
            return 1
        _login, _account, password = tup
        if not password:
            return 1
        sys.stdout.write(password)
        sys.stdout.flush()
    except (netrc.NetrcParseError, OSError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
