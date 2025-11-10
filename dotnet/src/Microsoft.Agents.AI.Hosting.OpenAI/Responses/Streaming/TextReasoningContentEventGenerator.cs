// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Streaming;

/// <summary>
/// A state machine for generating streaming events from reasoning text content.
/// Processes TextReasoningContent instances one at a time and emits appropriate streaming events based on internal state.
/// </summary>
internal sealed class TextReasoningContentEventGenerator(
        IdGenerator idGenerator,
        SequenceNumber seq,
        int outputIndex) : StreamingEventGenerator
{
    private State _currentState = State.Initial;
    private readonly string _itemId = idGenerator.GenerateReasoningId();
    private readonly StringBuilder _text = new();
    private const int SummaryIndex = 0; // Summary index for reasoning summary text

    /// <summary>
    /// Represents the state of the event generator.
    /// </summary>
    private enum State
    {
        Initial,
        AccumulatingText,
        Completed
    }

    public override bool IsSupported(AIContent content) => content is TextReasoningContent;

    public override IEnumerable<StreamingResponseEvent> ProcessContent(AIContent content)
    {
        if (this._currentState == State.Completed)
        {
            throw new InvalidOperationException("Cannot process content after the generator has been completed.");
        }

        // Only process TextReasoningContent
        if (content is not TextReasoningContent reasoningContent)
        {
            yield break;
        }

        // If is the first content, emit initial events
        if (this._currentState == State.Initial)
        {
            var incompleteItem = new ReasoningItemResource
            {
                Id = this._itemId,
                Status = "in_progress"
            };

            yield return new StreamingOutputItemAdded
            {
                SequenceNumber = seq.Increment(),
                OutputIndex = outputIndex,
                Item = incompleteItem
            };

            this._currentState = State.AccumulatingText;
        }

        // Accumulate text and emit delta event
        this._text.Append(reasoningContent.Text);

        yield return new StreamingReasoningSummaryTextDelta
        {
            SequenceNumber = seq.Increment(),
            ItemId = this._itemId,
            OutputIndex = outputIndex,
            SummaryIndex = SummaryIndex,
            Delta = reasoningContent.Text
        };
    }

    public override IEnumerable<StreamingResponseEvent> Complete()
    {
        if (this._currentState == State.Completed)
        {
            throw new InvalidOperationException("Complete has already been called.");
        }

        // If no content was processed, emit initial events first
        if (this._currentState == State.Initial)
        {
            yield break;
        }

        // Emit final events
        var finalText = this._text.ToString();

        yield return new StreamingReasoningSummaryTextDone
        {
            SequenceNumber = seq.Increment(),
            ItemId = this._itemId,
            OutputIndex = outputIndex,
            SummaryIndex = SummaryIndex,
            Text = finalText
        };

        yield return new StreamingOutputItemDone
        {
            SequenceNumber = seq.Increment(),
            OutputIndex = outputIndex,
            Item = new ReasoningItemResource
            {
                Id = this._itemId,
                Status = "completed"
            }
        };

        this._currentState = State.Completed;
    }
}
