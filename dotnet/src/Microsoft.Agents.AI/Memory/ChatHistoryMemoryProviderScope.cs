// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Allows scoping of chat history for the <see cref="ChatHistoryMemoryProvider"/>.
/// </summary>
public sealed class ChatHistoryMemoryProviderScope
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ChatHistoryMemoryProviderScope"/> class.
    /// </summary>
    public ChatHistoryMemoryProviderScope() { }

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatHistoryMemoryProviderScope"/> class by cloning an existing scope.
    /// </summary>
    /// <param name="sourceScope">The scope to clone.</param>
    public ChatHistoryMemoryProviderScope(ChatHistoryMemoryProviderScope sourceScope)
    {
        Throw.IfNull(sourceScope);

        this.ApplicationId = sourceScope.ApplicationId;
        this.AgentId = sourceScope.AgentId;
        this.ThreadId = sourceScope.ThreadId;
        this.UserId = sourceScope.UserId;
    }

    /// <summary>
    /// Gets or sets an optional ID for the application to scope chat history to.
    /// </summary>
    /// <remarks>If not set, the scope of the chat history will span all applications.</remarks>
    public string? ApplicationId { get; set; }

    /// <summary>
    /// Gets or sets an optional ID for the agent to scope chat history to.
    /// </summary>
    /// <remarks>If not set, the scope of the chat history will span all agents.</remarks>
    public string? AgentId { get; set; }

    /// <summary>
    /// Gets or sets an optional ID for the thread to scope chat history to.
    /// </summary>
    public string? ThreadId { get; set; }

    /// <summary>
    /// Gets or sets an optional ID for the user to scope chat history to.
    /// </summary>
    /// <remarks>If not set, the scope of the chat history will span all users.</remarks>
    public string? UserId { get; set; }
}
