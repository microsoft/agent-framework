// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Common.Id;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Invocation;

/// <summary>
/// Represents the context for an agent invocation.
/// </summary>
/// <param name="idGenerator">The ID generator.</param>
/// <param name="responseId">The response ID.</param>
/// <param name="conversationId">The conversation ID.</param>
/// <param name="jsonSerializerOptions">The JSON serializer options. If not provided, default options will be used.</param>
internal sealed class AgentInvocationContext(IIdGenerator idGenerator,
    string responseId,
    string conversationId,
    JsonSerializerOptions? jsonSerializerOptions = null)
{
    /// <summary>
    /// Gets the ID generator for this context.
    /// </summary>
    public IIdGenerator IdGenerator { get; } = idGenerator;

    /// <summary>
    /// Gets the response ID.
    /// </summary>
    public string ResponseId { get; } = responseId;

    /// <summary>
    /// Gets the conversation ID.
    /// </summary>
    public string ConversationId { get; } = conversationId;

    /// <summary>
    /// Gets the JSON serializer options.
    /// </summary>
    public JsonSerializerOptions JsonSerializerOptions { get; } = jsonSerializerOptions ?? ResponsesJsonSerializerOptions.Default;
}
