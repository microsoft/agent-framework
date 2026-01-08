"""SQLite-backed image storage utilities aligned with agent-framework conventions."""

from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence, TypeVar

from agent_framework._serialization import SerializationMixin
from agent_framework.observability import get_tracer
from opentelemetry.trace import SpanKind

__all__ = ["ImageRecord", "SQLiteImageStore", "SQLiteImageStoreState"]

DEFAULT_DB_PATH = Path(__file__).with_name("image_database.db")
DEFAULT_EXPORT_DIR = Path(__file__).with_name("extracted_images")

T = TypeVar("T")


@dataclass(slots=True)
class ImageRecord:
    """Structural representation of a row in the images table."""

    id: int
    text_id: str
    metadata: dict[str, Any] | None
    image_path: str | None
    image_name: str | None
    mime_type: str
    description: str | None
    created_at: str
    updated_at: str
    image_data: bytes | None = None

    def tags(self) -> list[str]:
        payload: Iterable[str] | str | None = None
        if isinstance(self.metadata, dict):
            payload = self.metadata.get("tags")
        if payload is None:
            return []
        if isinstance(payload, str):
            items = [item.strip() for item in payload.split(",")]
        else:
            items = [str(item).strip() for item in payload]
        unique: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item and item not in seen:
                seen.add(item)
                unique.append(item)
        return unique

    def to_dict(self, *, include_data: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "text_id": self.text_id,
            "metadata": self.metadata,
            "image_path": self.image_path,
            "image_name": self.image_name,
            "mime_type": self.mime_type,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags(),
        }
        if include_data and self.image_data is not None:
            encoded = base64.b64encode(self.image_data).decode("utf-8")
            result["base64_data"] = encoded
            result["data_url"] = f"data:{self.mime_type};base64,{encoded}"
        return result


class SQLiteImageStoreState(SerializationMixin):
    """Serializable configuration for SQLiteImageStore."""

    def __init__(self, *, db_path: str | None = None, export_dir: str | None = None) -> None:
        self.db_path = db_path or str(DEFAULT_DB_PATH)
        self.export_dir = export_dir or str(DEFAULT_EXPORT_DIR)


class SQLiteImageStore:
    """Async-first SQLite store used by the observability samples."""

    def __init__(self, *, db_path: str | Path = DEFAULT_DB_PATH, export_dir: str | Path = DEFAULT_EXPORT_DIR) -> None:
        self._db_path = Path(db_path)
        self._export_dir = Path(export_dir)
        self._export_dir.mkdir(parents=True, exist_ok=True)
        self._tracer = get_tracer()
        self._ensure_schema()

    async def add_image_from_bytes(
        self,
        *,
        text_id: str,
        image_bytes: bytes,
        image_name: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | str | None = None,
        tags: Sequence[str] | None = None,
        mime_type: str = "image/png",
        source_path: str | None = None,
    ) -> ImageRecord:
        metadata_json = self._prepare_metadata(metadata, tags)
        now = datetime.utcnow().isoformat()

        def _operation(connection: sqlite3.Connection) -> int:
            cursor = connection.execute(
                """
                INSERT INTO images (
                    text_id,
                    metadata,
                    image_path,
                    image_data,
                    image_name,
                    mime_type,
                    description,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    text_id,
                    metadata_json,
                    source_path,
                    sqlite3.Binary(image_bytes),
                    image_name,
                    mime_type,
                    description,
                    now,
                    now,
                ),
            )
            return cursor.lastrowid

        with self._tracer.start_as_current_span(
            "sqlite_image_store.add_image_from_bytes",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute("image.text_id", text_id)
            span.set_attribute("image.mime_type", mime_type)
            span.set_attribute("image.has_metadata", metadata_json is not None)
            record_id = await self._run(_operation)
        record = await self.get_image_by_id(record_id, include_data=False)
        if record is None:
            raise RuntimeError("Image insert succeeded but record fetch failed")
        return record

    async def add_image_from_file(
        self,
        *,
        text_id: str,
        file_path: str | Path,
        description: str | None = None,
        metadata: dict[str, Any] | str | None = None,
        tags: Sequence[str] | None = None,
        mime_type: str | None = None,
        persist_copy: bool = False,
    ) -> ImageRecord:
        source = Path(file_path)
        image_bytes = source.read_bytes()
        name = source.name
        stored_path: str | None
        if persist_copy:
            target_dir = self._export_dir / "imports"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / name
            target_path.write_bytes(image_bytes)
            stored_path = str(target_path)
        else:
            stored_path = str(source)
        return await self.add_image_from_bytes(
            text_id=text_id,
            image_bytes=image_bytes,
            image_name=name,
            description=description,
            metadata=metadata,
            tags=tags,
            mime_type=mime_type or self._guess_mime_type(source.suffix),
            source_path=stored_path,
        )

    async def add_image_from_base64(
        self,
        *,
        text_id: str,
        base64_data: str,
        image_name: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | str | None = None,
        tags: Sequence[str] | None = None,
        mime_type: str = "image/png",
        image_uri: str | None = None,
    ) -> ImageRecord:
        payload = base64.b64decode(base64_data)

        # If image_uri is supplied, fold it into metadata so it is persisted.
        merged_metadata: dict[str, Any] | str | None
        if image_uri is None:
            merged_metadata = metadata
        elif metadata is None:
            merged_metadata = {"image_uri": image_uri}
        elif isinstance(metadata, dict):
            merged = dict(metadata)
            merged.setdefault("image_uri", image_uri)
            merged_metadata = merged
        else:
            # metadata is a non-dict (e.g., str); wrap to preserve both
            merged_metadata = {"metadata": metadata, "image_uri": image_uri}

        return await self.add_image_from_bytes(
            text_id=text_id,
            image_bytes=payload,
            image_name=image_name,
            description=description,
            metadata=merged_metadata,
            tags=tags,
            mime_type=mime_type,
        )

    async def get_image_by_id(self, record_id: int, *, include_data: bool = False) -> ImageRecord | None:
        def _operation(connection: sqlite3.Connection) -> ImageRecord | None:
            cursor = connection.execute("SELECT * FROM images WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_record(row, include_data=include_data)

        with self._tracer.start_as_current_span(
            "sqlite_image_store.get_image_by_id",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute("image.id", record_id)
            record = await self._run(_operation)
            span.set_attribute("result.found", record is not None)
            return record

    async def get_image_by_text_id(self, text_id: str, *, include_data: bool = False) -> ImageRecord | None:
        def _operation(connection: sqlite3.Connection) -> ImageRecord | None:
            cursor = connection.execute(
                """
                SELECT * FROM images
                WHERE text_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (text_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_record(row, include_data=include_data)

        with self._tracer.start_as_current_span(
            "sqlite_image_store.get_image_by_text_id",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute("image.text_id", text_id)
            record = await self._run(_operation)
            span.set_attribute("result.found", record is not None)
            return record

    async def list_images(self, *, include_data: bool = False) -> list[ImageRecord]:
        def _operation(connection: sqlite3.Connection) -> list[ImageRecord]:
            cursor = connection.execute(
                "SELECT * FROM images ORDER BY created_at DESC, id DESC",
            )
            rows = cursor.fetchall()
            return [self._row_to_record(row, include_data=include_data) for row in rows]

        with self._tracer.start_as_current_span(
            "sqlite_image_store.list_images",
            kind=SpanKind.INTERNAL,
        ):
            return await self._run(_operation)

    async def search_images(self, query: str, *, include_data: bool = False) -> list[ImageRecord]:
        pattern = f"%{query}%"

        def _operation(connection: sqlite3.Connection) -> list[ImageRecord]:
            cursor = connection.execute(
                """
                SELECT * FROM images
                WHERE metadata LIKE ? OR description LIKE ?
                ORDER BY created_at DESC, id DESC
                """,
                (pattern, pattern),
            )
            rows = cursor.fetchall()
            return [self._row_to_record(row, include_data=include_data) for row in rows]

        with self._tracer.start_as_current_span(
            "sqlite_image_store.search_images",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute("search.query", query)
            return await self._run(_operation)

    async def save_image_to_file(
        self,
        *,
        record_id: int | None = None,
        text_id: str | None = None,
        output_dir: str | Path | None = None,
    ) -> Path | None:
        if record_id is None and text_id is None:
            raise ValueError("Either record_id or text_id must be provided")
        record = (
            await self.get_image_by_id(record_id, include_data=True) if record_id is not None else await self.get_image_by_text_id(text_id or "", include_data=True)
        )
        if record is None or record.image_data is None:
            return None
        directory = Path(output_dir) if output_dir else self._export_dir
        directory.mkdir(parents=True, exist_ok=True)
        extension = self._guess_extension(record.mime_type)
        filename = record.image_name or f"{record.text_id}_{record.id}.{extension}"
        target = directory / filename
        target.write_bytes(record.image_data)
        await self._update_image_path(record.id, str(target))
        return target

    async def add_tags(self, *, text_id: str, tags: Sequence[str], replace_existing: bool = False) -> ImageRecord | None:
        record = await self.get_image_by_text_id(text_id, include_data=False)
        if record is None:
            return None
        metadata_dict = dict(record.metadata) if isinstance(record.metadata, dict) else {}
        existing = [] if replace_existing else record.tags()
        merged = sorted({tag.strip().lower() for tag in (*existing, *tags) if tag.strip()})
        if merged:
            metadata_dict["tags"] = merged
        elif "tags" in metadata_dict:
            metadata_dict.pop("tags")
        await self._update_metadata(record.id, metadata_dict)
        return await self.get_image_by_id(record.id, include_data=False)

    async def get_all_available_tags(self) -> dict[str, Any]:
        records = await self.list_images(include_data=False)
        counts: dict[str, int] = {}
        for record in records:
            for tag in record.tags():
                counts[tag] = counts.get(tag, 0) + 1
        ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        return {
            "unique_tags": len(counts),
            "tags": [{"tag": tag, "count": count} for tag, count in ordered],
        }

    async def get_all_images_as_base64(self) -> list[dict[str, Any]]:
        records = await self.list_images(include_data=True)
        return [record.to_dict(include_data=True) for record in records if record.image_data is not None]

    async def export_images_as_base64_json(self, output_file: str | Path) -> Path:
        payload = {
            "exported_at": datetime.utcnow().isoformat(),
            "images": await self.get_all_images_as_base64(),
        }
        path = Path(output_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    async def clear(self) -> None:
        def _operation(connection: sqlite3.Connection) -> None:
            connection.execute("DELETE FROM images")

        with self._tracer.start_as_current_span(
            "sqlite_image_store.clear",
            kind=SpanKind.INTERNAL,
        ):
            await self._run(_operation)

    async def serialize(self, **kwargs: Any) -> dict[str, Any]:
        state = SQLiteImageStoreState(db_path=str(self._db_path), export_dir=str(self._export_dir))
        return state.to_dict(**kwargs)

    @classmethod
    async def deserialize(cls, serialized_store_state: Any, **kwargs: Any) -> SQLiteImageStore:
        state = SQLiteImageStoreState.from_dict(serialized_store_state, **kwargs)
        return cls(db_path=state.db_path, export_dir=state.export_dir)

    async def update_from_state(self, serialized_store_state: Any, **kwargs: Any) -> None:
        if not serialized_store_state:
            return
        state = SQLiteImageStoreState.from_dict(serialized_store_state, **kwargs)
        self._db_path = Path(state.db_path)
        self._export_dir = Path(state.export_dir)
        self._export_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    async def _update_metadata(self, record_id: int, metadata: dict[str, Any] | None) -> None:
        timestamp = datetime.utcnow().isoformat()
        metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None

        def _operation(connection: sqlite3.Connection) -> None:
            connection.execute(
                "UPDATE images SET metadata = ?, updated_at = ? WHERE id = ?",
                (metadata_json, timestamp, record_id),
            )

        await self._run(_operation)

    async def _update_image_path(self, record_id: int, image_path: str) -> None:
        timestamp = datetime.utcnow().isoformat()

        def _operation(connection: sqlite3.Connection) -> None:
            connection.execute(
                "UPDATE images SET image_path = ?, updated_at = ? WHERE id = ?",
                (image_path, timestamp, record_id),
            )

        await self._run(_operation)

    async def _run(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        def _wrapper() -> T:
            with sqlite3.connect(self._db_path) as connection:
                connection.row_factory = sqlite3.Row
                result = operation(connection)
                connection.commit()
                return result

        return await asyncio.to_thread(_wrapper)

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text_id TEXT NOT NULL,
                    metadata TEXT,
                    image_path TEXT,
                    image_data BLOB,
                    image_name TEXT,
                    mime_type TEXT NOT NULL DEFAULT 'image/png',
                    description TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """,
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_images_text_id ON images(text_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_images_metadata ON images(metadata)")
            connection.commit()

    def _row_to_record(self, row: sqlite3.Row, *, include_data: bool) -> ImageRecord:
        metadata_payload = row["metadata"]
        metadata: dict[str, Any] | None
        if metadata_payload:
            try:
                loaded = json.loads(metadata_payload)
                metadata = loaded if isinstance(loaded, dict) else {"value": loaded}
            except json.JSONDecodeError:
                metadata = {"value": metadata_payload}
        else:
            metadata = None
        image_data = row["image_data"] if include_data else None
        return ImageRecord(
            id=row["id"],
            text_id=row["text_id"],
            metadata=metadata,
            image_path=row["image_path"],
            image_name=row["image_name"],
            mime_type=row["mime_type"] or "image/png",
            description=row["description"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            image_data=image_data,
        )

    def _prepare_metadata(self, metadata: dict[str, Any] | str | None, tags: Sequence[str] | None) -> str | None:
        payload = self._metadata_to_dict(metadata)
        clean_tags = [tag.strip().lower() for tag in tags] if tags else []
        if clean_tags:
            payload["tags"] = sorted({tag for tag in clean_tags if tag})
        if not payload:
            return None
        payload.setdefault("metadata_updated_at", datetime.utcnow().isoformat())
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _metadata_to_dict(metadata: dict[str, Any] | str | None) -> dict[str, Any]:
        if metadata is None:
            return {}
        if isinstance(metadata, dict):
            return dict(metadata)
        text = metadata.strip()
        if not text:
            return {}
        try:
            loaded = json.loads(text)
            if isinstance(loaded, dict):
                return dict(loaded)
            return {"value": loaded}
        except json.JSONDecodeError:
            return {"value": text}

    @staticmethod
    def _guess_extension(mime_type: str | None) -> str:
        if not mime_type or "/" not in mime_type:
            return "png"
        tail = mime_type.split("/")[-1].strip().lower()
        return tail or "png"

    @staticmethod
    def _guess_mime_type(suffix: str) -> str:
        mapping = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
            ".webp": "image/webp",
        }
        return mapping.get(suffix.lower(), "image/png")
