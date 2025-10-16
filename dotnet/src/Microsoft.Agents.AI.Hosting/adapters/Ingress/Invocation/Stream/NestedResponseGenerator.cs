using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;

using Azure.AI.AgentsHosting.Ingress.Common;

using AzureAIAgents.Models;

namespace Azure.AI.AgentsHosting.Ingress.Invocation.Stream;

/// <summary>
/// Generates nested response events from agent outputs.
/// </summary>
public class NestedResponseGenerator : NestedStreamEventGeneratorBase<AzureAIAgents.Models.Response>
{
    /// <summary>
    /// Gets or sets the response ID.
    /// </summary>
    public required string ResponseId { get; init; }

    /// <summary>
    /// Gets or sets the conversation ID.
    /// </summary>
    public required string ConversationId { get; init; }

    /// <summary>
    /// Gets or sets the create response request.
    /// </summary>
    public required CreateResponse Request { get; init; }

    /// <summary>
    /// Gets or sets the output generator.
    /// </summary>
    public required INestedStreamEventGenerator<IEnumerable<ItemResource>> OutputGenerator { get; init; }

    /// <summary>
    /// Sets the action to subscribe to usage updates.
    /// </summary>
#pragma warning disable CA1044 // Properties should not be write only
    public Action<Action<ResponseUsage>> SubscribeUsageUpdate
    {
        init => value(SetUsage);
    }
#pragma warning restore CA1044

    private readonly DateTimeOffset _createdAt = DateTimeOffset.UtcNow;

    private ResponseUsage? _latestUsage;

    private AzureAIAgents.Models.Response? CompletedResponse { get; set; }

#pragma warning disable CS1998
    /// <inheritdoc/>
    public override async IAsyncEnumerable<NestedEventsGroup<AzureAIAgents.Models.Response>> GenerateAsync()
    {
        yield return new NestedEventsGroup<AzureAIAgents.Models.Response>()
        {
            CreateAggregate = () => this.CompletedResponse!,
            Events = this.GenerateEventsAsync()
        };
    }
#pragma warning restore CS1998

    private async IAsyncEnumerable<ResponseStreamEvent> GenerateEventsAsync()
    {
        yield return AzureAIAgentsModelFactory.ResponseCreatedEvent(this.Seq.GetNext(), this.ToResponse(status: ResponseStatus.InProgress));
        yield return AzureAIAgentsModelFactory.ResponseInProgressEvent(this.Seq.GetNext(), this.ToResponse(status: ResponseStatus.InProgress));

        IList<Func<IEnumerable<ItemResource>>> outputFactories = [];
#pragma warning disable CA2007 // Consider calling ConfigureAwait on the awaited task
        await foreach (var group in this.OutputGenerator.GenerateAsync())
        {
            this.CancellationToken.ThrowIfCancellationRequested();
            outputFactories.Add(group.CreateAggregate);
            await foreach(var e in group.Events)
            {
                this.CancellationToken.ThrowIfCancellationRequested();
                yield return e;
            }
        }
#pragma warning restore CA2007

        var outputs = outputFactories.SelectMany(f => f());
        this.CompletedResponse = ToResponse(status: ResponseStatus.Completed, outputs);
        yield return AzureAIAgentsModelFactory.ResponseCompletedEvent(this.Seq.GetNext(), this.CompletedResponse);
    }

    private AzureAIAgents.Models.Response ToResponse(ResponseStatus status = ResponseStatus.Completed, IEnumerable<ItemResource>? outputs = null)
    {
        return AzureAIAgentsModelFactory.Response(
            @object: "response",
            id: this.ResponseId,
            conversationId: this.ConversationId,
            metadata: this.Request.Metadata as IReadOnlyDictionary<string, string>,
            agent: this.Request.Agent.ToAgentId(),
            createdAt: this._createdAt,
            status: status,
            output: outputs ?? Array.Empty<ItemResource>(),
            usage: this._latestUsage
        );
    }

    private void SetUsage(ResponseUsage usage)
    {
        if (this._latestUsage == null)
        {
            this._latestUsage = usage;
            return;
        }

        this._latestUsage = AzureAIAgentsModelFactory.ResponseUsage(
            inputTokens: usage.InputTokens + this._latestUsage.InputTokens,
            inputTokensDetails: AzureAIAgentsModelFactory.ResponseUsageInputTokensDetails(
                cachedTokens: usage.InputTokensDetails.CachedTokens + this._latestUsage.InputTokensDetails.CachedTokens),
            outputTokens: usage.OutputTokens + this._latestUsage.OutputTokens,
            outputTokensDetails: AzureAIAgentsModelFactory.ResponseUsageOutputTokensDetails(
                reasoningTokens: usage.OutputTokensDetails.ReasoningTokens + this._latestUsage.OutputTokensDetails.ReasoningTokens),
            totalTokens: usage.TotalTokens + this._latestUsage.TotalTokens);
    }
}
