// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents a request to run an agent with a specific message and configuration.
/// </summary>
public record RunRequest
{
    /// <summary>
    /// Gets the list of chat messages to send to the agent (for multi-message requests).
    /// </summary>
    public IList<ChatMessage> Messages { get; init; } = [];

    /// <summary>
    /// Gets the optional response format for the agent's response.
    /// </summary>
    public ChatResponseFormat? ResponseFormat { get; init; }

    /// <summary>
    /// Gets whether to enable tool calls for this request.
    /// </summary>
    public bool EnableToolCalls { get; init; } = true;

    /// <summary>
    /// Gets the collection of tool names to enable. If not specified, all tools are enabled.
    /// </summary>
    public IList<string>? EnableToolNames { get; init; }

    /// <summary>
    /// Gets or sets the correlation ID for correlating this request with its response.
    /// </summary>
    [JsonInclude]
    internal string CorrelationId { get; set; } = Guid.NewGuid().ToString("N");

    /// <summary>
    /// Initializes a new instance of the <see cref="RunRequest"/> class for a single message.
    /// </summary>
    /// <param name="message">The message to send to the agent.</param>
    /// <param name="role">The role of the message sender (User or System).</param>
    /// <param name="responseFormat">Optional response format for the agent's response.</param>
    /// <param name="enableToolCalls">Whether to enable tool calls for this request.</param>
    /// <param name="enableToolNames">Optional collection of tool names to enable. If not specified, all tools are enabled.</param>
    public RunRequest(
        string message,
        ChatRole? role = null,
        ChatResponseFormat? responseFormat = null,
        bool enableToolCalls = true,
        IList<string>? enableToolNames = null)
        : this([new ChatMessage(role ?? ChatRole.User, message) { CreatedAt = DateTimeOffset.UtcNow }], responseFormat, enableToolCalls, enableToolNames)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="RunRequest"/> class for multiple messages.
    /// </summary>
    /// <param name="messages">The list of chat messages to send to the agent.</param>
    /// <param name="responseFormat">Optional response format for the agent's response.</param>
    /// <param name="enableToolCalls">Whether to enable tool calls for this request.</param>
    /// <param name="enableToolNames">Optional collection of tool names to enable. If not specified, all tools are enabled.</param>
    [JsonConstructor]
    public RunRequest(
        IList<ChatMessage> messages,
        ChatResponseFormat? responseFormat = null,
        bool enableToolCalls = true,
        IList<string>? enableToolNames = null)
    {
        this.Messages = messages;
        this.ResponseFormat = responseFormat;
        this.EnableToolCalls = enableToolCalls;
        this.EnableToolNames = enableToolNames;
    }
}
