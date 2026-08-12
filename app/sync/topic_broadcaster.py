"""All-categories broadcaster with target-topic matching and durable delivery reports."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from telegram import Bot
from telegram.error import RetryAfter, TelegramError

from app.audit.logger import AuditAction, log_action
from app.config import config
from app.database.engine import get_session
from app.database.models.category import Category
from app.database.models.media import Media, MediaStatus
from app.database.models.media_delivery import MediaDelivery, MediaDeliveryState
from app.database.models.sync_run import SyncRun, SyncRunStatus, SyncRunType
from app.database.models.topic_catalog import TopicCatalog
from app.sync.matching import TopicNameMatch, choose_best_topic_match
from app.sync.services import list_active_topics, upsert_topic

logger = logging.getLogger(__name__)


class BroadcastAlreadyRunningError(RuntimeError):
    """Raised when a durable active-broadcast guard rejects a duplicate request."""


@dataclass(slots=True)
class BroadcastReport:
    """Serializable summary returned to the Telegram UI and stored in SyncRun."""

    categories_total: int = 0
    categories_with_media: int = 0
    topics_matched: int = 0
    topics_created: int = 0
    messages_sent: int = 0
    duplicates_skipped: int = 0
    media_skipped: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)
    category_results: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "categories_total": self.categories_total,
            "categories_with_media": self.categories_with_media,
            "topics_matched": self.topics_matched,
            "topics_created": self.topics_created,
            "messages_sent": self.messages_sent,
            "duplicates_skipped": self.duplicates_skipped,
            "media_skipped": self.media_skipped,
            "failures": self.failures,
            "category_results": self.category_results,
        }

    def to_telegram_text(self) -> str:
        """Render a bounded Hebrew report suitable for a standard Telegram message."""
        lines = [
            "**דוח שליחה לכל הקטגוריות**",
            f"קטגוריות שנסרקו: {self.categories_total}",
            f"קטגוריות עם מדיה: {self.categories_with_media}",
            f"נושאים שהותאמו: {self.topics_matched}",
            f"נושאים שנוצרו: {self.topics_created}",
            f"מדיה שנשלחה: {self.messages_sent}",
            f"כפילויות שדולגו: {self.duplicates_skipped}",
            f"פריטים שדולגו: {self.media_skipped}",
        ]
        if self.failures:
            lines.append(f"כשלים: {len(self.failures)}")
            for failure in self.failures[:10]:
                lines.append(
                    f"• {failure['category']}: {failure['reason'][:180]}"
                )
            if len(self.failures) > 10:
                lines.append(f"• ועוד {len(self.failures) - 10} כשלים בדוח השמור.")
        else:
            lines.append("לא נמצאו כשלים.")
        return "\n".join(lines)


async def _create_run(requested_by_user_id: int) -> SyncRun:
    try:
        async with get_session() as session:
            run = SyncRun(
                run_type=SyncRunType.TOPIC_BROADCAST.value,
                status=SyncRunStatus.RUNNING.value,
                requested_by_user_id=requested_by_user_id,
                source_chat_id=config.SOURCE_GROUP_CHAT_ID,
                target_chat_id=config.TARGET_GROUP_CHAT_ID,
                report={},
            )
            session.add(run)
            await session.flush()
            await log_action(
                session,
                AuditAction.TOPIC_BROADCAST_STARTED,
                actor_telegram_id=requested_by_user_id,
                details={"sync_run_id": run.id},
            )
            return run
    except IntegrityError as exc:
        raise BroadcastAlreadyRunningError("A topic broadcast is already running.") from exc


async def _finish_run(run_id: int, report: BroadcastReport, error: str | None = None) -> None:
    async with get_session() as session:
        run = await session.get(SyncRun, run_id, with_for_update=True)
        if run is None:
            logger.error("Sync run %d disappeared before completion", run_id)
            return
        run.report = report.as_dict()
        run.error_summary = error[:2000] if error else None
        run.status = (
            SyncRunStatus.FAILED.value if error else SyncRunStatus.COMPLETED.value
        )
        run.completed_at = datetime.now(timezone.utc)
        await log_action(
            session,
            AuditAction.TOPIC_BROADCAST_COMPLETED,
            actor_telegram_id=run.requested_by_user_id,
            details={"sync_run_id": run.id, "report": run.report, "error": run.error_summary},
        )


async def _read_categories() -> list[Category]:
    async with get_session() as session:
        result = await session.execute(
            select(Category)
            .where(Category.is_deleted.is_(False))
            .order_by(Category.name.asc())
        )
        return list(result.scalars().all())


async def _read_ready_media(category_id: int) -> list[Media]:
    async with get_session() as session:
        result = await session.execute(
            select(Media)
            .where(
                Media.category_id == category_id,
                Media.status == MediaStatus.READY_TO_PUBLISH.value,
            )
            .order_by(Media.created_at.asc(), Media.id.asc())
        )
        return list(result.scalars().all())


async def _resolve_target_topic(
    bot: Bot, category: Category
) -> tuple[int | None, str, TopicNameMatch | None]:
    """Return the target thread ID, creating a topic only when no safe match exists."""
    async with get_session() as session:
        if (
            category.target_group_id == config.TARGET_GROUP_CHAT_ID
            and category.telegram_thread_id is not None
        ):
            existing = (
                await session.execute(
                    select(TopicCatalog).where(
                        TopicCatalog.chat_id == config.TARGET_GROUP_CHAT_ID,
                        TopicCatalog.thread_id == category.telegram_thread_id,
                        TopicCatalog.is_deleted.is_(False),
                        TopicCatalog.is_closed.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing.thread_id, "linked", None

        topics = await list_active_topics(session, config.TARGET_GROUP_CHAT_ID)
        match = choose_best_topic_match(category.name, topics)
        if match.is_match:
            topic = next(topic for topic in topics if topic.id == match.topic_id)
            category.telegram_thread_id = topic.thread_id
            category.target_group_id = config.TARGET_GROUP_CHAT_ID
            category.topic_missing = False
            await session.flush()
            return topic.thread_id, match.method, match

    # The network call is intentionally outside an open database transaction.
    try:
        created = await bot.create_forum_topic(
            chat_id=config.TARGET_GROUP_CHAT_ID, name=category.name
        )
    except TelegramError as exc:
        async with get_session() as session:
            category_row = await session.get(Category, category.id, with_for_update=True)
            if category_row is not None:
                category_row.topic_missing = True
        return None, f"create_failed:{exc}", None

    async with get_session() as session:
        await upsert_topic(
            session,
            chat_id=config.TARGET_GROUP_CHAT_ID,
            thread_id=created.message_thread_id,
            name=created.name,
            icon_color=created.icon_color,
        )
        category_row = await session.get(Category, category.id, with_for_update=True)
        if category_row is not None:
            category_row.telegram_thread_id = created.message_thread_id
            category_row.target_group_id = config.TARGET_GROUP_CHAT_ID
            category_row.topic_missing = False
        await log_action(
            session,
            AuditAction.TARGET_TOPIC_CREATED,
            target_category_id=category.id,
            details={
                "target_group_id": config.TARGET_GROUP_CHAT_ID,
                "target_thread_id": created.message_thread_id,
                "name": created.name,
            },
        )
    return created.message_thread_id, "created", None


async def _claim_delivery(
    *,
    media_id: int,
    run_id: int,
    target_thread_id: int,
) -> tuple[int | None, str | None]:
    """Durably claim one delivery before any external Telegram call."""
    async with get_session() as session:
        result = await session.execute(
            select(MediaDelivery)
            .where(
                MediaDelivery.media_id == media_id,
                MediaDelivery.target_chat_id == config.TARGET_GROUP_CHAT_ID,
                MediaDelivery.target_thread_id == target_thread_id,
            )
            .with_for_update()
        )
        delivery = result.scalar_one_or_none()
        if delivery is not None:
            if delivery.state == MediaDeliveryState.SENT.value:
                return None, "already_sent"
            if delivery.state == MediaDeliveryState.SENDING.value:
                delivery.state = MediaDeliveryState.FAILED.value
                delivery.last_error = (
                    "A prior delivery was interrupted while Telegram outcome was unknown; "
                    "not retried automatically to avoid a duplicate."
                )
                return None, "uncertain_previous_delivery"
            delivery.state = MediaDeliveryState.SENDING.value
            delivery.sync_run_id = run_id
            delivery.last_error = None
            await session.flush()
            return delivery.id, None

        delivery = MediaDelivery(
            media_id=media_id,
            sync_run_id=run_id,
            target_chat_id=config.TARGET_GROUP_CHAT_ID,
            target_thread_id=target_thread_id,
            state=MediaDeliveryState.SENDING.value,
        )
        session.add(delivery)
        await session.flush()
        return delivery.id, None


async def _mark_delivery_sent(delivery_id: int, message_id: int | None) -> None:
    async with get_session() as session:
        delivery = await session.get(MediaDelivery, delivery_id, with_for_update=True)
        if delivery is None or delivery.state != MediaDeliveryState.SENDING.value:
            return
        delivery.state = MediaDeliveryState.SENT.value
        delivery.target_message_id = message_id
        delivery.sent_at = datetime.now(timezone.utc)


async def _mark_delivery_failed(delivery_id: int, error: str) -> None:
    async with get_session() as session:
        delivery = await session.get(MediaDelivery, delivery_id, with_for_update=True)
        if delivery is None or delivery.state != MediaDeliveryState.SENDING.value:
            return
        delivery.state = MediaDeliveryState.FAILED.value
        delivery.last_error = error[:2000]


async def _send_media(bot: Bot, media: Media, target_thread_id: int):
    """Copy source messages when possible; otherwise use the bot-owned file handle."""
    if media.source_group_id is not None and media.source_message_id is not None:
        return await bot.copy_message(
            chat_id=config.TARGET_GROUP_CHAT_ID,
            from_chat_id=media.source_group_id,
            message_id=media.source_message_id,
            message_thread_id=target_thread_id,
        )

    common: dict[str, Any] = {
        "chat_id": config.TARGET_GROUP_CHAT_ID,
        "caption": media.caption,
        "message_thread_id": target_thread_id,
    }
    if media.media_type == "video":
        return await bot.send_video(video=media.file_id, **common)
    if media.media_type == "photo":
        return await bot.send_photo(photo=media.file_id, **common)
    if media.media_type == "document":
        return await bot.send_document(document=media.file_id, **common)
    raise ValueError(f"Unsupported media type: {media.media_type}")


async def broadcast_all_categories(bot: Bot, requested_by_user_id: int) -> BroadcastReport:
    """Publish all ready media into matching or newly created target forum topics."""
    run = await _create_run(requested_by_user_id)
    report = BroadcastReport()
    try:
        categories = await _read_categories()
        report.categories_total = len(categories)
        for category in categories:
            media_items = await _read_ready_media(category.id)
            if not media_items:
                report.media_skipped += 1
                report.category_results.append(
                    {"category": category.name, "status": "empty", "messages_sent": 0}
                )
                continue

            report.categories_with_media += 1
            target_thread_id, resolution, _match = await _resolve_target_topic(bot, category)
            if target_thread_id is None:
                reason = resolution.removeprefix("create_failed:")
                report.failures.append({"category": category.name, "reason": reason})
                report.category_results.append(
                    {"category": category.name, "status": "target_unavailable", "reason": reason}
                )
                continue
            if resolution == "created":
                report.topics_created += 1
            else:
                report.topics_matched += 1

            category_sent = 0
            category_failed = 0
            for media in media_items:
                delivery_id, skip_reason = await _claim_delivery(
                    media_id=media.id, run_id=run.id, target_thread_id=target_thread_id
                )
                if delivery_id is None:
                    if skip_reason == "already_sent":
                        report.duplicates_skipped += 1
                    else:
                        report.media_skipped += 1
                        report.failures.append(
                            {"category": category.name, "reason": skip_reason or "delivery skipped"}
                        )
                    continue
                try:
                    sent_message = await _send_media(bot, media, target_thread_id)
                except RetryAfter as exc:
                    retry_after = exc.retry_after
                    delay = (
                        retry_after.total_seconds()
                        if hasattr(retry_after, "total_seconds")
                        else float(retry_after)
                    )
                    await _mark_delivery_failed(
                        delivery_id, f"Telegram flood control requested retry after {delay:.0f}s."
                    )
                    await asyncio.sleep(delay)
                    category_failed += 1
                    report.failures.append(
                        {"category": category.name, "reason": "הגבלת קצב של Telegram; נסה שוב."}
                    )
                except (TelegramError, ValueError) as exc:
                    await _mark_delivery_failed(delivery_id, str(exc))
                    category_failed += 1
                    report.failures.append({"category": category.name, "reason": str(exc)})
                except Exception as exc:  # Defensive boundary around external delivery.
                    logger.exception("Unexpected all-categories delivery failure")
                    await _mark_delivery_failed(delivery_id, str(exc))
                    category_failed += 1
                    report.failures.append({"category": category.name, "reason": "שגיאה פנימית בעת השליחה."})
                else:
                    await _mark_delivery_sent(
                        delivery_id, getattr(sent_message, "message_id", None)
                    )
                    category_sent += 1
                    report.messages_sent += 1

            report.category_results.append(
                {
                    "category": category.name,
                    "status": "completed" if category_failed == 0 else "partial_failure",
                    "target_thread_id": target_thread_id,
                    "messages_sent": category_sent,
                    "messages_failed": category_failed,
                }
            )
    except Exception as exc:
        logger.exception("All-categories broadcast run %d failed", run.id)
        await _finish_run(run.id, report, str(exc))
        raise
    await _finish_run(run.id, report)
    return report
