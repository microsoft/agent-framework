// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using AgentHooks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>
/// Options controlling the AGENT-HOOKS-0.1 enforcement installed by
/// <see cref="AgentHooksChatClientExtensions.AsAIAgentWithAgentHooks(IChatClient, AgentHooksOptions, ChatClientAgentOptions?, IServiceProvider?)"/>.
/// </summary>
/// <remarks>
/// <para>
/// There are two ways to build the options. The constructor takes the interceptors and
/// the setters take the rest (the code path). <see cref="FromDeclaration"/> and its
/// path, JSON text and <see cref="JsonNode"/> variants take a host declaration document
/// (spec §7.7) instead: the document carries the mode, composition, identity provider,
/// approval references, timeouts and interceptor bindings, and the host registers in a
/// <see cref="HostRegistry"/> the binding kinds and the custom names the document may
/// reference. Options built from a declaration are sealed: the settable members throw
/// <see cref="InvalidOperationException"/>, except <see cref="RecordSink"/>, which the
/// contract leaves to the host.
/// </para>
/// <para>
/// A declaration is resolved against <see cref="AgentHooksHostSurface.Surface"/> when the
/// options are built, and every binding's kind resolver runs once then, so a document the
/// code cannot honour is refused as a <see cref="DeclarationException"/> before any agent
/// exists. Each agent run is its own agent-hooks session with its own emitter, so the kind
/// resolvers run again per run, the way the code path registers the same interceptor
/// instances on each run's emitter. Resolvers should be cheap and deterministic and share
/// state through closures.
/// </para>
/// </remarks>
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

    private AgentHooksOptions(HostDeclaration declaration, HostRegistry registry, ResolvedDeclaration resolved)
    {
        // Mode and Composition mirror the document for readers of the options: both
        // have the same type on both paths. Set them before the declaration, which
        // seals the setters. The resolver, identity provider and timeouts stay null
        // here: the document holds names and two separate timeouts, which
        // ResolvedDeclaration exposes as the core resolved them.
        this.Mode = resolved.Mode;
        this.Composition = resolved.Composition;
        this.Declaration = declaration;
        this.Registry = registry;
        this.ResolvedDeclaration = resolved;
    }

    /// <summary>
    /// Builds options from a host declaration document (spec §7.7).
    /// </summary>
    /// <param name="declaration">The document, as read by <see cref="HostDeclaration.FromPath"/>,
    /// <see cref="HostDeclaration.FromJson"/>, <see cref="HostDeclaration.FromNode"/> or the
    /// <see cref="DeclarationBuilder"/>.</param>
    /// <param name="configureRegistry">Registers, on a <see cref="HostRegistry"/> over
    /// <see cref="AgentHooksHostSurface.Surface"/>, the binding kinds the document uses
    /// (<see cref="HostRegistry.Kind"/>) and any custom identity provider, approval resolver or
    /// approval redactor it names.</param>
    /// <returns>Sealed options that build every run's emitter from the document.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="declaration"/> or <paramref name="configureRegistry"/> is <see langword="null"/>.</exception>
    /// <exception cref="DeclarationException">The document is refused: malformed, outside the surface,
    /// naming a kind or reference the registry lacks, or a binding its kind resolver rejected.</exception>
    /// <exception cref="ArgumentException">The document has no bindings (zero interceptors fail closed on every emission).</exception>
    public static AgentHooksOptions FromDeclaration(HostDeclaration declaration, Action<HostRegistry> configureRegistry)
    {
        _ = Throw.IfNull(declaration);
        _ = Throw.IfNull(configureRegistry);

        var registry = new HostRegistry(AgentHooksHostSurface.Surface);
        configureRegistry(registry);

        // Steps 2 to 11 of §7.7.6 run now: the core validates the document and resolves
        // it against the surface and the registered names, then every kind resolver
        // runs. A refusal here means no agent is ever built from this document.
        var resolved = InterceptionEmitter.FromDeclaration(declaration, registry).Declaration!;
        if (resolved.Bindings.Count == 0)
        {
            throw new ArgumentException(
                "agent-hooks enforcement requires at least one binding in the declaration (an emitter with zero " +
                "interceptors fails closed on every emission).",
                nameof(declaration));
        }

        return new AgentHooksOptions(declaration, registry, resolved);
    }

    /// <summary><see cref="HostDeclaration.FromPath"/> then <see cref="FromDeclaration"/>.</summary>
    /// <param name="path">The path of the declaration file.</param>
    /// <param name="configureRegistry">See <see cref="FromDeclaration"/>.</param>
    /// <returns>Sealed options that build every run's emitter from the document.</returns>
    public static AgentHooksOptions FromDeclarationPath(string path, Action<HostRegistry> configureRegistry) =>
        FromDeclaration(HostDeclaration.FromPath(Throw.IfNull(path)), configureRegistry);

    /// <summary><see cref="HostDeclaration.FromJson"/> then <see cref="FromDeclaration"/>.</summary>
    /// <param name="json">The declaration as JSON text.</param>
    /// <param name="configureRegistry">See <see cref="FromDeclaration"/>.</param>
    /// <returns>Sealed options that build every run's emitter from the document.</returns>
    public static AgentHooksOptions FromDeclarationJson(string json, Action<HostRegistry> configureRegistry) =>
        FromDeclaration(HostDeclaration.FromJson(Throw.IfNull(json)), configureRegistry);

    /// <summary><see cref="HostDeclaration.FromNode"/> then <see cref="FromDeclaration"/>.</summary>
    /// <param name="node">The declaration as a <see cref="JsonNode"/>.</param>
    /// <param name="configureRegistry">See <see cref="FromDeclaration"/>.</param>
    /// <returns>Sealed options that build every run's emitter from the document.</returns>
    public static AgentHooksOptions FromDeclarationNode(JsonNode? node, Action<HostRegistry> configureRegistry) =>
        FromDeclaration(HostDeclaration.FromNode(node), configureRegistry);

    /// <summary>Register an interceptor, optionally with a payload-free name recorded on the records' verdict summaries.</summary>
    /// <param name="interceptor">The interceptor to register.</param>
    /// <param name="name">An optional registration name.</param>
    /// <returns>This options instance.</returns>
    /// <exception cref="InvalidOperationException">The options were built from a declaration; its bindings are the interceptors.</exception>
    public AgentHooksOptions AddInterceptor(IInterceptor interceptor, string? name = null)
    {
        _ = Throw.IfNull(interceptor);
        this.ThrowIfDeclared(nameof(this.AddInterceptor));
        this._interceptors.Add(new KeyValuePair<string?, IInterceptor>(name, interceptor));
        return this;
    }

    /// <summary>Gets the registered interceptors, in registration order. Empty when the options were built from a declaration.</summary>
    public IReadOnlyList<KeyValuePair<string?, IInterceptor>> Interceptors => this._interceptors;

    /// <summary>Gets the host declaration the options were built from, or <see langword="null"/> on the code path.</summary>
    public HostDeclaration? Declaration { get; }

    /// <summary>Gets the declaration as the core resolved it against <see cref="AgentHooksHostSurface.Surface"/>,
    /// or <see langword="null"/> on the code path. Its <c>CanonicalJson()</c>
    /// is the same for a file, JSON text, a node or the builder carrying the same document.
    /// On the declaration path this is the source of truth: <see cref="Mode"/> and <see cref="Composition"/>
    /// mirror it, while the approval resolver, identity provider and timeouts are read here
    /// (<c>ApprovalResolver</c>, <c>IdentityProvider</c>, <c>InterceptorTimeoutMs</c>,
    /// <c>ApprovalResolverTimeoutMs</c>) because the document names them rather than holding instances.</summary>
    public ResolvedDeclaration? ResolvedDeclaration { get; }

    /// <summary>The registry the declaration resolves against; <see langword="null"/> on the code path.</summary>
    internal HostRegistry? Registry { get; }

    /// <summary>Gets or sets the optional approval resolver consulted for liftable denies.
    /// <see langword="null"/> when the options were built from a declaration: the document names the
    /// resolver (<c>ResolvedDeclaration.ApprovalResolver</c>) and the registry owns the instance.</summary>
    /// <exception cref="InvalidOperationException">The options were built from a declaration, which names the resolver.</exception>
    public IApprovalResolver? Resolver
    {
        get;
        set
        {
            this.ThrowIfDeclared(nameof(this.Resolver));
            field = value;
        }
    }

    /// <summary>Gets or sets whether verdicts are enforced (default) or recorded without acting.
    /// Read-only when the options were built from a declaration: the value is the document's.</summary>
    /// <exception cref="InvalidOperationException">The options were built from a declaration, which states the mode.</exception>
    public EnforcementMode Mode
    {
        get;
        set
        {
            this.ThrowIfDeclared(nameof(this.Mode));
            field = value;
        }
    } = EnforcementMode.Enforce;

    /// <summary>Gets or sets the composition profile and knobs; <see langword="null"/> uses the SDK default
    /// (<c>sequential/first_deny</c>, <c>on_approval: stop</c>). Read-only when the options were built from
    /// a declaration: the value is the document's, with its knobs resolved.</summary>
    /// <exception cref="InvalidOperationException">The options were built from a declaration, which states the composition.</exception>
    public CompositionConfig? Composition
    {
        get;
        set
        {
            this.ThrowIfDeclared(nameof(this.Composition));
            field = value;
        }
    }

    /// <summary>Gets or sets the identity provider; <see langword="null"/> uses the SDK default
    /// (<c>jcs-sha256</c>). Use <see cref="IdentityProvider.Null"/> for identity-unbound records.
    /// <see langword="null"/> when the options were built from a declaration: the document names the
    /// provider (<c>ResolvedDeclaration.IdentityProvider</c>) and the registry owns the instance.</summary>
    /// <exception cref="InvalidOperationException">The options were built from a declaration, which names the provider.</exception>
    public IdentityProvider? IdentityProvider
    {
        get;
        set
        {
            this.ThrowIfDeclared(nameof(this.IdentityProvider));
            field = value;
        }
    }

    /// <summary>Gets or sets the per-interceptor/resolver timeout; <see langword="null"/> uses the
    /// spec-recommended 5 seconds. <see langword="null"/> when the options were built from a declaration:
    /// the document states two timeouts (<c>ResolvedDeclaration.InterceptorTimeoutMs</c> and
    /// <c>ApprovalResolverTimeoutMs</c>), which one <see cref="TimeSpan"/> cannot mirror.</summary>
    /// <exception cref="InvalidOperationException">The options were built from a declaration, which states the timeouts.</exception>
    public TimeSpan? Timeout
    {
        get;
        set
        {
            this.ThrowIfDeclared(nameof(this.Timeout));
            field = value;
        }
    }

    /// <summary>Gets or sets an optional callback receiving every interception record. Allowed on both paths.</summary>
    public Action<InterceptionRecord>? RecordSink { get; set; }

    private void ThrowIfDeclared(string member)
    {
        if (this.Declaration is not null)
        {
            throw new InvalidOperationException(
                $"{member} cannot be set on options built from a host declaration: the document states it " +
                "(spec §7.7.7, sealed emitter). Change the document instead.");
        }
    }
}
