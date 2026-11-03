# Copyright (c) Microsoft. All rights reserved.

"""An injected Mistral SDK client owns its endpoint (#9965).

The wrapper used to resolve ``MISTRAL_SERVER_URL`` before inspecting the
injected client, so ``service_url()`` reported the ambient URL (used for
telemetry) while requests went to the injected client's endpoint.
"""

import os

from mistralai.client import Mistral

from agent_framework_mistral import MistralChatClient, MistralEmbeddingClient, RawMistralChatClient


def _make_injected_sdk(server_url: str) -> Mistral:
    return Mistral(api_key="dummy", server_url=server_url)


def test_chat_service_url_uses_injected_client_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_SERVER_URL", "https://env.example")
    sdk = _make_injected_sdk("https://client.example")

    client = RawMistralChatClient(client=sdk, model="mistral-test")

    assert client.service_url() == "https://client.example"
    assert client.server_url == "https://client.example"


def test_embedding_service_url_uses_injected_client_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_SERVER_URL", "https://env.example")
    sdk = _make_injected_sdk("https://client.example")

    client = MistralEmbeddingClient(client=sdk, model="mistral-embed")

    assert client.service_url() == "https://client.example"
    assert client.server_url == "https://client.example"


def test_chat_service_url_uses_env_when_no_client(monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_SERVER_URL", "https://env.example")
    monkeypatch.setenv("MISTRAL_API_KEY", "env-key")

    client = MistralChatClient()

    assert client.service_url() == "https://env.example"


def test_owned_client_keeps_explicit_server_url(monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "env-key")
    monkeypatch.setenv("MISTRAL_SERVER_URL", "https://env.example")

    raw = RawMistralChatClient(model="mistral-test", server_url="https://explicit.example")
    assert raw.server_url == "https://explicit.example"

    wrapped = MistralChatClient(server_url="https://explicit.example")
    assert wrapped.service_url() == "https://explicit.example"


def test_injected_client_consts_not_loaded(monkeypatch) -> None:
    # No MISTRAL_API_KEY in the environment at all; injecting a client must not
    # require one.
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_SERVER_URL", raising=False)
    sdk = _make_injected_sdk("https://client.example")

    chat = RawMistralChatClient(client=sdk, model="mistral-test")
    embedding = MistralEmbeddingClient(client=sdk, model="mistral-embed")

    assert chat._owns_client is False
    assert embedding._owns_client is False
    os.environ.pop("MISTRAL_API_KEY", None)
    os.environ.pop("MISTRAL_SERVER_URL", None)
