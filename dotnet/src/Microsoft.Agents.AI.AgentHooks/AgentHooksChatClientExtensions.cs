// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using AgentHooks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>
/// Factory for AGENT-HOOKS-0.1 enforced agents: composes a <see cref="ChatClientAgent"/>
/// whose runs emit every applicable interception point of the agent-hooks control
/// contract and enforce the combined verdicts fail-closed.
/// </summary>
/// <remarks>
/// <para>
/// The enforcement is one coherent feature riding three seams that this factory installs
/// as one indivisible unit (the seam decorators are internal, so a partial install is
/// impossible by construction):
/// <list type="bullet">
/// <item><description><c>agent_startup</c> / <c>input</c> / <c>output</c> / <c>agent_shutdown</c> at the agent seam,</description></item>
/// <item><description><c>pre_model_call</c> / <c>post_model_call</c> at the chat seam (below the function-invocation loop, so every model service call is bracketed individually),</description></item>
/// <item><description><c>pre_tool_call</c> / <c>post_tool_call</c> at the function-invocation seam.</description></item>
/// </list>
/// </para>
/// <para>
/// Enforcement semantics (<see cref="EnforcementMode.Enforce"/>): every interception
/// point is emitted before the guarded action runs (pre points) or before its result is
/// incorporated (post points); emission failures inside the SDK synthesize
/// <c>host_error:*</c> denies and are treated as blocks — the feature never fails open.
/// Transform verdicts are written back into the native values (messages, arguments,
/// results) so the framework executes exactly the value the interceptors approved, and
/// rich (non-text) content is preserved as content objects, never flattened to text. A
/// deny at <c>input</c>, <c>pre_model_call</c>, <c>post_model_call</c> or <c>output</c>
/// terminates the run: <see cref="InterceptionBlockedException"/> propagates to the
/// caller of <see cref="AIAgent.RunAsync(System.Collections.Generic.IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, System.Threading.CancellationToken)"/>
/// (for streaming runs, when the stream is consumed, with zero updates released). A deny
/// at the tool seam blocks the tool call and surfaces a tool-error payload to the model
/// so the agent loop can continue; a <c>host_error:*</c> deny there additionally halts
/// the run. Streaming is fail-closed by buffering: no partial content ever egresses
/// ahead of a verdict.
/// </para>
/// <para>
/// Durable history persistence is gated behind the verdicts: end-of-run history and
/// context-provider writes are deferred until the <c>output</c> verdict permits the
/// content (denied content never becomes durable; transformed content persists
/// post-transform), and per-service-call history persistence sits above the chat seam,
/// so it only ever observes responses its own <c>post_model_call</c> verdict permitted —
/// a permitted per-service-call write remains durable even if the run's <c>output</c> is
/// later denied. Nested and sibling agents (including sub-agents invoked as tools) have
/// their own providers and persist inline at their own run boundaries. Residual
/// limitation: history managed server-side by the model service (a conversation id) is
/// durable at the service the moment the model call executes and cannot be gated by any
/// framework layer.
/// </para>
/// <para>
/// Known limitation — service-side (hosted) tool execution: tools executed by the model
/// provider itself never pass through the function-invocation seam, so
/// <c>pre_tool_call</c> / <c>post_tool_call</c> cannot intercept them. Their calls and
/// outputs are surfaced faithfully in the <c>post_model_call</c> content projection,
/// where interceptors can observe and deny/transform the response that carries them.
/// </para>
/// <para>
/// Composition order: decorators applied to the <em>returned</em> agent run outside the
/// enforcement boundary (outer position is outer trust — the final <c>output</c> point
/// still guards whatever egresses); decorators applied to the <em>supplied</em> chat
/// client run inside it, below the verdicts. Install exactly one enforcement per agent:
/// nesting one guarded agent's seams inside another fails closed, a supplied client that
/// already contains a function-invocation loop is rejected (it would execute tools below
/// the verdicts), and per-run <see cref="ChatClientAgentRunOptions.ChatClientFactory"/>
/// callbacks are rejected on guarded agents (they would replace the guarded pipeline).
/// </para>
/// <para>
/// Observability note: the agent's built-in deferred-OpenTelemetry decorator sits above
/// the enforcement's chat seam, so when sensitive-data telemetry is enabled its
/// request-side spans capture the request content <em>before</em> any
/// <c>pre_model_call</c> transform is applied (an observer channel inside the
/// enforcement boundary, analogous to outer-position middleware in the Python feature).
/// Response-side telemetry observes only verdicted content; a denied call surfaces as an
/// error span with no response content.
/// </para>
/// <para>
/// Session scoping: by default each agent run is one agent-hooks session (fresh emitter
/// and sequence, <c>agent_startup</c>/<c>agent_shutdown</c> bracket the run). A host
/// that owns a longer-lived session constructs its own
/// <see cref="InterceptionEmitter"/> and <see cref="AgentContextBuilder"/> and uses the
/// host-owned overload; the enforcement then emits only the per-run points and the host
/// owns the session boundaries.
/// </para>
/// </remarks>
public static class AgentHooksChatClientExtensions
{
    /// <summary>
    /// Creates an <see cref="AIAgent"/> over <paramref name="chatClient"/> with
    /// AGENT-HOOKS-0.1 enforcement installed on every seam, one agent-hooks session per
    /// run.
    /// </summary>
    /// <param name="chatClient">The chat client the agent talks to. It is decorated by the enforcement's chat
    /// seam before the agent's default pipeline is applied, so every model service call is bracketed.</param>
    /// <param name="hooksOptions">The agent-hooks enforcement options; at least one interceptor is required.</param>
    /// <param name="agentOptions">Optional agent options; a copy is used, with any configured history and
    /// context providers wrapped so durable writes obey verdict-before-durability.</param>
    /// <param name="services">Optional service provider passed through to the agent.</param>
    /// <returns>The enforced agent.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="chatClient"/> or <paramref name="hooksOptions"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="hooksOptions"/> has no interceptors.</exception>
    public static AIAgent AsAIAgentWithAgentHooks(
        this IChatClient chatClient,
        AgentHooksOptions hooksOptions,
        ChatClientAgentOptions? agentOptions = null,
        IServiceProvider? services = null)
    {
        _ = Throw.IfNull(chatClient);
        _ = Throw.IfNull(hooksOptions);
        if (hooksOptions.Interceptors.Count == 0)
        {
            throw new ArgumentException(
                "agent-hooks enforcement requires at least one interceptor (an emitter with zero interceptors " +
                "fails closed on every emission).",
                nameof(hooksOptions));
        }

        var configuration = new AgentHooksConfiguration
        {
            Interceptors = [.. hooksOptions.Interceptors],
            Resolver = hooksOptions.Resolver,
            Mode = hooksOptions.Mode,
            Composition = hooksOptions.Composition,
            IdentityProvider = hooksOptions.IdentityProvider,
            Timeout = hooksOptions.Timeout,
            RecordSink = hooksOptions.RecordSink,
        };

        return Compose(chatClient, configuration, agentOptions, services);
    }

    /// <summary>
    /// Creates an <see cref="AIAgent"/> over <paramref name="chatClient"/> with
    /// AGENT-HOOKS-0.1 enforcement bound to a host-owned session: the fully configured
    /// <paramref name="emitter"/> and matching <paramref name="builder"/> are used for
    /// every run, only the per-run points (<c>input</c> through <c>output</c>) are
    /// emitted, and the host owns the <c>agent_startup</c> / <c>agent_shutdown</c>
    /// session boundaries.
    /// </summary>
    /// <param name="chatClient">The chat client the agent talks to.</param>
    /// <param name="emitter">The host-owned, fully configured <see cref="InterceptionEmitter"/>.</param>
    /// <param name="builder">The host-owned <see cref="AgentContextBuilder"/> matching <paramref name="emitter"/>.</param>
    /// <param name="agentOptions">Optional agent options; a copy is used, with providers wrapped as in the per-run overload.</param>
    /// <param name="services">Optional service provider passed through to the agent.</param>
    /// <returns>The enforced agent.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="chatClient"/>, <paramref name="emitter"/> or <paramref name="builder"/> is <see langword="null"/>.</exception>
    public static AIAgent AsAIAgentWithAgentHooks(
        this IChatClient chatClient,
        InterceptionEmitter emitter,
        AgentContextBuilder builder,
        ChatClientAgentOptions? agentOptions = null,
        IServiceProvider? services = null)
    {
        _ = Throw.IfNull(chatClient);
        _ = Throw.IfNull(emitter);
        _ = Throw.IfNull(builder);

        var configuration = new AgentHooksConfiguration
        {
            Interceptors = [],
            Emitter = emitter,
            Builder = builder,
        };

        return Compose(chatClient, configuration, agentOptions, services);
    }

    private static AgentHooksAgent Compose(
        IChatClient chatClient, AgentHooksConfiguration configuration, ChatClientAgentOptions? agentOptions, IServiceProvider? services)
    {
        if (chatClient.GetService<FunctionInvokingChatClient>() is not null)
        {
            // A supplied client that already contains a function-invocation loop would
            // sit BELOW the enforcement's chat seam, inverting the seam order: tools
            // would execute before any post_model_call verdict could deny the
            // tool-calling response, and the function seam would never see them.
            throw new ArgumentException(
                "The chat client supplied to the agent-hooks factory must not already contain a " +
                $"{nameof(FunctionInvokingChatClient)}: it would execute tools below the enforcement's chat seam, " +
                "before any post_model_call verdict and outside the tool seam. Supply the raw chat client instead — " +
                "the agent installs its own function-invocation loop above the enforcement.",
                nameof(chatClient));
        }

        // Diagnostics logger, resolved the same way the agent resolves its own.
        configuration.Logger =
            ((services?.GetService(typeof(Extensions.Logging.ILoggerFactory)) as Extensions.Logging.ILoggerFactory)
                ?? chatClient.GetService<Extensions.Logging.ILoggerFactory>()
                ?? Extensions.Logging.Abstractions.NullLoggerFactory.Instance)
            .CreateLogger("Microsoft.Agents.AI.AgentHooks");

        var options = agentOptions?.Clone() ?? new ChatClientAgentOptions();
        if (options.UseProvidedChatClientAsIs)
        {
            // UseProvidedChatClientAsIs signals a fully custom, do-not-touch client
            // stack — which is incompatible with this factory by definition: it always
            // decorates the supplied client with the enforcement's chat seam and relies
            // on the agent's default pipeline placing the function-invocation loop above
            // that seam. Honoring the flag would silently change where (and whether) the
            // seams sit, so it is rejected loudly instead.
            throw new ArgumentException(
                $"{nameof(ChatClientAgentOptions.UseProvidedChatClientAsIs)} is not supported with the agent-hooks " +
                "factory: the factory always decorates the supplied chat client with the enforcement's chat seam " +
                "and relies on the agent's default pipeline above it. Supply the raw chat client and let the " +
                "factory compose the stack.",
                nameof(agentOptions));
        }

        bool perServiceCallPersistence = options.RequirePerServiceCallChatHistoryPersistence;

        // Durability gating: wrap the durable-write providers so end-of-run writes defer
        // behind the output verdict. The wrappers belong to this composition only, so
        // other agents sharing the same underlying providers are unaffected.
        if (options.ChatHistoryProvider is null)
        {
            // With no provider configured, the agent creates a default
            // InMemoryChatHistoryProvider internally — which this factory would never
            // see, so denied output would become durable session history on the
            // zero-config path. Materialize the default here and gate it. An explicitly
            // configured provider changes the agent's conflict handling for
            // service-managed history (it warns/throws by default), so the conflict
            // flags are set to mimic the implicit default: silently disengage.
            options.ChatHistoryProvider = new InMemoryChatHistoryProvider();
            options.WarnOnChatHistoryProviderConflict = false;
            options.ThrowOnChatHistoryProviderConflict = false;
            options.ClearOnChatHistoryProviderConflict = true;
        }

        options.ChatHistoryProvider = new AgentHooksGatingChatHistoryProvider(
            options.ChatHistoryProvider, configuration, perServiceCallPersistence);

        if (options.AIContextProviders is not null)
        {
            options.AIContextProviders = options.AIContextProviders
                .Select(AIContextProvider (provider) => new AgentHooksGatingAIContextProvider(provider, configuration, perServiceCallPersistence))
                .ToList();
        }

        // Chat seam: decorate the supplied client so the agent's default pipeline
        // (including the function-invocation loop) is built on top of it — every model
        // service call is bracketed individually.
        var guardedClient = new AgentHooksChatClient(chatClient, configuration);
        var chatAgent = new ChatClientAgent(guardedClient, options, loggerFactory: null, services);

        // Function seam: bracket every host-executed tool invocation. Skipped when the
        // agent has no function-invocation loop (nothing executes tools framework-side;
        // hosted tools surface at post_model_call).
        AIAgent innerAgent = chatAgent;
        if (chatAgent.GetService<FunctionInvokingChatClient>() is not null)
        {
            innerAgent = new AIAgentBuilder(chatAgent)
                .Use(AgentHooksFunctionMiddleware.CreateCallback(configuration))
                .Build();
        }

        // Agent seam, outermost: owns the per-run state, the run bracket and the
        // persistence gate.
        return new AgentHooksAgent(innerAgent, configuration);
    }
}
