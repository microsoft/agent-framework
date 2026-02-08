// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Converters;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;

/// <summary>
/// Represents a message in a chat completion request.
/// </summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "role", UnknownDerivedTypeHandling = JsonUnknownDerivedTypeHandling.FailSerialization)]
[JsonDerivedType(typeof(DeveloperMessage), "developer")]
[JsonDerivedType(typeof(SystemMessage), "system")]
[JsonDerivedType(typeof(UserMessage), "user")]
[JsonDerivedType(typeof(AssistantMessage), "assistant")]
[JsonDerivedType(typeof(ToolMessage), "tool")]
[JsonDerivedType(typeof(FunctionMessage), "function")]
internal abstract record ChatCompletionRequestMessage
{
    /// <summary>
    /// The role of the content.
    /// </summary>
    [JsonIgnore]
    public abstract string Role { get; }

    /// <summary>
    /// The contents of the message.
    /// </summary>
    [JsonPropertyName("content")]
    public required MessageContent Content { get; init; }

    /// <summary>
    /// Converts to a <see cref="ChatMessage"/>.
    /// </summary>
    /// <returns>A <see cref="ChatMessage"/> representing the message.</returns>
    /// <exception cref="InvalidOperationException">Thrown when the content is neither text nor AI contents.</exception>
    public virtual ChatMessage ToChatMessage()
    {
        if (this.Content.IsText)
        {
            return new(ChatRole.User, this.Content.Text);
        }
        else if (this.Content.IsContents)
        {
            var aiContents = this.Content.Contents.Select(MessageContentPartConverter.ToAIContent).Where(c => c is not null).ToList();
            return new ChatMessage(ChatRole.User, aiContents!);
        }

        throw new InvalidOperationException("MessageContent has no value");
    }
}

/// <summary>
/// A developer message in a chat completion request.
/// Developer messages are used to provide instructions to the model at the system level.
/// </summary>
internal sealed record DeveloperMessage : ChatCompletionRequestMessage
{
    /// <inheritdoc/>
    [JsonIgnore]
    public override string Role => "developer";

    /// <summary>
    /// An optional name for the participant.
    /// Provides the model information to differentiate between participants of the same role.
    /// </summary>
    [JsonPropertyName("name")]
    public string? Name { get; init; }
}

/// <summary>
/// A system message in a chat completion request.
/// System messages provide high-level instructions for the conversation.
/// </summary>
internal sealed record SystemMessage : ChatCompletionRequestMessage
{
    /// <inheritdoc/>
    [JsonIgnore]
    public override string Role => "system";

    /// <summary>
    /// An optional name for the participant.
    /// Provides the model information to differentiate between participants of the same role.
    /// </summary>
    [JsonPropertyName("name")]
    public string? Name { get; init; }
}

/// <summary>
/// A user message in a chat completion request.
/// User messages represent input from the end user.
/// </summary>
internal sealed record UserMessage : ChatCompletionRequestMessage
{
    /// <inheritdoc/>
    [JsonIgnore]
    public override string Role => "user";

    /// <summary>
    /// An optional name for the participant.
    /// Provides the model information to differentiate between participants of the same role.
    /// </summary>
    [JsonPropertyName("name")]
    public string? Name { get; init; }
}

/// <summary>
/// An assistant message in a chat completion request.
/// Assistant messages represent previous responses from the model, used in multi-turn conversations.
/// </summary>
internal sealed record AssistantMessage : ChatCompletionRequestMessage
{
    /// <inheritdoc/>
    [JsonIgnore]
    public override string Role => "assistant";

    /// <summary>
    /// An optional name for the participant.
    /// Provides the model information to differentiate between participants of the same role.
    /// </summary>
    [JsonPropertyName("name")]
    public string? Name { get; init; }
}

/// <summary>
/// A tool message in a chat completion request.
/// Tool messages contain the result of a tool call made by the assistant.
/// </summary>
internal sealed record ToolMessage : ChatCompletionRequestMessage
{
    /// <inheritdoc/>
    [JsonIgnore]
    public override string Role => "tool";

    /// <summary>
    /// Tool call that this message is responding to.
    /// </summary>
    [JsonPropertyName("tool_call_id")]
    public required string ToolCallId { get; set; }
}

/// <summary>
/// Deprecated. A function message in a chat completion request.
/// Function messages have been replaced by tool messages.
/// </summary>
internal sealed record FunctionMessage : ChatCompletionRequestMessage
{
    /// <inheritdoc/>
    [JsonIgnore]
    public override string Role => "function";

    /// <summary>
    /// The name of the function to call.
    /// </summary>
    [JsonPropertyName("name")]
    public required string Name { get; init; }

    /// <summary>
    /// Converts to a <see cref="ChatMessage"/>.
    /// </summary>
    /// <returns>A <see cref="ChatMessage"/> representing the message.</returns>
    /// <exception cref="InvalidOperationException">Thrown when the content is not text.</exception>
    public override ChatMessage ToChatMessage()
    {
        if (this.Content.IsText)
        {
            return new(ChatRole.User, this.Content.Text);
        }

        throw new InvalidOperationException("FunctionMessage Content must be text");
    }
}
