"""
app/telegram/keyboards.py
===========================
All InlineKeyboardMarkup builders in one place.
No handler should build keyboards inline — always call a function from here.
SRS design rule: max 4 buttons per row (mobile readability).
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ─────────────────────────────────────────────
# Callback data prefixes (used for routing)
# ─────────────────────────────────────────────
class CB:
    # Main menu
    MAIN_MENU = "main_menu"
    MEDIA_MGMT = "media_mgmt"
    TOPICS = "topics"
    DUPLICATES = "duplicates"
    PUBLISH = "publish"
    RECYCLE_BIN = "recycle_bin"
    DASHBOARD = "dashboard"
    BACKUP = "backup"
    SETTINGS = "settings"
    ADMINS = "admins"

    # Media management sub-menu
    SORT_NEW = "sort_new"
    SORT_RESUME = "sort_resume"
    SEARCH = "search"
    FILTER = "filter"
    DIRECT_UPLOAD = "direct_upload"
    DIRECT_UPLOAD_CATEGORY = "direct_upload_cat:"  # + category ID
    DIRECT_UPLOAD_PAGE = "direct_upload_page:"  # + page number
    DIRECT_UPLOAD_CANCEL = "direct_upload_cancel"

    # Sorting actions
    SORT_PREV = "sort_prev"
    SORT_NEXT = "sort_next"
    SORT_SAVE = "sort_save"
    SORT_SKIP = "sort_skip"
    SORT_DELETE = "sort_delete"
    SORT_CAT_SELECT = "sort_cat:"  # + category_id
    SORT_CAT_NEW = "sort_cat_new"
    SORT_CAT_BACK = "sort_cat_back"
    SORT_PAGE = "sort_page:"  # + page_number

    # Handoff
    HANDOFF_CONFIRM = "handoff_confirm"
    HANDOFF_CANCEL = "handoff_cancel"

    # Categories
    CAT_RENAME = "cat_rename:"  # + cat_id
    CAT_LINK = "cat_link:"  # + cat_id
    CAT_DELETE = "cat_delete:"  # + cat_id
    CAT_MERGE = "cat_merge:"  # + cat_id
    CAT_DUPLICATE = "cat_dup:"  # + cat_id
    CAT_TRANSFER = "cat_transfer:"  # + cat_id
    CAT_NEW = "cat_new"
    CAT_SYNC = "cat_sync"
    CAT_LINK_SELECT = "cat_link_sel:"  # + cat_id:thread_id
    CAT_SYNC_CONFIRM = "cat_sync_ok"
    CAT_SYNC_CANCEL = "cat_sync_cancel"
    CAT_LINK_NOW = "cat_link_now"
    CAT_LINK_SKIP = "cat_link_skip"
    CAT_PAGE = "cat_page:"  # + page_number

    # Duplicates
    DUP_DELETE_MEMBER = "dup_del:"  # + media_id
    DUP_SCAN = "dup_scan"
    DUP_PAGE = "dup_page:"  # + page_number

    # Publishing
    PUB_TOPIC = "pub_topic"
    PUB_ALL = "pub_all"
    PUB_SCHEDULE = "pub_sched"
    PUB_SCHED_TOPIC = "pub_sched_topic"
    PUB_SCHED_ALL = "pub_sched_all"
    PUB_STOP = "pub_stop"
    PUB_ORDER = "pub_order:"  # + order_mode
    PUB_SCHED_ORDER = "pub_sched_order:"  # + order_mode
    PUB_CAT_SELECT = "pub_cat:"  # + category ID
    PUB_SCHED_CAT_SELECT = "pub_sched_cat:"  # + category ID
    PUB_ALL_CATEGORIES = "pub_all_categories"

    # Recycle bin
    REC_RESTORE = "rec_restore:"  # + media_id
    REC_PERM_DEL = "rec_perm:"  # + media_id
    REC_EMPTY = "rec_empty"
    REC_PAGE = "rec_page:"  # + page_number

    # Dashboard
    DASH_LOG = "dash_log"
    DASH_LOG_PAGE = "dash_log_page:"  # + page_number

    # Backup
    BACKUP_NOW = "backup_now"
    BACKUP_RESTORE = "backup_restore"

    # Settings
    SET_FLOOD = "set_flood"
    SET_ORDER = "set_order"
    SET_BACKUP_FREQ = "set_backup_freq"
    SET_SCHED_TOGGLE = "set_sched_toggle"

    # Admins
    ADM_ADD = "adm_add"
    ADM_EDIT = "adm_edit:"  # + admin_id
    ADM_REMOVE = "adm_remove:"  # + admin_id
    ADM_PERM = "adm_perm:"  # + admin_id:perm_key

    # Confirmation
    CONFIRM_YES = "confirm_yes"
    CONFIRM_NO = "confirm_no"

    # Media library
    LIB_ITEM = "lib_item:"  # + media_id
    LIB_MULTI = "lib_multi"
    LIB_DEL_SEL = "lib_del_sel"
    LIB_MOVE_SEL = "lib_move_sel"
    LIB_TAG_SEL = "lib_tag_sel"
    LIB_PUB_SEL = "lib_pub_sel"
    LIB_PAGE = "lib_page:"  # + page_number
    LIB_FILTER_CAT = "lib_fcat:"  # + cat_id
    LIB_FILTER_STATUS = "lib_fstat:"  # + status
    LIB_FILTER_TAG = "lib_ftag:"  # + tag_id

    # Item detail
    ITEM_TAG = "item_tag:"  # + media_id
    ITEM_MOVE = "item_move:"  # + media_id
    ITEM_REPUBLISH = "item_repub:"  # + media_id
    ITEM_DELETE = "item_del:"  # + media_id
    ITEM_BACK = "item_back"
    ITEM_MARK_READY = "item_ready:"  # + media_id


def main_menu_keyboard(
    is_owner: bool = False, pending_duplicates: int = 0
) -> InlineKeyboardMarkup:
    """Main menu keyboard (Appendix A structure)."""
    dup_label = (
        f"🔍 כפילויות ({pending_duplicates})"
        if pending_duplicates > 0
        else "🔍 כפילויות"
    )
    rows = [
        [InlineKeyboardButton("🎬 ניהול מדיה", callback_data=CB.MEDIA_MGMT)],
        [InlineKeyboardButton("📂 נושאים", callback_data=CB.TOPICS)],
        [InlineKeyboardButton(dup_label, callback_data=CB.DUPLICATES)],
        [InlineKeyboardButton("📢 פרסום", callback_data=CB.PUBLISH)],
        [
            InlineKeyboardButton("🗑 סל מיחזור", callback_data=CB.RECYCLE_BIN),
            InlineKeyboardButton("📊 דשבורד", callback_data=CB.DASHBOARD),
        ],
        [InlineKeyboardButton("💾 גיבוי", callback_data=CB.BACKUP)],
    ]
    if is_owner:
        rows.append([InlineKeyboardButton("⚙️ הגדרות", callback_data=CB.SETTINGS)])
    return InlineKeyboardMarkup(rows)


def media_mgmt_keyboard() -> InlineKeyboardMarkup:
    """Media-management actions with complete server-side handlers."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🆕 מיון חדש", callback_data=CB.SORT_NEW)],
            [InlineKeyboardButton("▶️ המשך מיון", callback_data=CB.SORT_RESUME)],
            [
                InlineKeyboardButton(
                    "⬆️ העלאה לקטגוריה", callback_data=CB.DIRECT_UPLOAD
                )
            ],
            [InlineKeyboardButton("⬅️ חזרה", callback_data=CB.MAIN_MENU)],
        ]
    )


def sorting_item_keyboard() -> InlineKeyboardMarkup:
    """Keyboard shown with each media item during sorting (SRS §10.1)."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➡️ הבא", callback_data=CB.SORT_NEXT)],
            [InlineKeyboardButton("💾 שמור בנושא", callback_data=CB.SORT_SAVE)],
            [
                InlineKeyboardButton("⏭ דלג", callback_data=CB.SORT_SKIP),
                InlineKeyboardButton("🗑 מחק", callback_data=CB.SORT_DELETE),
            ],
            [InlineKeyboardButton("🏠 תפריט ראשי", callback_data=CB.MAIN_MENU)],
        ]
    )


def category_select_keyboard(
    categories: list,
    page: int = 0,
    page_size: int = 8,
    back_cb: str = CB.SORT_CAT_BACK,
    select_prefix: str = CB.SORT_CAT_SELECT,
    page_prefix: str = CB.SORT_PAGE,
    include_create: bool = True,
) -> InlineKeyboardMarkup:
    """
    Paginated category selection keyboard.
    Used in sorting (save to topic) and other flows.
    """
    start = page * page_size
    end = start + page_size
    page_cats = categories[start:end]

    rows = []
    for cat in page_cats:
        emoji = cat.emoji or ""
        label = f"{emoji} {cat.name}".strip()
        rows.append(
            [InlineKeyboardButton(label, callback_data=f"{select_prefix}{cat.id}")]
        )

    if include_create:
        rows.append(
            [InlineKeyboardButton("➕ נושא חדש", callback_data=CB.SORT_CAT_NEW)]
        )

    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton("⬅️ הקודם", callback_data=f"{page_prefix}{page - 1}")
        )
    if end < len(categories):
        nav.append(
            InlineKeyboardButton("➡️ הבא", callback_data=f"{page_prefix}{page + 1}")
        )
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("⬅️ חזרה", callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)


def direct_upload_prompt_keyboard() -> InlineKeyboardMarkup:
    """Let an uploader explicitly leave the one-category upload mode."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✖️ סיים העלאה", callback_data=CB.DIRECT_UPLOAD_CANCEL
                )
            ],
            [InlineKeyboardButton("⬅️ ניהול מדיה", callback_data=CB.MEDIA_MGMT)],
        ]
    )


def confirm_keyboard(
    yes_cb: str = CB.CONFIRM_YES, no_cb: str = CB.CONFIRM_NO
) -> InlineKeyboardMarkup:
    """Generic confirmation dialog keyboard (SRS §29)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ אשר", callback_data=yes_cb),
                InlineKeyboardButton("❌ בטל", callback_data=no_cb),
            ],
        ]
    )


def back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏠 תפריט ראשי", callback_data=CB.MAIN_MENU)]]
    )


def publish_menu_keyboard(has_running_job: bool = False) -> InlineKeyboardMarkup:
    """Render only publishing actions implemented by the bot."""
    rows = [
        [InlineKeyboardButton("📢 פרסם נושא", callback_data=CB.PUB_TOPIC)],
        [InlineKeyboardButton("📢📢 פרסם הכל", callback_data=CB.PUB_ALL)],
        [
            InlineKeyboardButton(
                "📤 שלח לכל הקטגוריות", callback_data=CB.PUB_ALL_CATEGORIES
            )
        ],
        [InlineKeyboardButton("⏰ תזמן פרסום", callback_data=CB.PUB_SCHEDULE)],
    ]
    if has_running_job:
        rows.append([InlineKeyboardButton("⏹ עצור", callback_data=CB.PUB_STOP)])
    rows.append([InlineKeyboardButton("⬅️ חזרה", callback_data=CB.MAIN_MENU)])
    return InlineKeyboardMarkup(rows)


def publish_order_keyboard(
    callback_prefix: str = CB.PUB_ORDER, back_callback: str = CB.PUBLISH
) -> InlineKeyboardMarkup:
    """Render supported queue ordering choices for manual or scheduled publication."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎲 אקראי", callback_data=f"{callback_prefix}random"
                )
            ],
            [
                InlineKeyboardButton(
                    "📅 ישן→חדש", callback_data=f"{callback_prefix}oldest_first"
                ),
                InlineKeyboardButton(
                    "📅 חדש→ישן", callback_data=f"{callback_prefix}newest_first"
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏱ קצר→ארוך", callback_data=f"{callback_prefix}shortest_first"
                ),
                InlineKeyboardButton(
                    "⏱ ארוך→קצר", callback_data=f"{callback_prefix}longest_first"
                ),
            ],
            [InlineKeyboardButton("⬅️ חזרה", callback_data=back_callback)],
        ]
    )


def publish_schedule_scope_keyboard() -> InlineKeyboardMarkup:
    """Choose the source scope before collecting a one-off schedule time."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📢 תזמן נושא", callback_data=CB.PUB_SCHED_TOPIC)],
            [InlineKeyboardButton("📢📢 תזמן את הכל", callback_data=CB.PUB_SCHED_ALL)],
            [InlineKeyboardButton("⬅️ חזרה", callback_data=CB.PUBLISH)],
        ]
    )


def handoff_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ המשך במקומו", callback_data=CB.HANDOFF_CONFIRM
                ),
                InlineKeyboardButton("❌ ביטול", callback_data=CB.HANDOFF_CANCEL),
            ],
        ]
    )


def categories_list_keyboard(
    categories: list,
    page: int = 0,
    page_size: int = 5,
) -> InlineKeyboardMarkup:
    """Category management list keyboard (SRS §11)."""
    start = page * page_size
    end = start + page_size
    page_cats = categories[start:end]

    rows = []
    for cat in page_cats:
        emoji = cat.emoji or "📁"
        label = f"{emoji} {cat.name}"
        rows.append([InlineKeyboardButton(label, callback_data=f"cat_detail:{cat.id}")])

    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton("⬅️ הקודם", callback_data=f"{CB.CAT_PAGE}{page - 1}")
        )
    if end < len(categories):
        nav.append(
            InlineKeyboardButton("➡️ הבא", callback_data=f"{CB.CAT_PAGE}{page + 1}")
        )
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("➕ צור קטגוריה", callback_data=CB.CAT_NEW)])
    rows.append([InlineKeyboardButton("⬅️ חזרה", callback_data=CB.MAIN_MENU)])
    return InlineKeyboardMarkup(rows)


def category_actions_keyboard(cat_id: int) -> InlineKeyboardMarkup:
    """Actions that are currently supported for a selected category."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🗑 מחיקה", callback_data=f"{CB.CAT_DELETE}{cat_id}")],
            [InlineKeyboardButton("⬅️ חזרה לרשימה", callback_data=CB.TOPICS)],
        ]
    )


def recycle_bin_item_keyboard(media_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "♻️ שחזור", callback_data=f"{CB.REC_RESTORE}{media_id}"
                ),
                InlineKeyboardButton(
                    "🔥 מחיקה לצמיתות", callback_data=f"{CB.REC_PERM_DEL}{media_id}"
                ),
            ],
        ]
    )


def dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📜 יומן פעילות", callback_data=CB.DASH_LOG)],
            [InlineKeyboardButton("⬅️ חזרה", callback_data=CB.MAIN_MENU)],
        ]
    )


def settings_keyboard() -> InlineKeyboardMarkup:
    """Owner settings currently supported by complete, audited handlers."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("👤 ניהול משתמשים", callback_data=CB.ADMINS)],
            [InlineKeyboardButton("⬅️ חזרה", callback_data=CB.MAIN_MENU)],
        ]
    )


def admins_keyboard(admins: list) -> InlineKeyboardMarkup:
    """Owner-only actions for adding and revoking non-owner system access."""
    rows = [
        [
            InlineKeyboardButton("➕ הוסף Admin", callback_data=f"{CB.ADM_ADD}:admin"),
            InlineKeyboardButton(
                "➕ הוסף Viewer", callback_data=f"{CB.ADM_ADD}:viewer"
            ),
        ]
    ]
    for admin in admins:
        label = admin.display_name or admin.username or str(admin.telegram_user_id)
        rows.append(
            [
                InlineKeyboardButton(
                    f"🗑 הסר {label}", callback_data=f"{CB.ADM_REMOVE}{admin.id}"
                )
            ]
        )
    rows.append([InlineKeyboardButton("⬅️ חזרה", callback_data=CB.SETTINGS)])
    return InlineKeyboardMarkup(rows)


def backup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💾 גיבוי עכשיו", callback_data=CB.BACKUP_NOW)],
            [InlineKeyboardButton("📥 שחזור מגיבוי", callback_data=CB.BACKUP_RESTORE)],
            [InlineKeyboardButton("⬅️ חזרה", callback_data=CB.MAIN_MENU)],
        ]
    )
