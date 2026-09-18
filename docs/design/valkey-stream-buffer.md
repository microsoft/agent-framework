---
status: proposed
contact: Matthias Howell
date: 2026-07-16
---

# Resumable Streaming Middleware via Valkey Streams

## Context and Problem Statement

The Agent Framework supports streaming agent responses via `RunStreamingAsync`, yielding `AgentResponseUpdate` chunks as they are generated. If a client disconnects mid-stream — network interruption, page navigation, mobile backgrounding — all subsequent chunks are lost and the full response must be regenerated (LLM cost + latency + different output).

The framework already defines the **continuation token** abstraction for stream resumption:
- `AgentResponseUpdate.ContinuationToken` — stamped on each streaming update
- `AgentRunOptions.ContinuationToken` — passed on reconnect to resume from a point

However, today this only works when the **underlying service** natively supports background responses (e.g., OpenAI Responses API via `AllowBackgroundResponses = true`). This capability flows through Microsoft.Extensions.AI (M.E.AI) — the foundational library that Agent Framework builds on for chat client abstractions. For all other providers — Azure OpenAI Chat Completions, Anthropic, local models, etc. — there is no way to resume a disconnected stream.

**Goal**: Provide a framework-integrated, storage-backed resumable streaming capability that works with *any* `ChatClientAgent`, regardless of whether the underlying service supports background responses natively.

### Related Work

| Component | What it does | Limitation |
|-----------|-------------|------------|
| `AllowBackgroundResponses` + `ContinuationToken` | Service-level resume via M.E.AI | Only works if the service supports it |
| `IAgentResponseHandler` (DurableTask) | Captures background agent streams | Tied to durable entity execution model |
| `RedisStreamResponseHandler` (sample) | Writes to Redis Streams + polls | Sample code, not a reusable package |
| [Issue #5544](https://github.com/microsoft/agent-framework/issues/5544) | Feature request | Open |
| [PR #5576](https://github.com/microsoft/agent-framework/pull/5576) | Buffer implementation (standalone) | Missing AF integration |

## Design Overview

The solution has two layers:

1. **Middleware** (`ResumableStreamingAgent`) — a `DelegatingAIAgent` that intercepts `RunStreamingAsync`, buffers each chunk to durable storage, stamps continuation tokens, and replays from the buffer on resume. This is the framework-facing component that users wire into their agent pipeline.

2. **Buffer** (`ValkeyStreamBuffer`) — the storage backend that persists chunks to Valkey Streams. This is an implementation detail; the middleware could theoretically back onto any append-only log.

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         User Code                                          │
│                                                                            │
│  var agent = chatClient.AsAIAgent(...)                                     │
│      .AsBuilder()                                                          │
│      .Use(inner => new ResumableStreamingAgent(inner, streamBuffer))       │
│      .Build();                                                             │
│                                                                            │
│  // Initial stream                                                         │
│  await foreach (var update in agent.RunStreamingAsync(messages, session))   │
│  {                                                                         │
│      Console.Write(update.Text);                                           │
│      lastToken = update.ContinuationToken;  // ← stamped by middleware     │
│  }                                                                         │
│                                                                            │
│  // Resume after disconnect                                                │
│  var options = new AgentRunOptions { ContinuationToken = lastToken };      │
│  await foreach (var update in agent.RunStreamingAsync(session, options))    │
│  {                                                                         │
│      Console.Write(update.Text);  // ← only missed chunks                 │
│  }                                                                         │
└────────────────────────────────────────────────────────────────────────────┘
```

## Relationship to AllowBackgroundResponses

`AllowBackgroundResponses` and this middleware solve **different but overlapping** problems:

| Aspect | AllowBackgroundResponses | Resumable Streaming Middleware |
|--------|--------------------------|-------------------------------|
| Where does it run? | Service-level (M.E.AI → provider) | Agent Framework middleware |
| Provider support required? | Yes — provider must implement it | No — works with any `IChatClient` |
| Who keeps generating after disconnect? | The service (server-side) | The agent runtime (server-side) |
| Resume mechanism | Provider's continuation token | Valkey Stream entry ID |
| Data loss window | Zero (service manages state) | Zero (buffer captures all chunks) |

**Design position**: This middleware is a **complement** to `AllowBackgroundResponses`, not a replacement. Specifically:

- If the service supports `AllowBackgroundResponses` and the user enables it, the existing service-level continuation token flow works as-is. The middleware is **not needed** in that case.
- If the service does **not** support background responses (which is most services today), this middleware provides an equivalent capability at the framework layer.
- The middleware **does not wrap or replace** the service-level continuation token — it provides its own orthogonal token backed by the Valkey Stream entry ID.

In future, if a service already provides its own token, the middleware could detect this and pass it through rather than double-buffering. For now, the simpler model is: either use `AllowBackgroundResponses` (service handles it) **or** use this middleware (framework handles it).

## Architecture

### Initial Stream (Happy Path)

```
Client          ResumableStreamingAgent          Inner Agent          Valkey
  │                      │                          │                   │
  │ RunStreamingAsync()  │                          │                   │
  │─────────────────────►│ RunStreamingAsync()      │                   │
  │                      │─────────────────────────►│                   │
  │                      │          update[0]       │                   │
  │                      │◄─────────────────────────│                   │
  │                      │                          │  XADD             │
  │                      │──────────────────────────────────────────────►│
  │                      │                          │  entry_id="1-0"   │
  │                      │◄──────────────────────────────────────────────│
  │   update[0]          │                          │                   │
  │   + Token("1-0")     │                          │                   │
  │◄─────────────────────│                          │                   │
  │                      │          update[1]       │                   │
  │                      │◄─────────────────────────│                   │
  │   ... (same flow)    │                          │                   │
```

### Resume After Disconnect

```
Client          ResumableStreamingAgent                              Valkey
  │                      │                                             │
  │ RunStreamingAsync()  │                                             │
  │ + Token("3-0")       │                                             │
  │─────────────────────►│                                             │
  │                      │  Detects ContinuationToken → resume mode    │
  │                      │                                             │
  │                      │  XRANGE key (3-0 +                          │
  │                      │─────────────────────────────────────────────►│
  │                      │  entries [4-0, 5-0, 6-0, ...]               │
  │                      │◄─────────────────────────────────────────────│
  │  update[4] + Token   │                                             │
  │◄─────────────────────│                                             │
  │  update[5] + Token   │                                             │
  │◄─────────────────────│                                             │
  │  ...                 │                                             │
```

### Key Question: What if the stream is still in progress?

If the client disconnects and reconnects while the agent is still generating, the middleware needs to:
1. Replay buffered entries from the last-seen ID (XRANGE — immediate, gets caught up)
2. Continue streaming new entries as the inner agent produces them

This requires the middleware to **keep the inner agent running** on the server side even when the client disconnects. This is the same problem `AllowBackgroundResponses` solves at the service level, now at the framework level.

**Proposed approach — deferred execution model**:
- When `ResumableStreamingAgent.RunStreamingAsync` is called, it starts a background task that runs the inner agent and buffers all output to Valkey.
- The client-facing enumerable reads from the buffer (XREAD with blocking or polling).
- If the client disconnects (disposes the enumerator), the background task continues writing to the buffer.
- On reconnect with a continuation token, the middleware resumes reading from the buffer without re-invoking the inner agent.

This is conceptually the same as the `IAgentResponseHandler` pattern in durable agents, but packaged as reusable middleware.

**Alternative approach — replay-only (simpler, limited)**:
- The middleware only buffers during the initial stream and does not manage background execution.
- Resume only works after the full stream has completed (all entries already in buffer).
- Limitation: if the client disconnects mid-stream and the response hasn't finished, the buffer is incomplete.

The deferred execution model is more complete but more complex. We propose starting with the **deferred execution model** since it matches the user's expectation of "disconnect at any point, reconnect and get everything."

### Background Task Lifecycle

The deferred execution model spawns background tasks that outlive client connections. This requires careful lifecycle management:

**Task Registry**: The middleware maintains a `ConcurrentDictionary<string, ProducerTaskEntry>` mapping `streamId` to the active producer task and its metadata. This registry enables:
- Lookup on resume (is the producer still running for this stream?)
- Enumeration for graceful shutdown
- Diagnostics/monitoring of active producers

```csharp
internal sealed record ProducerTaskEntry(
    Task ProducerTask,
    CancellationTokenSource Cts,
    DateTimeOffset StartedAt,
    string StreamId);
```

**Cancellation**: Each producer task receives a composite `CancellationToken` linked from:
1. A per-task `CancellationTokenSource` (for explicit cancellation on cleanup)
2. A hard timeout derived from `ResumableStreamingOptions.MaxProducerLifetime` (default: 30 min) — prevents runaway tasks from an infinitely-streaming LLM
3. `IHostApplicationLifetime.ApplicationStopping` (if available via DI) — for graceful shutdown

**Exception Handling**: Producer tasks are wrapped with structured error handling:
- On exception: write an error sentinel to the stream, log at `Error` level, remove from registry
- Unobserved task exceptions are caught — never crash the process
- The error sentinel is a sanitized error code (not the raw exception message — see Security section)

**Backpressure / Max Concurrency**: `ResumableStreamingOptions.MaxConcurrentProducers` (default: 100) limits simultaneous background tasks. If the limit is reached, `RunStreamingAsync` falls back to non-buffered pass-through (stream works normally, just not resumable) and logs a warning. This prevents unbounded LLM call accumulation under rapid connect/disconnect patterns.

**Graceful Shutdown**: On `ApplicationStopping`:
1. Cancel all active producer `CancellationTokenSource`s
2. Wait up to a configurable `ShutdownGracePeriod` (default: 5s) for tasks to complete
3. For any task that doesn't complete in time, write an error sentinel (`"shutdown"`) to the stream
4. Log final registry state at `Information` level

**Container/Pod Recycling**: If the process is killed without graceful shutdown (SIGKILL, OOM), streams are left without a sentinel. The consumer-side `TailAsync` handles this via inactivity timeout (see TailAsync Termination section below). The `EXPIRE` set at stream creation provides a hard upper bound for cleanup.

## Public API

### ResumableStreamingAgent (Middleware)

```csharp
namespace Microsoft.Agents.AI.Valkey;

/// <summary>
/// A delegating agent that provides resumable streaming by buffering response
/// chunks to Valkey Streams. Clients can disconnect and resume from any point
/// using the continuation token stamped on each AgentResponseUpdate.
/// </summary>
public sealed class ResumableStreamingAgent : DelegatingAIAgent
{
    public ResumableStreamingAgent(
        AIAgent innerAgent,
        ValkeyStreamBuffer streamBuffer,
        ResumableStreamingOptions? options = null);

    // RunStreamingAsync: intercepts, buffers, stamps tokens, supports resume
    // RunAsync: delegates to inner agent (no buffering needed for non-streaming)
}
```

### ResumableStreamingOptions

```csharp
namespace Microsoft.Agents.AI.Valkey;

public sealed class ResumableStreamingOptions
{
    /// <summary>
    /// How long to keep completed streams in Valkey after last write (idle TTL).
    /// Applied via EXPIRE after the done/error sentinel is written.
    /// Default: 10 minutes.
    /// </summary>
    public TimeSpan StreamRetention { get; set; } = TimeSpan.FromMinutes(10);

    /// <summary>
    /// Hard upper bound on stream lifetime from creation — safety net for orphaned streams.
    /// The producer refreshes this on every Nth write, so active streams never hit this ceiling.
    /// Only dead producers (no writes, no refresh) eventually expire at this bound.
    /// Default: 2 hours.
    /// </summary>
    public TimeSpan MaxStreamLifetime { get; set; } = TimeSpan.FromHours(2);

    /// <summary>
    /// Maximum entries per stream (approximate XTRIM).
    /// Null means no trimming.
    /// </summary>
    public int? MaxLength { get; set; }

    /// <summary>
    /// Polling interval when tailing a still-active stream on resume.
    /// Default: 100ms.
    /// </summary>
    public TimeSpan PollInterval { get; set; } = TimeSpan.FromMilliseconds(100);

    /// <summary>
    /// Maximum time to wait for the stream key to be created by the producer before giving up.
    /// Default: 5 seconds.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This is a standalone timeout independent of <see cref="PollInterval"/>. During this window,
    /// the consumer polls with <c>EXISTS</c> at <see cref="PollInterval"/> intervals to detect
    /// stream creation. If the stream has not been created after this duration, the consumer
    /// yields <c>AgentStreamingException("stream_not_created")</c>.
    /// </para>
    /// <para>
    /// Changing <see cref="PollInterval"/> affects how frequently the consumer checks, but does NOT
    /// change how long it waits in total. For example, with PollInterval=500ms and
    /// MaxWaitForStreamCreation=5s, the consumer performs ~10 EXISTS checks before giving up.
    /// </para>
    /// </remarks>
    public TimeSpan MaxWaitForStreamCreation { get; set; } = TimeSpan.FromSeconds(5);

    /// <summary>
    /// How long TailAsync waits with no new entries before assuming the producer is dead.
    /// Default: 120 seconds.
    /// </summary>
    /// <remarks>
    /// <para>
    /// <strong>Key tuning parameter for reasoning models.</strong> Models with extended thinking
    /// (o1, o3, Claude with "extended thinking") can legitimately pause 60–120+ seconds between
    /// output tokens while processing complex queries. If this timeout fires during a legitimate
    /// thinking pause, the consumer terminates with "producer_timeout" even though the response
    /// is still being generated.
    /// </para>
    /// <para>
    /// Guidance: Set to at least 2× your model's maximum expected thinking time.
    /// For standard chat models (GPT-4o, Claude Sonnet): 30–60s is sufficient.
    /// For reasoning models (o1, o3, Claude with extended thinking): 120–300s recommended.
    /// </para>
    /// </remarks>
    public TimeSpan InactivityTimeout { get; set; } = TimeSpan.FromSeconds(120);

    /// <summary>
    /// Maximum concurrent background producer tasks.
    /// When exceeded, new streams fall back to non-buffered pass-through.
    /// Default: 100.
    /// </summary>
    public int MaxConcurrentProducers { get; set; } = 100;

    /// <summary>
    /// Maximum active (non-expired) streams per session.
    /// When exceeded, new streams fall back to non-buffered pass-through.
    /// Default: 5.
    /// </summary>
    public int MaxActiveStreamsPerSession { get; set; } = 5;

    /// <summary>
    /// Hard timeout for any single producer task.
    /// Prevents runaway tasks from infinitely-streaming LLMs.
    /// Default: 30 minutes.
    /// </summary>
    public TimeSpan MaxProducerLifetime { get; set; } = TimeSpan.FromMinutes(30);

    /// <summary>
    /// Grace period during host shutdown to allow active producers to write sentinels.
    /// Default: 5 seconds.
    /// </summary>
    public TimeSpan ShutdownGracePeriod { get; set; } = TimeSpan.FromSeconds(5);

    /// <summary>
    /// HMAC-SHA256 signing keys for continuation tokens.
    /// </summary>
    /// <remarks>
    /// <para>
    /// <strong>Required</strong>. At least one key must be provided. Each key must be minimum 32 bytes.
    /// </para>
    /// <para>
    /// <strong>Storage</strong>: Keys MUST come from a secrets manager (Azure Key Vault, AWS Secrets Manager,
    /// HashiCorp Vault, etc.) in production. Never store in plaintext configuration files.
    /// </para>
    /// <para>
    /// <strong>Rotation</strong>: The first key in the list is the "current" key used for signing new tokens.
    /// All keys in the list are tried for validation (in order). This enables zero-downtime rotation:
    /// add the new key at index 0, leave the old key at index 1 during the rotation window
    /// (should be at least <see cref="StreamRetention"/> to cover in-flight tokens), then remove the old key.
    /// </para>
    /// </remarks>
    public IReadOnlyList<TokenSigningKeyEntry> TokenSigningKeys { get; set; } = default!;

    /// <summary>
    /// How long a continuation token remains valid after issuance.
    /// Default: 2 hours (matches <see cref="MaxStreamLifetime"/>).
    /// </summary>
    /// <remarks>
    /// <para>
    /// <strong>Security-vs-UX tradeoff.</strong> This controls how long a disconnected client
    /// can reconnect and resume a stream. The token is the authorization grant for reading
    /// stream data — once expired, the client must re-invoke the agent (generating a new response).
    /// </para>
    /// <para>
    /// Setting this shorter than <see cref="MaxStreamLifetime"/> means the stream data may still
    /// exist in Valkey but the client can no longer access it (token expired). This limits the
    /// replay window if a token is leaked, but also limits reconnection time for mobile/unstable clients.
    /// </para>
    /// <para>
    /// Setting this to <see cref="MaxStreamLifetime"/> (the default) maximizes the reconnection window —
    /// the token remains valid as long as the data exists. Since the HMAC only grants read access
    /// to a stream that self-destructs at expiry anyway, the additional replay risk is minimal.
    /// </para>
    /// <para>
    /// For high-security scenarios (e.g., medical/legal PII), consider setting a shorter lifetime
    /// (e.g., 10–30 minutes) and documenting to clients that they must reconnect within that window.
    /// </para>
    /// </remarks>
    public TimeSpan TokenLifetime { get; set; } = TimeSpan.FromHours(2);
}

/// <summary>
/// A signing key entry with a key identifier for rotation support.
/// </summary>
public sealed class TokenSigningKeyEntry
{
    /// <summary>
    /// Key identifier (kid) — included in the token envelope so the validator knows
    /// which key to use for verification. Use a short stable identifier (e.g., "2026-07-01",
    /// a Key Vault version ID, or a hash of the key material).
    /// </summary>
    public required string KeyId { get; init; }

    /// <summary>
    /// The HMAC-SHA256 key material. Minimum 32 bytes.
    /// </summary>
    public required byte[] KeyMaterial { get; init; }
}
```

### ValkeyStreamBuffer (Implementation Detail)

The buffer provides the raw storage operations. It is public (users may want to use it directly for advanced scenarios) but the primary API is the middleware above.

```csharp
namespace Microsoft.Agents.AI.Valkey;

public sealed class ValkeyStreamBuffer
{
    public ValkeyStreamBuffer(
        IBaseClient client,
        ValkeyStreamBufferOptions? options = null,
        ILoggerFactory? loggerFactory = null);

    /// <summary>Appends a chunk. Returns the Valkey Stream entry ID.</summary>
    public Task<string> AppendAsync(string streamId, AgentResponseUpdate update, CancellationToken ct = default);

    /// <summary>Reads entries after a given ID (exclusive). Point-in-time replay.</summary>
    public IAsyncEnumerable<(string EntryId, AgentResponseUpdate Update)> ReadAsync(string streamId, string afterEntryId = "0-0", CancellationToken ct = default);

    /// <summary>Tails the stream via non-blocking polling until a terminal condition.</summary>
    /// <remarks>
    /// Terminates when any of: done sentinel, error sentinel, CancellationToken,
    /// or InactivityTimeout (default: 120s with no new entries).
    /// Uses non-blocking XREAD (not XREAD BLOCK) to avoid holding a connection
    /// idle during block waits in the Valkey.Glide client.
    /// </remarks>
    public IAsyncEnumerable<(string EntryId, AgentResponseUpdate Update)> TailAsync(string streamId, string afterEntryId, CancellationToken ct = default);

    /// <summary>Returns stream length.</summary>
    public Task<long> GetEntryCountAsync(string streamId, CancellationToken ct = default);

    /// <summary>Deletes the stream.</summary>
    public Task<bool> DeleteStreamAsync(string streamId, CancellationToken ct = default);
}
```

> **Note on client type**: The constructor accepts `IBaseClient` from `Valkey.Glide` — this is the base interface implemented by both `GlideClient` (standalone Valkey) and `GlideClusterClient` (Valkey Cluster). Both provide the same stream commands (`StreamAddAsync`, `StreamReadAsync`, `StreamRangeAsync`, `ExistsAsync`, `ExpireAsync`) so the buffer works transparently with either topology. GLIDE uses a single multiplexed connection per Valkey node — multiple concurrent operations are pipelined over this connection via the Rust core's async runtime. There is no separate connection multiplexer concept; the `IBaseClient` instance manages the multiplexed connection internally.

### ValkeyStreamBufferOptions

```csharp
namespace Microsoft.Agents.AI.Valkey;

public sealed class ValkeyStreamBufferOptions
{
    public string KeyPrefix { get; set; } = "agent_stream";
    public int? MaxLength { get; set; }
    public JsonSerializerOptions? JsonSerializerOptions { get; set; }
}
```

## Continuation Token Design

The middleware introduces a `ValkeyStreamContinuationToken`:

```csharp
internal sealed class ValkeyStreamContinuationToken : ResponseContinuationToken
{
    /// <summary>The Valkey Stream key (identifies which stream to read).</summary>
    internal string StreamId { get; }

    /// <summary>The last entry ID the client received.</summary>
    internal string LastEntryId { get; }

    /// <summary>Token creation timestamp (UTC epoch seconds).</summary>
    internal long IssuedAt { get; }

    /// <summary>Token expiry timestamp (UTC epoch seconds).</summary>
    internal long ExpiresAt { get; }

    /// <summary>Key identifier — identifies which signing key was used.</summary>
    internal string KeyId { get; }

    /// <summary>HMAC-SHA256 signature over (StreamId, LastEntryId, IssuedAt, ExpiresAt, KeyId).</summary>
    internal byte[] Signature { get; }
}
```

### Token Security

**HMAC Signing**: Tokens are signed with HMAC-SHA256 using a server-side secret key. The signature covers `StreamId`, `LastEntryId`, `IssuedAt`, `ExpiresAt`, and `KeyId` — preventing modification of any field without detection. The signing keys are provided via `ResumableStreamingOptions.TokenSigningKeys` (required, at least one entry, each with a `KeyId` and `KeyMaterial` of minimum 32 bytes). In DI scenarios these come from configuration/key vault.

**Key Rotation**: The token includes a `kid` (key identifier) field so the validator knows which key to use during rotation without trial-and-error. Rotation procedure:
1. Generate a new key in your secrets manager with a new `KeyId`
2. Add it at index 0 of `TokenSigningKeys` (becomes the signing key for new tokens)
3. Keep the old key at index 1 (still validates existing in-flight tokens)
4. After the rotation window (≥ `StreamRetention` — i.e., 10+ minutes to cover all in-flight tokens), remove the old key

During the dual-key window, the validator uses `kid` to look up the correct key directly. If `kid` doesn't match any configured key, validation fails immediately (token was signed with an expired/removed key).

**Expiry**: Each token carries an `ExpiresAt` timestamp set to `IssuedAt + TokenLifetime` (default: 2 hours, matching `MaxStreamLifetime`). On resume, the middleware validates:
1. `kid` maps to a known key in `TokenSigningKeys` (reject tokens signed with removed keys)
2. Signature is valid against the identified key (reject forged/modified tokens)
3. `ExpiresAt > now` (reject expired tokens)
4. `StreamId` matches the current session's expected prefix (reject cross-user access)

**Token lifetime vs stream lifetime**: By default, `TokenLifetime` equals `MaxStreamLifetime` (2 hours). This means the token remains valid as long as the stream data could possibly exist in Valkey — maximizing the reconnection window for mobile/unstable clients. Since the HMAC only grants read access to a stream that self-destructs at expiry anyway, the additional security exposure from a longer-lived token is minimal. For environments requiring a tighter replay window (PII, regulated data), set `TokenLifetime` shorter than `MaxStreamLifetime` and accept that some clients will receive "token expired" errors even though the data still exists.

**responseGuid Entropy**: The `responseGuid` portion of `streamId` (`{agentId}:{sessionId}:{responseGuid}`) MUST be generated from `RandomNumberGenerator.GetBytes(16)` (128 bits of CSPRNG entropy). It must NOT be time-based, sequential, or derived from predictable inputs. This prevents stream ID enumeration.

**Token format on wire**: `ToBytes()` produces a JSON envelope:
```json
{
  "type": "valkeyStreamContinuationToken",
  "streamId": "...",
  "lastEntryId": "1720886400000-3",
  "iat": 1720886400,
  "exp": 1720887000,
  "kid": "2026-07-01",
  "sig": "<base64url HMAC-SHA256>"
}
```

Clients cannot read or modify token internals in a way that produces a valid signature without knowing the server-side key. The `kid` field allows the server to look up the correct key during validation without trying all configured keys.

### Token Flow

```
Initial request:
  options.ContinuationToken = null
  → middleware starts inner agent, buffers to Valkey, stamps each update with token

Resume request:
  options.ContinuationToken = ValkeyStreamContinuationToken { StreamId, LastEntryId }
  → middleware skips inner agent invocation, reads/tails from buffer after LastEntryId
```

## Usage Examples

### Basic Integration

```csharp
// Setup — using Valkey.Glide client
using Valkey.Glide;

var config = new GlideClientConfiguration([new NodeAddress("localhost", 6379)]);
await using var client = await GlideClient.CreateClient(config);
var streamBuffer = new ValkeyStreamBuffer(client);

// Build agent with resumable streaming middleware
AIAgent agent = chatClient
    .AsAIAgent(model: "gpt-4o", instructions: "You are helpful.")
    .AsBuilder()
    .Use(inner => new ResumableStreamingAgent(inner, streamBuffer))
    .Build();

// Stream — every update now carries a ContinuationToken
AgentSession session = await agent.CreateSessionAsync();
ResponseContinuationToken? lastToken = null;

await foreach (var update in agent.RunStreamingAsync(messages, session))
{
    Console.Write(update.Text);
    lastToken = update.ContinuationToken;
}
```

### Resume After Disconnect

```csharp
// Client reconnects with saved token
var options = new AgentRunOptions { ContinuationToken = lastToken };

await foreach (var update in agent.RunStreamingAsync(session, options))
{
    Console.Write(update.Text);  // Only chunks after the disconnect
    lastToken = update.ContinuationToken;
}
```

### DI Registration (ASP.NET / Hosted Service)

```csharp
// Valkey.Glide uses a single multiplexed connection per node — no IConnectionMultiplexer needed.
// Register the GlideClient as a singleton (it's thread-safe and pools connections internally).
services.AddSingleton<IBaseClient>(sp =>
{
    var config = new GlideClientConfiguration([new NodeAddress("localhost", 6379)]);
    return GlideClient.CreateClient(config).GetAwaiter().GetResult();
});
services.AddSingleton<ValkeyStreamBuffer>();

// Register a factory — agents hold mutable session state and should not be singletons.
services.AddTransient<AIAgent>(sp =>
{
    var buffer = sp.GetRequiredService<ValkeyStreamBuffer>();
    return chatClient.AsAIAgent(...)
        .AsBuilder()
        .Use(inner => new ResumableStreamingAgent(inner, buffer))
        .Build();
});
```

> **Note**: `ValkeyStreamBuffer` and `IBaseClient` (GlideClient/GlideClusterClient) are stateless/thread-safe and safe as singletons. GLIDE uses a single multiplexed connection per Valkey node with pipelining — you do not configure pool size or connection strings the same way as StackExchange.Redis. The `AIAgent` itself is registered as transient (or scoped) because agent instances carry mutable per-invocation state (sessions, context). Each request should get its own agent instance built from the shared buffer.

For **Valkey Cluster** deployments, use `GlideClusterClient` instead:

```csharp
services.AddSingleton<IBaseClient>(sp =>
{
    var config = new GlideClusterClientConfiguration([
        new NodeAddress("node1", 6379),
        new NodeAddress("node2", 6379),
        new NodeAddress("node3", 6379)
    ]);
    return GlideClusterClient.CreateClient(config).GetAwaiter().GetResult();
});
```

## Data Model

### Stream Entry

Each entry contains one field:

| Field | Value |
|-------|-------|
| `content` | JSON-serialized `AgentResponseUpdate` |

A sentinel entry marks stream completion:

| Field | Value |
|-------|-------|
| `done` | `"true"` |

The sentinel allows the `TailAsync` reader to know when to stop polling.

### Stream Key

```
{keyPrefix}:{streamId}
```

The `streamId` is generated by the middleware as `{agentId}:{sessionId}:{responseGuid}` to ensure uniqueness per streaming invocation.

### Valkey Commands

| Operation | Command | Use |
|-----------|---------|-----|
| Write chunk | `XADD key MAXLEN ~ N * content {json}` | Producer |
| Write done | `XADD key * done true` | Producer |
| Replay (resume, complete stream) | `XRANGE key ({lastId} +` | Consumer |
| Tail (resume, in-progress stream) | `XREAD COUNT 100 STREAMS key {lastId}` (non-blocking, polled) | Consumer |
| Count | `XLEN key` | Diagnostics |
| Expire | `EXPIRE key {seconds}` | Cleanup |
| Delete | `DEL key` | Cleanup |

### Read Strategy by Stage

The consumer uses different read strategies depending on the stream's state:

| Stage | Strategy | Command | Rationale |
|-------|----------|---------|-----------|
| Resume (stream complete) | Point-in-time replay | `XRANGE key ({lastId} +` | All entries buffered; single request returns everything |
| Resume (stream in progress) | Replay then poll | `XRANGE` then `XREAD COUNT 100 STREAMS key {lastId}` (non-blocking poll) | Catch up via XRANGE, then poll for new entries |
| Initial stream (client connected) | Poll from buffer | `XREAD COUNT 100 STREAMS key {lastId}` (non-blocking poll at `PollInterval`) | Producer writes concurrently; consumer polls buffer |

**Why non-blocking polling, not XREAD BLOCK**: `XREAD BLOCK` holds a connection idle for the entire block duration. With Valkey.Glide (the client used by this package), this occupies the single multiplexed connection to that node for the block timeout — preventing other pipelined operations from completing until the block returns or times out. Rather than requiring a dedicated client instance solely for blocking reads, `TailAsync` uses non-blocking `XREAD` (or `XRANGE`) with `PollInterval` (default 100ms) between iterations. This keeps the multiplexed connection fully available for concurrent operations and simplifies resource management.

**Two-phase stream creation detection**: The Valkey.Glide C# client's `StreamReadAsync` returns an empty `StreamEntry[]` for **both** "stream key doesn't exist" and "stream exists but has no entries after the given ID." The consumer cannot distinguish these cases from `XREAD` alone.

To handle this, the consumer uses a **two-phase approach** during the stream creation wait:

1. **Phase 1 — Wait for stream creation** (`MaxWaitForStreamCreation`, default: 5s): On each poll iteration, the consumer calls `ExistsAsync(key)` to check whether the stream key has been created. If `EXISTS` returns `false`, the stream hasn't been created yet — keep waiting. If `EXISTS` returns `true`, transition to Phase 2 immediately.

2. **Phase 2 — Normal polling**: Once the stream exists, the consumer switches to standard `XREAD` polling. An empty result now unambiguously means "no new entries yet" (not "stream doesn't exist"). The `InactivityTimeout` governs how long the consumer waits for the first/next entry.

If the stream still doesn't exist after `MaxWaitForStreamCreation`, the consumer yields an `AgentStreamingException("stream_not_created")` — the producer likely failed before writing its first entry.

**Why not rely on XREAD alone?** Without the `EXISTS` check, the consumer cannot tell whether:
- (a) The producer hasn't started yet (keep waiting), or
- (b) The producer started, the stream exists, but no entries have been written after the given ID (start normal inactivity timeout)

This ambiguity could cause premature timeout (entering inactivity timeout while still in the creation-wait phase) or missed creation-wait (never entering the wait path when the stream genuinely hasn't been created).

| Phase | Command | Empty result means | Action |
|-------|---------|-------------------|--------|
| 1 (creation wait) | `EXISTS key` | Stream not created yet | Retry until `MaxWaitForStreamCreation` |
| 1 (creation wait) | `EXISTS key` → true | Stream exists | Transition to Phase 2 |
| 2 (normal polling) | `XREAD` | No new entries after ID | Continue polling (governed by `InactivityTimeout`) |

**Termination signals**: The consumer stops polling when it encounters:
1. A `done` sentinel entry → stream completed successfully
2. An `error` sentinel entry → producer failed (throw to consumer)
3. Inactivity timeout exceeded → producer presumed dead (see TailAsync section)
4. CancellationToken triggered → client disconnected again

### TailAsync Termination Guarantees

`TailAsync` must **always** terminate — it cannot hang indefinitely waiting for a dead producer. The termination contract:

| Condition | Behavior | Yielded to consumer |
|-----------|----------|---------------------|
| `done` sentinel entry | Stop iteration normally | Nothing (sentinel is metadata, not content) |
| `error` sentinel entry | Stop iteration, throw | `AgentStreamingException` with error code |
| `CancellationToken` cancelled | Stop iteration, throw | `OperationCanceledException` |
| Inactivity timeout | Stop iteration, throw | `AgentStreamingException("producer_timeout")` |
| Stream key deleted/expired | Stop iteration, throw | `AgentStreamingException("stream_not_found")` |

**Inactivity Timeout**: If no new entry arrives within `InactivityTimeout` (default: 120s), `TailAsync` terminates. This covers the case where the producer crashed without writing a sentinel (OOM kill, pod eviction, network partition). The timeout is deliberately longer than typical LLM inter-token latency (50–200ms) and also accommodates reasoning models that may pause for extended thinking (60–120s between tokens). The default of 120s is chosen to avoid false-triggering on reasoning models while still providing a bounded wait for truly dead producers.

**Task registry short-circuit on resume**: When a client reconnects with a continuation token, the middleware performs a task registry check *before* entering the `TailAsync` polling loop:

1. Validate the token (kid, signature, expiry, session prefix)
2. Look up `streamId` in the `ConcurrentDictionary<string, ProducerTaskEntry>` registry
3. If the producer task has **terminated** (task completed/faulted/cancelled) AND the stream has no terminal sentinel (checked via a single `XRANGE key - + COUNT 1 REV` looking for done/error in the last entry):
   → Return `AgentStreamingException("stream_incomplete")` **immediately** without entering the polling loop

This reduces error response time from 120s (full `InactivityTimeout` wait) to near-instant for the specific scenario where a client disconnects during a Valkey outage, Valkey recovers, the client reconnects, but the error sentinel write had failed. The registry lookup is a `ConcurrentDictionary` lookup (O(1), no I/O) and the sentinel check is a single Valkey command, making this path negligible in cost.

If the producer task is **still running** in the registry, the consumer enters the normal `TailAsync` polling loop — the producer is actively writing entries and inactivity timeout governs as usual.

**No heartbeat entries (design choice)**: We considered having the producer write periodic heartbeat entries so the consumer can distinguish "alive but slow" from "dead." This was rejected for Phase 1 because:
- It adds stream entries that carry no content value (wastes space under MaxLength caps)
- It complicates the consumer logic (must filter heartbeats from real content)
- The inactivity timeout (120s default) is generous enough to accommodate reasoning models without false-triggering
- If a model genuinely pauses for >120s between tokens, the timeout can be tuned via options

**Phase 2 reconsideration**: If slow-model support becomes a priority and tuning alone is insufficient, heartbeats (producer writes keepalives during thinking pauses) would solve this definitively. The producer would write a `heartbeat` entry (filtered by the consumer) every N seconds to prove liveness. This allows the `InactivityTimeout` to be set much lower (e.g., 10s) while still supporting arbitrarily long thinking pauses.

**Valkey.Glide Connection Consideration**: `TailAsync` uses non-blocking `XREAD` (no `BLOCK` parameter) with `await Task.Delay(PollInterval)` between iterations. This avoids occupying the single multiplexed connection with a blocking wait — all other pipelined operations on the same `IBaseClient` continue to execute normally. The trade-off is slightly higher latency (up to `PollInterval` delay between a chunk being written and being read) which is acceptable for the resume use case.

## Edge Cases and Failure Modes

### Client disconnects while stream is in progress
The background producer task continues writing to the buffer. On reconnect, the consumer tails from the last-seen entry ID, receiving both buffered entries and new entries as they arrive.

### Client never reconnects
The stream expires after `StreamRetention` (default 10 min) via EXPIRE, or is bounded by MaxLength.

### Orphaned streams (producer crash without sentinel)

If the producer process is killed (SIGKILL, OOM, pod eviction) before writing a `done` or `error` sentinel, the stream becomes orphaned. Mitigations layered in order of defense:

1. **EXPIRE as safety net**: The producer sets `EXPIRE key {MaxStreamLifetime}` (default: 2 hours) on stream creation. This is a generous hard upper bound — it exists solely to prevent permanent orphans when all other cleanup mechanisms fail. It is NOT the primary cleanup mechanism.
2. **Producer refreshes EXPIRE**: The producer refreshes `EXPIRE key {MaxStreamLifetime}` every N chunks (default: every 50 entries). This means an actively-writing producer will never hit the ceiling. Only a dead producer (no more writes, no refresh) eventually expires.
3. **Sentinel-triggered retention**: When the producer writes the `done` or `error` sentinel, it sets `EXPIRE key {StreamRetention}` (default: 10 min). This is the primary cleanup — the retention countdown begins only after the stream is complete.
4. **Consumer inactivity timeout**: `TailAsync` terminates after `InactivityTimeout` (default: 120s) with no new entries. The consumer receives a timeout error rather than hanging forever.
5. **Graceful shutdown sentinels**: On `ApplicationStopping`, active producers write error sentinels before the process exits (see Background Task Lifecycle).

This layering ensures:
- A slow but active stream (e.g., 25 minutes of LLM output) is never prematurely expired — the producer keeps refreshing
- Once complete, the client has the full `StreamRetention` window (10 min) to reconnect and replay
- A truly orphaned stream (dead producer, no sentinel) is cleaned up after `MaxStreamLifetime` (2 hours)

### EXPIRE semantics clarification

The stream's EXPIRE value changes through its lifecycle:

```
Timeline:
  t=0      XADD first chunk + EXPIRE 7200 (MaxStreamLifetime = 2 hours, safety net)
  t=5s     XADD chunk 50 → EXPIRE 7200 (refresh)
  t=10s    XADD chunk 100 → EXPIRE 7200 (refresh)
  ...
  t=90s    XADD done sentinel → EXPIRE 600 (StreamRetention = 10 min from NOW)
  t=690s   Key expires (10 min after completion)
```

If the producer dies without writing a sentinel:
```
  t=0      XADD first chunk + EXPIRE 7200
  t=5s     XADD chunk 50 → EXPIRE 7200 (refresh)
  t=8s     *** Producer killed ***
  t=7208s  Key expires (2 hours after last refresh — safety net)
```

The consumer doesn't wait that long — `TailAsync` times out after 120s of inactivity and reports an error to the client.

### Valkey unavailability mid-stream

If the middleware's `XADD` fails during streaming (network partition, Valkey restart, connection failure):

**Chosen approach — degrade gracefully (Option A)**:
- The producer catches the Valkey exception, logs at `Warning` level
- The current client continues receiving updates directly from the inner agent (normal `IAsyncEnumerable` pass-through)
- The stream is marked as non-resumable in the task registry
- The continuation token on subsequent updates is set to `null` — signaling to the client that resumability is temporarily unavailable
- If Valkey recovers mid-stream, the producer does NOT resume writing (partial streams are confusing) — the stream remains non-resumable for this invocation

This ensures the user always gets their response, even if they lose resumability for that particular stream.

**Token semantics during degradation**:
- Before Valkey failure: updates carry `ContinuationToken` values (entries 1–N are buffered)
- After Valkey failure: all subsequent updates have `ContinuationToken = null`
- The **first** null token signals the transition; all subsequent tokens remain null
- A client can distinguish "never was resumable" (all tokens null from the start) from "was resumable but lost it mid-stream" (tokens were non-null, then became null) by tracking this transition

**Partial stream and resume attempts**:

If entries 1–50 were successfully buffered before Valkey fails, and entries 51+ are delivered via pass-through, the partial stream remains in Valkey until it expires. If a client attempts to resume from entry 45:
- Entries 46–50 would be replayed from the buffer
- The stream has no `done` sentinel (producer stopped writing)
- `TailAsync` would wait up to `InactivityTimeout` (120s) for new entries that will never arrive, then throw `AgentStreamingException("producer_timeout")`

This is a poor experience. To address it, the producer writes an **error sentinel** to the partial stream when entering degraded mode:

```
XADD key * error stream_incomplete
```

This sentinel is written as a **best-effort** operation — it may succeed if Valkey is partially available (e.g., the failure was transient) or fail silently if Valkey is still unreachable. The result:

| Sentinel written? | Resume attempt behavior |
|-------------------|------------------------|
| Yes (`stream_incomplete`) | Consumer reads entries 46–50, encounters sentinel, throws `AgentStreamingException("stream_incomplete")`. Client knows not to retry. |
| No (Valkey unreachable) | Consumer reads entries 46–50, waits for `InactivityTimeout`, throws `AgentStreamingException("producer_timeout")`. Same terminal outcome, just slower. |

**Stream expiry for partial streams**: The existing partial stream will EXPIRE naturally at `MaxStreamLifetime` (2 hours from last EXPIRE refresh). It is non-resumable from the point of degradation — documenting this explicitly in the error sentinel allows clients to make immediate retry decisions rather than waiting for the inactivity timeout.

**Error codes for degradation**:

| Error Code | Meaning |
|-----------|---------|
| `stream_incomplete` | Producer lost Valkey connectivity mid-stream; entries after this point were not buffered |

This is added to the existing error code table in the Security Considerations section.

### Agent fails mid-stream (exception)
The middleware writes an error sentinel to the stream:
```
XADD key * error {error_code}
```
The error entry contains a sanitized error code (e.g., `"agent_error"`, `"timeout"`, `"cancelled"`) — not the raw exception message (see Security section). The full exception is logged server-side at `Error` level with the `streamId` for correlation.

On resume, the consumer reads this entry and throws an `AgentStreamingException` with the error code.

### Duplicate delivery
If the client disconnects exactly at the moment of receiving an entry, on resume it may receive the next entry (since its last-seen token was for the prior entry). This is **at-least-once delivery** — clients should be idempotent or track the last processed entry ID. In practice, for streaming text to a UI, this means a word might appear twice at the boundary — likely acceptable for most use cases, though consumers with strict exactly-once requirements would need deduplication logic.

### Multiple concurrent streams for same session
Each streaming invocation gets a unique `streamId` (contains a GUID), so concurrent streams do not conflict.

## Server Requirements

- Any Valkey server or Redis OSS 5.0+ (Streams introduced in Redis 5.0)
- No modules required — core Stream commands only
- Cluster compatible — each stream key routes to its own slot independently. Since all operations on a given stream (`XADD`, `XREAD`, `XRANGE`, `EXPIRE`, `EXISTS`) are single-key commands, no cross-slot issues arise. Hash tags (e.g., `{resume}:agent:session:guid`) are **NOT** needed and **NOT** recommended — they would concentrate all streams on a single shard, creating a hotspot
- For durability: enable AOF with `appendfsync everysec` or `always`
- **maxmemory-policy**: Use `noeviction` — stream entries must not be silently evicted mid-stream. If memory is exhausted, `XADD` returns an OOM error which the producer handles via graceful degradation (see Edge Cases).

### Memory Sizing Guidance

Estimate required memory as:

```
memory ≈ avg_chunk_json_size × chunks_per_response × concurrent_active_streams × retention_multiplier
```

Example: 500 bytes/chunk × 200 chunks × 50 concurrent streams × 1.5 (overhead) ≈ **7.5 MB**

In practice, agent responses are bounded by model output limits (4K–16K tokens), so individual streams are small. The primary concern is concurrent stream count during traffic spikes.

## Resource Exhaustion and Rate Limiting

Each agent invocation creates a new Valkey stream. Without limits, a malicious or compromised client rapidly initiating runs can exhaust Valkey memory or starve other operations.

### Per-Session Stream Caps

`ResumableStreamingOptions.MaxActiveStreamsPerSession` (default: 5) limits the number of concurrent non-expired streams associated with a single session. When the cap is reached:
- New streaming invocations fall back to non-buffered pass-through (stream works, just not resumable)
- Log at `Warning` level with the session ID

### Rate Limiting on Stream Creation

`ResumableStreamingOptions.StreamCreationRateLimit` provides token-bucket rate limiting per authenticated principal:
- Default: 10 streams per minute per session
- Exceeding the rate returns a non-resumable stream (same graceful degradation as above)
- This prevents rapid connect/disconnect patterns from accumulating unbounded streams during the retention window

### Valkey OOM Behavior

When Valkey reports `OOM command not allowed` (with `noeviction` policy):
- The producer handles this identically to Valkey unavailability — graceful degradation to non-resumable streaming
- Log at `Error` level with available Valkey memory diagnostics if accessible
- The `MaxLength` option (approximate XTRIM) provides per-stream size bounds but does not cap total stream count

## Implementation Plan

### Relationship to PR #5576

[PR #5576](https://github.com/microsoft/agent-framework/pull/5576) currently contains the standalone `ValkeyStreamBuffer` (append/read/count/delete) plus a sample and unit tests. This design doc proposes **enhancing that same PR** to deliver the full integration story. The PR will be updated in place — not replaced by a follow-up.

What PR #5576 already has (being kept as-is):
- `ValkeyStreamBuffer` with `AppendAsync`, `ReadAsync`, `GetEntryCountAsync`, `DeleteStreamAsync`
- `ValkeyStreamBufferOptions` (KeyPrefix, MaxLength, JsonSerializerOptions)
- 64 unit tests with mocked `IBaseClient`
- Solution/project registration

What will be added to PR #5576:
- `TailAsync` method on `ValkeyStreamBuffer` (XREAD-based polling for live tailing of in-progress streams)
- Done sentinel and error entry support in the buffer
- `ResumableStreamingAgent` (`DelegatingAIAgent` middleware)
- `ValkeyStreamContinuationToken` (`ResponseContinuationToken` subclass)
- Updated sample demonstrating the middleware-based usage (replacing the raw-buffer-only sample)
- Additional unit tests for middleware logic

### Phased delivery

**Phase 1 — this PR**: Buffer enhancements + middleware + continuation token integration. Delivers the complete resumable streaming feature as described in this doc.

**Phase 2 — future work** (separate PRs):
- Consumer group support for multi-instance scenarios
- Metrics/OpenTelemetry integration (stream lag, buffer size)
- TTL-based auto-expiry option
- Python parity (`agent-framework-valkey` package)
- Optional pass-through when service already provides continuation tokens

## Alternatives Considered

### ChatClientAgentOptions.StreamBuffer (Issue #5544's proposed API)

[Issue #5544](https://github.com/microsoft/agent-framework/issues/5544) proposes adding a `StreamBuffer` property directly to `ChatClientAgentOptions`, so that wiring looks like:

```csharp
AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    StreamBuffer = streamBuffer
});
```

This is a deliberate departure from that proposed API surface. We chose the middleware/decorator approach instead because:
- A property on `ChatClientAgentOptions` couples a specific storage technology to the core agent type — every `ChatClientAgent` would carry awareness of stream buffering even when not using it
- It only works for `ChatClientAgent` implementations, not other agent types (custom agents, workflow agents, etc.)
- The `DelegatingAIAgent` + `AIAgentBuilder.Use()` pattern is the established AF convention for composable cross-cutting concerns (see `FunctionInvocationDelegatingAgent`, `PurviewAgent`, `ToolApprovalAgent`)
- The middleware approach allows the same `ValkeyStreamBuffer` to be reused with any agent type via `.Use()`

That said, if the maintainers prefer the `ChatClientAgentOptions` shape (e.g., for discoverability or because most users are on `ChatClientAgent`), the middleware could still exist internally while exposing the simpler options-based API as sugar on top. We're open to guidance here.

### Use IAgentResponseHandler (durable task pattern)

Implement as an `IAgentResponseHandler`. Rejected because:
- Tied to the durable entity execution model
- Requires the `DurableTask` package dependency
- The middleware pattern works without durable infrastructure

### Generic buffer interface (IStreamBuffer)

Abstract the buffer behind an interface so other backends (Cosmos, Kafka, etc.) could be used. Deferred because:
- Premature abstraction — Valkey Streams are a natural fit and no one has requested other backends
- Can be extracted later if demand arises without breaking changes

## Testing Strategy

### Testability Design

`ValkeyStreamBuffer` remains `sealed` (no public interface to maintain), but the middleware depends on it through an **internal interface** for test seams:

```csharp
internal interface IStreamBufferOperations
{
    Task<string> AppendAsync(string streamId, AgentResponseUpdate update, CancellationToken ct);
    IAsyncEnumerable<(string EntryId, AgentResponseUpdate Update)> ReadAsync(string streamId, string afterEntryId, CancellationToken ct);
    IAsyncEnumerable<(string EntryId, AgentResponseUpdate Update)> TailAsync(string streamId, string afterEntryId, CancellationToken ct);
    Task<long> GetEntryCountAsync(string streamId, CancellationToken ct);
    Task<bool> DeleteStreamAsync(string streamId, CancellationToken ct);
}
```

`ValkeyStreamBuffer` implements this interface explicitly (internal). The middleware's constructor accepts `IStreamBufferOperations` internally (via `[InternalsVisibleTo]` the test project), allowing unit tests to mock the buffer without Castle proxy tricks on a sealed class. The public constructor still takes `ValkeyStreamBuffer` directly — the interface is not part of the public API surface.

This is standard .NET practice for internal test seams without expanding public API weight.

### Test Matrix

| Level | What | How |
|-------|------|-----|
| Unit (buffer) | XADD/XRANGE/XLEN/DEL delegation | Mocked `IBaseClient` |
| Unit (middleware) | Token stamping, resume detection, producer/consumer flow | Mocked `IStreamBufferOperations` + fake inner agent |
| Unit (token) | HMAC signing, validation, expiry, forgery rejection | Direct token construction |
| Unit (lifecycle) | Task registry, cancellation, backpressure limits | Mocked buffer + controlled task completion |
| Integration (sample) | Full append → disconnect → resume cycle | Live Valkey, simulated chunks |
| Integration (live LLM) | Real agent stream → disconnect → resume | Live Valkey + Azure OpenAI |

## Security Considerations

### Data in transit
Agent response chunks may contain PII. Valkey must be configured with TLS for all connections. The `GlideClientConfiguration` should be configured with TLS enabled (`UseTls = true`).

### Data at rest
Stream entries are stored as plaintext JSON in Valkey. Valkey persistence (AOF/RDB) writes this to disk unencrypted. An attacker with filesystem access to the Valkey host can read all buffered responses.

**Deployment guidance** (add to Server Requirements):
- **Minimum**: Enable disk encryption (LUKS/dm-crypt, EBS encryption, Azure Disk Encryption) for the Valkey data directory
- **Recommended for regulated environments**: Application-side envelope encryption — encrypt the `content` field with a per-stream DEK (data encryption key) before `XADD`, decrypt on `XRANGE`/`XREAD`. The DEK is stored in the token or in a separate key vault, not in Valkey itself.
- Phase 1 does **not** implement application-side encryption. This is documented as a known limitation in the README and can be added as an optional `IPayloadEncryptor` in Phase 2.

### Token security
See [Continuation Token Design](#continuation-token-design) — tokens are HMAC-signed and carry expiry. Cross-user access is prevented by signature validation + session prefix matching.

### Error message information leakage (CWE-209)
Error sentinels written to the stream must NOT contain raw exception messages — these may leak internal paths, connection strings, Valkey hostnames, or stack traces. Error entries use a fixed set of sanitized error codes:

| Error Code | Meaning |
|-----------|---------|
| `agent_error` | The inner agent threw an exception |
| `timeout` | Producer exceeded `MaxProducerLifetime` |
| `cancelled` | Producer was cancelled (graceful shutdown or explicit) |
| `shutdown` | Host process shutting down |
| `valkey_unavailable` | Valkey connection lost during production |
| `stream_incomplete` | Producer lost Valkey connectivity mid-stream; entries after this point were not buffered |
| `stream_not_created` | Stream key was never created within `MaxWaitForStreamCreation`; producer likely failed before first write |

The full exception (including message, stack trace, and inner exceptions) is logged server-side at `Error` level with the `streamId` as a correlation key. Clients receive only the error code.

### Compromised store
If Valkey is compromised, adversarial content could be injected into replayed responses. The middleware does not validate content semantics — it faithfully deserializes and returns whatever is stored. Defense-in-depth (network isolation, ACLs, TLS client certificates) is the primary mitigation.
