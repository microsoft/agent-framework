"""Async helpers for working with the local SQLite image store."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from collections.abc import Awaitable, Iterable, Sequence

from agent_framework.observability import get_tracer
from opentelemetry.trace import SpanKind

from db_setup import ImageRecord, SQLiteImageStore

__all__ = ["DatabaseImageTool"]


class DatabaseImageTool:
    """High-level façade that wraps :class:`SQLiteImageStore` operations.

    The observability samples previously depended on Semantic Kernel decorators and a
    bespoke ``ImageDatabase`` class. This version aligns the tool with the new
    :class:`SQLiteImageStore` implementation so callers can reuse the modern async API
    while still having convenient synchronous entry points for quick scripts.
    """

    def __init__(
        self,
        *,
        store: SQLiteImageStore | None = None,
        db_path: str | Path | None = None,
        export_dir: str | Path | None = None,
    ) -> None:
        store_kwargs: dict[str, Any] = {}
        if db_path is not None:
            store_kwargs["db_path"] = db_path
        if export_dir is not None:
            store_kwargs["export_dir"] = export_dir
        self._store = store or SQLiteImageStore(**store_kwargs)
        self._tracer = get_tracer()

    async def get_image_by_text_id_async(
        self,
        text_id: str,
        *,
        include_data: bool = False,
        export_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        with self._tracer.start_as_current_span(
            "database_image_tool.get_image_by_text_id", kind=SpanKind.INTERNAL
        ) as span:
            span.set_attribute("image.text_id", text_id)
            record = await self._store.get_image_by_text_id(text_id, include_data=include_data)
            if record is None:
                span.set_attribute("result.found", False)
                return {
                    "success": False,
                    "error": f"No image found with text_id: {text_id}",
                    "text_id": text_id,
                }

            payload = self._record_to_payload(record, include_data=include_data)
            saved_path: Path | None = None
            if export_dir is not None:
                saved_path = await self._store.save_image_to_file(text_id=text_id, output_dir=export_dir)
                if saved_path is not None:
                    payload["image_path"] = str(saved_path)

            span.set_attribute("result.found", True)
            span.set_attribute("result.tags_count", len(payload.get("tags", [])))
            if saved_path is not None:
                span.set_attribute("result.export_path", str(saved_path))
            return {"success": True, "image": payload}

    def get_image_by_text_id(
        self,
        text_id: str,
        *,
        include_data: bool = False,
        export_dir: str | Path | None = None,
        as_json: bool = True,
    ) -> str | dict[str, Any]:
        result = self._run(
            self.get_image_by_text_id_async(
                text_id,
                include_data=include_data,
                export_dir=export_dir,
            )
        )
        return json.dumps(result, ensure_ascii=False) if as_json else result

    async def get_image_by_metadata_tags_async(
        self,
        tags: Sequence[str] | str,
        match_mode: str = "any",
    ) -> dict[str, Any]:
        normalized_tags = self._normalize_tags(tags)
        mode = match_mode.lower().strip() or "any"
        with self._tracer.start_as_current_span(
            "database_image_tool.get_image_by_metadata_tags", kind=SpanKind.INTERNAL
        ) as span:
            span.set_attribute("search.tags", normalized_tags)
            span.set_attribute("search.match_mode", mode)

            if not normalized_tags:
                span.set_attribute("result.count", 0)
                return {
                    "success": False,
                    "error": "No valid tags provided",
                    "search_tags": [],
                    "match_mode": mode,
                }

            records = await self._store.list_images(include_data=False)
            matches: list[ImageRecord] = []
            for record in records:
                record_tags = [tag.lower() for tag in record.tags()]
                if not record_tags:
                    continue
                if mode == "all":
                    if all(tag in record_tags for tag in normalized_tags):
                        matches.append(record)
                else:
                    if any(tag in record_tags for tag in normalized_tags):
                        matches.append(record)

            serialized = [self._record_to_payload(record, include_data=False) for record in matches]
            span.set_attribute("result.count", len(serialized))
            return {
                "success": True,
                "search_tags": normalized_tags,
                "match_mode": mode,
                "results": serialized,
                "count": len(serialized),
            }

    def get_image_by_metadata_tags(
        self,
        tags: Sequence[str] | str,
        match_mode: str = "any",
        *,
        as_json: bool = True,
    ) -> str | dict[str, Any]:
        result = self._run(self.get_image_by_metadata_tags_async(tags, match_mode=match_mode))
        return json.dumps(result, ensure_ascii=False) if as_json else result

    async def add_tags_to_image_async(
        self,
        text_id: str,
        tags: Sequence[str] | str,
        *,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        normalized_tags = self._normalize_tags(tags)
        with self._tracer.start_as_current_span(
            "database_image_tool.add_tags_to_image", kind=SpanKind.INTERNAL
        ) as span:
            span.set_attribute("image.text_id", text_id)
            span.set_attribute("tags.input", normalized_tags)
            span.set_attribute("tags.replace_existing", replace_existing)

            if not normalized_tags:
                span.set_attribute("result.status", "invalid_tags")
                return {
                    "success": False,
                    "error": "No valid tags provided",
                    "text_id": text_id,
                }

            before = await self._store.get_image_by_text_id(text_id, include_data=False)
            before_tags = before.tags() if before else []
            updated = await self._store.add_tags(
                text_id=text_id,
                tags=normalized_tags,
                replace_existing=replace_existing,
            )
            if updated is None:
                span.set_attribute("result.status", "not_found")
                return {
                    "success": False,
                    "error": f"Image not found with text_id: {text_id}",
                    "text_id": text_id,
                }

            payload = self._record_to_payload(updated, include_data=False)
            span.set_attribute("result.status", "success")
            span.set_attribute("result.final_tags_count", len(payload.get("tags", [])))
            return {
                "success": True,
                "text_id": text_id,
                "previous_tags": before_tags,
                "final_tags": payload.get("tags", []),
                "replace_existing": replace_existing,
                "image": payload,
            }

    def add_tags_to_image(
        self,
        text_id: str,
        tags: Sequence[str] | str,
        *,
        replace_existing: bool = False,
        as_json: bool = True,
    ) -> str | dict[str, Any]:
        result = self._run(
            self.add_tags_to_image_async(
                text_id,
                tags,
                replace_existing=replace_existing,
            )
        )
        return json.dumps(result, ensure_ascii=False) if as_json else result

    async def get_all_available_tags_async(self) -> dict[str, Any]:
        with self._tracer.start_as_current_span(
            "database_image_tool.get_all_available_tags", kind=SpanKind.INTERNAL
        ) as span:
            data = await self._store.get_all_available_tags()
            span.set_attribute("result.unique_tags", data.get("unique_tags", 0))
            return {"success": True, **data}

    def get_all_available_tags(self, *, as_json: bool = True) -> str | dict[str, Any]:
        result = self._run(self.get_all_available_tags_async())
        return json.dumps(result, ensure_ascii=False) if as_json else result

    async def search_images_by_metadata_async(self, metadata_query: str) -> dict[str, Any]:
        with self._tracer.start_as_current_span(
            "database_image_tool.search_images_by_metadata", kind=SpanKind.INTERNAL
        ) as span:
            span.set_attribute("search.query", metadata_query)
            records = await self._store.search_images(metadata_query, include_data=False)
            serialized = [self._record_to_payload(record, include_data=False) for record in records]
            span.set_attribute("result.count", len(serialized))
            return {
                "success": True,
                "query": metadata_query,
                "results": serialized,
                "count": len(serialized),
            }

    def search_images_by_metadata(self, metadata_query: str, *, as_json: bool = True) -> str | dict[str, Any]:
        result = self._run(self.search_images_by_metadata_async(metadata_query))
        return json.dumps(result, ensure_ascii=False) if as_json else result

    async def list_all_images_async(self, include_data: bool = False) -> dict[str, Any]:
        with self._tracer.start_as_current_span(
            "database_image_tool.list_all_images", kind=SpanKind.INTERNAL
        ) as span:
            records = await self._store.list_images(include_data=include_data)
            serialized = [self._record_to_payload(record, include_data=include_data) for record in records]
            span.set_attribute("result.count", len(serialized))
            return {"success": True, "images": serialized, "total_count": len(serialized)}

    def list_all_images(self, *, include_data: bool = False, as_json: bool = True) -> str | dict[str, Any]:
        result = self._run(self.list_all_images_async(include_data=include_data))
        return json.dumps(result, ensure_ascii=False) if as_json else result

    async def extract_image_to_current_session_async(
        self,
        text_id: str,
        *,
        output_dir: str | Path = "session_images",
    ) -> dict[str, Any]:
        with self._tracer.start_as_current_span(
            "database_image_tool.extract_image", kind=SpanKind.INTERNAL
        ) as span:
            span.set_attribute("image.text_id", text_id)
            saved_path = await self._store.save_image_to_file(text_id=text_id, output_dir=output_dir)
            if saved_path is None:
                span.set_attribute("result.status", "not_found")
                return {
                    "success": False,
                    "error": f"Image not found or no data for text_id: {text_id}",
                    "text_id": text_id,
                }

            span.set_attribute("result.status", "extracted")
            span.set_attribute("result.path", str(saved_path))
            return {"success": True, "text_id": text_id, "image_path": str(saved_path)}

    def extract_image_to_current_session(
        self,
        text_id: str,
        *,
        output_dir: str | Path = "session_images",
    ) -> str:
        result = self._run(
            self.extract_image_to_current_session_async(text_id, output_dir=output_dir)
        )
        return result["image_path"] if result.get("success") else result.get("error", "Unexpected error")

    def _run(self, coro: Awaitable[Any]) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        raise RuntimeError(
            "DatabaseImageTool synchronous APIs cannot be used while an event loop is running. "
            "Use the '*_async' coroutine instead."
        )

    @staticmethod
    def _normalize_tags(tags: Sequence[str] | str | None) -> list[str]:
        if tags is None:
            return []
        if isinstance(tags, str):
            candidates = tags.split(",")
        else:
            candidates = tags

        normalized: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            value = candidate.strip().lower()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    @staticmethod
    def _record_to_payload(record: ImageRecord, *, include_data: bool) -> dict[str, Any]:
        payload = record.to_dict(include_data=include_data)
        if payload.get("metadata") is None:
            payload["metadata"] = {}
        payload["tags"] = record.tags()
        payload["image_path"] = record.image_path
        return payload
