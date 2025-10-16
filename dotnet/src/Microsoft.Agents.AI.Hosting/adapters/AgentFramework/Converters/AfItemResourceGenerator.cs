// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text;
using System.Threading.Tasks;
using Azure.AI.AgentsHosting.Ingress.Common;
using Azure.AI.AgentsHosting.Ingress.Common.Id;
using Azure.AI.AgentsHosting.Ingress.Invocation;
using Azure.AI.AgentsHosting.Ingress.Invocation.Stream;
using AzureAIAgents.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Converters;

/// <summary>
/// Generates item resources from agent run response updates.
/// </summary>
public class AfItemResourceGenerator
    : NestedChunkedUpdatingGeneratorBase<IEnumerable<ItemResource>, AgentRunResponseUpdate>
{
    /// <summary>
    /// Gets the context in which the agent invocation is executed.
    /// </summary>
    public required AgentInvocationContext Context { get; init; }

    /// <summary>
    /// Gets or sets the action to be invoked when there is an update on usage.
    /// </summary>
    public Action<ResponseUsage>? NotifyOnUsageUpdate { get; init; }

    /// <summary>
    /// Determines whether the message ID has changed between two agent run response updates.
    /// </summary>
    /// <param name="previous">The previous <see cref="AgentRunResponseUpdate"/> instance to compare.</param>
    /// <param name="current">The current <see cref="AgentRunResponseUpdate"/> instance to compare.</param>
    /// <returns><see langword="true"/> if the message ID of the current update differs from the previous update; otherwise, <see
    /// langword="false"/>.</returns>
    protected override bool Changed(AgentRunResponseUpdate previous, AgentRunResponseUpdate current)
    {
        return previous.MessageId != current.MessageId;
    }

    /// <summary>
    /// Creates a new instance of <see cref="NestedEventsGroup{T}"/> that aggregates items from the specified update
    /// group.
    /// </summary>
    /// <remarks>The method processes the provided <paramref name="updateGroup"/> asynchronously, adding each
    /// item to the aggregate collection.</remarks>
    /// <param name="updateGroup">An asynchronous enumerable of <see cref="AgentRunResponseUpdate"/> objects to process and aggregate into the
    /// group.</param>
    /// <returns>A <see cref="NestedEventsGroup{T}"/> containing the aggregated <see cref="ItemResource"/> items.</returns>
    protected override NestedEventsGroup<IEnumerable<ItemResource>> CreateGroup(
        IAsyncEnumerable<AgentRunResponseUpdate> updateGroup)
    {
        List<ItemResource> items = [];
        return new NestedEventsGroup<IEnumerable<ItemResource>>()
        {
            CreateAggregate = () => items,
            Events = this.GenerateEventsAsync(updateGroup, items.Add)
        };
    }

    private async IAsyncEnumerable<ResponseStreamEvent> GenerateEventsAsync(
        IAsyncEnumerable<AgentRunResponseUpdate> updates,
        Action<ItemResource> onItemResource)
    {
        var p = await this.FlattenContentsAsync(updates).PeekAsync(this.CancellationToken).ConfigureAwait(false);
        if (!p.HasValue)
        {
            yield break;
        }

        var events = p.First.content switch
        {
            FunctionCallContent => this.GenerateFunctionCallEventsAsync(ReadContentsAsync(p.Source), onItemResource),
            FunctionResultContent => this.GenerateFunctionCallOutputEventsAsync(ReadContentsAsync(p.Source), onItemResource),
            TextContent => this.GenerateAssistantMessageEventsAsync(ReadContentsAsync(p.Source), onItemResource),
            _ => null!
        };

        await foreach (var e in events.WithCancellation(this.CancellationToken).ConfigureAwait(false))
        {
            yield return e;
        }
    }

    private static async IAsyncEnumerable<AIContent> ReadContentsAsync(
        IAsyncEnumerable<(AgentRunResponseUpdate update, AIContent content)> contents)
    {
        await foreach (var (_, content) in contents.ConfigureAwait(false))
        {
            yield return content;
        }
    }

    private async IAsyncEnumerable<(AgentRunResponseUpdate update, AIContent content)> FlattenContentsAsync(
        IAsyncEnumerable<AgentRunResponseUpdate> updates)
    {
        await foreach (var update in updates.ConfigureAwait(false))
        {
            foreach (var content in update.Contents)
            {
                switch (content)
                {
                    case UsageContent usageContent:
                        if (this.NotifyOnUsageUpdate != null && usageContent.Details != null)
                        {
                            this.NotifyOnUsageUpdate(usageContent.Details.ToResponseUsage()!);
                        }
                        continue;
                    case FunctionCallContent or FunctionResultContent or TextContent:
                        yield return (update, content);
                        break;
                }
            }
        }
    }

    private async IAsyncEnumerable<ResponseStreamEvent> GenerateFunctionCallEventsAsync(
        IAsyncEnumerable<AIContent> source,
        Action<ItemResource> onItemResource)
    {
        await foreach (var content in source.WithCancellation(this.CancellationToken).ConfigureAwait(false))
        {
            if (content is not FunctionCallContent functionCallContent)
            {
                continue;
            }

            var groupSeq = this.GroupSeq.GetNext();
            var item = functionCallContent.ToFunctionToolCallItemResource(this.Context.IdGenerator.GenerateFunctionCallId());
            onItemResource(item);

            yield return AzureAIAgentsModelFactory.ResponseOutputItemAddedEvent(
                sequenceNumber: this.Seq.GetNext(),
                outputIndex: groupSeq,
                item: item);

            yield return AzureAIAgentsModelFactory.ResponseFunctionCallArgumentsDeltaEvent(
                sequenceNumber: this.Seq.GetNext(),
                itemId: item.Id,
                outputIndex: this.GroupSeq.Current(),
                delta: item.Arguments);

            yield return AzureAIAgentsModelFactory.ResponseFunctionCallArgumentsDoneEvent(
                sequenceNumber: this.Seq.GetNext(),
                itemId: item.Id,
                outputIndex: this.GroupSeq.Current(),
                arguments: item.Arguments);

            yield return AzureAIAgentsModelFactory.ResponseOutputItemDoneEvent(
                sequenceNumber: this.Seq.GetNext(),
                outputIndex: groupSeq,
                item: item);
        }
    }

    private async IAsyncEnumerable<ResponseStreamEvent> GenerateFunctionCallOutputEventsAsync(
        IAsyncEnumerable<AIContent> source,
        Action<ItemResource> onItemResource)
    {
        await foreach (var content in source.WithCancellation(this.CancellationToken).ConfigureAwait(false))
        {
            if (content is not FunctionResultContent functionResultContent)
            {
                continue;
            }

            var groupSeq = this.GroupSeq.GetNext();
            var item = functionResultContent.ToFunctionToolCallOutputItemResource(this.Context.IdGenerator.GenerateFunctionOutputId());
            onItemResource(item);

            yield return AzureAIAgentsModelFactory.ResponseOutputItemAddedEvent(
                sequenceNumber: this.Seq.GetNext(),
                outputIndex: groupSeq,
                item: item);

            yield return AzureAIAgentsModelFactory.ResponseOutputItemDoneEvent(
                sequenceNumber: this.Seq.GetNext(),
                outputIndex: groupSeq,
                item: item);
        }
    }

    private async IAsyncEnumerable<ResponseStreamEvent> GenerateAssistantMessageEventsAsync(
        IAsyncEnumerable<AIContent> source,
        Action<ItemResource> onItemResource)
    {
        var groupSeq = this.GroupSeq.GetNext();
        var itemId = this.Context.IdGenerator.GenerateMessageId();
        var incompleteItem = new ResponsesAssistantMessageItemResource(
            id: itemId,
            status: ResponsesMessageItemResourceStatus.Completed,
            content: []
        );

        yield return AzureAIAgentsModelFactory.ResponseOutputItemAddedEvent(
            sequenceNumber: this.Seq.GetNext(),
            outputIndex: groupSeq,
            item: incompleteItem);

        yield return AzureAIAgentsModelFactory.ResponseContentPartAddedEvent(
            sequenceNumber: this.Seq.GetNext(),
            itemId: itemId,
            outputIndex: groupSeq,
            contentIndex: 0,
            part: new ItemContentOutputText(string.Empty, []));

        var text = new StringBuilder();
        await foreach (var content in source.WithCancellation(this.CancellationToken).ConfigureAwait(false))
        {
            if (content is not TextContent textContent)
            {
                continue;
            }

            text.Append(textContent.Text);
            yield return AzureAIAgentsModelFactory.ResponseTextDeltaEvent(
                sequenceNumber: this.Seq.GetNext(),
                itemId: itemId,
                outputIndex: groupSeq,
                contentIndex: 0,
                delta: textContent.Text
            );
        }

        var itemContent = new ItemContentOutputText(text.ToString(), []);
        yield return AzureAIAgentsModelFactory.ResponseContentPartDoneEvent(
            sequenceNumber: this.Seq.GetNext(),
            itemId: itemId,
            outputIndex: groupSeq,
            contentIndex: 0,
            part: itemContent);

        var itemResource = new ResponsesAssistantMessageItemResource(
            id: itemId,
            status: ResponsesMessageItemResourceStatus.Completed,
            content: [itemContent]
        );
        onItemResource(itemResource);
        yield return AzureAIAgentsModelFactory.ResponseOutputItemDoneEvent(
            sequenceNumber: this.Seq.GetNext(),
            outputIndex: groupSeq,
            item: itemResource);
    }
}
