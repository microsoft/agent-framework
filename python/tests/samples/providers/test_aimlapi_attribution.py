# Copyright (c) Microsoft. All rights reserved.

"""Contract tests for the aimlapi.com provider samples.

The four attribution headers the samples send are silently ignored by the service when
malformed — a bad partner id is not rejected, it is simply not attributed — so a typo is
invisible at runtime. These tests assert the shapes instead.

The samples live in a script-style tree that is not an importable package, so they are
loaded by path.
"""

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

PYTHON_ROOT = Path(__file__).parents[3]
SAMPLES_DIR = PYTHON_ROOT / "samples" / "02-agents" / "providers" / "aimlapi"

SAMPLE_FILES = [
    "aimlapi_chat_completion_client_basic.py",
    "aimlapi_chat_completion_client_with_function_tools.py",
]

# Backend contract: /^part_[A-Za-z0-9]{1,64}$/ — alphanumerics only after the prefix.
PARTNER_ID_PATTERN = re.compile(r"^part_[A-Za-z0-9]{1,64}$")

# Backend contract: "<channel>/<client>", channel in {web, agent, mcp}, client [a-z0-9-]{1,32}.
SOURCE_PATTERN = re.compile(r"^(web|agent|mcp)/[a-z0-9-]{1,32}$")

EXPECTED_HEADER_KEYS = {
    "HTTP-Referer",
    "X-Title",
    "X-AIMLAPI-Partner-ID",
    "X-AIMLAPI-Source",
}


def load_sample(file_name: str) -> ModuleType:
    """Import a sample module by path."""
    path = SAMPLES_DIR / file_name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=SAMPLE_FILES)
def sample(request: pytest.FixtureRequest) -> ModuleType:
    return load_sample(request.param)


def test_partner_id_is_well_formed(sample: ModuleType) -> None:
    partner_id = sample.AIMLAPI_ATTRIBUTION_HEADERS["X-AIMLAPI-Partner-ID"]
    assert PARTNER_ID_PATTERN.match(partner_id), f"malformed partner id: {partner_id!r}"


def test_source_is_well_formed(sample: ModuleType) -> None:
    source = sample.AIMLAPI_ATTRIBUTION_HEADERS["X-AIMLAPI-Source"]
    assert SOURCE_PATTERN.match(source), f"malformed source: {source!r}"


def test_referer_and_title_identify_the_host_project(sample: ModuleType) -> None:
    """HTTP-Referer and X-Title name the calling project, not the model provider."""
    headers = sample.AIMLAPI_ATTRIBUTION_HEADERS
    assert set(headers) == EXPECTED_HEADER_KEYS
    assert headers["HTTP-Referer"] == "https://github.com/microsoft/agent-framework"
    assert headers["X-Title"] == "Microsoft Agent Framework"


def test_headers_are_scoped_to_the_aimlapi_origin(sample: ModuleType) -> None:
    """Attribution must not be able to ride a request to a different provider."""
    assert sample.AIMLAPI_BASE_URL == "https://api.aimlapi.com/v1"


def test_client_gets_a_copy_not_the_shared_constant(monkeypatch: pytest.MonkeyPatch, sample: ModuleType) -> None:
    """Building a client must not hand out or mutate the module-level constant."""
    monkeypatch.setenv("AIMLAPI_API_KEY", "test-key-not-a-real-one")
    before = dict(sample.AIMLAPI_ATTRIBUTION_HEADERS)

    client = sample.create_client()
    assert client.default_headers is not sample.AIMLAPI_ATTRIBUTION_HEADERS
    for key, value in before.items():
        assert client.default_headers[key] == value

    client.default_headers["X-Title"] = "mutated"
    assert sample.AIMLAPI_ATTRIBUTION_HEADERS == before
