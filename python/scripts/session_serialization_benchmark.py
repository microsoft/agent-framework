# Copyright (c) Microsoft. All rights reserved.

"""Compare AgentSession serialization formats using realistic Agent Framework objects.

Run from ``python/``:

    uv run --with orjson python scripts/session_serialization_benchmark.py

The benchmark compares:

- Standard-library JSON
- orjson
- Pydantic `model_dump_json` / `model_validate_json`
- msgspec JSON
- msgspec MessagePack (binary)
- An AgentSession-shaped msgspec Struct using JSON
- An AgentSession-shaped msgspec Struct using MessagePack

The first five measurements include AgentSession ``to_dict`` / ``from_dict``
conversion. The Struct variants instead map session fields directly and route
only the dynamic state dictionary through the same registry helpers. JSON and
MessagePack payloads are written to disk to report actual file size and cached
filesystem round-trip latency.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import msgspec
import orjson
from agent_framework import (
    AgentSession,
    Content,
    InMemoryHistoryProvider,
    Message,
    register_state_type,
)
from agent_framework._sessions import (  # pyright: ignore[reportPrivateUsage]
    _deserialize_state,
    _serialize_state,
    _validate_durable_state_value,
)
from pydantic import BaseModel


@dataclass(slots=True)
class BenchmarkClassState:
    """Representative application-defined state class."""

    item_id: int
    label: str
    scores: list[float]
    attributes: dict[str, str]

    TYPE = "benchmark_class_state"

    def to_dict(self) -> dict[str, Any]:
        """Serialize this state object."""
        return {
            "item_id": self.item_id,
            "label": self.label,
            "scores": self.scores,
            "attributes": self.attributes,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BenchmarkClassState:
        """Restore this state object."""
        return cls(
            item_id=int(value["item_id"]),
            label=str(value["label"]),
            scores=[float(score) for score in value["scores"]],
            attributes={str(key): str(item) for key, item in value["attributes"].items()},
        )


class BenchmarkProfileState(BaseModel):
    """Representative explicitly registered Pydantic state."""

    user_id: str
    preferences: dict[str, str]
    counters: list[int]


class PydanticSessionSnapshot(BaseModel):
    """Typed Pydantic representation used by the Pydantic benchmark."""

    type: Literal["session"]
    session_id: str
    service_session_id: str | dict[str, Any] | None = None
    state: dict[str, Any]


class StructStatePayload:
    """Opaque wrapper that forces msgspec to invoke the state registry hook."""

    __slots__ = ("value",)

    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value


class StructAgentSession(msgspec.Struct):
    """AgentSession-shaped msgspec Struct used by the direct benchmark."""

    session_id: str
    service_session_id: str | dict[str, Any] | None
    state: StructStatePayload
    version: Literal["1.0"] = "1.0"


register_state_type(BenchmarkClassState)
register_state_type(BenchmarkProfileState, type_id="benchmark_profile_state")


@dataclass(frozen=True, slots=True)
class Codec:
    """One benchmarked serialization codec."""

    name: str
    suffix: str
    encode: Callable[[AgentSession], bytes]
    decode: Callable[[bytes], AgentSession]


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """Collected timing and size metrics for one codec."""

    codec: str
    file_size: int
    encode_median_ms: float
    encode_p95_ms: float
    decode_median_ms: float
    decode_p95_ms: float
    roundtrip_median_ms: float
    roundtrip_p95_ms: float
    disk_roundtrip_median_ms: float
    disk_roundtrip_p95_ms: float


def _stdlib_json_encode(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _stdlib_json_decode(value: bytes) -> Any:
    return json.loads(value)


def _pydantic_json_encode(value: dict[str, Any]) -> bytes:
    snapshot = PydanticSessionSnapshot.model_validate(value)
    return snapshot.model_dump_json().encode("utf-8")


def _pydantic_json_decode(value: bytes) -> Any:
    return PydanticSessionSnapshot.model_validate_json(value).model_dump()


def _encode_via_dict(
    session: AgentSession,
    encoder: Callable[[dict[str, Any]], bytes],
) -> bytes:
    return encoder(session.to_dict())


def _decode_via_dict(
    payload: bytes,
    decoder: Callable[[bytes], Any],
    *,
    codec_name: str,
) -> AgentSession:
    decoded = decoder(payload)
    if not isinstance(decoded, Mapping):
        raise TypeError(f"{codec_name} decoded the session to {type(decoded).__name__}, not a mapping")
    return AgentSession.from_dict(dict(decoded))


def _struct_enc_hook(value: Any) -> Any:
    if isinstance(value, StructStatePayload):
        serialized = _serialize_state(value.value)
        _validate_durable_state_value(serialized, path="state")
        return serialized
    raise NotImplementedError(f"Unsupported type: {type(value).__name__}")


def _struct_dec_hook(target_type: type[Any], value: Any) -> Any:
    if target_type is StructStatePayload:
        if not isinstance(value, Mapping):
            raise TypeError("Struct state payload must decode to a mapping")
        return StructStatePayload(_deserialize_state(dict(value)))
    raise NotImplementedError(f"Unsupported type: {target_type.__name__}")


STRUCT_JSON_ENCODER = msgspec.json.Encoder(enc_hook=_struct_enc_hook)
STRUCT_JSON_DECODER = msgspec.json.Decoder(StructAgentSession, dec_hook=_struct_dec_hook)
STRUCT_MSGPACK_ENCODER = msgspec.msgpack.Encoder(enc_hook=_struct_enc_hook)
STRUCT_MSGPACK_DECODER = msgspec.msgpack.Decoder(StructAgentSession, dec_hook=_struct_dec_hook)


def _to_struct(session: AgentSession) -> StructAgentSession:
    service_session_id = session.service_session_id
    return StructAgentSession(
        session_id=session.session_id,
        service_session_id=dict(service_session_id) if isinstance(service_session_id, Mapping) else service_session_id,
        state=StructStatePayload(session.state),
    )


def _from_struct(snapshot: StructAgentSession) -> AgentSession:
    session = AgentSession(
        session_id=snapshot.session_id,
        service_session_id=snapshot.service_session_id,
    )
    session.state = snapshot.state.value
    return session


def _dict_codec(
    *,
    name: str,
    suffix: str,
    encoder: Callable[[dict[str, Any]], bytes],
    decoder: Callable[[bytes], Any],
) -> Codec:
    return Codec(
        name=name,
        suffix=suffix,
        encode=lambda session: _encode_via_dict(session, encoder),
        decode=lambda payload: _decode_via_dict(payload, decoder, codec_name=name),
    )


CODECS = (
    _dict_codec(
        name="stdlib-json",
        suffix=".stdlib.json",
        encoder=_stdlib_json_encode,
        decoder=_stdlib_json_decode,
    ),
    _dict_codec(
        name="orjson",
        suffix=".orjson.json",
        encoder=orjson.dumps,
        decoder=orjson.loads,
    ),
    _dict_codec(
        name="pydantic-json",
        suffix=".pydantic.json",
        encoder=_pydantic_json_encode,
        decoder=_pydantic_json_decode,
    ),
    _dict_codec(
        name="msgspec-json",
        suffix=".msgspec.json",
        encoder=msgspec.json.encode,
        decoder=msgspec.json.decode,
    ),
    _dict_codec(
        name="msgspec-binary",
        suffix=".msgspec.msgpack",
        encoder=msgspec.msgpack.encode,
        decoder=msgspec.msgpack.decode,
    ),
    Codec(
        name="agent-struct-json",
        suffix=".agent-struct.json",
        encode=lambda session: STRUCT_JSON_ENCODER.encode(_to_struct(session)),
        decode=lambda payload: _from_struct(STRUCT_JSON_DECODER.decode(payload)),
    ),
    Codec(
        name="agent-struct-binary",
        suffix=".agent-struct.msgpack",
        encode=lambda session: STRUCT_MSGPACK_ENCODER.encode(_to_struct(session)),
        decode=lambda payload: _from_struct(STRUCT_MSGPACK_DECODER.decode(payload)),
    ),
)


def _build_messages(count: int, text_bytes: int) -> list[Message]:
    """Build a varied conversation dominated by Message objects."""
    padding = "x" * max(0, text_bytes - 80)
    messages: list[Message] = []
    for index in range(count):
        role = "user" if index % 2 == 0 else "assistant"
        contents = [
            Content.from_text(
                text=(
                    f"Message {index}: benchmark conversation text with Unicode café 東京. "
                    f"Payload={padding}"
                )
            )
        ]
        if index % 20 == 5:
            contents.append(
                Content.from_function_call(
                    call_id=f"call_{index}",
                    name="lookup",
                    arguments={"query": f"item-{index}", "limit": 5},
                )
            )
        elif index % 20 == 6:
            contents.append(
                Content.from_function_result(
                    call_id=f"call_{index - 1}",
                    result={"items": [f"result-{index}-{item}" for item in range(5)]},
                )
            )
        messages.append(
            Message(
                role=role,
                contents=contents,
                author_name=f"participant-{index % 7}",
                additional_properties={
                    "sequence": index,
                    "trace": {"span": f"span-{index}", "sampled": index % 3 == 0},
                },
            )
        )
    return messages


async def build_large_session(
    *,
    message_count: int,
    class_state_count: int,
    text_bytes: int,
) -> AgentSession:
    """Build a large session through InMemoryHistoryProvider."""
    session = AgentSession(
        session_id="serialization-benchmark",
        service_session_id={
            "conversation_id": "benchmark-conversation",
            "response_id": "benchmark-response",
        },
    )
    history = InMemoryHistoryProvider()
    history_state = session.state.setdefault(history.source_id, {})
    await history.save_messages(
        session.session_id,
        _build_messages(message_count, text_bytes),
        state=history_state,
    )

    session.state["plain"] = {
        "flags": [True, False, None],
        "numbers": list(range(class_state_count)),
        "nested": {
            f"key_{index}": {
                "value": index,
                "text": f"plain-state-{index}",
                "tags": [f"tag-{item}" for item in range(5)],
            }
            for index in range(class_state_count)
        },
    }
    session.state["classes"] = [
        BenchmarkClassState(
            item_id=index,
            label=f"class-state-{index}",
            scores=[index / 10, index / 20, index / 30],
            attributes={
                "category": f"category-{index % 11}",
                "partition": f"partition-{index % 17}",
            },
        )
        for index in range(class_state_count)
    ]
    session.state["profiles"] = [
        BenchmarkProfileState(
            user_id=f"user-{index}",
            preferences={
                "language": "en",
                "theme": "dark" if index % 2 else "light",
                "timezone": f"UTC+{index % 12}",
            },
            counters=[index, index * 2, index * 3],
        )
        for index in range(max(1, class_state_count // 10))
    ]
    return session


def _percentile(values: list[int], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * percentile) - 1)
    return ordered[index] / 1_000_000


def _median_ms(values: list[int]) -> float:
    return statistics.median(values) / 1_000_000


def _time_ns(function: Callable[[], Any], iterations: int) -> list[int]:
    timings: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        function()
        timings.append(time.perf_counter_ns() - started)
    return timings


def _verify_roundtrip(original: AgentSession, restored: AgentSession) -> None:
    """Verify that framework and custom objects were reconstructed."""
    original_messages = original.state[InMemoryHistoryProvider.DEFAULT_SOURCE_ID]["messages"]
    restored_messages = restored.state[InMemoryHistoryProvider.DEFAULT_SOURCE_ID]["messages"]
    if len(restored_messages) != len(original_messages):
        raise AssertionError("Message count changed during round-trip")
    if not isinstance(restored_messages[0], Message):
        raise AssertionError("Message objects were not reconstructed")
    if not isinstance(restored.state["classes"][0], BenchmarkClassState):
        raise AssertionError("Custom class state was not reconstructed")
    if not isinstance(restored.state["profiles"][0], BenchmarkProfileState):
        raise AssertionError("Pydantic state was not reconstructed")


def benchmark_codec(
    codec: Codec,
    session: AgentSession,
    *,
    output_directory: Path,
    warmups: int,
    iterations: int,
) -> BenchmarkResult:
    """Benchmark one codec and write its representative payload to disk."""
    payload = codec.encode(session)
    restored = codec.decode(payload)
    _verify_roundtrip(session, restored)

    for _ in range(warmups):
        codec.encode(session)
        codec.decode(payload)
        codec.decode(codec.encode(session))

    encode_timings = _time_ns(lambda: codec.encode(session), iterations)
    decode_timings = _time_ns(lambda: codec.decode(payload), iterations)
    roundtrip_timings = _time_ns(lambda: codec.decode(codec.encode(session)), iterations)

    output_path = output_directory / f"session{codec.suffix}"
    output_path.write_bytes(payload)

    def disk_roundtrip() -> None:
        current_payload = codec.encode(session)
        output_path.write_bytes(current_payload)
        codec.decode(output_path.read_bytes())

    disk_roundtrip_timings = _time_ns(disk_roundtrip, iterations)
    return BenchmarkResult(
        codec=codec.name,
        file_size=output_path.stat().st_size,
        encode_median_ms=_median_ms(encode_timings),
        encode_p95_ms=_percentile(encode_timings, 0.95),
        decode_median_ms=_median_ms(decode_timings),
        decode_p95_ms=_percentile(decode_timings, 0.95),
        roundtrip_median_ms=_median_ms(roundtrip_timings),
        roundtrip_p95_ms=_percentile(roundtrip_timings, 0.95),
        disk_roundtrip_median_ms=_median_ms(disk_roundtrip_timings),
        disk_roundtrip_p95_ms=_percentile(disk_roundtrip_timings, 0.95),
    )


def _format_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KiB"
    return f"{value / (1024 * 1024):.2f} MiB"


def print_results(results: list[BenchmarkResult]) -> None:
    """Print an aligned summary table and relative size ratios."""
    headers = (
        "codec",
        "size",
        "encode med/p95 ms",
        "decode med/p95 ms",
        "roundtrip med/p95 ms",
        "disk med/p95 ms",
    )
    rows = [
        (
            result.codec,
            _format_bytes(result.file_size),
            f"{result.encode_median_ms:.3f}/{result.encode_p95_ms:.3f}",
            f"{result.decode_median_ms:.3f}/{result.decode_p95_ms:.3f}",
            f"{result.roundtrip_median_ms:.3f}/{result.roundtrip_p95_ms:.3f}",
            f"{result.disk_roundtrip_median_ms:.3f}/{result.disk_roundtrip_p95_ms:.3f}",
        )
        for result in results
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]

    def render(row: tuple[str, ...]) -> str:
        return " | ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    print(render(headers))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(render(row))

    baseline = results[0].file_size
    print("\nFile size relative to stdlib JSON:")
    for result in results:
        print(f"  {result.codec:<16} {result.file_size / baseline:>7.3f}x")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--messages", type=int, default=2_000, help="Number of Message objects in history.")
    parser.add_argument("--class-state", type=int, default=500, help="Number of custom class state objects.")
    parser.add_argument("--text-bytes", type=int, default=512, help="Approximate text payload per Message.")
    parser.add_argument("--iterations", type=int, default=25, help="Measured iterations per operation.")
    parser.add_argument("--warmups", type=int, default=5, help="Warmup iterations per codec.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Keep representative payload files in this directory instead of a temporary directory.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session = asyncio.run(
        build_large_session(
            message_count=args.messages,
            class_state_count=args.class_state,
            text_bytes=args.text_bytes,
        )
    )
    history_count = len(session.state[InMemoryHistoryProvider.DEFAULT_SOURCE_ID]["messages"])
    print(
        f"Session: {history_count} messages, {args.class_state} class objects, "
        f"{len(session.state['profiles'])} Pydantic objects"
    )
    print(f"Iterations: {args.iterations} measured, {args.warmups} warmups\n")

    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        results = [
            benchmark_codec(
                codec,
                session,
                output_directory=args.output_dir,
                warmups=args.warmups,
                iterations=args.iterations,
            )
            for codec in CODECS
        ]
        print_results(results)
        print(f"\nPayload files retained in: {args.output_dir.resolve()}")
        return

    with tempfile.TemporaryDirectory(prefix="agent-session-serialization-") as temporary_directory:
        results = [
            benchmark_codec(
                codec,
                session,
                output_directory=Path(temporary_directory),
                warmups=args.warmups,
                iterations=args.iterations,
            )
            for codec in CODECS
        ]
        print_results(results)


if __name__ == "__main__":
    main()
