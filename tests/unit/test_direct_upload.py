"""Tests for direct category-upload UI state and callback contracts."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.telegram.handlers.direct_upload_handler import (
    clear_pending_upload_category,
    get_pending_upload_category_id,
)
from app.telegram.keyboards import CB, category_select_keyboard, media_mgmt_keyboard


def test_direct_upload_state_returns_selected_category_for_fresh_selection():
    context = SimpleNamespace(
        user_data={
            "direct_upload_category_id": 12,
            "direct_upload_started_at": datetime.now(timezone.utc),
        }
    )

    assert get_pending_upload_category_id(context) == 12


def test_direct_upload_state_expires_and_clears_stale_selection():
    context = SimpleNamespace(
        user_data={
            "direct_upload_category_id": 12,
            "direct_upload_started_at": datetime.now(timezone.utc)
            - timedelta(hours=13),
        }
    )

    assert get_pending_upload_category_id(context) is None
    assert context.user_data == {}


def test_direct_upload_state_can_be_cancelled():
    context = SimpleNamespace(
        user_data={
            "direct_upload_category_id": 12,
            "direct_upload_started_at": datetime.now(timezone.utc),
            "other_state": "kept",
        }
    )

    clear_pending_upload_category(context)

    assert context.user_data == {"other_state": "kept"}


def test_media_menu_exposes_direct_upload_action():
    callbacks = [
        button.callback_data
        for row in media_mgmt_keyboard().inline_keyboard
        for button in row
    ]

    assert CB.DIRECT_UPLOAD in callbacks


def test_direct_upload_category_picker_uses_dedicated_callback_prefixes():
    category = SimpleNamespace(id=7, emoji="📁", name="ישראלי")
    keyboard = category_select_keyboard(
        [category],
        select_prefix=CB.DIRECT_UPLOAD_CATEGORY,
        page_prefix=CB.DIRECT_UPLOAD_PAGE,
        include_create=False,
    )
    callbacks = [
        button.callback_data for row in keyboard.inline_keyboard for button in row
    ]

    assert f"{CB.DIRECT_UPLOAD_CATEGORY}7" in callbacks
    assert CB.SORT_CAT_NEW not in callbacks
