"""
app/telegram/messages.py
==========================
Centralised catalogue of all user-facing message texts (Hebrew).
No message text should appear anywhere else in the codebase.
Corresponds to SRS §43 (UI message catalogue).
"""


class MSG:
    # --- General ---
    UNAUTHORIZED = "אין לך הרשאה להשתמש בבוט זה."
    VIEWER_NOT_AVAILABLE = "התכונה הזו עדיין לא זמינה."
    ERROR_GENERIC = "אירעה שגיאה. אנא נסה שוב."
    CANCELLED = "הפעולה בוטלה."

    # --- Main Menu ---
    MAIN_MENU_WELCOME = "ברוך הבא למערכת ניהול המדיה. בחר פעולה:"

    # --- Media Management sub-menu ---
    MEDIA_MGMT_MENU = "🎬 ניהול מדיה — בחר פעולה:"
    NO_ACTIVE_SESSION = "אין סשן מיון פעיל כרגע. התחל מיון חדש?"

    # --- Sorting ---
    SORT_ITEM_CAPTION = (
        "פריט #{id}\nגודל: {size} MB\n{duration_line}הועלה: {date}\nעל ידי: {uploader}"
    )
    SORT_DURATION_LINE = "משך: {duration} שניות\n"
    SORT_SAVED = "✅ נשמר בקטגוריה: {category_name}"
    SORT_DELETED = "🗑 הפריט הועבר לסל המיחזור."
    SORT_EMPTY = "🎉 אין פריטים הממתינים למיון כרגע. חזרה לתפריט הראשי."
    SORT_RESUMED = "▶️ ממשיך מהמקום שבו הפסקת, פריט #{id}"
    SORT_CHOOSE_CATEGORY = "בחר קטגוריה לשמירת הפריט:"
    SORT_CONCURRENT_CONFLICT = "⚠️ פריט זה כבר סווג בינתיים."

    # --- Handoff ---
    HANDOFF_PROMPT = (
        "⚠️ מנהל {name} כבר נמצא במיון פעיל (פריט #{media_id}). להמשיך במקומו?"
    )
    HANDOFF_NOTIFY = (
        "ℹ️ מנהל {name} המשיך את המיון בזמן שלא היית זמין. ההתקדמות שלו נשמרה."
    )

    # --- Categories ---
    CATEGORIES_MENU = "🗂 ניהול נושאים — בחר קטגוריה או צור חדשה:"
    CATEGORY_CREATE_NAME_PROMPT = "הזן שם לקטגוריה החדשה:"
    CATEGORY_LINK_NOW_PROMPT = (
        "האם לקשר קטגוריה זו ל-Topic קיים עכשיו, או לדלג ולקשר מאוחר יותר?"
    )
    CATEGORY_LINKED = "✅ הקטגוריה '{name}' קושרה בהצלחה ל-Topic '{topic_name}'."
    CATEGORY_RENAME_PROMPT = "הזן שם חדש לקטגוריה '{name}':"
    CATEGORY_RENAMED = "✅ הקטגוריה שונתה ל-'{name}'."
    CATEGORY_DELETED = "🗑 הקטגוריה נמחקה. {count} פריטים חזרו לתור המיון."
    CATEGORY_MERGE_CHOOSE = "בחר קטגוריה שאליה למזג את '{name}':"
    CATEGORY_MERGED = "✅ הקטגוריה '{source}' מוזגה לתוך '{target}'."
    CATEGORY_SYNC_PROMPT = (
        "נמצאו {n} Topics שלא מקושרים. הצע קישור אוטומטי לפי שם דומה?"
    )
    CATEGORY_SYNC_NONE = "כל ה-Topics כבר מקושרים לקטגוריות."
    CATEGORY_NAME_EXISTS = "⚠️ קטגוריה בשם '{name}' כבר קיימת."
    CATEGORY_NOT_FOUND = "⚠️ הקטגוריה לא נמצאה."

    # --- Import ---
    IMPORT_ALREADY_EXISTS = "⚠️ פריט זה כבר קיים במאגר (סטטוס: {status})."
    TOPIC_SYNC_LIVE_UPDATED = "✅ קטלוג הנושאים עודכן מהודעת Telegram חדשה."
    TOPIC_SYNC_HISTORICAL_GUIDANCE = (
        "ייבוא ההיסטוריה מוכן. יש להריץ את כלי הייבוא החד־פעמי מהמחשב שלך; "
        "הוא יבקש התחברות לחשבון Telegram באופן מאובטח ולא ישמור קודים או סיסמה בשרת."
    )
    DIRECT_UPLOAD_CATEGORY_MISSING = (
        "הקטגוריה שנבחרה אינה זמינה יותר. בחר קטגוריה חדשה לפני העלאה נוספת."
    )
    DIRECT_UPLOAD_SAVED = "✅ הפריט נשמר ישירות בקטגוריה: {category_name}"
    DIRECT_UPLOAD_DUPLICATE = (
        "⚠️ הפריט כבר קיים במאגר ולכן לא נשמר שוב (סטטוס: {status})."
    )


    # --- Duplicates ---
    DUPLICATES_MENU = "🔁 נמצאו {n} קבוצות כפילויות הממתינות לסקירה שלך:"
    DUPLICATES_NONE = "✅ אין כפילויות הממתינות לסקירה."

    # --- Publishing ---
    PUBLISH_MENU = "🚀 תפריט פרסום — בחר פעולה:"
    PUBLISH_CHOOSE_ORDER = "בחר סדר פרסום:"
    PUBLISH_DRY_RUN_HEADER = "תצוגה מקדימה — כך ייראה סדר הפרסום (לא נשלח דבר בפועל):"
    PUBLISH_PROGRESS = (
        "🚀 מפרסם ל: {category}\n"
        "{bar} {pct}% ({done}/{total})\n"
        "✅ נשלחו: {sent}   ⚠️ נכשלו: {failed}   ⏭ דולגו: {skipped}"
    )
    PUBLISH_BUSY = "יש כבר תהליך פרסום פעיל. עצור אותו קודם או המתן לסיום."
    PUBLISH_COMPLETED_DM = (
        "⏰ פרסום מתוזמן הושלם — קטגוריה: {category}. "
        "נשלחו: {sent}, נכשלו: {failed}, דולגו: {skipped}."
    )
    PUBLISH_BROKEN_DM = (
        "⚠️ פריט #{id} לא ניתן לפרסום — הקובץ פג תוקף בטלגרם. הפריט סומן כ'שבור'."
    )
    PUBLISH_NO_ITEMS = "אין פריטים מוכנים לפרסום בקטגוריה זו."
    TOPIC_BROADCAST_STARTED = (
        "השליחה לכל הקטגוריות התחילה. בסיום יישלח דוח עם הצלחות, כפילויות וחריגות."
    )
    TOPIC_BROADCAST_ALREADY_RUNNING = "כבר מתבצעת שליחה לכל הקטגוריות."


    # --- Recycle Bin ---
    RECYCLE_BIN_MENU = "🗑 סל מיחזור — פריטים שנמחקו:"
    RECYCLE_BIN_EMPTY = "✅ סל המיחזור ריק."
    RECYCLE_RESTORED = "♻️ הפריט שוחזר בהצלחה."
    RECYCLE_PERM_DELETED = "🔥 הפריט נמחק לצמיתות."

    # --- Dashboard ---
    DASHBOARD_HEADER = "📊 דשבורד — נכון ל-{datetime}"

    # --- Backup ---
    BACKUP_COMPLETED = "✅ הגיבוי הושלם ונשלח אליך כקובץ. שמור אותו במקום בטוח."
    BACKUP_RESTORE_SUMMARY = (
        "📥 שחזור זה יוסיף/יעדכן {categories} קטגוריות ו-{media} רשומות מדיה — "
        "רשומות קיימות שיזוהו לפי file_unique_id יעודכנו, לא ישוכפלו."
    )

    # --- Settings ---
    SETTINGS_MENU = "⚙️ הגדרות — בחר פרמטר לעריכה:"
    SETTINGS_SAVED = "✅ ההגדרה נשמרה."

    # --- Admins ---
    ADMINS_MENU = "👤 ניהול מנהלים — רשימה נוכחית:"
    ADMIN_ADDED = "✅ המנהל נוסף בהצלחה."
    ADMIN_REMOVED = "🗑 המנהל הוסר."
    ADMIN_PERMISSIONS_SAVED = "✅ ההרשאות עודכנו."
    ADMIN_FORWARD_PROMPT = (
        "העבר (Forward) הודעה מהמשתמש שברצונך להוסיף כמנהל, "
        "או הזן את ה-Telegram ID המספרי שלו:"
    )
    ADMIN_NOT_FOUND = "⚠️ המנהל לא נמצא."

    # --- Confirmation dialogs (SRS §29) ---
    CONFIRM_TEMPLATE = (
        "⚠️ פעולה זו {description}.\n{details}\nלא ניתן לבטל פעולה זו.\n\nהאם להמשיך?"
    )
    CONFIRM_DELETE_MEDIA = "תעביר את הפריט לסל המיחזור"
    CONFIRM_PERM_DELETE_MEDIA = "תמחק את הפריט לצמיתות מהמאגר (לא נוגע בטלגרם)"
    CONFIRM_DELETE_CATEGORY = "תמחק את הקטגוריה ותחזיר {count} פריטים לתור המיון"
    CONFIRM_MERGE_CATEGORY = "תמזג את '{source}' לתוך '{target}' ותעביר את כל הפריטים"
    CONFIRM_PUBLISH_ALL = "תפרסם {count} פריטים לכל הקטגוריות"
    CONFIRM_EMPTY_RECYCLE_BIN = "תמחק לצמיתות את כל {count} הפריטים בסל המיחזור"
    CONFIRM_REMOVE_ADMIN = "תסיר את המנהל {name} מהמערכת"
    CONFIRM_RESTORE_BACKUP = "תשחזר גיבוי ותדרוס נתונים קיימים"

    # --- Search ---
    SEARCH_PROMPT = "הזן טקסט לחיפוש (כיתוב, תגית, או מזהה פריט):"
    SEARCH_NO_RESULTS = "לא נמצאו תוצאות עבור '{query}'."

    # --- Pong (Phase 0 test) ---
    PONG = "pong 🏓"
