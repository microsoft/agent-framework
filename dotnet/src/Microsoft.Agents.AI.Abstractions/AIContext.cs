// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents additional context information that can be dynamically provided to AI models during agent invocations.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="AIContext"/> serves as a container for contextual information that <see cref="AIContextProvider"/> instances
/// can supply to enhance AI model interactions. This context is merged with
/// the agent's base configuration before being passed to the underlying AI model.
/// </para>
/// <para>
/// The context system enables dynamic, runtime-specific enhancements to agent capabilities including:
/// <list type="bullet">
/// <item><description>Adding relevant background information from knowledge bases</description></item>
/// <item><description>Injecting task-specific instructions or guidelines</description></item>
/// <item><description>Providing specialized tools or functions for the current interaction</description></item>
/// <item><description>Including contextual messages that inform the AI about the current situation</description></item>
/// </list>
/// </para>
/// <para>
/// Context information is transient by default and applies only to the current invocation, however messages
/// added through the <see cref="Messages"/> property will be permanently incorporated into the conversation history.
/// </para>
/// </remarks>
public sealed class AIContext
{
    /// <summary>
    /// Gets or sets additional instructions to provide to the AI model for the current invocation.
    /// </summary>
    /// <value>
    /// Instructions text that will be combined with any existing agent instructions or system prompts,
    /// or <see langword="null"/> if no additional instructions should be provided.
    /// </value>
    /// <remarks>
    /// <para>
    /// These instructions are transient and apply only to the current AI model invocation. They are combined
    /// with any existing agent instructions, system prompts, and conversation history to provide comprehensive
    /// context to the AI model.
    /// </para>
    /// <para>
    /// Instructions can be used to:
    /// <list type="bullet">
    /// <item><description>Provide context-specific behavioral guidance</description></item>
    /// <item><description>Add domain-specific knowledge or constraints</description></item>
    /// <item><description>Modify the agent's persona or response style for the current interaction</description></item>
    /// <item><description>Include situational awareness information</description></item>
    /// </list>
    /// </para>
    /// </remarks>
    public string? Instructions { get; set; }

    /// <summary>
    /// Gets or sets the sequence of messages to use for the current invocation.
    /// </summary>
    /// <value>
    /// A sequence of <see cref="ChatMessage"/> instances to be used for the current invocation,
    /// or <see langword="null"/> if no messages should be used.
    /// </value>
    /// <remarks>
    /// <para>
    /// Unlike <see cref="Instructions"/> and <see cref="Tools"/>, messages added through this property may become
    /// permanent additions to the conversation history.
    /// If chat history is managed by the underlying AI service, these messages will become part of chat history.
    /// If chat history is managed using a <see cref="ChatHistoryProvider"/>, these messages will be passed to the
    /// <see cref="ChatHistoryProvider.InvokedCoreAsync(ChatHistoryProvider.InvokedContext, System.Threading.CancellationToken)"/> method,
    /// and the provider can choose which of these messages to permanently add to the conversation history.
    /// </para>
    /// <para>
    /// This property is useful for:
    /// <list type="bullet">
    /// <item><description>Injecting relevant historical context e.g. memories</description></item>
    /// <item><description>Injecting relevant background information e.g. via Retrieval Augmented Generation</description></item>
    /// <item><description>Adding system messages that provide ongoing context</description></item>
    /// </list>
    /// </para>
    /// </remarks>
    public IEnumerable<ChatMessage>? Messages { get; set; }

    /// <summary>
    /// Gets or sets a sequence of tools or functions to make available to the AI model for the current invocation.
    /// </summary>
    /// <value>
    /// A sequence of <see cref="AITool"/> instances that will be available to the AI model during the current invocation,
    /// or <see langword="null"/> if no additional tools should be provided.
    /// </value>
    /// <remarks>
    /// <para>
    /// These tools are transient and apply only to the current AI model invocation. Any existing tools
    /// are provided as input to the <see cref="AIContextProvider"/> instances, so context providers can choose to modify or replace the existing tools
    /// as needed based on the current context. The resulting set of tools is then passed to the underlying AI model, which may choose to utilize them when generating responses.
    /// </para>
    /// <para>
    /// Context-specific tools enable:
    /// <list type="bullet">
    /// <item><description>Providing specialized functions based on user intent or conversation context</description></item>
    /// <item><description>Adding domain-specific capabilities for particular types of queries</description></item>
    /// <item><description>Enabling access to external services or data sources relevant to the current task</description></item>
    /// <item><description>Offering interactive capabilities tailored to the current conversation state</description></item>
    /// </list>
    /// </para>
    /// </remarks>
    public IEnumerable<AITool>? Tools { get; set; }
}
