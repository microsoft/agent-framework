// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations;

/// <summary>
/// Provides JSON serialization options and context for Conversations API to support AOT and trimming.
/// </summary>
internal static class ConversationsJsonUtilities
{
    /// <summary>
    /// Gets the default <see cref="JsonSerializerOptions"/> instance used for Conversations API serialization.
    /// Includes support for AIContent types and all conversation-related types.
    /// </summary>
    public static JsonSerializerOptions DefaultOptions { get; } = CreateDefaultOptions();

    [UnconditionalSuppressMessage("Trimming", "IL2026:RequiresUnreferencedCode", Justification = "Type info resolver chaining is AOT-safe.")]
    [UnconditionalSuppressMessage("AOT", "IL3050:RequiresDynamicCode", Justification = "Type info resolver chaining is AOT-safe.")]
    private static JsonSerializerOptions CreateDefaultOptions()
    {
        // Start with our source-generated context
        JsonSerializerOptions options = new(ConversationsJsonContext.Default.Options);

        // Chain with AIContent types from Microsoft.Extensions.AI
        options.TypeInfoResolverChain.Add(AIJsonUtilities.DefaultOptions.TypeInfoResolver!);

        options.MakeReadOnly();
        return options;
    }
}

/// <summary>
/// Provides a JSON serialization context for Conversations API to support AOT and trimming.
/// </summary>
[JsonSourceGenerationOptions(
    PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
[JsonSerializable(typeof(Conversation))]
[JsonSerializable(typeof(ConversationItem))]
[JsonSerializable(typeof(ConversationListResponse))]
[JsonSerializable(typeof(CreateConversationRequest))]
[JsonSerializable(typeof(CreateItemsRequest))]
[JsonSerializable(typeof(CreateItemsResponse))]
[JsonSerializable(typeof(UpdateConversationRequest))]
[JsonSerializable(typeof(DeleteResponse))]
[JsonSerializable(typeof(ListResponse<ConversationItem>))]
[JsonSerializable(typeof(ErrorResponse))]
[JsonSerializable(typeof(List<Conversation>))]
[JsonSerializable(typeof(List<ConversationItem>))]
[JsonSerializable(typeof(Dictionary<string, string>))]
[JsonSerializable(typeof(Dictionary<string, object>))]
[JsonSerializable(typeof(Dictionary<string, object>[]))]
[JsonSerializable(typeof(List<Dictionary<string, object>>))]
[JsonSerializable(typeof(object))]
internal sealed partial class ConversationsJsonContext : JsonSerializerContext;

/// <summary>
/// Represents an error response from the Conversations API.
/// </summary>
internal sealed class ErrorResponse
{
    /// <summary>
    /// Gets or sets the error details.
    /// </summary>
    [JsonPropertyName("error")]
    public required ErrorDetails Error { get; init; }
}

/// <summary>
/// Represents the details of an error.
/// </summary>
internal sealed class ErrorDetails
{
    /// <summary>
    /// Gets or sets the error message.
    /// </summary>
    [JsonPropertyName("message")]
    public required string Message { get; init; }

    /// <summary>
    /// Gets or sets the error type.
    /// </summary>
    [JsonPropertyName("type")]
    public required string Type { get; init; }
}
