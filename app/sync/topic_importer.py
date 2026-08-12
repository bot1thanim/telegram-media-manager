"""One-time local importer for historical Telegram forum topics and media.

This module is intentionally a local CLI, never a Render webhook handler. It
uses the account owner's Telegram User API authorization only to enumerate
existing forum topics/messages. The session file remains on the operator's
computer and is excluded from Git and the production database.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from telethon import TelegramClient, utils
from telethon.tl.functions.messages import GetForumTopicsRequest

from app.audit.logger import AuditAction, log_action
from app.config import config
from app.database.engine import close_engine, get_session, init_engine
from app.database.models.sync_run import SyncRun, SyncRunStatus, SyncRunType
from app.sync.services import ensure_source_category, ingest_source_media, upsert_topic

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HistoricalImportReport:
    """JSON-safe one-time-import result with per-topic exceptions."""

    source_topics: int = 0
    target_topics: int = 0
    categories_created: int = 0
    media_imported: int = 0
    duplicates_skipped: int = 0
    media_without_supported_type: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_topics": self.source_topics,
            "target_topics": self.target_topics,
            "categories_created": self.categories_created,
            "media_imported": self.media_imported,
            "duplicates_skipped": self.duplicates_skipped,
            "media_without_supported_type": self.media_without_supported_type,
            "failures": self.failures,
        }


def _required_import_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is required only for the local historical importer. "
            "Do not add it to Render."
        )
    return value


def _default_session_path() -> str:
    configured = os.environ.get("TELEGRAM_IMPORT_SESSION_PATH")
    if configured:
        return str(Path(configured).expanduser())
    return str(Path.home() / ".telegram-media-manager-import.session")


def _supported_media(
    message,
) -> tuple[str, str, str, int | None, int | None] | None:
    """Return type, handles, stable identity, size and duration for supported media."""
    if message.video is not None:
        media_type = "video"
        duration = getattr(message.video, "duration", None)
    elif message.photo is not None:
        media_type = "photo"
        duration = None
    elif message.document is not None:
        media_type = "document"
        duration = None
    else:
        return None

    packed_file_id = utils.pack_bot_file_id(message.media)
    if not packed_file_id:
        # The broadcaster copies historical source messages by their chat/message
        # identity. This value only fulfils the legacy non-null database field.
        packed_file_id = f"historical-source-{message.id}"
    file_size = getattr(getattr(message, "file", None), "size", None)
    media_identity = getattr(getattr(message, media_type, None), "id", None)
    file_unique_id = (
        f"mtproto-{media_type}-{media_identity}"
        if media_identity is not None
        else hashlib.sha256(f"{message.chat_id}:{message.id}".encode("utf-8")).hexdigest()
    )
    return media_type, packed_file_id, file_unique_id, file_size, duration


async def _iter_forum_topics(client: TelegramClient, entity) -> AsyncIterator[Any]:
    """Page all forum topics using Telegram's documented offset tuple."""
    offset_date = None
    offset_id = 0
    offset_topic = 0
    while True:
        page = await client(
            GetForumTopicsRequest(
                peer=entity,
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=100,
            )
        )
        topics = list(page.topics)
        if not topics:
            return
        for topic in topics:
            yield topic
        if len(topics) < 100:
            return
        last_topic = topics[-1]
        offset_date = last_topic.date
        offset_id = last_topic.top_message
        offset_topic = last_topic.id


async def _create_sync_run(source_chat_id: int, target_chat_id: int) -> SyncRun:
    async with get_session() as session:
        run = SyncRun(
            run_type=SyncRunType.HISTORICAL_IMPORT.value,
            status=SyncRunStatus.RUNNING.value,
            source_chat_id=source_chat_id,
            target_chat_id=target_chat_id,
            report={},
        )
        session.add(run)
        await session.flush()
        await log_action(
            session,
            AuditAction.TOPIC_SYNC_STARTED,
            details={"sync_run_id": run.id},
        )
        return run


async def _finish_sync_run(
    run_id: int, report: HistoricalImportReport, error: str | None = None
) -> None:
    async with get_session() as session:
        run = await session.get(SyncRun, run_id, with_for_update=True)
        if run is None:
            return
        run.report = report.as_dict()
        run.error_summary = error[:2000] if error else None
        run.status = (
            SyncRunStatus.FAILED.value if error else SyncRunStatus.COMPLETED.value
        )
        run.completed_at = datetime.now(timezone.utc)
        await log_action(
            session,
            AuditAction.TOPIC_SYNC_COMPLETED,
            details={"sync_run_id": run.id, "report": run.report, "error": run.error_summary},
        )


async def _catalog_target_topics(
    client: TelegramClient, entity, target_chat_id: int, report: HistoricalImportReport
) -> None:
    async for topic in _iter_forum_topics(client, entity):
        async with get_session() as session:
            await upsert_topic(
                session,
                chat_id=target_chat_id,
                thread_id=topic.id,
                name=topic.title,
                icon_color=topic.icon_color,
                is_closed=bool(topic.closed),
            )
        report.target_topics += 1


async def _import_source_topic(
    client: TelegramClient,
    entity,
    source_chat_id: int,
    topic,
    report: HistoricalImportReport,
) -> None:
    """Catalog one source topic and process all messages under its thread root."""
    async with get_session() as session:
        await upsert_topic(
            session,
            chat_id=source_chat_id,
            thread_id=topic.id,
            name=topic.title,
            icon_color=topic.icon_color,
            is_closed=bool(topic.closed),
        )
        category, created = await ensure_source_category(
            session,
            source_group_id=source_chat_id,
            source_thread_id=topic.id,
            topic_name=topic.title,
        )
        category_id = category.id
        if created:
            report.categories_created += 1
    report.source_topics += 1

    async for message in client.iter_messages(entity, reply_to=topic.id, reverse=True):
        supported = _supported_media(message)
        if supported is None:
            report.media_without_supported_type += 1
            continue
        media_type, file_id, stable_unique_id, file_size, duration = supported
        async with get_session() as session:
            result = await ingest_source_media(
                session,
                file_id=file_id,
                file_unique_id=stable_unique_id,
                media_type=media_type,
                file_size=file_size,
                caption=message.text,
                duration=duration,
                uploader_id=getattr(message, "sender_id", None),
                source_group_id=source_chat_id,
                source_thread_id=topic.id,
                source_message_id=message.id,
                category_id=category_id,
            )
        if result.is_new:
            report.media_imported += 1
        else:
            report.duplicates_skipped += 1


async def import_historical_topics(
    *, source_chat_id: int, target_chat_id: int
) -> HistoricalImportReport:
    """Connect locally, catalog target topics, and import source-topic media once."""
    api_id_raw = _required_import_env("TELEGRAM_API_ID")
    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise RuntimeError("TELEGRAM_API_ID must be numeric.") from exc
    api_hash = _required_import_env("TELEGRAM_API_HASH")
    session_path = _default_session_path()
    Path(session_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

    report = HistoricalImportReport()
    run = await _create_sync_run(source_chat_id, target_chat_id)
    client = TelegramClient(session_path, api_id, api_hash)
    try:
        await client.start()
        source_entity = await client.get_entity(source_chat_id)
        target_entity = await client.get_entity(target_chat_id)

        await _catalog_target_topics(client, target_entity, target_chat_id, report)
        async for topic in _iter_forum_topics(client, source_entity):
            try:
                await _import_source_topic(
                    client, source_entity, source_chat_id, topic, report
                )
            except Exception as exc:  # A bad topic must not cancel the entire import.
                logger.exception("Historical import failed for topic %s", topic.id)
                report.failures.append(
                    {"topic": str(topic.title), "reason": str(exc)[:500]}
                )
    except Exception as exc:
        await _finish_sync_run(run.id, report, str(exc))
        raise
    finally:
        await client.disconnect()

    await _finish_sync_run(run.id, report)
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import historical Telegram forum topics/media into Telegram Media Manager."
    )
    parser.add_argument(
        "--source-chat-id",
        type=int,
        default=config.SOURCE_GROUP_CHAT_ID,
        help="Source forum group ID; defaults to SOURCE_GROUP_CHAT_ID.",
    )
    parser.add_argument(
        "--target-chat-id",
        type=int,
        default=config.TARGET_GROUP_CHAT_ID,
        help="Target forum group ID; defaults to TARGET_GROUP_CHAT_ID.",
    )
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    init_engine(config.DATABASE_URL)
    try:
        report = await import_historical_topics(
            source_chat_id=args.source_chat_id, target_chat_id=args.target_chat_id
        )
    finally:
        await close_engine()
    print("Historical topic import completed:")
    for key, value in report.as_dict().items():
        if key != "failures":
            print(f"{key}: {value}")
    print(f"failures: {len(report.failures)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    asyncio.run(_main())
