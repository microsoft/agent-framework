// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Common;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Common.Id;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Invocation;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Invocation.Stream;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;

/// <summary>
/// Generates item resources from agent run response updates.
/// </summary>
internal sealed class AfItemResourceGenerator
    : INestedStreamEventGenerator<IEnumerable<ItemResource>>
{
    /// <summary>
    /// Gets or sets the sequence number generator.
    /// </summary>
    public required ISequenceNumber Seq { get; init; }

    /// <summary>
    /// Gets or sets the updates to process.
    /// </summary>
    public required IAsyncEnumerable<AgentRunResponseUpdate> Updates { get; init; }

    /// <summary>
    /// Gets the sequence number generator for groups.
    /// </summary>
    private ISequenceNumber GroupSeq { get; } = SequenceNumberFactory.Default;

    /// <summary>
    /// Gets the context in which the agent invocation is executed.
    /// </summary>
    public required AgentInvocationContext Context { get; init; }

    /// <summary>
    /// Gets or sets the action to be invoked when there is an update on usage.
    /// </summary>
    public Action<ResponseUsage>? NotifyOnUsageUpdate { get; init; }

    /// <inheritdoc/>
    public async IAsyncEnumerable<NestedEventsGroup<IEnumerable<ItemResource>>> GenerateAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await foreach (var updateGroup in this.Updates.ChunkOnChangeAsync(this.IsChanged, cancellationToken: cancellationToken).ConfigureAwait(false))
        {
            cancellationToken.ThrowIfCancellationRequested();
            yield return this.CreateGroup(updateGroup);
        }
    }

    private bool IsChanged(AgentRunResponseUpdate? previous, AgentRunResponseUpdate? current) => previous != null && current != null && this.Changed(previous, current);

    /// <summary>
    /// Determines whether the message ID has changed between two agent run response updates.
    /// </summary>
    /// <param name="previous">The previous <see cref="AgentRunResponseUpdate"/> instance to compare.</param>
    /// <param name="current">The current <see cref="AgentRunResponseUpdate"/> instance to compare.</param>
    /// <returns><see langword="true"/> if the message ID of the current update differs from the previous update; otherwise, <see
    /// langword="false"/>.</returns>
    private bool Changed(AgentRunResponseUpdate previous, AgentRunResponseUpdate current)
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
    private NestedEventsGroup<IEnumerable<ItemResource>> CreateGroup(
        IAsyncEnumerable<AgentRunResponseUpdate> updateGroup)
    {
        List<ItemResource> items = [];
        return new NestedEventsGroup<IEnumerable<ItemResource>>()
        {
            CreateAggregate = () => items,
            Events = this.GenerateEventsAsync(updateGroup, items.Add)
        };
    }

    private async IAsyncEnumerable<StreamingResponseEvent> GenerateEventsAsync(
        IAsyncEnumerable<AgentRunResponseUpdate> updates,
        Action<ItemResource> onItemResource,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var p = await this.FlattenContentsAsync(updates, cancellationToken).PeekAsync(cancellationToken).ConfigureAwait(false);
        if (!p.HasValue)
        {
            yield break;
        }

        var events = p.First.Content switch
        {
            FunctionCallContent => this.GenerateFunctionCallEventsAsync(ReadContentsAsync(p.Source, cancellationToken), onItemResource, cancellationToken),
            FunctionResultContent => this.GenerateFunctionCallOutputEventsAsync(ReadContentsAsync(p.Source, cancellationToken), onItemResource, cancellationToken),
            TextContent => this.GenerateAssistantMessageEventsAsync(ReadContentsAsync(p.Source, cancellationToken), onItemResource, cancellationToken),
            _ => null
        };

        if (events is not null)
        {
            await foreach (var e in events.WithCancellation(cancellationToken).ConfigureAwait(false))
            {
                yield return e;
            }
        }
    }

    private static async IAsyncEnumerable<AIContent> ReadContentsAsync(
        IAsyncEnumerable<(AgentRunResponseUpdate update, AIContent content)> contents,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await foreach (var (_, content) in contents.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            yield return content;
        }
    }

    private async IAsyncEnumerable<(AgentRunResponseUpdate Update, AIContent Content)> FlattenContentsAsync(
        IAsyncEnumerable<AgentRunResponseUpdate> updates,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await foreach (var update in updates.WithCancellation(cancellationToken).ConfigureAwait(false))
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

    private async IAsyncEnumerable<StreamingResponseEvent> GenerateFunctionCallEventsAsync(
        IAsyncEnumerable<AIContent> source,
        Action<ItemResource> onItemResource,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await foreach (var content in source.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            if (content is not FunctionCallContent functionCallContent)
            {
                continue;
            }

            var groupSeq = this.GroupSeq.GetNext();
            var item = functionCallContent.ToFunctionToolCallItemResource(this.Context.IdGenerator.GenerateFunctionCallId(), this.Context.JsonSerializerOptions);
            onItemResource(item);

            yield return new StreamingOutputItemAdded
            {
                SequenceNumber = this.Seq.GetNext(),
                OutputIndex = groupSeq,
                Item = item
            };

            yield return new StreamingFunctionCallArgumentsDelta
            {
                SequenceNumber = this.Seq.GetNext(),
                ItemId = item.Id,
                OutputIndex = this.GroupSeq.Current(),
                Delta = item.Arguments
            };

            yield return new StreamingFunctionCallArgumentsDone
            {
                SequenceNumber = this.Seq.GetNext(),
                ItemId = item.Id,
                OutputIndex = this.GroupSeq.Current(),
                Arguments = item.Arguments
            };

            yield return new StreamingOutputItemDone
            {
                SequenceNumber = this.Seq.GetNext(),
                OutputIndex = groupSeq,
                Item = item
            };
        }
    }

    private async IAsyncEnumerable<StreamingResponseEvent> GenerateFunctionCallOutputEventsAsync(
        IAsyncEnumerable<AIContent> source,
        Action<ItemResource> onItemResource,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await foreach (var content in source.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            if (content is not FunctionResultContent functionResultContent)
            {
                continue;
            }

            var groupSeq = this.GroupSeq.GetNext();
            var item = functionResultContent.ToFunctionToolCallOutputItemResource(this.Context.IdGenerator.GenerateFunctionOutputId());
            onItemResource(item);

            yield return new StreamingOutputItemAdded
            {
                SequenceNumber = this.Seq.GetNext(),
                OutputIndex = groupSeq,
                Item = item
            };

            yield return new StreamingOutputItemDone
            {
                SequenceNumber = this.Seq.GetNext(),
                OutputIndex = groupSeq,
                Item = item
            };
        }
    }

    private async IAsyncEnumerable<StreamingResponseEvent> GenerateAssistantMessageEventsAsync(
        IAsyncEnumerable<AIContent> source,
        Action<ItemResource> onItemResource,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var groupSeq = this.GroupSeq.GetNext();
        var itemId = this.Context.IdGenerator.GenerateMessageId();
        var incompleteItem = new ResponsesAssistantMessageItemResource(
            id: itemId,
            status: ResponsesMessageItemResourceStatus.InProgress,
            content: []
        );

        yield return new StreamingOutputItemAdded
        {
            SequenceNumber = this.Seq.GetNext(),
            OutputIndex = groupSeq,
            Item = incompleteItem
        };

        yield return new StreamingContentPartAdded
        {
            SequenceNumber = this.Seq.GetNext(),
            ItemId = itemId,
            OutputIndex = groupSeq,
            ContentIndex = 0,
            Part = new ItemContentOutputText(string.Empty, [])
        };

        var text = new StringBuilder();
        await foreach (var content in source.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            if (content is not TextContent textContent)
            {
                continue;
            }

            text.Append(textContent.Text);
            yield return new StreamingOutputTextDelta
            {
                SequenceNumber = this.Seq.GetNext(),
                ItemId = itemId,
                OutputIndex = groupSeq,
                ContentIndex = 0,
                Delta = textContent.Text
            };
        }

        var itemContent = new ItemContentOutputText(text.ToString(), []);
        yield return new StreamingContentPartDone
        {
            SequenceNumber = this.Seq.GetNext(),
            ItemId = itemId,
            OutputIndex = groupSeq,
            ContentIndex = 0,
            Part = itemContent
        };

        var itemResource = new ResponsesAssistantMessageItemResource(
            id: itemId,
            status: ResponsesMessageItemResourceStatus.Completed,
            content: [itemContent]
        );
        onItemResource(itemResource);
        yield return new StreamingOutputItemDone
        {
            SequenceNumber = this.Seq.GetNext(),
            OutputIndex = groupSeq,
            Item = itemResource
        };
    }
}
