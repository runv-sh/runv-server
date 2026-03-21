"""
Nomes canónicos dos templates de email (texto puro) em templates/.

Placeholders comuns: {username}, {email}, {request_id}, {admin_email},
{default_from}, {host}, {reason}, {quota_info}, {timestamp}, {error_summary}
"""

from __future__ import annotations

from typing import Final

# --- Admin ---
ADMIN_NEW_REQUEST: Final[str] = "admin_new_request"
ADMIN_USER_CREATED: Final[str] = "admin_user_created"
ADMIN_USER_DELETED: Final[str] = "admin_user_deleted"
ADMIN_ERROR: Final[str] = "admin_error"

# --- Utilizador ---
USER_REQUEST_RECEIVED: Final[str] = "user_request_received"
USER_APPROVED: Final[str] = "user_approved"
USER_REJECTED: Final[str] = "user_rejected"
USER_ACCOUNT_CREATED: Final[str] = "user_account_created"
USER_QUOTA_WARNING: Final[str] = "user_quota_warning"
USER_ACCOUNT_REMOVED: Final[str] = "user_account_removed"

# --- Sistema ---
SYSTEM_TEST: Final[str] = "system_test"

ALL_TEMPLATES: Final[tuple[str, ...]] = (
    ADMIN_NEW_REQUEST,
    ADMIN_USER_CREATED,
    ADMIN_USER_DELETED,
    ADMIN_ERROR,
    USER_REQUEST_RECEIVED,
    USER_APPROVED,
    USER_REJECTED,
    USER_ACCOUNT_CREATED,
    USER_QUOTA_WARNING,
    USER_ACCOUNT_REMOVED,
    SYSTEM_TEST,
)
