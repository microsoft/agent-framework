// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration.Handoff;

/// <summary>
/// An actor used with the <see cref="HandoffOrchestration{TInput,TOutput}"/>.
/// </summary>
internal sealed class HandoffActor : AgentActor
{
    private readonly ChatClientAgent _chatAgent;
    private readonly HandoffLookup _handoffs;
    private readonly ActorType _resultHandoff;
    private readonly List<ChatMessage> _cache;
    private readonly ChatOptions _options;

    private string? _handoffAgent;
    private string? _taskSummary;

    /// <summary>
    /// Initializes a new instance of the <see cref="HandoffActor"/> class.
    /// </summary>
    /// <param name="id">The unique identifier of the agent.</param>
    /// <param name="runtime">The runtime associated with the agent.</param>
    /// <param name="context">The orchestration context.</param>
    /// <param name="agent">An <see cref="Agent"/>.</param>>
    /// <param name="handoffs">The handoffs available to this agent</param>
    /// <param name="resultHandoff">The handoff agent for capturing the result.</param>
    /// <param name="logger">The logger to use for the actor</param>
    public HandoffActor(ActorId id, IAgentRuntime runtime, OrchestrationContext context, ChatClientAgent agent, HandoffLookup handoffs, ActorType resultHandoff, ILogger<HandoffActor>? logger = null)
        : base(id, runtime, context, agent, logger)
    {
        if (handoffs.ContainsKey(agent.Name ?? agent.Id))
        {
            throw new ArgumentException($"The agent {agent.Name ?? agent.Id} cannot have a handoff to itself.", nameof(handoffs));
        }

        this._cache = [];
        this._chatAgent = agent;
        this._handoffs = handoffs;
        this._resultHandoff = resultHandoff;
        this._options =
            new ChatOptions
            {
                Tools = [.. this.CreateHandoffFunctions()],
                ToolMode = ChatToolMode.Auto
            };

        this.RegisterMessageHandler<HandoffMessages.InputTask>(this.HandleAsync);
        this.RegisterMessageHandler<HandoffMessages.Request>(this.HandleAsync);
        this.RegisterMessageHandler<HandoffMessages.Response>(this.HandleAsync);
    }

    /// <inheritdoc/>
    protected override Task InvokeAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentRunOptions options,
        CancellationToken cancellationToken = default) =>
        this._chatAgent.RunAsync(
            [.. messages],
            this.Thread,
            options,
            this._options,
            cancellationToken);

    /// <inheritdoc/>
    protected override IAsyncEnumerable<ChatResponseUpdate> InvokeStreamingAsync(IReadOnlyCollection<ChatMessage> messages, AgentRunOptions options, CancellationToken cancellationToken) =>
        this._chatAgent.RunStreamingAsync(
            messages,
            this.Thread,
            options,
            this._options,
            cancellationToken);

    /// <summary>
    /// Gets or sets the callback to be invoked for interactive input.
    /// </summary>
    public OrchestrationInteractiveCallback? InteractiveCallback { get; init; }

    private ValueTask HandleAsync(HandoffMessages.InputTask item, MessageContext messageContext, CancellationToken cancellationToken)
    {
        this._taskSummary = null;
        this._cache.AddRange(item.Messages);
        return default;
    }

    private ValueTask HandleAsync(HandoffMessages.Response item, MessageContext messageContext, CancellationToken cancellationToken)
    {
        this._cache.Add(item.Message);
        return default;
    }

    private async ValueTask HandleAsync(HandoffMessages.Request item, MessageContext messageContext, CancellationToken cancellationToken)
    {
        try
        {
            this.Logger.LogHandoffAgentInvoke(this.Id);

            while (this._taskSummary == null)
            {
                ChatMessage response;
                try
                {
                    response = await this.InvokeAsync(this._cache, cancellationToken).ConfigureAwait(false);
                }
                catch (Exception exception)
                {
                    this.Logger.LogError(exception, "Failure");
                    throw;
                }

                this._cache.Clear();

                this.Logger.LogHandoffAgentResult(this.Id, response.Text);

                // The response can potentially be a TOOL message from the Handoff plugin due to the filter
                // which will terminate the conversation when a function from the handoff plugin is called.
                // Since we don't want to publish that message, so we only publish if the response is an ASSISTANT message.
                if (response.Role == ChatRole.Assistant)
                {
                    await this.PublishMessageAsync(new HandoffMessages.Response { Message = response }, this.Context.Topic, messageId: null, cancellationToken).ConfigureAwait(false);
                }

                if (this._handoffAgent != null)
                {
                    ActorType handoffType = this._handoffs[this._handoffAgent].AgentType;
                    await this.PublishMessageAsync(new HandoffMessages.Request(), handoffType, cancellationToken).ConfigureAwait(false);

                    this._handoffAgent = null;
                    break;
                }

                if (this.InteractiveCallback != null && this._taskSummary == null)
                {
                    ChatMessage input = await this.InteractiveCallback().ConfigureAwait(false);
                    await this.PublishMessageAsync(new HandoffMessages.Response { Message = input }, this.Context.Topic, messageId: null, cancellationToken).ConfigureAwait(false);
                    this._cache.Add(input);
                    continue;
                }

                await this.EndAsync(response.Text ?? "No handoff or human response function requested. Ending task.", cancellationToken).ConfigureAwait(false);
            }
        }
        catch (Exception exception)
        {
            this.Logger.LogError(exception, "Failure");
            throw;
        }
    }

    private IEnumerable<AIFunction> CreateHandoffFunctions()
    {
        yield return AIFunctionFactory.Create(
            this.EndAsync,
            name: "end_task",
            description: "Complete the task with a summary when no further requests are given.");

        foreach (KeyValuePair<string, (ActorType AgentType, string Description)> handoff in this._handoffs)
        {
            AIFunction handoffFunction =
                AIFunctionFactory.Create(
                    () => this.Handoff(handoff.Key),
                    name: $"transfer_to_{handoff.Key}",
                    description: handoff.Value.Description);

            yield return handoffFunction;
        }
    }

    private void Handoff(string agentName)
    {
        this.Logger.LogHandoffFunctionCall(this.Id, agentName);
        this._handoffAgent = agentName;

        FunctionInvokingChatClient.CurrentContext!.Terminate = true;
    }

    private async ValueTask EndAsync(string summary, CancellationToken cancellationToken)
    {
        this.Logger.LogHandoffSummary(this.Id, summary);
        this._taskSummary = summary;
        await this.PublishMessageAsync(new HandoffMessages.Result { Message = new ChatMessage(ChatRole.Assistant, summary) }, this._resultHandoff, cancellationToken).ConfigureAwait(false);

        if (FunctionInvokingChatClient.CurrentContext is not null)
        {
            FunctionInvokingChatClient.CurrentContext.Terminate = true;
        }
    }
}
