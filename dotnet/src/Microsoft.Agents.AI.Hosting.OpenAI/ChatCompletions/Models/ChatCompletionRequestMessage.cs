// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Converters;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;

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

    public override ChatMessage ToChatMessage()
    {
        if (this.Content.IsText)
        {
            return new(ChatRole.User, this.Content.Text);
        }

        throw new InvalidOperationException("FunctionMessage Content must be text");
    }
}
