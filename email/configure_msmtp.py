#!/usr/bin/env python3
"""
Encaminhamento: o configurador predefinido passou a ser Mailgun API.

Use ``configure_mailgun.py`` (recomendado) ou ``configure_msmtp_legacy.py`` (SMTP/msmtp).
"""

from __future__ import annotations

import sys


def main() -> int:
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
