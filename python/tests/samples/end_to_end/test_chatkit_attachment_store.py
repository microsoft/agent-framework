# Copyright (c) Microsoft. All rights reserved.

"""Tests for the ChatKit integration sample attachment store."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_ATTACHMENT_STORE_PATH = (
    Path(__file__).parents[3] / "samples" / "05-end-to-end" / "chatkit-integration" / "attachment_store.py"
)


def _load_attachment_store_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("chatkit_attachment_store", _ATTACHMENT_STORE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


attachment_store_module = _load_attachment_store_module()


def test_get_file_path_returns_direct_child(tmp_path: Path) -> None:
    store = attachment_store_module.FileBasedAttachmentStore(uploads_dir=str(tmp_path))

    assert store.get_file_path("attachment-123") == tmp_path / "attachment-123"


@pytest.mark.parametrize(
    "attachment_id",
    ["../outside", "nested/attachment-123", "/tmp/attachment-123", "", "."],
)
def test_get_file_path_rejects_paths_outside_direct_upload_directory(tmp_path: Path, attachment_id: str) -> None:
    store = attachment_store_module.FileBasedAttachmentStore(uploads_dir=str(tmp_path))

    with pytest.raises(ValueError, match="Invalid attachment ID"):
        store.get_file_path(attachment_id)
