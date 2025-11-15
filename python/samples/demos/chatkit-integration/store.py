# Copyright (c) Microsoft. All rights reserved.

"""SQLite-based store implementation for ChatKit data persistence.

This module provides a complete Store implementation using SQLite for data persistence.
It includes proper thread safety, user isolation, and follows the ChatKit Store protocol.
"""

import sqlite3
import uuid
from typing import Any

from chatkit.store import NotFoundError, Store
from chatkit.types import (
    Attachment,
    Page,
    ThreadItem,
    ThreadMetadata,
)
from pydantic import BaseModel


class ThreadData(BaseModel):
    """Model for serializing thread data to SQLite."""

    thread: ThreadMetadata


class ItemData(BaseModel):
    """Model for serializing thread item data to SQLite."""

    item: ThreadItem


class AttachmentData(BaseModel):
    """Model for serializing attachment data to SQLite."""

    attachment: Attachment


class SQLiteStore(Store[dict[str, Any]]):
    """SQLite-based store implementation for ChatKit data.

    This implementation follows the pattern from the ChatKit Python tests
    and provides persistent storage for threads, messages, and attachments.

    Features:
    - Thread-safe SQLite connections with WAL mode
    - User isolation for multi-tenant support
    - Proper error handling and transaction management
    - Complete Store protocol implementation

    Note: This is for demonstration purposes. In production, you should
    implement proper error handling, connection pooling, and migration strategies.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or "chatkit_demo.db"  # Use file-based DB for demo
        self._create_tables()

    def _create_connection(self):
        # Enable thread safety and WAL mode for better concurrent access
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _create_tables(self):
        with self._create_connection() as conn:
            # Create threads table
            conn.execute(
                """CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                data TEXT NOT NULL
                )"""
            )

            # Create items table
            conn.execute(
                """CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                data TEXT NOT NULL
                )"""
            )

            # Create attachments table
            conn.execute(
                """CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                data TEXT NOT NULL
                )"""
            )
            conn.commit()

    def generate_thread_id(self, context: dict[str, Any]) -> str:
        return f"thr_{uuid.uuid4().hex[:8]}"

    def generate_item_id(
        self,
        item_type: str,
        thread: ThreadMetadata,
        context: dict[str, Any],
    ) -> str:
        prefix_map = {
            "message": "msg",
            "tool_call": "tc",
            "task": "tsk",
            "workflow": "wf",
            "attachment": "atc",
        }
        prefix = prefix_map.get(item_type, "itm")
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    async def load_thread(self, thread_id: str, context: dict[str, Any]) -> ThreadMetadata:
        user_id = context.get("user_id", "demo_user")

        with self._create_connection() as conn:
            cursor = conn.execute(
                "SELECT data FROM threads WHERE id = ? AND user_id = ?",
                (thread_id, user_id),
            ).fetchone()

            if cursor is None:
                raise NotFoundError(f"Thread {thread_id} not found")

            thread_data = ThreadData.model_validate_json(cursor[0])
            return thread_data.thread

    async def save_thread(self, thread: ThreadMetadata, context: dict[str, Any]) -> None:
        user_id = context.get("user_id", "demo_user")

        with self._create_connection() as conn:
            thread_data = ThreadData(thread=thread)

            # Replace existing thread data
            conn.execute(
                "DELETE FROM threads WHERE id = ? AND user_id = ?",
                (thread.id, user_id),
            )
            conn.execute(
                "INSERT INTO threads (id, user_id, created_at, data) VALUES (?, ?, ?, ?)",
                (
                    thread.id,
                    user_id,
                    thread.created_at.isoformat(),
                    thread_data.model_dump_json(),
                ),
            )
            conn.commit()

    async def load_thread_items(
        self,
        thread_id: str,
        after: str | None,
        limit: int,
        order: str,
        context: dict[str, Any],
    ) -> Page[ThreadItem]:
        user_id = context.get("user_id", "demo_user")

        with self._create_connection() as conn:
            created_after: str | None = None
            if after:
                after_cursor = conn.execute(
                    "SELECT created_at FROM items WHERE id = ? AND user_id = ?",
                    (after, user_id),
                ).fetchone()
                if after_cursor is None:
                    raise NotFoundError(f"Item {after} not found")
                created_after = after_cursor[0]

            query = """
                SELECT data FROM items
                WHERE thread_id = ? AND user_id = ?
            """
            params: list[Any] = [thread_id, user_id]

            if created_after:
                query += " AND created_at > ?" if order == "asc" else " AND created_at < ?"
                params.append(created_after)

            query += f" ORDER BY created_at {order} LIMIT ?"
            params.append(limit + 1)

            items_cursor = conn.execute(query, params).fetchall()
            items = [ItemData.model_validate_json(row[0]).item for row in items_cursor]

            has_more = len(items) > limit
            if has_more:
                items = items[:limit]

            return Page[ThreadItem](data=items, has_more=has_more, after=items[-1].id if items else None)

    async def save_attachment(self, attachment: Attachment, context: dict[str, Any]) -> None:
        user_id = context.get("user_id", "demo_user")

        with self._create_connection() as conn:
            attachment_data = AttachmentData(attachment=attachment)
            conn.execute(
                "INSERT OR REPLACE INTO attachments (id, user_id, data) VALUES (?, ?, ?)",
                (
                    attachment.id,
                    user_id,
                    attachment_data.model_dump_json(),
                ),
            )
            conn.commit()

    async def load_attachment(self, attachment_id: str, context: dict[str, Any]) -> Attachment:
        user_id = context.get("user_id", "demo_user")

        with self._create_connection() as conn:
            cursor = conn.execute(
                "SELECT data FROM attachments WHERE id = ? AND user_id = ?",
                (attachment_id, user_id),
            ).fetchone()

            if cursor is None:
                raise NotFoundError(f"Attachment {attachment_id} not found")

            attachment_data = AttachmentData.model_validate_json(cursor[0])
            return attachment_data.attachment

    async def delete_attachment(self, attachment_id: str, context: dict[str, Any]) -> None:
        user_id = context.get("user_id", "demo_user")

        with self._create_connection() as conn:
            conn.execute(
                "DELETE FROM attachments WHERE id = ? AND user_id = ?",
                (attachment_id, user_id),
            )
            conn.commit()

    async def load_threads(
        self,
        limit: int,
        after: str | None,
        order: str,
        context: dict[str, Any],
    ) -> Page[ThreadMetadata]:
        user_id = context.get("user_id", "demo_user")

        with self._create_connection() as conn:
            created_after: str | None = None
            if after:
                after_cursor = conn.execute(
                    "SELECT created_at FROM threads WHERE id = ? AND user_id = ?",
                    (after, user_id),
                ).fetchone()
                if after_cursor is None:
                    raise NotFoundError(f"Thread {after} not found")
                created_after = after_cursor[0]

            query = "SELECT data FROM threads WHERE user_id = ?"
            params: list[Any] = [user_id]

            if created_after:
                query += " AND created_at > ?" if order == "asc" else " AND created_at < ?"
                params.append(created_after)

            query += f" ORDER BY created_at {order} LIMIT ?"
            params.append(limit + 1)

            threads_cursor = conn.execute(query, params).fetchall()
            threads = [ThreadData.model_validate_json(row[0]).thread for row in threads_cursor]

            has_more = len(threads) > limit
            if has_more:
                threads = threads[:limit]

            return Page[ThreadMetadata](data=threads, has_more=has_more, after=threads[-1].id if threads else None)

    async def add_thread_item(self, thread_id: str, item: ThreadItem, context: dict[str, Any]) -> None:
        user_id = context.get("user_id", "demo_user")

        with self._create_connection() as conn:
            item_data = ItemData(item=item)
            conn.execute(
                "INSERT INTO items (id, thread_id, user_id, created_at, data) VALUES (?, ?, ?, ?, ?)",
                (
                    item.id,
                    thread_id,
                    user_id,
                    item.created_at.isoformat(),
                    item_data.model_dump_json(),
                ),
            )
            conn.commit()

    async def save_item(self, thread_id: str, item: ThreadItem, context: dict[str, Any]) -> None:
        user_id = context.get("user_id", "demo_user")

        with self._create_connection() as conn:
            item_data = ItemData(item=item)
            conn.execute(
                "UPDATE items SET data = ? WHERE id = ? AND thread_id = ? AND user_id = ?",
                (
                    item_data.model_dump_json(),
                    item.id,
                    thread_id,
                    user_id,
                ),
            )
            conn.commit()

    async def load_item(self, thread_id: str, item_id: str, context: dict[str, Any]) -> ThreadItem:
        user_id = context.get("user_id", "demo_user")

        with self._create_connection() as conn:
            cursor = conn.execute(
                "SELECT data FROM items WHERE id = ? AND thread_id = ? AND user_id = ?",
                (item_id, thread_id, user_id),
            ).fetchone()

            if cursor is None:
                raise NotFoundError(f"Item {item_id} not found in thread {thread_id}")

            item_data = ItemData.model_validate_json(cursor[0])
            return item_data.item

    async def delete_thread(self, thread_id: str, context: dict[str, Any]) -> None:
        user_id = context.get("user_id", "demo_user")

        with self._create_connection() as conn:
            conn.execute(
                "DELETE FROM threads WHERE id = ? AND user_id = ?",
                (thread_id, user_id),
            )
            conn.execute(
                "DELETE FROM items WHERE thread_id = ? AND user_id = ?",
                (thread_id, user_id),
            )
            conn.commit()

    async def delete_thread_item(self, thread_id: str, item_id: str, context: dict[str, Any]) -> None:
        user_id = context.get("user_id", "demo_user")

        with self._create_connection() as conn:
            conn.execute(
                "DELETE FROM items WHERE id = ? AND thread_id = ? AND user_id = ?",
                (item_id, thread_id, user_id),
            )
            conn.commit()
