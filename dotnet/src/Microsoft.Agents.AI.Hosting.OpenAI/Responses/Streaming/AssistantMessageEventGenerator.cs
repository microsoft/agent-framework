// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Streaming;

/// <summary>
/// A state machine for generating streaming events from assistant message content.
/// Processes AIContent instances one at a time and emits appropriate streaming events based on internal state.
/// </summary>
internal sealed class AssistantMessageEventGenerator(
        IdGenerator idGenerator,
        SequenceNumber seq,
        int outputIndex) : StreamingEventGenerator
{
    private State _currentState = State.Initial;
    private readonly string _itemId = idGenerator.GenerateMessageId();
    private readonly StringBuilder _text = new();
    private readonly List<JsonElement> _annotations = [];

    /// <summary>
    /// Represents the state of the event generator.
    /// </summary>
    private enum State
    {
        Initial,
        AccumulatingText,
        Completed
    }

    public override bool IsSupported(AIContent content) => content is TextContent;

    public override IEnumerable<StreamingResponseEvent> ProcessContent(AIContent content)
    {
        if (this._currentState == State.Completed)
        {
            throw new InvalidOperationException("Cannot process content after the generator has been completed.");
        }

        // Annotation-only AIContent updates apply only to an already active text item.
        if (content is not TextContent textContent)
        {
            if (this._currentState == State.AccumulatingText)
            {
                foreach (StreamingResponseEvent evt in this.EmitAnnotations(content, textOffset: 0))
                {
                    yield return evt;
                }
            }

            yield break;
        }

        // If is the first content, emit initial events
        if (this._currentState == State.Initial)
        {
            var incompleteItem = new ResponsesAssistantMessageItemResource
            {
                Id = this._itemId,
                Status = ResponsesMessageItemResourceStatus.InProgress,
                Content = []
            };

            yield return new StreamingOutputItemAdded
            {
                SequenceNumber = seq.Increment(),
                OutputIndex = outputIndex,
                Item = incompleteItem
            };

            yield return new StreamingContentPartAdded
            {
                SequenceNumber = seq.Increment(),
                ItemId = this._itemId,
                OutputIndex = outputIndex,
                ContentIndex = 0,
                Part = new ItemContentOutputText { Text = string.Empty, Annotations = [], Logprobs = [] }
            };

            this._currentState = State.AccumulatingText;
        }

        // Capture the current item offset before appending this content's text.
        int textOffset = this._text.Length;

        // Accumulate text and emit delta event
        this._text.Append(textContent.Text);

        yield return new StreamingOutputTextDelta
        {
            SequenceNumber = seq.Increment(),
            ItemId = this._itemId,
            OutputIndex = outputIndex,
            ContentIndex = 0,
            Delta = textContent.Text
        };

        foreach (StreamingResponseEvent evt in this.EmitAnnotations(textContent, textOffset))
        {
            yield return evt;
        }
    }

    private IEnumerable<StreamingResponseEvent> EmitAnnotations(AIContent content, int textOffset)
    {
        foreach (JsonElement annotation in ItemContentConverter.ToAnnotations(content, textOffset))
        {
            bool isDuplicate = false;
            foreach (JsonElement existingAnnotation in this._annotations)
            {
                if (string.Equals(existingAnnotation.GetRawText(), annotation.GetRawText(), StringComparison.Ordinal))
                {
                    isDuplicate = true;
                    break;
                }
            }

            if (isDuplicate)
            {
                continue;
            }

            int annotationIndex = this._annotations.Count;
            this._annotations.Add(annotation);
            yield return new StreamingOutputTextAnnotationAdded
            {
                SequenceNumber = seq.Increment(),
                ItemId = this._itemId,
                OutputIndex = outputIndex,
                ContentIndex = 0,
                AnnotationIndex = annotationIndex,
                Annotation = annotation
            };
        }
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
        var itemContent = new ItemContentOutputText
        {
            Text = finalText,
            Annotations = [.. this._annotations],
            Logprobs = []
        };

        // Emit response.output_text.done event
        yield return new StreamingOutputTextDone
        {
            SequenceNumber = seq.Increment(),
            ItemId = this._itemId,
            OutputIndex = outputIndex,
            ContentIndex = 0,
            Text = finalText
        };

        yield return new StreamingContentPartDone
        {
            SequenceNumber = seq.Increment(),
            ItemId = this._itemId,
            OutputIndex = outputIndex,
            ContentIndex = 0,
            Part = itemContent
        };

        yield return new StreamingOutputItemDone
        {
            SequenceNumber = seq.Increment(),
            OutputIndex = outputIndex,
            Item = new ResponsesAssistantMessageItemResource
            {
                Id = this._itemId,
                Status = ResponsesMessageItemResourceStatus.Completed,
                Content = [itemContent]
            }
        };

        this._currentState = State.Completed;
    }
}
