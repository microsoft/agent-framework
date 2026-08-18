// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using AgentHooks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

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

    /// <summary>The logger for enforcement diagnostics (swallowed best-effort failures are tracked here).</summary>
    public ILogger Logger { get; set; } = NullLogger.Instance;
}
