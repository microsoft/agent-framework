// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Represents the context for an agent invocation.
/// </summary>
/// <param name="idGenerator">The ID generator.</param>
/// <param name="jsonSerializerOptions">The JSON serializer options. If not provided, default options will be used.</param>
internal sealed class AgentInvocationContext(IdGenerator idGenerator, JsonSerializerOptions? jsonSerializerOptions = null)
{
    /// <summary>
    /// Gets the ID generator for this context.
    /// </summary>
    public IdGenerator IdGenerator { get; } = idGenerator;

    /// <summary>
    /// Gets the response ID.
    /// </summary>
    public string ResponseId => this.IdGenerator.ResponseId;

    /// <summary>
    /// Gets the conversation ID.
    /// </summary>
    public string ConversationId => this.IdGenerator.ConversationId;

    /// <summary>
    /// Gets the JSON serializer options.
    /// </summary>
    public JsonSerializerOptions JsonSerializerOptions { get; } = jsonSerializerOptions ?? OpenAIHostingJsonUtilities.DefaultOptions;
}
