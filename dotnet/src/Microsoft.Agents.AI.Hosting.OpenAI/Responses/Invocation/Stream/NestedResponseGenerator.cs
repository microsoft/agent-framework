// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Common;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Invocation.Stream;

/// <summary>
/// Generates nested response events from agent outputs.
/// </summary>
internal sealed class NestedResponseGenerator : INestedStreamEventGenerator<Response>
{
    /// <summary>
    /// Gets the sequence number generator.
    /// </summary>
    public ISequenceNumber Seq { get; }

    /// <summary>
    /// Gets the response ID.
    /// </summary>
    public string ResponseId { get; }

    /// <summary>
    /// Gets the conversation ID.
    /// </summary>
    public string ConversationId { get; }

    /// <summary>
    /// Gets the create response request.
    /// </summary>
    public CreateResponse Request { get; }

    /// <summary>
    /// Gets the output generator.
    /// </summary>
    public INestedStreamEventGenerator<IEnumerable<ItemResource>> OutputGenerator { get; }

    private readonly DateTimeOffset _createdAt = DateTimeOffset.UtcNow;

    /// <summary>
    /// Initializes a new instance of the <see cref="NestedResponseGenerator"/> class.
    /// </summary>
    /// <param name="seq">The sequence number generator.</param>
    /// <param name="responseId">The response ID.</param>
    /// <param name="conversationId">The conversation ID.</param>
    /// <param name="request">The create response request.</param>
    /// <param name="outputGenerator">The output generator.</param>
    /// <param name="subscribeUsageUpdate">The action to subscribe to usage updates.</param>
    public NestedResponseGenerator(
        ISequenceNumber seq,
        string responseId,
        string conversationId,
        CreateResponse request,
        INestedStreamEventGenerator<IEnumerable<ItemResource>> outputGenerator,
        Action<Action<ResponseUsage>> subscribeUsageUpdate)
    {
        this.Seq = seq;
        this.ResponseId = responseId;
        this.ConversationId = conversationId;
        this.Request = request;
        this.OutputGenerator = outputGenerator;
        subscribeUsageUpdate(this.SetUsage);
    }

    private ResponseUsage? _latestUsage;

    private Response? CompletedResponse { get; set; }

#pragma warning disable CS1998
    /// <inheritdoc/>
    public async IAsyncEnumerable<NestedEventsGroup<Response>> GenerateAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        yield return new NestedEventsGroup<Response>()
        {
            CreateAggregate = () => this.CompletedResponse!,
            Events = this.GenerateEventsAsync(cancellationToken)
        };
    }
#pragma warning restore CS1998

    private async IAsyncEnumerable<StreamingResponseEvent> GenerateEventsAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        yield return new StreamingResponseCreated { SequenceNumber = this.Seq.GetNext(), Response = this.ToResponse(status: ResponseStatus.InProgress) };
        yield return new StreamingResponseInProgress { SequenceNumber = this.Seq.GetNext(), Response = this.ToResponse(status: ResponseStatus.InProgress) };

        IList<Func<IEnumerable<ItemResource>>> outputFactories = [];
        await foreach (var group in this.OutputGenerator.GenerateAsync(cancellationToken).ConfigureAwait(false))
        {
            cancellationToken.ThrowIfCancellationRequested();
            outputFactories.Add(group.CreateAggregate);
            await foreach (var e in group.Events.WithCancellation(cancellationToken).ConfigureAwait(false))
            {
                cancellationToken.ThrowIfCancellationRequested();
                yield return e;
            }
        }

        var outputs = outputFactories.SelectMany(f => f());
        this.CompletedResponse = this.ToResponse(status: ResponseStatus.Completed, outputs);
        yield return new StreamingResponseCompleted { SequenceNumber = this.Seq.GetNext(), Response = this.CompletedResponse };
    }

    private Response ToResponse(ResponseStatus status = ResponseStatus.Completed, IEnumerable<ItemResource>? outputs = null)
    {
        return new Response
        {
            Id = this.ResponseId,
            CreatedAt = this._createdAt.ToUnixTimeSeconds(),
            Model = this.Request.Agent?.Name ?? this.Request.Model ?? "unknown",
            Status = status,
            Agent = this.Request.Agent?.ToAgentId(),
            Conversation = new ConversationReference { Id = this.ConversationId },
            Metadata = this.Request.Metadata != null ? new Dictionary<string, string>(this.Request.Metadata) : null,
            Output = outputs?.ToList() ?? [],
            Usage = this._latestUsage,
            ParallelToolCalls = true,
            Tools = []
        };
    }

    private void SetUsage(ResponseUsage usage)
    {
        if (this._latestUsage == null)
        {
            this._latestUsage = usage;
            return;
        }

        this._latestUsage = new ResponseUsage
        {
            InputTokens = usage.InputTokens + this._latestUsage.InputTokens,
            InputTokensDetails = new InputTokensDetails
            {
                CachedTokens = usage.InputTokensDetails.CachedTokens + this._latestUsage.InputTokensDetails.CachedTokens
            },
            OutputTokens = usage.OutputTokens + this._latestUsage.OutputTokens,
            OutputTokensDetails = new OutputTokensDetails
            {
                ReasoningTokens = usage.OutputTokensDetails.ReasoningTokens + this._latestUsage.OutputTokensDetails.ReasoningTokens
            },
            TotalTokens = usage.TotalTokens + this._latestUsage.TotalTokens
        };
    }
}
