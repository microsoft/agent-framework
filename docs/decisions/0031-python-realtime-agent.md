---
status: proposed
contact: eavanvalkenburg
date: 2026-06-30
deciders: eavanvalkenburg
consulted:
informed:
---

# Python realtime agents for direct realtime models and STT-agent-TTS pipelines

## Context and Problem Statement

Python Agent Framework has mature request/response agent and chat-client abstractions:
`Agent`, `BaseAgent`, `BaseChatClient`, `SupportsChatGetResponse`, `AgentSession`, `AgentResponse`,
`AgentResponseUpdate`, `Content`, `ResponseStream`, middleware, tools, telemetry, and history providers. It does not
yet have a realtime agent surface for live audio/text interaction.

Realtime agent work needs to cover two related but different architectures:

1. **Direct realtime model**: one model/provider session accepts audio/text input and emits audio, text/transcripts,
   function calls, and control events over a live bidirectional connection. OpenAI Realtime-style APIs are the first
   target.
2. **Sandwich setup**: speech-to-text (STT) converts live audio into text, a normal Agent Framework agent reasons and
   calls tools over that text, and text-to-speech (TTS) renders the agent output back to audio.

Both can look like "a voice agent" to a caller, but they do not have the same semantics. Direct realtime models may own
server-side VAD, barge-in, session continuation, and tool-call timing. Sandwich pipelines have three independently
failing components, more explicit cancellation boundaries, and tool calls usually happen in the inner text agent. The
Python architecture needs one caller-facing realtime conversation model where that is honest, without hiding the
capability differences.

Related prior decisions and designs:

- The .NET realtime ADR proposes a `RealtimeAgent` over `IRealtimeClient` as a subclass of `AIAgent`, with an
  `AgentConversation` full-duplex surface.
- Python does not have a direct `AIAgent` equivalent. The compatibility target for half-duplex scenarios is the
  structural `SupportsAgentRun` protocol.
- Semantic Kernel ADR 0065 chooses an event-centered realtime client model and explicitly avoids owning microphone and
  speaker device handling in the runtime.

## Decision Drivers

- **Agent composition**: realtime agents should still compose with existing agent middleware, telemetry, context
  providers, workflows, and handoffs where possible.
- **Direct and sandwich coverage**: the architecture should handle both direct realtime model sessions and
  STT-agent-TTS pipelines.
- **Different semantics stay visible**: a shared surface must not imply identical latency, interruption, continuation,
  or tool-call behavior across direct and sandwich implementations.
- **Full-duplex fidelity**: live send and receive must both be possible without flattening realtime into a simple
  request/response chat call.
- **Half-duplex compatibility**: callers should still be able to use `run(...)` and `run(..., stream=True)` for simple
  one-turn flows.
- **No event loss**: every provider or pipeline signal must be representable at the Agent Framework layer, with raw
  provider objects available as an escape hatch.
- **Function invocation reuse**: direct realtime model tool calls should reuse the existing tested function-invocation
  behavior rather than duplicate approval, middleware, declaration-only, progressive-tool, budget, and error logic.
- **Provider separation**: core should contain provider-neutral abstractions only; OpenAI realtime implementation belongs
  in `agent-framework-openai`.
- **Live resource boundaries**: live sockets, audio streams, and receive tasks are disposable runtime resources and do not
  belong in serializable `AgentSession` state.
- **Practical media integration**: local microphone/speaker loops and hosted media streams such as Azure Communication
  Services Call Automation should be easy to wire without users rebuilding the same bridge code each time.
- **Audio device neutrality**: framework core should define audio bridge seams, but concrete microphone/speaker drivers
  should live in samples or optional integrations.

## Considered Options

- **Option 1: Add `RealtimeAgent` as the realtime-specific agent type**
- **Option 2: Extend `Agent` to also be the realtime agent type**

## Decision Outcome

Chosen option: **Option 1: Add `RealtimeAgent` as the realtime-specific agent type**, because it keeps the live realtime
lifecycle explicit while still giving callers one realtime concept for both direct realtime model sessions and sandwich
pipelines.

For sandwich setups, use a concrete `RealtimePipeline` class that composes speech-to-text, an inner
`SupportsAgentRun`, and text-to-speech. The constructor order should follow the audio-to-audio flow:

```python
pipeline = RealtimePipeline(
    speech_to_text=speech_to_text_client,
    agent=text_agent,
    text_to_speech=text_to_speech_client,
)

agent = RealtimeAgent(client=pipeline)
```

This requires adding provider-neutral speech-to-text and text-to-speech abstractions in addition to the
`RealtimePipeline` class itself. Those abstractions are part of the architecture, but they should be implemented after
the direct realtime model path unless a concrete STT/TTS provider or sample is selected for the first slice.

Comparison with Semantic Kernel Python realtime and canonical code shapes are included in the appendices so the main
decision stays readable while still making the proposed API concrete.

The selected architecture has these layers.

### Agent-level live conversation

Introduce an experimental `AgentConversation` as the Agent Framework live full-duplex surface. It is an async context
manager / async disposable object, not an `AgentSession`.

`AgentConversation` owns a live exchange and exposes operations for:

- sending user text/messages;
- sending text, audio content, or explicit realtime events;
- interrupting/canceling active output;
- receiving a single ordered stream of `AgentResponseUpdate` values through `async for update in conversation`, with
  `ResponseStream` used only when a final `AgentResponse` can be defined;
- closing the live resources.

The exact method names are implementation details, but the type must make lifecycle clear: callers must close it or use
`async with`.

`AgentConversation` is also the convenience boundary. It may accept `Message`, `Content`, strings, and audio helper
inputs and translate them into provider-level realtime events. Provider sessions should not own these agent-level
conveniences.

Illustrative shape:

```python
class AgentConversation:
    """Live full-duplex conversation owned by a RealtimeAgent."""

    @property
    def updates(self) -> AsyncIterable[AgentResponseUpdate]:
        """The single ordered stream of agent-level realtime updates."""
        ...

    def __aiter__(self) -> AsyncIterator[AgentResponseUpdate]:
        """Iterate over the same stream as updates."""
        ...

    async def send(self, value: str | Message | Content | RealtimeEvent) -> None:
        """Send input or an explicit realtime command to the live conversation."""
        ...

    async def interrupt(self) -> None:
        """Interrupt/cancel active output when the provider or pipeline supports it."""
        ...

    async def close(self) -> None:
        """Close the live conversation and release provider resources."""
        ...

    async def __aenter__(self) -> "AgentConversation":
        """Start the live provider session and receive loop."""
        ...

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any) -> None:
        """Close the live provider session and stop the receive loop."""
        ...
```

`AgentConversation` has these responsibilities:

- **Own the single receive loop**. The provider session is single-reader. `AgentConversation` is the only component that
  calls `RealtimeClientSessionProtocol.receive(...)`.
- **Project events to updates**. It maps each provider `RealtimeEvent` to one `AgentResponseUpdate` and exposes only
  agent-level updates to callers.
- **Serialize outbound writes**. It should prevent overlapping sends from corrupting provider state. A simple async lock
  around `send(...)` and `interrupt(...)` is enough unless
  a provider proves otherwise.
- **Own lifecycle and cleanup**. It is an async context manager. Exiting it closes the provider session, cancels the
  receive task, drains/terminates queues, and surfaces receive-loop failures.
- **Preserve session state**. Durable continuation values discovered during the live conversation are copied back to the
  associated `RealtimeAgentSession` / `AgentSession` when they are future-call continuation state.

`AgentConversation` should not:

- expose provider `RealtimeEvent` as its primary output stream;
- own platform microphone/speaker drivers;
- be serializable or stored in `AgentSession`;
- run a second tool loop for sandwich pipelines when the inner `SupportsAgentRun` already owns tool invocation.

Continuous conversation and scoped response requests are different:

- `conversation.updates` is the open-ended full-duplex update stream. It may run until the conversation is closed and
  does not necessarily have a final `AgentResponse`.
- `async for update in conversation` is shorthand for iterating `conversation.updates`.
- The minimal `AgentConversation` shape does not need a `request_response()` method. Use
  `conversation.send(RealtimeEvent(...))` for explicit provider response commands such as response creation when the
  provider requires them.
- `RealtimeAgent.run(..., stream=True)` owns the bounded response/`ResponseStream` projection for half-duplex scenarios.

Entering and exiting the async context should be deterministic:

- `__aenter__` creates or enters the underlying `RealtimeClientSessionProtocol`, applies initial session options, replays
  any initial messages/history that belong to the conversation, installs tools/session settings, and starts the single
  receive loop that maps `RealtimeEvent` values to `AgentResponseUpdate` values.
- `__aenter__` should not implicitly request a model response unless the caller passed an explicit option such as
  `create_response=True`.
- `__aexit__` stops accepting new sends, requests provider/session close, cancels the receive loop if it is still
  running, drains or terminates the update stream, propagates receive-loop errors unless already superseded by the context
  exception, and writes durable continuation state back to the associated `AgentSession`.
- `close()` should be idempotent and should perform the same cleanup as `__aexit__`.

### Audio I/O and hosted media bridges

`AgentConversation` should start with one send path: text, messages, content, audio content, and explicit realtime events
are sent through `conversation.send(...)`. Audio is emitted as `AgentResponseUpdate` content.

The framework should define small provider-neutral audio bridge shapes, for example an audio frame type and source/sink
protocols, so callers can connect microphone/speaker helpers or hosted media streams to `AgentConversation`. Concrete
device drivers and ACS-specific web apps should remain samples or optional integrations, but users should not have to
drop below the agent/conversation API to build the common loops:

- local microphone -> `conversation.send(Content.from_data(...))`;
- conversation audio content -> local speaker;
- ACS websocket audio data -> `conversation.send(Content.from_data(...))`;
- conversation audio content -> ACS websocket audio data;
- VAD/barge-in events -> local or hosted "stop current playback" signal.

A dedicated low-latency audio callback can be added later if the content-update path is not smooth enough for local
speaker playback, WebRTC tracks, or ACS websocket forwarding.

Do not add a broad audio framework in the first implementation. The first implementation should use the smallest bridge
contracts proven by one local mic/speaker sample and one hosted media stream sample, if those samples are part of the
same work. Otherwise leave concrete bridge helpers for a later slice.

### Direct realtime model path

Add provider-neutral direct realtime client/session protocols in core. The shape should be small:

- a realtime client creates a live realtime session;
- a realtime session sends `RealtimeEvent` commands;
- a realtime session yields provider events mapped to `AgentResponseUpdate`;
- raw provider events remain reachable through `raw_representation`.

Add `RawRealtimeAgent` / `RealtimeAgent` over this client/session shape:

- `run(..., stream=False)` opens an ephemeral realtime session, sends one turn, drains until the terminal response event,
  and returns `AgentResponse`;
- `run(..., stream=True)` does the same but yields `AgentResponseUpdate` values through `ResponseStream`;
- `start_conversation(...)` returns `AgentConversation` for full-duplex live use.

`RealtimeAgent` must satisfy `SupportsAgentRun` so it can participate in half-duplex agent scenarios, including
workflows, delegation, and any utility that accepts agent-like objects. It does not need to be a subclass of `Agent`;
shared behavior should come from `BaseAgent`, middleware/telemetry layers, and the structural protocol.

The implementation should mirror the existing Raw/Layered pattern without inheriting the chat-specific `RawAgent`:

```python
class RawRealtimeAgent(BaseAgent):
    ...


class RealtimeAgent(AgentMiddlewareLayer, AgentTelemetryLayer, RawRealtimeAgent):
    ...
```

`RawRealtimeAgent` should derive from `BaseAgent`, not `RawAgent`. `RawAgent` is the chat-client agent implementation:
it assumes `SupportsChatGetResponse`, chat options, chat response parsing, and the chat function-calling loop. Reusing it
would make realtime inherit request/response chat assumptions that the realtime protocol is explicitly trying to avoid.

`BaseAgent` is the right base because it provides identity, context provider storage, middleware storage, session
factories, tool-as-agent support, and provider hooks without imposing a chat-client transport. The full `RealtimeAgent`
then gets agent middleware and telemetry by layering `AgentMiddlewareLayer` and `AgentTelemetryLayer` over
`RawRealtimeAgent`, just as `Agent` layers them over `RawAgent`.

OpenAI realtime is the first provider implementation and belongs in `agent-framework-openai`, for example as
`RawOpenAIRealtimeClient` / `OpenAIRealtimeClient`. Core must not take an OpenAI SDK dependency.

### Sandwich STT-agent-TTS path

Add `RealtimePipeline` for sandwich setups. It composes a speech-to-text component, an inner `SupportsAgentRun`, and a
text-to-speech component behind the same `AgentConversation` surface. This also requires adding provider-neutral STT and
TTS abstractions that are small enough to support both local samples and hosted media integrations.

This is a staged part of the architecture. The direct realtime model path should land first. `RealtimePipeline`, STT, and
TTS abstractions should land in the first implementation only if there is a concrete provider or sample validating their
shape. Otherwise the ADR records the intended architecture and defers the concrete API.

The sandwich implementation should:

- accept live audio input through `AgentConversation`;
- stream or batch audio into the speech-to-text abstraction;
- feed recognized text into the inner agent;
- stream the inner agent's text updates into the text-to-speech abstraction;
- emit synthesized audio as `Content.from_data(..., media_type="audio/...")`;
- surface STT/TTS/pipeline lifecycle events as realtime control-event content;
- use the inner agent's normal function invocation behavior instead of creating a second outer tool loop by default.

Concrete provider implementations can live in provider packages or samples, but the provider-neutral STT/TTS protocol
shape and `RealtimePipeline` class are part of the architecture.

### Event and content representation

Content-bearing realtime events map to existing `Content` types where possible:

- text and transcripts -> `Content.from_text`;
- audio frames or synthesized audio -> `Content.from_data(..., media_type="audio/...")`;
- function calls -> `Content.from_function_call`;
- function results -> `Content.from_function_result`;
- errors -> `Content.from_error`;
- usage -> `Content.from_usage`.

Control signals with no normal content payload use a small experimental realtime event content path, for example
`Content.from_realtime_event(...)`. The realtime event metadata should include:

- a provider-neutral event kind suitable for pattern matching;
- the service or pipeline event type string when available;
- optional event attributes that are safe to serialize;
- raw provider/pipeline object references in `raw_representation`, excluded from serialization as other raw objects are.

Every direct provider server event must become an `AgentResponseUpdate`, either with normal content or realtime event
content. Sandwich pipelines should also emit their own lifecycle signals, such as STT speech start/end, transcript
available, inner-agent response start/end, TTS audio start/end, interruption, cancellation, and errors.

### Session and identity

`AgentConversation` is live runtime state. `AgentSession` is durable serialized state. Do not store sockets, tasks, audio
streams, or provider session objects in `AgentSession`.

Add a `RealtimeAgentSession` only for durable state and compatibility checks. It can carry service-owned continuation
state through `service_session_id` and namespaced serializable state where needed. Following ADR 0029, values are placed
by lifecycle:

- future-call continuation -> `AgentSession.service_session_id` or namespaced session state;
- single response/event identity -> response/update/event metadata;
- unfinished work resume -> continuation tokens if needed later;
- per-run correlation -> run/telemetry context, not `AgentSession`;
- live socket state -> `AgentConversation`, never `AgentSession`.

Direct realtime model sessions and sandwich pipeline sessions are not interchangeable. Implementations should detect
obviously incompatible session state before making remote calls when practical.

### Function invocation

Direct realtime model tool calls should reuse the existing function-invocation implementation. The current
`FunctionInvocationLayer.get_response(...)` wrapper is chat-client-roundtrip oriented, but the execution behavior under
it is provider-neutral and already handles:

- normalized `FunctionInvocationConfiguration`;
- function middleware pipelines;
- tool approval requests and responses;
- declaration-only tools;
- argument validation;
- progressive tool exposure through `FunctionInvocationContext.tools`;
- `UserInputRequiredException`;
- max iterations / max function calls / consecutive error limits;
- detailed versus generic tool error shaping.

Refactor that execution behavior into a shared internal executor used by both `FunctionInvocationLayer` and direct
realtime agents. The refactor should preserve current chat behavior first; realtime should call the shared executor
after it is covered by regression tests.

For sandwich pipelines, function invocation normally belongs to the inner text agent. Do not add a second outer realtime
tool loop unless a concrete scenario requires it.

### Half-duplex behavior

The first direct realtime implementation should open a fresh ephemeral realtime session per `run(...)`. It sends the
input, requests or commits a response, drains until the terminal response event, and closes the live session. Warm
connection reuse is a later optimization because it complicates cancellation, session compatibility, and resource
ownership.

Sandwich `run(...)` follows the same half-duplex projection: it processes one input turn through STT if needed, runs the
inner agent, optionally synthesizes audio, emits updates, and closes live resources.

### Provider scope

The first concrete provider should be OpenAI direct realtime in `agent-framework-openai`. Gemini Live or another
protocol-different provider is useful later as a portability proof. Sandwich implementations should be designed in the
ADR now but can land after the direct-model skeleton unless a first STT/TTS provider is selected.

### Deferred decisions

- Warm connection reuse for half-duplex `run(...)`.
- WebRTC/browser-oriented transport APIs.
- Concrete `RealtimePipeline`, STT, and TTS implementations if no first-slice provider or sample validates their shape.
- Built-in microphone and speaker handlers.
- Dedicated realtime middleware separate from existing agent/function middleware.
- Final public STT and TTS protocol names.

### Consequences

- Good, because callers get one Agent Framework live conversation concept for realtime use.
- Good, because direct realtime providers and sandwich pipelines can share event/output handling without pretending to be
  the same implementation.
- Good, because direct provider code remains outside core.
- Good, because function invocation reuses existing tested behavior instead of inventing a parallel tool loop.
- Good, because `AgentSession` remains durable state and `AgentConversation` owns live resources.
- Neutral, because the shared surface must be carefully documented to avoid hiding capability differences.
- Bad, because the design introduces new live-resource lifecycle concerns that existing chat agents do not have.
- Bad, because sandwich pipelines require more cancellation and backpressure plumbing than direct realtime model sessions.

## Validation

Validation should happen in stages:

1. ADR review validates the architecture before implementation.
2. Unit tests with fake realtime sessions validate direct realtime model behavior, half-duplex finalization, streaming
   finalization, event preservation, cleanup, receive-loop errors, and single-reader behavior.
3. Unit tests validate `Content.from_realtime_event(...)` serialization and `AgentResponse.from_updates(...)`
   aggregation.
4. Regression tests validate that extracting the shared function-invocation executor does not change existing chat client
   tool behavior.
5. Realtime tool tests validate direct function call -> function result / approval / user-input flows through the shared
   executor.
6. Sandwich tests, once a first implementation exists, validate STT -> agent -> TTS event flow, cancellation, and TTS
   output mapping.
7. OpenAI provider tests validate event mappers with fake SDK payloads. Live integration tests can be added later and
   marked `flaky` and `integration` with environment-based skips.

## Pros and Cons of the Options

### Option 1: Add `RealtimeAgent` as the realtime-specific agent type

Add `RawRealtimeAgent` / `RealtimeAgent` as first-class agent types for realtime. They should satisfy
`SupportsAgentRun` for half-duplex compatibility and reuse the same base/middleware/telemetry stack where practical, but
their constructor and methods can be explicit about live realtime behavior.
Illustrative direct-model and sandwich setup snippets are in the appendix.

- Good, because it covers both architecture families without forking the user-facing concept.
- Good, because the public type advertises that this agent owns live realtime session behavior.
- Good, because `Agent` can remain focused on chat-style request/response clients.
- Good, because `start_conversation(...)` and realtime-specific options do not have to be grafted onto every `Agent`.
- Good, because it keeps live resource lifetime explicit.
- Good, because direct providers can preserve provider events while sandwich pipelines can surface pipeline events.
- Good, because it allows OpenAI direct realtime first without blocking the sandwich architecture.
- Neutral, because users must learn when to use `Agent` versus `RealtimeAgent`.
- Bad, because the common abstraction has to be narrow and carefully policed; otherwise it becomes a leaky lowest-common
  denominator.
- Bad, because framework integrations that special-case the concrete `Agent` type may need to generalize to the agent
  protocol/base class.

### Option 2: Extend `Agent` to also be the realtime agent type

Reuse `Agent` as the only public agent type. `Agent` would accept either a chat client, a direct realtime client, or a
sandwich realtime pipeline, and would grow realtime-specific APIs such as `start_conversation(...)`.
Illustrative direct-model and sandwich setup snippets are in the appendix.

- Good, because users have one public agent type to learn.
- Good, because existing `Agent(...)` samples and mental model remain the starting point.
- Neutral, because `Agent` would need to accept multiple client protocols with different lifecycle semantics.
- Bad, because it overloads the meaning of `client=`: chat clients are request/response, realtime clients own live
  full-duplex sessions, and sandwich pipelines are composed systems.
- Bad, because `Agent` would need realtime-only APIs such as `start_conversation(...)` even when used with normal chat
  clients.
- Bad, because type checking and overloads become harder: `Agent[ChatOptions]` and realtime options have different
  execution shapes.
- Bad, because live resource lifetime is easier to miss when hidden behind the existing chat-agent constructor.

## Appendix: Comparison with Semantic Kernel Python realtime

Semantic Kernel's Python realtime design, as captured in ADR 0065, is primarily a **client abstraction**. It centers on a
realtime client that can create/update/close a session, send events, and receive an async stream of `RealtimeEvent`
objects. Its event model treats both content and control signals as events, with provider details retained through
service event type/raw event fields. It also deliberately leaves microphone and speaker handling to application code or
samples.

This proposal keeps those lessons but maps them into Agent Framework's agent model:

- **Client versus agent**: Semantic Kernel exposes a realtime client surface directly. Agent Framework should expose a
  `RealtimeAgent` and `AgentConversation`, with provider clients below that surface, so realtime composes with agent
  middleware, sessions, workflows, handoffs, telemetry, and tools.
- **Event shape**: Semantic Kernel returns `RealtimeEvent` subclasses directly. Agent Framework should surface
  `AgentResponseUpdate` values whose `contents` are normal `Content` items where possible, plus a small
  realtime-event content type for control signals. Raw provider events remain available through `raw_representation`.
- **Tool invocation**: Semantic Kernel integrates realtime events with Kernel functions. Agent Framework should reuse the
  existing function-invocation implementation under `FunctionInvocationLayer` so approval flow, function middleware,
  declaration-only tools, progressive tools, user-input requests, and tool error shaping stay consistent with chat
  agents.
- **Direct and sandwich setups**: Semantic Kernel ADR 0065 focuses on direct realtime API clients. Agent Framework should
  explicitly support both direct realtime models and STT -> agent -> TTS sandwich pipelines behind the same
  `AgentConversation` surface, while documenting that their latency, interruption, and continuation semantics differ.
- **Session lifetime**: Semantic Kernel's realtime client owns realtime session operations. Agent Framework should keep
  live sockets/tasks in `AgentConversation` and keep `AgentSession` for durable, serializable continuation state only.
- **Audio path**: Semantic Kernel exposes `audio_output_callback` so audio can be forwarded before normal event handling
  for smoother playback. Agent Framework should start with audio as normal conversation updates and small
  source/sink-style bridge helpers. A dedicated low-latency audio callback can be added later if the normal update path
  proves insufficient for local devices or hosted media streams.

### Semantic Kernel local websocket shape with function calling

```python
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.open_ai import (
    AzureRealtimeExecutionSettings,
    AzureRealtimeWebsocket,
    ListenEvents,
    TurnDetection,
)
from semantic_kernel.contents import ChatHistory, RealtimeTextEvent

kernel = Kernel()
kernel.add_functions(plugin_name="helpers", functions=[goodbye, get_weather, get_date_time])

# Sample helpers own local microphone/speaker integration.
realtime_client = AzureRealtimeWebsocket()
audio_player = AudioPlayerWebsocket()
audio_recorder = AudioRecorderWebsocket(realtime_client=realtime_client)

settings = AzureRealtimeExecutionSettings(
    instructions="You are a helpful voice assistant.",
    voice="alloy",
    turn_detection=TurnDetection(type="server_vad", create_response=True, silence_duration_ms=800, threshold=0.8),
    function_choice_behavior=FunctionChoiceBehavior.Auto(),
)

chat_history = ChatHistory()
chat_history.add_user_message("Hi there, I'm based in Amsterdam.")

async with (
    audio_recorder,
    realtime_client(settings=settings, chat_history=chat_history, kernel=kernel, create_response=True),
    audio_player,
):
    async for event in realtime_client.receive(audio_output_callback=audio_player.client_callback):
        match event:
            case RealtimeTextEvent():
                print(event.text.text, end="")
            case _:
                if event.service_type == ListenEvents.RESPONSE_CREATED:
                    print("\nAssistant transcript: ", end="")
```

### Proposed Agent Framework local websocket shape with function calling

```python
from agent_framework.realtime import RealtimeAgent
from agent_framework.openai import OpenAIRealtimeClient

agent = RealtimeAgent(
    client=OpenAIRealtimeClient(model="gpt-4o-realtime-preview", voice="alloy"),
    instructions="You are a helpful voice assistant.",
    tools=[get_weather],
    default_options={
        "turn_detection": {"type": "server_vad", "create_response": True, "silence_duration_ms": 800, "threshold": 0.8},
        "input_audio_transcription": {"model": "whisper-1"},
    },
)

# Sample/optional helpers own local microphone/speaker integration.
audio_player = RealtimeAudioPlayer()
audio_recorder = RealtimeAudioRecorder()

async with (
    audio_player,
    agent.start_conversation(
        messages=["Hi there, I'm based in Amsterdam."],
    ) as conversation,
    audio_recorder.stream_to(conversation),
):
    async for update in conversation:
        for content in update.contents:
            if content.has_top_level_media_type("audio"):
                await audio_player.write(content)
        if update.text:
            print(update.text, end="")
```

### Proposed Agent Framework sandwich shape

```python
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework.realtime import RealtimeAgent, RealtimePipeline

text_agent = Agent(
    client=OpenAIChatClient(model="gpt-4.1"),
    instructions="You are a helpful assistant.",
    tools=[get_weather],
)

agent = RealtimeAgent(
    client=RealtimePipeline(
        speech_to_text=speech_to_text_client,
        agent=text_agent,
        text_to_speech=text_to_speech_client,
    ),
)
```

### Semantic Kernel Call Automation bridge shape

```python
async def from_realtime_to_acs(audio: ndarray) -> None:
    await websocket.send(json.dumps({
        "kind": "AudioData",
        "audioData": {"data": base64.b64encode(audio.tobytes()).decode("utf-8")},
    }))


async def from_acs_to_realtime(client: RealtimeClientBase) -> None:
    while True:
        data = json.loads(await websocket.receive())
        if data["kind"] == "AudioData":
            await client.send(RealtimeAudioEvent(audio=AudioContent(data=data["audioData"]["data"])))


async with client(settings=settings, create_response=True, kernel=kernel):
    receive_task = asyncio.create_task(handle_realtime_messages(client, audio_output_callback=from_realtime_to_acs))
    await from_acs_to_realtime(client)
    receive_task.cancel()
```

### Proposed Agent Framework Call Automation bridge shape

```python
from agent_framework import Content
from agent_framework.realtime import AgentConversation


async def from_realtime_to_acs(content: Content) -> None:
    await websocket.send(json.dumps({
        "kind": "AudioData",
        "audioData": {"data": content.data},
    }))


async def from_acs_to_realtime(conversation: AgentConversation) -> None:
    while True:
        data = json.loads(await websocket.receive())
        if data["kind"] == "AudioData":
            await conversation.send(
                Content.from_data(base64.b64decode(data["audioData"]["data"]), media_type="audio/pcm")
            )


async def handle_agent_updates(conversation: AgentConversation) -> None:
    async for update in conversation:
        for content in update.contents:
            if content.has_top_level_media_type("audio"):
                await from_realtime_to_acs(content)
            elif content.type == "realtime_event" and content.service_event_type == "input_audio_buffer.speech_started":
                await websocket.send(json.dumps({"Kind": "StopAudio", "AudioData": None, "StopAudio": {}}))


async with agent.start_conversation() as conversation:
    receive_task = asyncio.create_task(handle_agent_updates(conversation))
    await from_acs_to_realtime(conversation)
    receive_task.cancel()
```

### Rejected option shape: extending `Agent`

This shows the alternative rejected in the decision outcome.

```python
from agent_framework import Agent
from agent_framework.openai import OpenAIRealtimeClient

agent = Agent(
    client=OpenAIRealtimeClient(model="gpt-4o-realtime-preview", voice="alloy"),
    instructions="You are a helpful voice assistant.",
    tools=[get_weather],
)

async with agent.start_conversation() as conversation:
    await conversation.send(Content.from_data(audio_chunk, media_type="audio/pcm"))
    async for update in conversation:
        ...
```

## Appendix: Proposed Python realtime client protocol

The direct realtime model path should use a small provider-neutral protocol. The agent owns mapping between this protocol
and `AgentConversation` / `AgentResponseUpdate`; provider packages own mapping between the protocol and provider SDK
objects.

Illustrative protocol shape:

```python
from collections.abc import AsyncIterable, Mapping
from typing import Any, Protocol, runtime_checkable
from typing_extensions import TypedDict

from agent_framework import Content


class RealtimeSessionOptions(TypedDict, total=False):
    """Provider-neutral realtime session options with provider-specific extension fields."""

    instructions: str
    voice: str
    input_audio_format: str
    output_audio_format: str
    input_audio_transcription: Mapping[str, Any]
    turn_detection: Mapping[str, Any] | None
    create_response: bool


class RealtimeEvent:
    """Provider-neutral event to send to, or receive from, a realtime session."""

    event_type: str
    content: Content | None
    service_event_type: str | None
    additional_properties: Mapping[str, Any]
    raw_representation: Any | None


@runtime_checkable
class RealtimeClientSessionProtocol(Protocol):
    """Live provider session for one realtime connection."""

    options: RealtimeSessionOptions

    async def send(self, event: RealtimeEvent) -> None:
        """Send one realtime event or command to the realtime provider."""
        ...

    def receive(
        self,
    ) -> AsyncIterable[RealtimeEvent]:
        """Yield provider events. Only one active receiver is allowed per session."""
        ...

    async def close(self) -> None:
        """Close the live provider session."""
        ...

    async def __aenter__(self) -> "RealtimeClientSessionProtocol":
        """Enter the live provider session context."""
        ...

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any) -> None:
        """Exit and close the live provider session context."""
        ...


@runtime_checkable
class RealtimeClientProtocol(Protocol):
    """Provider client capable of creating realtime sessions."""

    async def start_session(
        self,
        *,
        options: RealtimeSessionOptions | None = None,
    ) -> RealtimeClientSessionProtocol:
        """Create a live realtime provider session."""
        ...

```

Notes:

- `RealtimeAgent` may expose a higher-level `start_conversation(...)` method that accepts agent run options and returns
  `AgentConversation`; provider clients expose `start_session(...)`.
- `AgentConversation`, not `RealtimeClientSessionProtocol`, owns convenience inputs such as strings, `Message`, `Content`,
  local audio helpers, and hosted media bridge helpers. It translates them into provider-level `RealtimeEvent` values.
- `RealtimeClientSessionProtocol.receive(...)` intentionally returns a plain `AsyncIterable[RealtimeEvent]`, not
  `ResponseStream`, because it is the provider-level live event feed and has no provider-neutral final response.
- `ResponseStream` belongs at the agent layer:
  - `RealtimeAgent.run(..., stream=True)` returns `ResponseStream[AgentResponseUpdate, AgentResponse]`.
  - A continuously open conversation may expose an async stream of updates without requiring callers to finalize it into
    one response.
  - A scoped `AgentConversation` response helper can return `ResponseStream[AgentResponseUpdate, AgentResponse]` later if
    the API proves necessary.
- `receive(...)` is single-reader. `AgentConversation` should own that read loop and project provider events into
  agent-level updates.
- `RealtimeSessionOptions` should likely be a `TypedDict` in implementation, not a concrete mapping subclass. The shape
  above is illustrative.
- Provider-specific options and event fields are allowed through mapping-style extension fields, but provider SDK objects
  stay in `raw_representation`.

## Appendix: Realtime data model roles

The realtime design uses existing Agent Framework message/content models where possible and adds a realtime event model
only for live-session events. These types have different jobs:

| Type | Role | Lifetime | Examples | Serialized? |
| --- | --- | --- | --- | --- |
| `Content` | One semantic payload item. | Reusable across chat, agent, realtime, and tool flows. | text delta, audio bytes, function call, function result, error, usage, realtime control event content. | Yes, except `raw_representation`. |
| `Message` | A role-authored collection of content items. | Conversation/history unit for half-duplex runs and seeded context. | user text message, assistant response message, tool result message. | Yes, except `raw_representation`. |
| `RealtimeEvent` | One live realtime protocol/pipeline signal. | Live session send/receive unit. | `response.created`, `response.audio.delta`, `input_audio_buffer.speech_started`, pipeline transcript-ready event. | Mostly yes; raw provider object excluded. |
| `AgentResponseUpdate` | One caller-facing streamed agent update. | Output stream item from `run(..., stream=True)` or `AgentConversation`. | audio update, transcript update, function-call update, VAD event update. | Yes, except `raw_representation`. |

### `Content`

`Content` remains the framework's semantic payload type. Realtime should not introduce new content classes for data the
framework already understands:

- text/transcripts -> `Content.from_text(...)`;
- audio -> `Content.from_data(..., media_type="audio/...")`;
- tool requests -> `Content.from_function_call(...)`;
- tool results -> `Content.from_function_result(...)`;
- errors -> `Content.from_error(...)`;
- usage -> `Content.from_usage(...)`.

Only realtime control signals that do not naturally fit an existing content type need a new content shape, for example
`Content.from_realtime_event(...)`. That content should carry serializable event metadata and keep the raw provider event
in `raw_representation`.

`Content.from_realtime_event(...)` is not a replacement for `RealtimeEvent`. It is the semantic `Content` payload used
when a realtime control signal needs to appear in an `AgentResponseUpdate.contents` list. `RealtimeEvent` is the live
session event envelope; realtime-event content is the agent-response payload created from that envelope when there is no
text/audio/function/error content to carry.

Do not make `Content.from_realtime_event(...)` a wrapper that optionally carries text, audio, function-call, or
function-result content. That creates two envelopes for the same event and gives users two ways to find the same
payload. Payload-bearing events should use normal `Content` directly in `RealtimeEvent.content`; control-only events
should use `Content.from_realtime_event(...)` only when projected into an `AgentResponseUpdate`.

Example:

```python
event = RealtimeEvent(
    event_type="lifecycle",
    content=None,
    service_event_type="input_audio_buffer.speech_started",
    additional_properties={"audio_start_ms": 1200},
    raw_representation=openai_event,
)

update = AgentResponseUpdate(
    contents=[
        Content.from_realtime_event(
            event_type=event.event_type,
            service_event_type=event.service_event_type,
            additional_properties=event.additional_properties,
            raw_representation=event.raw_representation,
        )
    ],
    additional_properties={"service_event_type": event.service_event_type},
    raw_representation=event,
)
```

In short:

- `RealtimeEvent` says "the live realtime session emitted this event."
- `Content.from_realtime_event(...)` says "this event has no normal semantic payload, so carry the control signal as a
  content item in the agent update."

### `Message`

`Message` is still the durable conversation/history unit. It groups one or more `Content` items under a role such as
`user`, `assistant`, or `tool`.

Realtime uses `Message` in two places:

- **Half-duplex input/output**: `RealtimeAgent.run(...)` accepts normal `Message`/string/`Content` inputs and returns an
  `AgentResponse` containing normal `Message` objects.
- **Session seeding / history replay**: a direct realtime model session can be created from existing `Message` history so
  an ephemeral socket can reconstruct context.

`Message` should not represent every provider event. A VAD event, response-created signal, or audio buffer update is not
a durable authored chat message; it should remain a realtime event or an `AgentResponseUpdate` with realtime-event
content.

### `RealtimeEvent`

`RealtimeEvent` is the live wire-level abstraction for direct realtime providers and pipeline internals. It is not the
main user-facing response type. It exists so provider clients can report every service signal without forcing all signals
into `Message`.

On the receive side, `RealtimeEvent` is closest to `ChatResponseUpdate`: it is a provider-level streamed item that the
agent projects into `AgentResponseUpdate`. It is not called `RealtimeUpdate` because the same type also represents
outbound live-session commands. "Update" would imply response-only/output-only semantics, which is wrong for operations
like response create, response cancel, audio buffer clear, session update, and interruption.

Returning only `Content` from the provider session is not enough because realtime services emit events where the event
itself carries important meaning beyond the payload:

- multiple events can carry the same semantic content type but require different handling, for example
  `response.audio.delta`, `response.audio.done`, and `response.audio_transcript.done`;
- control events often have no semantic payload but still matter, for example speech started/stopped, response created,
  response done, rate-limit updates, cancellation, and errors;
- event-level identifiers such as response id, item id, output index, content index, timestamps, and provider event type
  are needed for ordering, correlation, interruption, and final aggregation;
- some send operations are commands rather than content, for example response creation, cancellation, buffer clear, or
  session update;
- tool-call arguments may arrive across multiple service events and need event-level correlation before they become a
  complete `Content.from_function_call(...)`;
- hosted media and sandwich pipelines also need lifecycle events that are not authored messages and are not naturally
  text/audio/function content.

`Content` should answer "what semantic payload is present?" `RealtimeEvent` should answer "what happened in the live
session, and what provider/pipeline metadata came with it?"

What `RealtimeEvent` adds over `Message` / `AgentResponseUpdate` is narrow, and should stay narrow:

- **Outbound commands**: `Message` and `AgentResponseUpdate` are not a good fit for commands like response create,
  response cancel, input buffer clear, session update, or interruption. `RealtimeEvent` can represent these live-session
  operations without pretending they are authored conversation messages or agent output updates.
- **Provider/session boundary**: provider clients should not have to manufacture `AgentResponseUpdate` values. That is the
  agent projection layer's job, just like chat clients return `ChatResponseUpdate` and agents map those to
  `AgentResponseUpdate`.
- **Pre-projection correlation**: raw provider events often need event type, response id, item id, output/content indexes,
  timestamps, and raw SDK objects before the agent decides how to project them. `RealtimeEvent` keeps that protocol
  metadata together until projection.

If `RealtimeEvent` stops being the provider/session boundary and becomes only another way to carry `Content`, delete it.
It should not exist as a third user-facing response model.

#### Sub-option: one content item or a list of content items

There are two reasonable shapes for the payload field.

Option A: `RealtimeEvent.content: Content | None`

- Good, because each realtime event has one clear payload or no payload.
- Good, because it avoids making `RealtimeEvent`, `Message`, and `AgentResponseUpdate` all own `list[Content]`.
- Good, because it forces provider mappers to split multi-payload provider events into simpler framework events.
- Good, because it matches the current Semantic Kernel Python shape: `RealtimeAudioEvent.audio`,
  `RealtimeTextEvent.text`, `RealtimeFunctionCallEvent.function_call`, and related event subclasses each carry one
  typed payload, while base `RealtimeEvent` carries service/control event metadata.
- Neutral, because a raw provider event that contains multiple payloads may become multiple `RealtimeEvent` instances that
  share the same `raw_representation`.
- Bad, because it can lose the fact that one raw provider event contained multiple semantic payloads unless that
  relationship is recorded in metadata.
- Bad, because wrapping to `AgentResponseUpdate` always has to put the single content into a list.

Option B: `RealtimeEvent.contents: Sequence[Content]`

- Good, because it mirrors `Message.contents`, `ChatResponseUpdate.contents`, and `AgentResponseUpdate.contents`.
- Good, because one raw provider event with multiple semantic payloads can remain one framework event.
- Good, because wrapping into `AgentResponseUpdate` is mechanically simple: copy `event.contents`.
- Neutral, because many realtime events will still have zero or one content item.
- Bad, because it creates another envelope with a content list, which overlaps with `Message` and `AgentResponseUpdate`.
- Bad, because users may have to learn whether a payload is in the event list, the update list, or a final message list.
- Bad, because it encourages stuffing unrelated payloads into one event instead of keeping event semantics precise.

Decision: use **Option A: `RealtimeEvent.content: Content | None`**. This matches the Semantic Kernel Python realtime
model and keeps realtime event handling simple: one live event has one payload or no payload. Provider mappers should
split raw provider events with multiple semantic payloads into multiple `RealtimeEvent` instances that share the same
`raw_representation`.

It should carry:

- `event_type`: a provider-neutral category such as `audio`, `text`, `function_call`, `function_result`, `error`,
  `service`, or `lifecycle`;
- `content`: one optional `Content` item when the event has a semantic payload;
- `service_event_type`: the provider or pipeline event name, such as `response.audio.delta` or
  `input_audio_buffer.speech_started`;
- `additional_properties`: serializable event metadata such as response id, item id, timestamps, or status;
- `raw_representation`: the provider SDK event object or pipeline object, excluded from serialization.

For sending, `RealtimeEvent` is the escape hatch for operations that are not just "send this message" or "send this
audio." Examples include response creation, cancellation, clearing an audio buffer, or provider-specific session updates.

For receiving, provider clients map raw service events into `RealtimeEvent`; `RealtimeAgent` then maps those into
`AgentResponseUpdate` values for callers.

### Wrapping `RealtimeEvent` into agent responses

There is one wrapping path: `RealtimeAgent` wraps each received `RealtimeEvent` into one `AgentResponseUpdate`.
`Content.from_realtime_event(...)` is not a second wrapping mechanism; it is only the fallback content item used when the
event has no existing semantic content. The update preserves the event as its raw representation and exposes the event's
payload as normal update content:

```python
def map_realtime_event_to_agent_update(event: RealtimeEvent, agent: RealtimeAgent) -> AgentResponseUpdate:
    content = event.content or Content.from_realtime_event(
        event_type=event.event_type,
        service_event_type=event.service_event_type,
        additional_properties=event.additional_properties,
        raw_representation=event.raw_representation,
    )

    return AgentResponseUpdate(
        contents=[content],
        role=_role_from_realtime_event(event),
        author_name=agent.name,
        agent_id=agent.id,
        response_id=event.additional_properties.get("response_id"),
        message_id=event.additional_properties.get("item_id"),
        additional_properties={
            "event_type": event.event_type,
            "service_event_type": event.service_event_type,
            **event.additional_properties,
        },
        raw_representation=event,
    )
```

The wrapping rules are:

- Always create an `AgentResponseUpdate` with `raw_representation` set to the `RealtimeEvent`.
- If `event.content` is present, put that one `Content` item in `AgentResponseUpdate.contents`.
- If `event.content` is absent, create one `Content.from_realtime_event(...)` item and put it in
  `AgentResponseUpdate.contents`.
- If one raw provider event carries multiple semantic payloads, split it into multiple `RealtimeEvent` instances that
  share the same `raw_representation` rather than adding a list of contents to `RealtimeEvent`.
- Do not wrap normal text/audio/function/error payloads inside `Content.from_realtime_event(...)`.
- The `RealtimeEvent.raw_representation` points to the provider SDK object or pipeline object.
- Copy serializable identifiers such as response id, item id, event type, and service event type into
  `additional_properties` or the standard `response_id` / `message_id` fields when they match existing meanings.
- Do not manufacture a durable `Message` for every `RealtimeEvent`. Messages are only created when finalizing a
  half-duplex `AgentResponse` or when a realtime event actually represents an authored conversation item.

For half-duplex `run(...)`, `RealtimeAgent` accumulates the streamed updates until the terminal response event and then
builds a normal `AgentResponse`. That final response should contain authored assistant/tool messages reconstructed from
content-bearing updates, while pure control events remain available through the response `raw_representation` list and
through any realtime-event content that was emitted during streaming.

### Mapping rules

The mapping should be explicit and boring:

| Input/output situation | Preferred model |
| --- | --- |
| User sends text to a realtime conversation | `Message` or `Content.from_text(...)`, converted to provider input-text events. |
| User sends audio bytes | `conversation.send(Content.from_data(...))`, converted to provider input-audio events. |
| Caller needs a provider-specific control operation | `RealtimeEvent`. |
| Provider emits audio | `RealtimeEvent(content=Content.from_data(...))` -> `AgentResponseUpdate(contents=[...])`. |
| Provider emits transcript/text | `RealtimeEvent(content=Content.from_text(...))` -> `AgentResponseUpdate(contents=[...])`. |
| Provider emits a function call | `RealtimeEvent(content=Content.from_function_call(...))`; direct realtime tool loop invokes existing function machinery. |
| Provider emits a lifecycle/control signal | `RealtimeEvent(content=None)` -> `AgentResponseUpdate(contents=[Content.from_realtime_event(...)])`. |
| Half-duplex final response | Accumulate relevant `AgentResponseUpdate` items into normal `AgentResponse(messages=[Message(...)])`. |

This separation keeps `Message` useful for durable conversation history, keeps `Content` as the common semantic payload
model, and keeps `RealtimeEvent` focused on live protocol/pipeline events that may not be authored messages.

## Appendix: Comparison with .NET `IRealtimeClient`

| Concern | .NET `IRealtimeClient` / `IRealtimeClientSession` | Proposed Python protocol |
| --- | --- | --- |
| Client role | `IRealtimeClient` creates `IRealtimeClientSession` instances. | `RealtimeClientProtocol.start_session(...)` creates `RealtimeClientSessionProtocol` instances. |
| Session lifetime | `IRealtimeClientSession` is `IAsyncDisposable`. | `RealtimeClientSessionProtocol` is an async context manager with `close()`. |
| Send operation | `SendAsync(RealtimeClientMessage, ...)`. | `send(RealtimeEvent)`. `Message` / `Content` conveniences live on `AgentConversation`. |
| Receive operation | `GetStreamingResponseAsync(...)` yields `RealtimeServerMessage`; single-reader constraint is called out. | `receive(...)` yields `RealtimeEvent`; single-reader constraint is explicit and normally owned by `AgentConversation`. |
| Options | `RealtimeSessionOptions` configures voice, VAD, formats, tools, and provider settings. | `RealtimeSessionOptions` carries the same conceptual fields using Python `TypedDict`/mapping conventions and provider extension fields. |
| Audio | MEAI events can carry audio; .NET ADR projects audio to `DataContent` at agent level. | Audio flows as normal `Content.from_data(...)` payloads on `RealtimeEvent`; a callback can be added later if needed. |
| Break-glass access | `GetService(...)` and raw representations expose MEAI/provider SDK objects. | `raw_representation` exposes provider SDK objects on events/updates. |
| Agent projection | .NET `RealtimeAgent : AIAgent` wraps `IRealtimeClient`; `AgentConversation` is agent-level. | Python has no `AIAgent`; `RealtimeAgent` wraps `RealtimeClientProtocol`, exposes `AgentConversation`, and must satisfy `SupportsAgentRun` for half-duplex compatibility. |
| Function invocation | .NET expects reuse of `RealtimeClientBuilder` middleware, including function invocation. | Python should reuse/extract the existing `FunctionInvocationLayer` executor for direct realtime tool calls. |
| Sandwich pipeline | Not the main `IRealtimeClient` focus in the .NET ADR. | Explicitly included through `RealtimePipeline(STT, SupportsAgentRun, TTS)` using the same `AgentConversation` surface. |

The proposed Python protocol intentionally stays close to .NET in the client/session split, live async lifetime,
single-reader receive stream, options concept, raw-representation escape hatch, and agent-level `AgentConversation`
projection. It
differs where Python needs a more idiomatic or practical shape:

- Python uses structural `Protocol` types instead of C# interfaces.
- Python uses async context managers instead of `IAsyncDisposable`.
- Python includes `Message`/`Content` send conveniences to reduce boilerplate in samples and hosting bridges.
- Python includes `RealtimePipeline` as a first-class sandwich composition target, while .NET's ADR focuses on direct
  realtime clients.

## More Information

- .NET realtime ADR draft: `https://github.com/rogerbarreto/agent-framework-public/blob/features/realtime-agent/docs/decisions/0030-realtime-ai-agent.md`
- Semantic Kernel realtime client ADR: `https://github.com/microsoft/semantic-kernel/blob/main/docs/decisions/0065-realtime-api-clients.md`
- Python session identity ADR: [`0029-python-agent-session-identity.md`](0029-python-agent-session-identity.md)
- Provider package separation ADR: [`0021-provider-leading-clients.md`](0021-provider-leading-clients.md)
