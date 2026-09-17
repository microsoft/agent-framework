// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using AgentHooks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>
/// Options controlling the AGENT-HOOKS-0.1 enforcement installed by
/// <see cref="AgentHooksChatClientExtensions.AsAIAgentWithAgentHooks(IChatClient, AgentHooksOptions, ChatClientAgentOptions?, IServiceProvider?)"/>.
/// </summary>
public sealed class AgentHooksOptions
{
    private readonly List<KeyValuePair<string?, IInterceptor>> _interceptors = [];

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentHooksOptions"/> class.
    /// </summary>
    /// <param name="interceptors">The agent-hooks interceptors to register. At least one interceptor is required
    /// (an emitter with zero interceptors fails closed on every emission).</param>
    /// <exception cref="ArgumentNullException"><paramref name="interceptors"/> or one of its elements is <see langword="null"/>.</exception>
    public AgentHooksOptions(params IEnumerable<IInterceptor> interceptors)
    {
        _ = Throw.IfNull(interceptors);

        // Materialized exactly once: the sequence may be single-enumeration.
        foreach (var interceptor in interceptors)
        {
            _ = this.AddInterceptor(interceptor);
        }
    }

    /// <summary>Register an interceptor, optionally with a payload-free name recorded on the records' verdict summaries.</summary>
    /// <param name="interceptor">The interceptor to register.</param>
    /// <param name="name">An optional registration name.</param>
    /// <returns>This options instance.</returns>
    public AgentHooksOptions AddInterceptor(IInterceptor interceptor, string? name = null)
    {
        _ = Throw.IfNull(interceptor);
        this._interceptors.Add(new KeyValuePair<string?, IInterceptor>(name, interceptor));
        return this;
    }

    /// <summary>Gets the registered interceptors, in registration order.</summary>
    public IReadOnlyList<KeyValuePair<string?, IInterceptor>> Interceptors => this._interceptors;

    /// <summary>Gets or sets the optional approval resolver consulted for liftable denies.</summary>
    public IApprovalResolver? Resolver { get; set; }

    /// <summary>Gets or sets whether verdicts are enforced (default) or recorded without acting.</summary>
    public EnforcementMode Mode { get; set; } = EnforcementMode.Enforce;

    /// <summary>Gets or sets the composition profile and knobs; <see langword="null"/> uses the SDK default
    /// (<c>sequential/first_deny</c>, <c>on_approval: stop</c>).</summary>
    public CompositionConfig? Composition { get; set; }

    /// <summary>Gets or sets the identity provider; <see langword="null"/> uses the SDK default
    /// (<c>jcs-sha256</c>). Use <see cref="IdentityProvider.Null"/> for identity-unbound records.</summary>
    public IdentityProvider? IdentityProvider { get; set; }

    /// <summary>Gets or sets the per-interceptor/resolver timeout; <see langword="null"/> uses the
    /// spec-recommended 5 seconds.</summary>
    public TimeSpan? Timeout { get; set; }

    /// <summary>Gets or sets an optional callback receiving every interception record.</summary>
    public Action<InterceptionRecord>? RecordSink { get; set; }
}
