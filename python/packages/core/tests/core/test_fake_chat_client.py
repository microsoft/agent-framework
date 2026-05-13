# Copyright (c) Microsoft. All rights reserved.

import pytest
from agent_framework import (
    ChatResponse,
    Message,
    chat_middleware,
)
from agent_framework.exceptions import ChatClientInvalidRequestException
from agent_framework.fake import FakeChatClient


def test_init() -> None:
    fake_chat_client = FakeChatClient(model="fake-model", responses=["Hello!", "This framework is amazing!"])
    assert fake_chat_client.model == "fake-model"
    assert fake_chat_client._responses == ["Hello!", "This framework is amazing!"]
    assert not fake_chat_client._cycle


def test_serialize() -> None:
    settings = {
        "responses": ["Hello!", "This framework is amazing!"],
        "model": "fake-model-serialize",
        "cycle": False,
    }

    fake_chat_client = FakeChatClient.from_dict(settings)
    serialized = fake_chat_client.to_dict()

    assert isinstance(serialized, dict)
    # only public attributes are serialized
    assert serialized["model"] == "fake-model-serialize"


def test_chat_middleware() -> None:
    @chat_middleware
    async def sample_middleware(context, call_next):
        await call_next()

    fake_chat_client = FakeChatClient(responses=["Hello!"], middleware=[sample_middleware])
    assert len(fake_chat_client.chat_middleware) == 1
    assert fake_chat_client.chat_middleware[0] == sample_middleware


async def test_empty_messages() -> None:
    fake_chat_client = FakeChatClient(responses=["Test :)"])
    with pytest.raises(ChatClientInvalidRequestException):
        await fake_chat_client.get_response(messages=[])


async def test_get_response() -> None:
    fake_chat_client = FakeChatClient(
        responses=[
            "the most beautiful number is 1729",
            "It is the smallest number that can be written as the "
            "sum of cubes in two different ways: 1729 = 1** + 12**3 = 9**3 + 10**3",
        ],
        cycle=False,
    )

    result_first = await fake_chat_client.get_response(
        messages=[Message(contents=["what is the most beautiful number?"], role="user")]
    )
    assert result_first.text == "the most beautiful number is 1729"
    result_second = await fake_chat_client.get_response(messages=[Message(contents=["and why is it?"], role="user")])
    assert (
        result_second.text == "It is the smallest number that can be written as the "
        "sum of cubes in two different ways: 1729 = 1** + 12**3 = 9**3 + 10**3"
    )
    with pytest.raises(
        ChatClientInvalidRequestException,
        match="FakeChatClient response list is exhausted. Provide more responses or enable cycle=True.",
    ):
        await fake_chat_client.get_response(messages=[Message(contents=["Do you have more?"], role="user")])


async def test_get_response_cycle() -> None:
    client = FakeChatClient(responses=["a", "b"], cycle=True)
    messages = [Message(role="user", contents=["hi"])]

    r1 = await client.get_response(messages=messages)
    r2 = await client.get_response(messages=messages)
    r3 = await client.get_response(messages=messages)
    r4 = await client.get_response(messages=messages)

    assert r1.text == "a"
    assert r2.text == "b"
    assert r3.text == "a"
    assert r4.text == "b"


async def test_get_response_stream() -> None:
    client = FakeChatClient(responses=["streaming response"])
    messages = [Message(role="user", contents=["hi"])]

    stream = client.get_response(messages=messages, stream=True)
    updates = [update async for update in stream]
    final = await stream.get_final_response()

    assert len(updates) == 1
    assert updates[0].text == "streaming response"
    assert final.text == "streaming response"


async def test_chat_response_model_override_from_queue() -> None:
    queued = ChatResponse(messages=[Message(role="assistant", contents=["hi"])], model="original-model")
    client = FakeChatClient(responses=[queued], model="default-model")
    messages = [Message(role="user", contents=["hello"])]

    result = await client.get_response(messages=messages, options={"model": "override-model"})

    assert result.model == "override-model"


async def test_chat_response_model_override_from_options_response() -> None:
    one_off = ChatResponse(messages=[Message(role="assistant", contents=["hi"])], model="original-model")
    client = FakeChatClient(responses=[], model="default-model")
    messages = [Message(role="user", contents=["hello"])]

    result = await client.get_response(messages=messages, options={"response": one_off, "model": "override-model"})

    assert result.model == "override-model"


async def test_middleware_wraps_response() -> None:
    @chat_middleware
    async def wrapping_middleware(context, call_next):
        await call_next()
        context.result = ChatResponse(
            messages=[Message(role="assistant", contents=[f"[wrapped] {context.result.text}"])],
            model=context.result.model,
        )

    client = FakeChatClient(responses=["hello"], middleware=[wrapping_middleware])
    result = await client.get_response(messages=[Message(role="user", contents=["hello"])])

    assert result.text == "[wrapped] hello"
