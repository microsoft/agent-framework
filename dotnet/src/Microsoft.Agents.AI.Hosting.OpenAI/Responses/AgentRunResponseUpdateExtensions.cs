// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Streaming;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Extension methods for <see cref="AgentRunResponseUpdate"/>.
/// </summary>
internal static class AgentRunResponseUpdateExtensions
{
    /// <summary>
    /// Converts a stream of <see cref="AgentRunResponseUpdate"/> to stream of <see cref="StreamingResponseEvent"/>.
    /// </summary>
    /// <param name="updates">The agent run response updates.</param>
    /// <param name="request">The create response request.</param>
    /// <param name="context">The agent invocation context.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>A stream of response events.</returns>
    internal static async IAsyncEnumerable<StreamingResponseEvent> ToStreamingResponseAsync(
        this IAsyncEnumerable<AgentRunResponseUpdate> updates,
        CreateResponse request,
        AgentInvocationContext context,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var seq = new SequenceNumber();
        var createdAt = DateTimeOffset.UtcNow;
        var latestUsage = ResponseUsage.Zero;
        yield return new StreamingResponseCreated { SequenceNumber = seq.Increment(), Response = CreateResponse(status: ResponseStatus.InProgress) };
        yield return new StreamingResponseInProgress { SequenceNumber = seq.Increment(), Response = CreateResponse(status: ResponseStatus.InProgress) };

        var outputIndex = 0;
        List<ItemResource> items = [];
        var updateEnumerator = updates.GetAsyncEnumerator(cancellationToken);
        await using var _ = updateEnumerator.ConfigureAwait(false);

        AgentRunResponseUpdate? previousUpdate = null;
        StreamingEventGenerator? generator = null;
        while (await updateEnumerator.MoveNextAsync().ConfigureAwait(false))
        {
            cancellationToken.ThrowIfCancellationRequested();
            var update = updateEnumerator.Current;

            if (!IsSameMessage(update, previousUpdate))
            {
                // Finalize the current generator when moving to a new message.
                foreach (var evt in generator?.Complete() ?? [])
                {
                    OnEvent(evt);
                    yield return evt;
                }

                generator = null;
                outputIndex++;
                previousUpdate = update;
            }

            using var contentEnumerator = update.Contents.GetEnumerator();
            while (contentEnumerator.MoveNext())
            {
                var content = contentEnumerator.Current;

                // Usage content is handled separately.
                if (content is UsageContent usageContent && usageContent.Details != null)
                {
                    latestUsage += usageContent.Details.ToResponseUsage();
                    continue;
                }

                // Create a new generator if there is no existing one or the existing one does not support the content.
                if (generator?.IsSupported(content) != true)
                {
                    // Finalize the current generator, if there is one.
                    foreach (var evt in generator?.Complete() ?? [])
                    {
                        OnEvent(evt);
                        yield return evt;
                    }

                    // Increment output index when switching generators
                    if (generator is not null)
                    {
                        outputIndex++;
                    }

                    // Create a new generator based on the content type.
                    generator = content switch
                    {
                        TextContent => new AssistantMessageEventGenerator(context.IdGenerator, seq, outputIndex),
                        TextReasoningContent => new TextReasoningContentEventGenerator(context.IdGenerator, seq, outputIndex),
                        FunctionCallContent => new FunctionCallEventGenerator(context.IdGenerator, seq, outputIndex, context.JsonSerializerOptions),
                        FunctionResultContent => new FunctionResultEventGenerator(context.IdGenerator, seq, outputIndex),
                        ErrorContent => new ErrorContentEventGenerator(context.IdGenerator, seq, outputIndex),
                        UriContent uriContent when uriContent.HasTopLevelMediaType("image") => new ImageContentEventGenerator(context.IdGenerator, seq, outputIndex),
                        DataContent dataContent when dataContent.HasTopLevelMediaType("image") => new ImageContentEventGenerator(context.IdGenerator, seq, outputIndex),
                        DataContent dataContent when dataContent.HasTopLevelMediaType("audio") => new AudioContentEventGenerator(context.IdGenerator, seq, outputIndex),
                        HostedFileContent => new HostedFileContentEventGenerator(context.IdGenerator, seq, outputIndex),
                        DataContent => new FileContentEventGenerator(context.IdGenerator, seq, outputIndex),
                        _ => null
                    };

                    // If no generator could be created, skip this content.
                    if (generator is null)
                    {
                        continue;
                    }
                }

                foreach (var evt in generator.ProcessContent(content))
                {
                    OnEvent(evt);
                    yield return evt;
                }
            }
        }

        // Finalize the active generator.
        foreach (var evt in generator?.Complete() ?? [])
        {
            OnEvent(evt);
            yield return evt;
        }

        yield return new StreamingResponseCompleted { SequenceNumber = seq.Increment(), Response = CreateResponse(status: ResponseStatus.Completed, outputs: items) };

        void OnEvent(StreamingResponseEvent evt)
        {
            if (evt is StreamingOutputItemDone itemDone)
            {
                items.Add(itemDone.Item);
            }
        }

        Response CreateResponse(ResponseStatus status = ResponseStatus.Completed, IEnumerable<ItemResource>? outputs = null)
        {
            return new Response
            {
                Id = context.ResponseId,
                CreatedAt = createdAt.ToUnixTimeSeconds(),
                Model = request.Agent?.Name ?? request.Model,
                Status = status,
                Agent = request.Agent?.ToAgentId(),
                Conversation = request.Conversation ?? new ConversationReference { Id = context.ConversationId },
                Metadata = request.Metadata != null ? new Dictionary<string, string>(request.Metadata) : [],
                Instructions = request.Instructions,
                Temperature = request.Temperature ?? 1.0,
                TopP = request.TopP ?? 1.0,
                Output = outputs?.ToList() ?? [],
                Usage = latestUsage,
                ParallelToolCalls = request.ParallelToolCalls ?? true,
                Tools = [.. request.Tools ?? []],
                ToolChoice = request.ToolChoice,
                ServiceTier = request.ServiceTier ?? "default",
                Store = request.Store ?? true,
                PreviousResponseId = request.PreviousResponseId,
                Reasoning = request.Reasoning,
                Text = request.Text,
                MaxOutputTokens = request.MaxOutputTokens,
                Truncation = request.Truncation,
#pragma warning disable CS0618 // Type or member is obsolete
                User = request.User,
                PromptCacheKey = request.PromptCacheKey,
#pragma warning restore CS0618 // Type or member is obsolete
                SafetyIdentifier = request.SafetyIdentifier,
                TopLogprobs = request.TopLogprobs,
                MaxToolCalls = request.MaxToolCalls,
                Background = request.Background,
                Prompt = request.Prompt,
                Error = null
            };
        }
    }

    private static bool IsSameMessage(AgentRunResponseUpdate? first, AgentRunResponseUpdate? second)
    {
        return IsSameValue(first?.MessageId, second?.MessageId)
            && IsSameValue(first?.AuthorName, second?.AuthorName)
            && IsSameRole(first?.Role, second?.Role);

        static bool IsSameValue(string? str1, string? str2) =>
            str1 is not { Length: > 0 } || str2 is not { Length: > 0 } || str1 == str2;

        static bool IsSameRole(ChatRole? value1, ChatRole? value2) =>
            !value1.HasValue || !value2.HasValue || value1.Value == value2.Value;
    }
}
