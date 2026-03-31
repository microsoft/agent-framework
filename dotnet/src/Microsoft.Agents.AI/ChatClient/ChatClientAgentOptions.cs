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
    /// Gets or sets a value indicating whether the <see cref="ChatClientAgent"/> should simulate
    /// service-stored chat history behavior using its configured <see cref="ChatHistoryProvider"/>.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When set to <see langword="true"/>, a <see cref="ServiceStoredSimulatingChatClient"/> decorator is
    /// injected between the <see cref="FunctionInvokingChatClient"/> and the leaf <see cref="IChatClient"/>
    /// in the chat client pipeline. This decorator takes full ownership of the chat history lifecycle:
    /// it loads history from the <see cref="ChatHistoryProvider"/> before each service call and persists
    /// new messages after each service call. It also returns a sentinel <see cref="ChatOptions.ConversationId"/>
    /// on the response, causing the <see cref="FunctionInvokingChatClient"/> to treat the conversation
    /// as service-managed — clearing accumulated history and not injecting duplicate
    /// <see cref="FunctionCallContent"/> during approval-response processing.
    /// </para>
    /// <para>
    /// This mode aligns the behavior of framework-managed chat history with service-stored chat history,
    /// ensuring consistency in how messages are stored and loaded, including during function calling loops
    /// and tool-call termination scenarios.
    /// </para>
    /// <para>
    /// When set to <see langword="false"/> (the default), the <see cref="ChatClientAgent"/> handles
    /// chat history persistence at the end of the full agent run via the <see cref="ChatHistoryProvider"/>
    /// pipeline.
    /// </para>
    /// <para>
    /// When setting the <see cref="UseProvidedChatClientAsIs"/> setting to <see langword="true"/> and
    /// <see cref="SimulateServiceStoredChatHistory"/> to <see langword="true"/>, ensure that your custom chat client stack includes a
    /// <see cref="ServiceStoredSimulatingChatClient"/> to enable per-service-call persistence.
    /// If no <see cref="ServiceStoredSimulatingChatClient"/> is provided, and you are not storing chat history via other means,
    /// no chat history may be stored.
    /// When using a custom chat client stack, you can add a <see cref="ServiceStoredSimulatingChatClient"/>
    /// manually via the <see cref="ChatClientBuilderExtensions.UseServiceStoredChatHistorySimulation"/>
    /// extension method.
    /// </para>
    /// </remarks>
    /// <value>
    /// Default is <see langword="false"/>.
    /// </value>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public bool SimulateServiceStoredChatHistory { get; set; }

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
            SimulateServiceStoredChatHistory = this.SimulateServiceStoredChatHistory,
        };
}
