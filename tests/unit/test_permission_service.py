"""
tests/unit/test_permission_service.py
========================================
Unit tests for app/services/permission_service.py
"""

import pytest
import pytest_asyncio

from app.database.models.admin import Admin
from app.services.permission_service import (
    Permission,
    UserRole,
    get_user_role,
    has_permission,
    is_authorized,
)

OWNER_ID = 7706183809
ADMIN_ID = 111111111
VIEWER_ID = 222222222
STRANGER_ID = 999999999


@pytest_asyncio.fixture
async def session_with_users(db_session):
    """Seed the DB with an admin and a viewer."""
    admin = Admin(
        telegram_user_id=ADMIN_ID,
        role="admin",
        permissions={
            Permission.IMPORT: True,
            Permission.CATEGORIZE: True,
            Permission.PUBLISH: False,
            Permission.MANAGE_CATEGORIES: False,
            Permission.MANAGE_TAGS: False,
            Permission.VIEW_DASHBOARD: True,
            Permission.MANAGE_BACKUPS: False,
        },
    )
    viewer = Admin(
        telegram_user_id=VIEWER_ID,
        role="viewer",
        permissions={},
    )
    db_session.add(admin)
    db_session.add(viewer)
    await db_session.flush()
    return db_session


@pytest.mark.asyncio
async def test_owner_role(session_with_users):
    role = await get_user_role(session_with_users, OWNER_ID, OWNER_ID)
    assert role == UserRole.OWNER


@pytest.mark.asyncio
async def test_admin_role(session_with_users):
    role = await get_user_role(session_with_users, ADMIN_ID, OWNER_ID)
    assert role == UserRole.ADMIN


@pytest.mark.asyncio
async def test_viewer_role(session_with_users):
    role = await get_user_role(session_with_users, VIEWER_ID, OWNER_ID)
    assert role == UserRole.VIEWER


@pytest.mark.asyncio
async def test_unauthorized_role(session_with_users):
    role = await get_user_role(session_with_users, STRANGER_ID, OWNER_ID)
    assert role == UserRole.UNAUTHORIZED


@pytest.mark.asyncio
async def test_owner_has_all_permissions(session_with_users):
    for perm in [
        Permission.IMPORT,
        Permission.CATEGORIZE,
        Permission.PUBLISH,
        Permission.MANAGE_CATEGORIES,
        Permission.MANAGE_TAGS,
        Permission.VIEW_DASHBOARD,
        Permission.MANAGE_BACKUPS,
    ]:
        assert await has_permission(session_with_users, OWNER_ID, OWNER_ID, perm)


@pytest.mark.asyncio
async def test_admin_has_granted_permissions(session_with_users):
    assert await has_permission(
        session_with_users, ADMIN_ID, OWNER_ID, Permission.IMPORT
    )
    assert await has_permission(
        session_with_users, ADMIN_ID, OWNER_ID, Permission.CATEGORIZE
    )
    assert await has_permission(
        session_with_users, ADMIN_ID, OWNER_ID, Permission.VIEW_DASHBOARD
    )


@pytest.mark.asyncio
async def test_admin_lacks_revoked_permissions(session_with_users):
    assert not await has_permission(
        session_with_users, ADMIN_ID, OWNER_ID, Permission.PUBLISH
    )
    assert not await has_permission(
        session_with_users, ADMIN_ID, OWNER_ID, Permission.MANAGE_CATEGORIES
    )


@pytest.mark.asyncio
async def test_viewer_has_no_permissions(session_with_users):
    for perm in [
        Permission.IMPORT,
        Permission.CATEGORIZE,
        Permission.PUBLISH,
    ]:
        assert not await has_permission(session_with_users, VIEWER_ID, OWNER_ID, perm)


@pytest.mark.asyncio
async def test_unauthorized_has_no_permissions(session_with_users):
    assert not await has_permission(
        session_with_users, STRANGER_ID, OWNER_ID, Permission.IMPORT
    )


@pytest.mark.asyncio
async def test_is_authorized_owner(session_with_users):
    assert await is_authorized(session_with_users, OWNER_ID, OWNER_ID)


@pytest.mark.asyncio
async def test_is_authorized_admin(session_with_users):
    assert await is_authorized(session_with_users, ADMIN_ID, OWNER_ID)


@pytest.mark.asyncio
async def test_is_authorized_viewer(session_with_users):
    assert await is_authorized(session_with_users, VIEWER_ID, OWNER_ID)


@pytest.mark.asyncio
async def test_is_not_authorized_stranger(session_with_users):
    assert not await is_authorized(session_with_users, STRANGER_ID, OWNER_ID)
