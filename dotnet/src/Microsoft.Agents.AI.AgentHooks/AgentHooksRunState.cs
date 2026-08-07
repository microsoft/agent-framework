// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using AgentHooks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>
/// The configuration shared by all seams composed by one factory call.
/// </summary>
/// <remarks>
/// Reference identity of this object is the ownership token: the chat and tool seams
/// only bind to an ambient run state created by their own factory call, so nesting two
/// agent-hooks-enabled agents can never silently misroute emissions.
/// </remarks>
internal sealed class AgentHooksConfiguration
{
    public required IReadOnlyList<KeyValuePair<string?, IInterceptor>> Interceptors { get; init; }

    public IApprovalResolver? Resolver { get; init; }

    public EnforcementMode Mode { get; init; } = EnforcementMode.Enforce;

    public CompositionConfig? Composition { get; init; }

    public IdentityProvider? IdentityProvider { get; init; }

    public TimeSpan? Timeout { get; init; }

    public Action<InterceptionRecord>? RecordSink { get; init; }

    /// <summary>Host-owned session: when set, the middleware emits only the per-run points on this emitter.</summary>
    public InterceptionEmitter? Emitter { get; init; }

    /// <summary>Host-owned session: the builder matching <see cref="Emitter"/>.</summary>
    public AgentContextBuilder? Builder { get; init; }
}

/// <summary>
/// Per-run enforcement state shared by the seams via an <see cref="AsyncLocal{T}"/>.
/// </summary>
internal sealed class AgentHooksRunState
{
    private static readonly AsyncLocal<AgentHooksRunState?> s_current = new();

    public AgentHooksRunState(InterceptionEmitter emitter, AgentContextBuilder builder, bool sessionScoped, AgentHooksConfiguration configuration)
    {
        this.Emitter = emitter;
        this.Builder = builder;
        this.SessionScoped = sessionScoped;
        this.Configuration = configuration;
    }

    /// <summary>The run state covering the current async flow, if any.</summary>
    public static AgentHooksRunState? Current
    {
        get => s_current.Value;
        set => s_current.Value = value;
    }

    public InterceptionEmitter Emitter { get; }

    public AgentContextBuilder Builder { get; }

    /// <summary>Whether the session (and its startup/shutdown boundaries) is host-owned.</summary>
    public bool SessionScoped { get; }

    public AgentHooksConfiguration Configuration { get; }

    /// <summary>
    /// Set when the enforcement layer itself failed (interceptor host error at the tool
    /// seam, projection bug): the run must not egress; the agent seam rethrows this at
    /// the run boundary.
    /// </summary>
    public Exception? Halted { get; set; }

    /// <summary>
    /// Set when a run-level verdict denied content. Once set, the run's durable
    /// persistence is refused fail-closed (denied content never becomes durable, and the
    /// denied turn's request messages are not persisted either).
    /// </summary>
    public bool Denied { get; set; }

    /// <summary>The gate deferring this run's end-of-run durable writes behind the output verdict.</summary>
    public RunPersistenceGate Gate { get; } = new();

    /// <summary>
    /// The run's final (output-verdicted, post-transform) response messages, set by the
    /// agent seam before the gate is flushed. Deferred end-of-run persists substitute
    /// these for the response messages they captured, so streamed runs — whose inner
    /// agent assembled its own message list before the output verdict existed — persist
    /// the verdicted content, never the pre-transform value.
    /// </summary>
    public IList<ChatMessage>? VerdictedResponseMessages { get; set; }
}

/// <summary>
/// Collects a guarded run's durable persistence side effects so they only execute after
/// the covering verdict permits the content.
/// </summary>
/// <remarks>
/// The .NET equivalent of the Python feature's run persistence gate, radically simplified
/// by construction ownership: the gate is consulted only by the gating provider wrappers
/// that the agent-hooks factory itself installed on its own agent, so nested or sibling
/// agents (which have their own providers) always persist inline at their own run
/// boundaries, with no run-identity bookkeeping.
/// </remarks>
internal sealed class RunPersistenceGate
{
    private readonly object _lock = new();
    private List<Func<CancellationToken, ValueTask>>? _pending;

    /// <summary>Queue one deferred persistence callback.</summary>
    public void Collect(Func<CancellationToken, ValueTask> persist)
    {
        lock (this._lock)
        {
            (this._pending ??= []).Add(persist);
        }
    }

    /// <summary>Execute the deferred persistence in order (the covering verdict permitted the content).</summary>
    public async ValueTask FlushAsync(CancellationToken cancellationToken)
    {
        List<Func<CancellationToken, ValueTask>>? pending;
        lock (this._lock)
        {
            pending = this._pending;
            this._pending = null;
        }

        if (pending is not null)
        {
            foreach (var persist in pending)
            {
                await persist(cancellationToken).ConfigureAwait(false);
            }
        }
    }

    /// <summary>Discard the deferred persistence (the covering verdict denied the content).</summary>
    public void Drop()
    {
        lock (this._lock)
        {
            this._pending = null;
        }
    }
}
