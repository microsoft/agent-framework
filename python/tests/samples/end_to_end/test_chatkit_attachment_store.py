# Copyright (c) Microsoft. All rights reserved.

"""Tests for the ChatKit integration sample attachment store."""

import importlib.util
import json
from io import BytesIO
from pathlib import Path
from types import ModuleType

import agent_framework
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


@pytest.fixture
def chatkit_app_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    sample_dir = _ATTACHMENT_STORE_PATH.parent
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FOUNDRY_MODEL", "test-model")
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.com")
    monkeypatch.setattr(agent_framework, "FunctionResultContent", object, raising=False)
    monkeypatch.syspath_prepend(str(sample_dir))

    spec = importlib.util.spec_from_file_location("chatkit_integration_app", sample_dir / "app.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_get_file_path_returns_direct_child(tmp_path: Path) -> None:
    store = attachment_store_module.FileBasedAttachmentStore(uploads_dir=str(tmp_path))

    assert store.get_file_path("attachment-123") == tmp_path / "attachment-123"


@pytest.mark.parametrize(
    "attachment_id",
    [
        "../outside",
        "nested/attachment-123",
        "nested/../attachment-123",
        r"nested\attachment-123",
        r"nested\..\attachment-123",
        "/tmp/attachment-123",
        "",
        ".",
        "..",
    ],
)
def test_get_file_path_rejects_non_filename_ids(tmp_path: Path, attachment_id: str) -> None:
    store = attachment_store_module.FileBasedAttachmentStore(uploads_dir=str(tmp_path))

    with pytest.raises(ValueError, match="Invalid attachment ID"):
        store.get_file_path(attachment_id)


async def test_attachment_routes_return_bad_request_for_invalid_id(chatkit_app_module: ModuleType) -> None:
    upload = chatkit_app_module.UploadFile(file=BytesIO(b"contents"), filename="attachment.txt")

    upload_response = await chatkit_app_module.upload_file(".", upload)
    preview_response = await chatkit_app_module.preview_image(".")

    assert upload_response.status_code == 400
    assert json.loads(upload_response.body) == {"error": "Invalid attachment ID."}
    assert preview_response.status_code == 400
    assert json.loads(preview_response.body) == {"error": "Invalid attachment ID."}
