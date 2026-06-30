"""Central role hierarchy and permission helpers for Assistify RBAC."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status

ROLE_RANK: dict[str, int] = {
    "customer": 0,
    "employee": 1,
    "admin": 2,
    "master_admin": 3,
    "superadmin": 4,
}

MANAGEABLE_BY: dict[str, frozenset[str]] = {
    "superadmin": frozenset({"master_admin", "admin", "employee", "customer"}),
    "master_admin": frozenset({"admin", "employee", "customer"}),
    "admin": frozenset({"employee", "customer"}),
}

STAFF_ROLES = frozenset({"admin", "master_admin", "employee"})
TENANT_STAFF_ROLES = frozenset({"admin", "master_admin"})
MASTER_ADMIN_OR_HIGHER = frozenset({"master_admin", "superadmin"})
ALL_ROLES = frozenset(ROLE_RANK.keys())


def normalize_role(role: str | None) -> str:
    return str(role or "").strip().lower()


def roles_visible_to(caller_role: str | None) -> frozenset[str]:
    """Roles a caller may see in user listings."""
    role = normalize_role(caller_role)
    if role == "superadmin":
        return ALL_ROLES
    if role == "master_admin":
        return frozenset({"admin", "employee", "customer"})
    if role == "admin":
        return frozenset({"employee", "customer"})
    return frozenset()


def roles_assignable_by(caller_role: str | None) -> frozenset[str]:
    """Roles a caller may create or assign."""
    role = normalize_role(caller_role)
    return MANAGEABLE_BY.get(role, frozenset())


def assert_can_assign_role(caller_role: str | None, new_role: str) -> None:
    caller = normalize_role(caller_role)
    target = normalize_role(new_role)
    if target not in ALL_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    allowed = roles_assignable_by(caller)
    if target not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{caller}' cannot assign role '{target}'",
        )


def assert_can_manage_user(caller: dict[str, Any], target: dict[str, Any]) -> None:
    """Enforce tenant scope and hierarchical manage rights."""
    caller_role = normalize_role(caller.get("role"))
    target_role = normalize_role(target.get("role"))

    if caller_role == "superadmin":
        return

    caller_tid = caller.get("tenant_id")
    target_tid = target.get("tenant_id")
    if caller_tid is None or target_tid is None or int(caller_tid) != int(target_tid):
        raise HTTPException(status_code=403, detail="Cannot manage users outside your business")

    allowed_targets = roles_assignable_by(caller_role)
    if target_role not in allowed_targets:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot manage users with role '{target_role}'",
        )


def sql_role_filter_for_caller(caller_role: str | None) -> tuple[str, list[str]]:
    """Return SQL fragment and params to filter users by visible roles."""
    visible = roles_visible_to(caller_role)
    if not visible:
        return " AND 1=0", []
    placeholders = ",".join("?" * len(visible))
    return f" AND role IN ({placeholders})", list(sorted(visible))
