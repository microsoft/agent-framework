// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using AgentHooks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>
/// Model bracket: emits <c>pre_model_call</c> and <c>post_model_call</c> around each
/// individual model service call.
/// </summary>
/// <remarks>
/// <para>
/// Installed by the agent-hooks factory directly on the supplied chat client, so it sits
/// below <see cref="FunctionInvokingChatClient"/> in the agent's default pipeline and
/// brackets every service call of the tool loop individually.
/// </para>
/// <para>
/// Streaming is fail-closed by buffering (spec §12.1 <c>buffered_output</c>): the model
/// stream is fully consumed internally, the <c>post_model_call</c> verdict is applied to
/// the assembled response, and only then are the (possibly re-derived) updates released.
/// No partial content ever egresses ahead of the verdict.
/// </para>
/// <para>
/// Durability note: <c>PerServiceCallChatHistoryPersistingChatClient</c> sits above this
/// decorator, so a permitted (and possibly transformed) response is what gets persisted,
/// and a denied response throws before the persister ever sees it — verdict precedes
/// durability by pipeline order at this seam.
/// </para>
/// </remarks>
internal sealed class AgentHooksChatClient : DelegatingChatClient
{
    private readonly AgentHooksConfiguration _configuration;

    internal AgentHooksChatClient(IChatClient innerClient, AgentHooksConfiguration configuration)
        : base(innerClient)
    {
        this._configuration = configuration;
    }

    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        var state = this.RequireRunState();
        string modelId = this.ResolveModelId(options);
        var effectiveMessages = await this.EmitPreModelCallAsync(state, modelId, messages, cancellationToken).ConfigureAwait(false);

        var response = await base.GetResponseAsync(effectiveMessages, options, cancellationToken).ConfigureAwait(false);

        await EmitPostModelCallAsync(state, modelId, response, cancellationToken).ConfigureAwait(false);
        return response;
    }

    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var state = this.RequireRunState();
        string modelId = this.ResolveModelId(options);
        var effectiveMessages = await this.EmitPreModelCallAsync(state, modelId, messages, cancellationToken).ConfigureAwait(false);

        // Spec §12.1: the complete response is assembled before post_model_call is
        // emitted, and nothing (updates or tool calls) is released beforehand. A deny
        // throws before any update egresses.
        List<ChatResponseUpdate> buffered = [];
        await foreach (var update in base.GetStreamingResponseAsync(effectiveMessages, options, cancellationToken).ConfigureAwait(false))
        {
            buffered.Add(update);
        }

        var response = buffered.ToChatResponse();
        bool changed = await EmitPostModelCallAsync(state, modelId, response, cancellationToken).ConfigureAwait(false);

        // No-divergence rule: a transformed response re-derives the released updates
        // from the verdicted content; otherwise the buffered updates replay as-is.
        foreach (var update in changed ? response.ToChatResponseUpdates() : (IEnumerable<ChatResponseUpdate>)buffered)
        {
            yield return update;
        }
    }

    private AgentHooksRunState RequireRunState()
    {
        var state = AgentHooksRunState.Current
            ?? throw new InvalidOperationException(
                "The agent-hooks chat seam was invoked without an active agent-hooks run. The agent-hooks " +
                "decorators must be installed as one unit by the agent-hooks factory; do not extract or reuse " +
                "the inner chat client outside the agent it guards.");

        if (!ReferenceEquals(state.Configuration, this._configuration))
        {
            throw new InvalidOperationException(
                "The agent-hooks chat seam found an active agent-hooks run owned by a different agent-hooks " +
                "installation. Nesting one agent-hooks-guarded agent's chat client inside another guarded agent " +
                "is not supported: emissions would silently bind to the wrong emitter.");
        }

        return state;
    }

    private string ResolveModelId(ChatOptions? options) =>
        options?.ModelId
        ?? this.GetService<ChatClientMetadata>()?.DefaultModelId
        ?? this.InnerClient.GetType().Name;

    private async Task<List<ChatMessage>> EmitPreModelCallAsync(
        AgentHooksRunState state, string modelId, IEnumerable<ChatMessage> messages, CancellationToken cancellationToken)
    {
        List<ChatMessage> messageList = [.. messages];
        var before = ModelRequestCodec.ToWire(messageList);
        EmitOutcome outcome;
        try
        {
            outcome = await state.Emitter.EmitAsync(state.Builder.PreModelCall(modelId, before), cancellationToken).ConfigureAwait(false);
        }
        catch (InterceptionBlockedException)
        {
            state.Denied = true;
            throw;
        }

        return ModelRequestCodec.WriteBack(messageList, before, outcome.Target) ?? messageList;
    }

    /// <summary>Emit <c>post_model_call</c> over the assembled response; apply transforms. Returns whether the response changed.</summary>
    private static async Task<bool> EmitPostModelCallAsync(
        AgentHooksRunState state, string modelId, ChatResponse response, CancellationToken cancellationToken)
    {
        var before = ModelResponseCodec.ToWire(response);
        EmitOutcome outcome;
        try
        {
            outcome = await state.Emitter.EmitAsync(
                state.Builder.PostModelCall(
                    response.ModelId ?? modelId,
                    before["content"]?.DeepClone(),
                    (System.Text.Json.Nodes.JsonArray)before["tool_calls"]!.DeepClone(),
                    Wire.FinishReasonString(response.FinishReason),
                    Wire.UsageToWire(response.Usage),
                    response.ResponseId),
                cancellationToken).ConfigureAwait(false);
        }
        catch (InterceptionBlockedException)
        {
            // §6.1: the denied response must not be incorporated; downstream persistence
            // (the per-service-call persister sits above this seam) never runs, and any
            // later gated persist for this run is refused via the denied flag.
            state.Denied = true;
            throw;
        }

        return ModelResponseCodec.WriteBack(response, before, outcome.Target);
    }
}
