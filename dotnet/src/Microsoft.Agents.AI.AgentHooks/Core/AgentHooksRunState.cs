// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using AgentHooks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks;

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
