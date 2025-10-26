// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides a mutable variant of <see cref="ChatClientAgent"/> that allows runtime modification
/// of <see cref="Instructions"/> and <see cref="ChatOptions"/> properties.
/// </summary>
/// <remarks>
/// This class derives from <see cref="ChatClientAgent"/> and introduces the ability to modify
/// the agent's instructions and chat options after construction. Unlike the base <see cref="ChatClientAgent"/>
/// class where these properties are read-only, this mutable variant allows for dynamic agent behavior.
/// </remarks>
public class MutableChatClientAgent : ChatClientAgent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="MutableChatClientAgent"/> class.
    /// </summary>
    /// <param name="chatClient">The chat client to use when running the agent.</param>
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
    /// This is only relevant when the <see cref="IChatClient"/> doesn't already contain a <see cref="FunctionInvokingChatClient"/>
    /// and the agent needs to insert one.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="chatClient"/> is <see langword="null"/>.</exception>
    public MutableChatClientAgent(IChatClient chatClient, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null, IServiceProvider? services = null)
        : this(
              chatClient,
              new ChatClientAgentOptions
              {
                  Name = name,
                  Description = description,
                  Instructions = instructions,
                  ChatOptions = tools is null ? null : new ChatOptions
                  {
                      Tools = tools,
                  }
              },
              loggerFactory,
              services)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="MutableChatClientAgent"/> class.
    /// </summary>
    /// <param name="chatClient">The chat client to use when running the agent.</param>
    /// <param name="options">
    /// Configuration options that control all aspects of the agent's behavior, including chat settings,
    /// message store factories, context provider factories, and other advanced configurations.
    /// If <see langword="null"/>, an empty options object is created to allow mutation.
    /// </param>
    /// <param name="loggerFactory">
    /// Optional logger factory for creating loggers used by the agent and its components.
    /// </param>
    /// <param name="services">
    /// Optional service provider for resolving dependencies required by AI functions and other agent components.
    /// This is particularly important when using custom tools that require dependency injection.
    /// This is only relevant when the <see cref="IChatClient"/> doesn't already contain a <see cref="FunctionInvokingChatClient"/>
    /// and the agent needs to insert one.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="chatClient"/> is <see langword="null"/>.</exception>
    public MutableChatClientAgent(IChatClient chatClient, ChatClientAgentOptions? options, ILoggerFactory? loggerFactory = null, IServiceProvider? services = null)
        : base(chatClient, options ?? new ChatClientAgentOptions(), loggerFactory, services)
    {
    }

    /// <summary>
    /// Gets or sets the system instructions that guide the agent's behavior during conversations.
    /// </summary>
    /// <value>
    /// A string containing the system instructions that are provided to the underlying chat client
    /// to establish the agent's role, personality, and behavioral guidelines. May be <see langword="null"/>
    /// if no specific instructions were configured.
    /// </value>
    /// <remarks>
    /// These instructions are typically provided to the AI model as system messages to establish
    /// the context and expected behavior for the agent's responses. Changes to this property
    /// will affect subsequent agent invocations.
    /// </remarks>
    public new string? Instructions
    {
        get => base.AgentOptions!.Instructions;
        set => base.AgentOptions!.Instructions = value;
    }

    /// <summary>
    /// Gets or sets the default <see cref="ChatOptions"/> used by the agent.
    /// </summary>
    /// <value>
    /// The default chat options applied to agent invocations. May be <see langword="null"/>
    /// if no default options were configured.
    /// </value>
    /// <remarks>
    /// These options control various aspects of the chat completion, including max tokens,
    /// tools, reasoning, and other model-specific settings. Changes to these options
    /// will affect subsequent agent invocations.
    /// </remarks>
    public new ChatOptions? ChatOptions
    {
        get => base.AgentOptions!.ChatOptions;
        set => base.AgentOptions!.ChatOptions = value;
    }
}
