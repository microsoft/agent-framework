// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

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
    /// Gets or sets a value indicating whether the <see cref="ChatClientAgent"/> should persist
    /// chat history after each individual service call within the <see cref="FunctionInvokingChatClient"/>
    /// loop, rather than at the end of the full agent run.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When set to <see langword="true"/>, a <see cref="PerServiceCallChatHistoryPersistingChatClient"/>
    /// decorator becomes active in the chat client pipeline. It handles two complementary scenarios:
    /// </para>
    /// <list type="bullet">
    /// <item>
    /// <term>Framework-managed chat history</term>
    /// <description>
    /// The decorator loads history from the <see cref="ChatHistoryProvider"/> before each service call
    /// and persists new request and response messages after each call. It returns a sentinel
    /// <see cref="ChatOptions.ConversationId"/> on the response, causing the
    /// <see cref="FunctionInvokingChatClient"/> to treat the conversation as service-managed — clearing
    /// accumulated history between iterations and not injecting duplicate <see cref="FunctionCallContent"/>
    /// during approval-response processing.
    /// </description>
    /// </item>
    /// <item>
    /// <term>AI Service-stored chat history</term>
    /// <description>
    /// When the service manages its own chat history (returning a real <see cref="ChatOptions.ConversationId"/>),
    /// the decorator updates <see cref="ChatClientAgentSession.ConversationId"/> after each service call so
    /// that intermediate ConversationId changes are captured immediately. For some services (e.g., the
    /// Conversations API with the Responses API), there is only one thread with one ID, so every service
    /// call updates it anyway and updating the <see cref="ChatClientAgentSession.ConversationId"/> has little effect
    /// since it's the same ID. For other services (e.g., Responses API with Response IDs), a new ID is generated
    /// with each service call, so updating the <see cref="ChatClientAgentSession.ConversationId"/> ensures that the
    /// latest ID is always captured, even mid-run.
    /// Enabling this option ensures consistent per-service-call behavior across all service types.
    /// </description>
    /// </item>
    /// </list>
    /// <para>
    /// When set to <see langword="false"/> (the default), the <see cref="ChatClientAgent"/> handles
    /// chat history persistence at the end of the full agent run via the <see cref="ChatHistoryProvider"/> if using
    /// framework-managed chat history. For AI service-stored chat history, the <see cref="ChatClientAgentSession.ConversationId"/>
    /// updates happen only at the end of the run.
    /// </para>
    /// <para>
    /// When setting the <see cref="UseProvidedChatClientAsIs"/> setting to <see langword="true"/> and
    /// <see cref="RequirePerServiceCallChatHistoryPersistence"/> to <see langword="true"/>, ensure that your custom chat client stack includes a
    /// <see cref="PerServiceCallChatHistoryPersistingChatClient"/> to enable per-service-call persistence.
    /// If no <see cref="PerServiceCallChatHistoryPersistingChatClient"/> is provided, and you are not storing chat history via other means,
    /// no chat history may be stored.
    /// When using a custom chat client stack, you can add a <see cref="PerServiceCallChatHistoryPersistingChatClient"/>
    /// manually via the <see cref="ChatClientBuilderExtensions.UsePerServiceCallChatHistoryPersistence"/>
    /// extension method.
    /// </para>
    /// </remarks>
    /// <value>
    /// Default is <see langword="false"/>.
    /// </value>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public bool RequirePerServiceCallChatHistoryPersistence { get; set; }

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
            RequirePerServiceCallChatHistoryPersistence = this.RequirePerServiceCallChatHistoryPersistence,
        };
}
