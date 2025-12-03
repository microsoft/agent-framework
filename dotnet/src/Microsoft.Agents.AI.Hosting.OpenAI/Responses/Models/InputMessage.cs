// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// A message input to the model with a role indicating instruction following hierarchy.
/// Aligns with the OpenAI Responses API InputMessage/EasyInputMessage schema.
/// </summary>
internal sealed class InputMessage
{
    /// <summary>
    /// The role of the message input. One of user, assistant, system, or developer.
    /// </summary>
    [JsonPropertyName("role")]
    public required ChatRole Role { get; init; }

    /// <summary>
    /// Text, image, or audio input to the model, used to generate a response.
    /// Can be a simple string or a list of content items with different types.
    /// </summary>
    [JsonPropertyName("content")]
    public required InputMessageContent Content { get; init; }

    /// <summary>
    /// The type of the message input. Always "message".
    /// </summary>
    [JsonPropertyName("type")]
    public string Type => "message";

    /// <summary>
    /// Converts this InputMessage to a ChatMessage.
    /// </summary>
    public ChatMessage ToChatMessage()
    {
        if (this.Content.IsText)
        {
            return new ChatMessage(this.Role, this.Content.Text);
        }
        else if (this.Content.IsContents)
        {
            // Convert ItemContent to AIContent
            var aiContents = this.Content.Contents!.Select(ItemContentConverter.ToAIContent).Where(c => c is not null).ToList();
            return new ChatMessage(this.Role, aiContents!);
        }

        throw new InvalidOperationException("InputMessageContent has no value");
    }
}
