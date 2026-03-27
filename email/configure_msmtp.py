#!/usr/bin/env python3
"""
Encaminhamento: o configurador predefinido passou a ser Mailgun API.

Use ``configure_mailgun.py`` (recomendado) ou ``configure_msmtp_legacy.py`` (SMTP/msmtp).
"""

from __future__ import annotations

import sys
from pathlib import Path

ADMIN_DIR = Path(__file__).resolve().parent.parent / "scripts" / "admin"
if str(ADMIN_DIR) not in sys.path:
    sys.path.insert(0, str(ADMIN_DIR))

from admin_guard import ensure_admin_cli


def main() -> int:
    ensure_admin_cli(script_name=Path(__file__).name)
    print(
        "Este comando foi substituído.\n"
        "  Mailgun (API, predefinido): sudo python3 email/configure_mailgun.py\n"
        "  SMTP legado (msmtp):        sudo python3 email/configure_msmtp_legacy.py\n"
        "  ou:                         sudo python3 email/configure_mailgun.py --legacy-smtp",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
