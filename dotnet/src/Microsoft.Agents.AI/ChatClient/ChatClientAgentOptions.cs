// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents metadata for a chat client agent, including its identifier, name, instructions, and description.
/// </summary>
/// <remarks>
/// This class is used to encapsulate information about a chat client agent, such as its unique
/// identifier, display name, operational instructions, and a descriptive summary. It can be used to store and transfer
/// agent-related metadata within a chat application.
/// </remarks>
public sealed class ChatClientAgentOptions
{
    /// <summary>
    /// Gets or sets the agent id.
    /// </summary>
    public string? Id { get; set; }

    /// <summary>
    /// Gets or sets the agent name.
    /// </summary>
    public string? Name { get; set; }

    /// <summary>
    /// Gets or sets the agent description.
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// Gets or sets the default chatOptions to use.
    /// </summary>
    public ChatOptions? ChatOptions { get; set; }

    /// <summary>
    /// Gets or sets the <see cref="ChatHistoryProvider"/> instance to use for providing chat history for this agent.
    /// </summary>
    public ChatHistoryProvider? ChatHistoryProvider { get; set; }

    /// <summary>
    /// Gets or sets the list of <see cref="AIContextProvider"/> instances to use for providing additional context for each agent run.
    /// </summary>
    public IEnumerable<AIContextProvider>? AIContextProviders { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether to use the provided <see cref="IChatClient"/> instance as is,
    /// without applying any default decorators.
    /// </summary>
    /// <remarks>
    /// By default the <see cref="ChatClientAgent"/> applies decorators to the provided <see cref="IChatClient"/>
    /// for doing for example automatic function invocation. Setting this property to <see langword="true"/>
    /// disables adding these default decorators.
    /// Disabling is recommended if you want to decorate the <see cref="IChatClient"/> with different decorators
    /// than the default ones. The provided <see cref="IChatClient"/> instance should then already be decorated
    /// with the desired decorators.
    /// </remarks>
    public bool UseProvidedChatClientAsIs { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether to set the <see cref="ChatClientAgent.ChatHistoryProvider"/> to <see langword="null"/>
    /// if the underlying AI service indicates that it manages chat history (for example, by returning a conversation id in the response), but a <see cref="ChatHistoryProvider"/> is configured for the agent.
    /// </summary>
    /// <remarks>
    /// Note that even if this setting is set to <see langword="false"/>, the <see cref="ChatHistoryProvider"/> will still not be used if the underlying AI service indicates that it manages chat history.
    /// </remarks>
    /// <value>
    /// Default is <see langword="true"/>.
    /// </value>
    public bool ClearOnChatHistoryProviderConflict { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether to log a warning if the underlying AI service indicates that it manages chat history
    /// (for example, by returning a conversation id in the response), but a <see cref="ChatHistoryProvider"/> is configured for the agent.
    /// </summary>
    /// <value>
    /// Default is <see langword="true"/>.
    /// </value>
    public bool WarnOnChatHistoryProviderConflict { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether an exception is thrown if the underlying AI service indicates that it manages chat history
    /// (for example, by returning a conversation id in the response), but a <see cref="ChatHistoryProvider"/> is configured for the agent.
    /// </summary>
    /// <value>
    /// Default is <see langword="true"/>.
    /// </value>
    public bool ThrowOnChatHistoryProviderConflict { get; set; } = true;

    /// <summary>
    /// Creates a new instance of <see cref="ChatClientAgentOptions"/> with the same values as this instance.
    /// </summary>
    public ChatClientAgentOptions Clone()
        => new()
        {
            Id = this.Id,
            Name = this.Name,
            Description = this.Description,
            ChatOptions = this.ChatOptions?.Clone(),
            ChatHistoryProvider = this.ChatHistoryProvider,
            AIContextProviders = this.AIContextProviders is null ? null : new List<AIContextProvider>(this.AIContextProviders),
            UseProvidedChatClientAsIs = this.UseProvidedChatClientAsIs,
            ClearOnChatHistoryProviderConflict = this.ClearOnChatHistoryProviderConflict,
            WarnOnChatHistoryProviderConflict = this.WarnOnChatHistoryProviderConflict,
            ThrowOnChatHistoryProviderConflict = this.ThrowOnChatHistoryProviderConflict,
        };
}
