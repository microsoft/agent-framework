// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using AgentHooks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>
/// Run bracket: emits <c>agent_startup</c>, <c>input</c>, <c>output</c> and
/// <c>agent_shutdown</c>, owns the per-run enforcement state shared with the chat and
/// function seams, and releases the run's deferred durable persistence only after the
/// <c>output</c> verdict permits the content.
/// </summary>
/// <remarks>
/// Streaming runs are fail-closed by buffering: the inner stream is fully consumed, the
/// <c>output</c> verdict is applied to the assembled response, deferred persistence is
/// flushed (or dropped on deny), and only then are the (possibly re-derived) updates
/// released. A deny releases zero updates and surfaces
/// <see cref="InterceptionBlockedException"/> when the stream is consumed.
/// </remarks>
internal sealed class AgentHooksAgent : DelegatingAIAgent
{
    private const string FrameworkName = "agent-framework";

    private readonly AgentHooksConfiguration _configuration;

    internal AgentHooksAgent(AIAgent innerAgent, AgentHooksConfiguration configuration)
        : base(innerAgent)
    {
        this._configuration = configuration;
    }

    /// <inheritdoc />
    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        var state = this.CreateRunState();
        var previous = AgentHooksRunState.Current;
        AgentHooksRunState.Current = state;
        string shutdownReason = "completed";
        try
        {
            List<ChatMessage> messageList = [.. messages];
            await this.EmitRunStartAsync(state, messageList, options, cancellationToken).ConfigureAwait(false);

            var response = await this.InnerAgent.RunAsync(messageList, session, this.WrapRunOptions(options), cancellationToken).ConfigureAwait(false);

            if (state.Halted is Exception halted)
            {
                // The enforcement layer itself failed mid-run: strand the deferred
                // persistence (fail closed) and surface the halt to the caller.
                state.Denied = true;
                state.Gate.Drop();
                throw halted;
            }

            _ = await EmitOutputAsync(state, response, cancellationToken).ConfigureAwait(false);

            // The verdict permitted the content: release the persistence the run
            // deferred behind the gate. A deny drops it instead, so denied content
            // never becomes durable, and transformed content persists post-transform
            // (the deferred persists substitute the verdicted messages).
            state.VerdictedResponseMessages = response.Messages;
            await state.Gate.FlushAsync(cancellationToken).ConfigureAwait(false);
            return response;
        }
        catch (InterceptionBlockedException)
        {
            state.Denied = true;
            state.Gate.Drop();
            shutdownReason = "error";
            throw;
        }
        catch (OperationCanceledException)
        {
            shutdownReason = "cancelled";
            throw;
        }
        catch (Exception)
        {
            shutdownReason = "error";
            throw;
        }
        finally
        {
            await this.EmitShutdownAsync(state, shutdownReason).ConfigureAwait(false);
            AgentHooksRunState.Current = previous;
        }
    }

    /// <inheritdoc />
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // All guarded work (including full consumption of the inner stream) happens in
        // the helper, so a deny surfaces when the returned stream is consumed and zero
        // updates egress ahead of the verdict.
        var released = await this.RunStreamingGuardedAsync(messages, session, options, cancellationToken).ConfigureAwait(false);
        foreach (var update in released)
        {
            yield return update;
        }
    }

    private async Task<IReadOnlyList<AgentResponseUpdate>> RunStreamingGuardedAsync(
        IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, CancellationToken cancellationToken)
    {
        var state = this.CreateRunState();
        var previous = AgentHooksRunState.Current;
        AgentHooksRunState.Current = state;
        string shutdownReason = "completed";
        try
        {
            List<ChatMessage> messageList = [.. messages];
            await this.EmitRunStartAsync(state, messageList, options, cancellationToken).ConfigureAwait(false);

            List<AgentResponseUpdate> buffered = [];
            await foreach (var update in this.InnerAgent.RunStreamingAsync(messageList, session, this.WrapRunOptions(options), cancellationToken).ConfigureAwait(false))
            {
                buffered.Add(update);
            }

            if (state.Halted is Exception halted)
            {
                state.Denied = true;
                state.Gate.Drop();
                throw halted;
            }

            var response = buffered.ToAgentResponse();
            bool transformed = await EmitOutputAsync(state, response, cancellationToken).ConfigureAwait(false);
            state.VerdictedResponseMessages = response.Messages;
            await state.Gate.FlushAsync(cancellationToken).ConfigureAwait(false);

            // No-divergence rule: a transformed output re-derives the released updates
            // from the verdicted response, so streamed egress can never diverge from the
            // verdicted content.
            return transformed ? RederiveUpdates(response) : buffered;
        }
        catch (InterceptionBlockedException)
        {
            state.Denied = true;
            state.Gate.Drop();
            shutdownReason = "error";
            throw;
        }
        catch (OperationCanceledException)
        {
            shutdownReason = "cancelled";
            throw;
        }
        catch (Exception)
        {
            shutdownReason = "error";
            throw;
        }
        finally
        {
            await this.EmitShutdownAsync(state, shutdownReason).ConfigureAwait(false);
            AgentHooksRunState.Current = previous;
        }
    }

    /// <summary>
    /// Re-derive stream updates from the (transformed) verdicted response, preserving the
    /// response-level metadata that <see cref="AgentResponse.ToAgentResponseUpdates"/>
    /// does not project — currently the <see cref="AgentResponse.ContinuationToken"/>,
    /// without which a transformed streaming background response could not be resumed.
    /// </summary>
    internal static IReadOnlyList<AgentResponseUpdate> RederiveUpdates(AgentResponse response)
    {
        var updates = response.ToAgentResponseUpdates();
        if (response.ContinuationToken is { } continuationToken)
        {
            if (updates.Length == 0)
            {
                updates = [new AgentResponseUpdate { AgentId = response.AgentId, ResponseId = response.ResponseId }];
            }

            updates[^1].ContinuationToken = continuationToken;
        }

        return updates;
    }

    private AgentHooksRunState CreateRunState()
    {
        var configuration = this._configuration;
        if (configuration is { Emitter: not null, Builder: not null })
        {
            // Session-scoped: the host constructed the emitter/builder pair and owns
            // the agent-hooks session boundaries — one session (one sequence, one
            // record trail, one approval ledger) spans multiple agent runs, so this
            // agent emits only the per-run points and never agent_startup /
            // agent_shutdown (the host brackets the session itself).
            return new AgentHooksRunState(configuration.Emitter, configuration.Builder, sessionScoped: true, configuration);
        }

        string agentId = this.Id ?? this.Name ?? "agent";
        var builder = new AgentContextBuilder(
            agentId,
            framework: FrameworkName,
            sessionId: Guid.NewGuid().ToString("N", CultureInfo.InvariantCulture),
            agentName: this.Name);
        var emitter = new InterceptionEmitter(configuration.Mode, configuration.Resolver, configuration.Timeout);
        if (configuration.Composition is not null)
        {
            _ = emitter.SetComposition(configuration.Composition);
        }

        if (configuration.IdentityProvider is not null)
        {
            _ = emitter.SetIdentityProvider(configuration.IdentityProvider);
        }

        if (configuration.RecordSink is not null)
        {
            _ = emitter.SetRecordSink(configuration.RecordSink);
        }

        foreach (var (name, interceptor) in configuration.Interceptors)
        {
            _ = emitter.Register(interceptor, name);
        }

        // Not session-scoped: the default scoping is one agent-hooks session per run.
        // The emitter and builder created above are fresh for this run — fresh session
        // id, sequence numbering starting at zero, and an isolated record trail — so
        // concurrent runs on this agent cannot interleave their emissions, and
        // agent_startup / agent_shutdown bracket the run (emitted by this agent, see
        // EmitRunStartAsync / EmitShutdownAsync, which skip them when session-scoped).
        return new AgentHooksRunState(emitter, builder, sessionScoped: false, configuration);
    }

    /// <summary>Emit <c>agent_startup</c> (per-run sessions) and <c>input</c>; apply input transforms.</summary>
    private async Task EmitRunStartAsync(
        AgentHooksRunState state, List<ChatMessage> messages, AgentRunOptions? options, CancellationToken cancellationToken)
    {
        if (!state.SessionScoped)
        {
            _ = await state.Emitter.EmitAsync(state.Builder.AgentStartup(this.ResolveToolNames(options)), cancellationToken).ConfigureAwait(false);
        }

        // The projection returns content and role directly (single producer, invariant
        // by construction) so nothing here re-reads payload properties by name.
        var before = InputCodec.ToWire(messages);
        var outcome = await state.Emitter.EmitAsync(
            state.Builder.Input(before.Content?.DeepClone(), before.Role), cancellationToken).ConfigureAwait(false);
        InputCodec.WriteBack(messages, before.Payload, outcome.Target);
    }

    /// <summary>Emit <c>output</c> over the assembled response; apply output transforms. Returns whether the response changed.</summary>
    private static async Task<bool> EmitOutputAsync(AgentHooksRunState state, AgentResponse response, CancellationToken cancellationToken)
    {
        var before = OutputCodec.ToWire(response);
        var outcome = await state.Emitter.EmitAsync(state.Builder.Output(before), cancellationToken).ConfigureAwait(false);
        return OutputCodec.WriteBack(response, before, outcome.Target);
    }

    /// <summary>Best-effort <c>agent_shutdown</c> (per-run sessions only; blocks there are record-only).</summary>
    private async Task EmitShutdownAsync(AgentHooksRunState state, string reason)
    {
        if (state.SessionScoped)
        {
            return;
        }

        try
        {
            _ = await state.Emitter.EmitUncheckedAsync(state.Builder.AgentShutdown(reason)).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is not OutOfMemoryException)
        {
            // agent_shutdown is a best-effort trail closure: a failure to emit it
            // (including I/O-style faults from a record sink) must not mask the run's
            // own outcome, which is already propagating — but it is logged so the
            // incomplete session trail is trackable. Truly fatal exceptions
            // (OutOfMemory; StackOverflow is uncatchable) are not swallowed.
            state.Configuration.Logger.LogAgentShutdownEmissionFailed(reason, exception);
        }
    }

    /// <summary>Project the registered tool names for <c>agent_startup</c> (spec <c>tools_registered</c>).</summary>
    /// <remarks>
    /// This is deliberately the run-start snapshot: the tools declared on the agent and
    /// on the run options when the run begins. Tools registered dynamically during the
    /// run (for example by context providers during run preparation) cannot be known at
    /// <c>agent_startup</c> time; they surface in each <c>pre_model_call</c> emission's
    /// <c>tools</c> projection (the completed per-call set) and are bracketed by
    /// <c>pre_tool_call</c>/<c>post_tool_call</c> like any other tool when invoked.
    /// </remarks>
    private List<string> ResolveToolNames(AgentRunOptions? options)
    {
        List<string> names = [];
        if (this.GetService<ChatOptions>()?.Tools is { } agentTools)
        {
            names.AddRange(agentTools.Select(tool => tool.Name));
        }

        if (options is ChatClientAgentRunOptions { ChatOptions.Tools: { } runTools })
        {
            names.AddRange(runTools.Select(tool => tool.Name));
        }

        return names;
    }

    /// <summary>
    /// Guard per-run options against enforcement bypasses.
    /// </summary>
    /// <remarks>
    /// <list type="bullet">
    /// <item><description>A per-run <see cref="ChatClientAgentRunOptions.ChatClientFactory"/> would replace the
    /// guarded chat pipeline — and the tool-wrapping stage riding it — silently removing the chat and tool seams,
    /// so it is rejected loudly (fail closed).</description></item>
    /// <item><description>A <see cref="ChatHistoryProvider"/> override can ride either the base
    /// <see cref="AgentRunOptions.AdditionalProperties"/> (merged into the chat options with precedence by the
    /// agent) or <see cref="ChatOptions.AdditionalProperties"/>; both would bypass the gating wrapper installed at
    /// construction, so both are wrapped — on a clone, never mutating the caller's options.</description></item>
    /// </list>
    /// </remarks>
    private AgentRunOptions? WrapRunOptions(AgentRunOptions? options)
    {
        if (options is null)
        {
            return null;
        }

        if (options is ChatClientAgentRunOptions { ChatClientFactory: { } factory } && !IsFrameworkFunctionMiddlewareFactory(factory))
        {
            throw new InvalidOperationException(
                $"A per-run {nameof(ChatClientAgentRunOptions.ChatClientFactory)} is not supported on an " +
                "agent-hooks-guarded agent: it would replace the guarded chat pipeline (and the tool-wrapping " +
                "stage riding it), silently removing the pre/post_model_call and pre/post_tool_call seams. " +
                "Decorate the chat client supplied to the agent-hooks factory instead.");
        }

        bool wrapBase = this.HasUnwrappedProviderOverride(options.AdditionalProperties);
        bool wrapChat = options is ChatClientAgentRunOptions { ChatOptions.AdditionalProperties: { } chatProperties } &&
            this.HasUnwrappedProviderOverride(chatProperties);
        if (!wrapBase && !wrapChat && options is not ChatClientAgentRunOptions)
        {
            return options;
        }

        // Copy-on-write: Clone() deep-copies both dictionaries, so the caller's options
        // are never mutated. Chat-typed options are ALWAYS cloned, even when nothing
        // needs wrapping: the framework's function-invocation middleware (including this
        // composition's own tool seam) chains its factory onto the options instance it
        // receives in place, so forwarding the caller's instance would leak that factory
        // into it — reusing the same options for a second run would then trip the
        // rejection above, and concurrent reuse would race.
        var cloned = options.Clone();
        this.WrapProviderOverride(cloned.AdditionalProperties);
        if (cloned is ChatClientAgentRunOptions clonedChatOptions)
        {
            this.WrapProviderOverride(clonedChatOptions.ChatOptions?.AdditionalProperties);
        }

        return cloned;
    }

    /// <summary>
    /// Whether a per-run chat-client factory was installed by the framework's own
    /// function-invocation middleware (an agent decorator composed outside this agent).
    /// </summary>
    /// <remarks>
    /// That factory wraps the pipeline it is given (it only rewrites the run's tools to
    /// add the middleware bracket), so the enforcement seams below stay intact — outer
    /// position is outer trust, exactly like any other decorator on the returned agent.
    /// A caller-supplied factory chained through it is still rejected by walking the
    /// chain. The type check is intentionally narrow: anything unrecognized stays
    /// rejected (fail closed).
    /// </remarks>
    private static bool IsFrameworkFunctionMiddlewareFactory(Func<IChatClient, IChatClient>? factory)
    {
        while (factory is not null)
        {
            if (factory.Method.DeclaringType?.FullName?.StartsWith(
                    "Microsoft.Agents.AI.FunctionInvocationDelegatingAgent", StringComparison.Ordinal) is not true)
            {
                return false;
            }

            // The framework middleware chains any pre-existing factory into its closure;
            // walk it so a caller-supplied factory cannot ride in unnoticed.
            factory = factory.Target?.GetType()
                .GetFields(System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic)
                .Where(field => field.FieldType == typeof(Func<IChatClient, IChatClient>))
                .Select(field => (Func<IChatClient, IChatClient>?)field.GetValue(factory.Target))
                .FirstOrDefault(value => value is not null);
        }

        return true;
    }

    private bool HasUnwrappedProviderOverride(AdditionalPropertiesDictionary? properties) =>
        properties is not null &&
        properties.TryGetValue(out ChatHistoryProvider? overrideProvider) &&
        overrideProvider is not null &&
        !this.IsOwnGatingWrapper(overrideProvider);

    private void WrapProviderOverride(AdditionalPropertiesDictionary? properties)
    {
        if (properties is not null &&
            properties.TryGetValue(out ChatHistoryProvider? overrideProvider) &&
            overrideProvider is not null &&
            !this.IsOwnGatingWrapper(overrideProvider))
        {
            bool perServiceCall = this.GetService<ChatClientAgentOptions>()?.RequirePerServiceCallChatHistoryPersistence is true;
            properties[typeof(ChatHistoryProvider).FullName!] =
                new AgentHooksGatingChatHistoryProvider(overrideProvider, this._configuration, perServiceCall);
        }
    }

    /// <summary>
    /// Whether <paramref name="provider"/> is a gating wrapper owned by <em>this</em>
    /// installation. Ownership matters: a gating wrapper belonging to a different
    /// agent-hooks installation runs inline under this run's state (its own gate is not
    /// covering here), so it must be re-wrapped like any unguarded provider — skipping
    /// it would let a denied run's history persist through the foreign wrapper.
    /// </summary>
    private bool IsOwnGatingWrapper(ChatHistoryProvider provider) =>
        provider is AgentHooksGatingChatHistoryProvider wrapper &&
        ReferenceEquals(wrapper.Configuration, this._configuration);
}
