using Azure.AI.AgentsHosting.Ingress.Common;

using AzureAIAgents.Models;

namespace Azure.AI.AgentsHosting.Ingress.Invocation.Stream;

public class NestedResponseGenerator : NestedStreamEventGeneratorBase<AzureAIAgents.Models.Response>
{
    public required string ResponseId { get; init; }

    public required string ConversationId { get; init; }

    public required CreateResponse Request { get; init; }

    public required INestedStreamEventGenerator<IEnumerable<ItemResource>> OutputGenerator { get; init; }

    public Action<Action<ResponseUsage>> SubscribeUsageUpdate
    {
        init => value(SetUsage);
    }

    private readonly DateTimeOffset _createdAt = DateTimeOffset.UtcNow;

    private ResponseUsage? _latestUsage;

    private AzureAIAgents.Models.Response? CompletedResponse { get; set; }

#pragma warning disable CS1998
    public override async IAsyncEnumerable<NestedEventsGroup<AzureAIAgents.Models.Response>> Generate()
    {
        yield return new NestedEventsGroup<AzureAIAgents.Models.Response>()
        {
            CreateAggregate = () => CompletedResponse!,
            Events = GenerateEventsAsync()
        };
    }
#pragma warning restore CS1998

    private async IAsyncEnumerable<ResponseStreamEvent> GenerateEventsAsync()
    {
        yield return AzureAIAgentsModelFactory.ResponseCreatedEvent(Seq.Next(), ToResponse(status: ResponseStatus.InProgress));
        yield return AzureAIAgentsModelFactory.ResponseInProgressEvent(Seq.Next(), ToResponse(status: ResponseStatus.InProgress));

        IList<Func<IEnumerable<ItemResource>>> outputFactories = [];
        await foreach (var group in OutputGenerator.Generate().WithCancellation(CancellationToken).ConfigureAwait(false))
        {
            outputFactories.Add(group.CreateAggregate);
            await foreach(var e in group.Events.WithCancellation(CancellationToken).ConfigureAwait(false))
            {
                yield return e;
            }
        }

        var outputs = outputFactories.SelectMany(f => f());
        CompletedResponse = ToResponse(status: ResponseStatus.Completed, outputs);
        yield return AzureAIAgentsModelFactory.ResponseCompletedEvent(Seq.Next(), CompletedResponse);
    }

    private AzureAIAgents.Models.Response ToResponse(ResponseStatus status = ResponseStatus.Completed, IEnumerable<ItemResource>? outputs = null)
    {
        return AzureAIAgentsModelFactory.Response(
            @object: "response",
            id: ResponseId,
            conversationId: ConversationId,
            metadata: Request.Metadata as IReadOnlyDictionary<string, string>,
            agent: Request.Agent.ToAgentId(),
            createdAt: _createdAt,
            status: status,
            output: outputs ?? Array.Empty<ItemResource>(),
            usage: _latestUsage
        );
    }

    private void SetUsage(ResponseUsage usage)
    {
        if (_latestUsage == null)
        {
            _latestUsage = usage;
            return;
        }

        _latestUsage = AzureAIAgentsModelFactory.ResponseUsage(
            inputTokens: usage.InputTokens + _latestUsage.InputTokens,
            inputTokensDetails: AzureAIAgentsModelFactory.ResponseUsageInputTokensDetails(
                cachedTokens: usage.InputTokensDetails.CachedTokens + _latestUsage.InputTokensDetails.CachedTokens),
            outputTokens: usage.OutputTokens + _latestUsage.OutputTokens,
            outputTokensDetails: AzureAIAgentsModelFactory.ResponseUsageOutputTokensDetails(
                reasoningTokens: usage.OutputTokensDetails.ReasoningTokens + _latestUsage.OutputTokensDetails.ReasoningTokens),
            totalTokens: usage.TotalTokens + _latestUsage.TotalTokens);
    }
}
