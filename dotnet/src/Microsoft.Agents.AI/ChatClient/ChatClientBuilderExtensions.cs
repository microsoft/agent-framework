// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Provides extension methods for building a <see cref="ChatClientAgent"/> from a <see cref="ChatClientBuilder"/>.
/// </summary>
public static class ChatClientBuilderExtensions
{
    /// <summary>
    /// Build a <see cref="ChatClientAgent"/> from the <see cref="IChatClient"/> pipeline described by this <see cref="ChatClientBuilder"/>.
    /// </summary>
    /// <param name="builder">A builder for creating pipelines of <see cref="IChatClient"/>.</param>
    /// <param name="instructions">
    /// Optional system instructions that guide the agent's behavior. These instructions are provided to the <see cref="IChatClient"/>
    /// with each invocation to establish the agent's role and behavior.
    /// </param>
    /// <param name="name">
    /// Optional name for the agent. This name is used for identification and logging purposes.
    /// </param>
    /// <param name="description">
    /// Optional human-readable description of the agent's purpose and capabilities.
    /// This description can be useful for documentation and agent discovery scenarios.
    /// </param>
    /// <param name="tools">
    /// Optional collection of tools that the agent can invoke during conversations.
    /// These tools augment any tools that may be provided to the agent via <see cref="ChatOptions.Tools"/> when
    /// the agent is run.
    /// </param>
    /// <param name="loggerFactory">
    /// Optional logger factory for creating loggers used by the agent and its components.
    /// </param>
    /// <param name="services">
    /// Optional service provider for resolving dependencies required by AI functions and other agent components.
    /// This is particularly important when using custom tools that require dependency injection.
    /// </param>
    /// <returns>A new <see cref="ChatClientAgent"/> instance.</returns>
    public static ChatClientAgent BuildAIAgent(
        this ChatClientBuilder builder,
        string? instructions = null,
        string? name = null,
        string? description = null,
        IList<AITool>? tools = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null) =>
        Throw.IfNull(builder).Build(services).AsAIAgent(
            instructions: instructions,
            name: name,
            description: description,
            tools: tools,
            loggerFactory: loggerFactory,
            services: services);

    /// <summary>
    /// Creates a new <see cref="ChatClientAgent"/> instance.
    /// </summary>
    /// <param name="builder">A builder for creating pipelines of <see cref="IChatClient"/>.</param>
    /// <param name="options">
    /// Configuration options that control all aspects of the agent's behavior, including chat settings,
    /// message store factories, context provider factories, and other advanced configurations.
    /// </param>
    /// <param name="loggerFactory">
    /// Optional logger factory for creating loggers used by the agent and its components.
    /// </param>
    /// <param name="services">
    /// Optional service provider for resolving dependencies required by AI functions and other agent components.
    /// This is particularly important when using custom tools that require dependency injection.
    /// </param>
    /// <returns>A new <see cref="ChatClientAgent"/> instance.</returns>
    public static ChatClientAgent BuildAIAgent(
        this ChatClientBuilder builder,
        ChatClientAgentOptions? options,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null) =>
        Throw.IfNull(builder).Build(services).AsAIAgent(
            options: options,
            loggerFactory: loggerFactory,
            services: services);

    /// <summary>
    /// Adds a <see cref="ChatHistoryPersistingChatClient"/> to the chat client pipeline.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This decorator should be positioned between the <see cref="FunctionInvokingChatClient"/> and the leaf
    /// <see cref="IChatClient"/> in the pipeline. It intercepts service calls to either persist messages
    /// immediately or mark them for later persistence, depending on the <paramref name="markOnly"/> parameter.
    /// </para>
    /// <para>
    /// If <paramref name="markOnly"/> is set to <see langword="true"/>, the <see cref="ChatClientAgent"/>
    /// should be configured with <see cref="ChatClientAgentOptions.PersistChatHistoryAtEndOfRun"/> set to <see langword="true"/>
    /// as without this combination, messages will never be persisted when using a <see cref="ChatHistoryProvider"/> for
    /// chat history persistence.
    /// </para>
    /// <para>
    /// This extension method is intended for use with custom chat client stacks when
    /// <see cref="ChatClientAgentOptions.UseProvidedChatClientAsIs"/> is <see langword="true"/>.
    /// When <see cref="ChatClientAgentOptions.UseProvidedChatClientAsIs"/> is <see langword="false"/> (the default),
    /// the <see cref="ChatClientAgent"/> automatically injects this decorator.
    /// </para>
    /// <para>
    /// This decorator only works within the context of a running <see cref="ChatClientAgent"/> and will throw an
    /// exception if used in any other stack.
    /// </para>
    /// </remarks>
    /// <param name="builder">The <see cref="ChatClientBuilder"/> to add the decorator to.</param>
    /// <param name="markOnly">
    /// When <see langword="true"/>, messages are marked with metadata but not persisted immediately,
    /// and the session's <see cref="ChatClientAgentSession.ConversationId"/> is not updated.
    /// The <see cref="ChatClientAgent"/> will persist only the marked messages and update the
    /// conversation ID at the end of the run.
    /// When <see langword="false"/> (the default), messages are persisted and the conversation ID
    /// is updated immediately after each service call.
    /// </param>
    /// <returns>The <paramref name="builder"/> for chaining.</returns>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public static ChatClientBuilder UseChatHistoryPersisting(this ChatClientBuilder builder, bool markOnly = false)
    {
        return builder.Use(innerClient => new ChatHistoryPersistingChatClient(innerClient, markOnly));
    }
}
