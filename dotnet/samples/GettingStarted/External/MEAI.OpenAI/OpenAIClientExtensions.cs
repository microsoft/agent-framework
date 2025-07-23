// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging;
using OpenAI.Chat;
using OpenAI.Responses;

namespace OpenAI;

/// <summary>
/// Provides extension methods for <see cref="OpenAIClient"/>, <see cref="ChatClient"/>, and <see cref="OpenAIResponseClient"/>
/// to simplify the creation of AI agents that work with OpenAI services.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between OpenAI SDK client objects and the Microsoft Extensions AI Agent framework,
/// allowing developers to easily create AI agents that leverage OpenAI's chat completion and response services.
/// The methods handle the conversion from OpenAI clients to <see cref="IChatClient"/> instances and then wrap them
/// in <see cref="ChatClientAgent"/> objects that implement the <see cref="AIAgent"/> interface.
/// </remarks>
public static class OpenAIClientExtensions
{
    /// <summary>
    /// Creates an AI agent from an <see cref="OpenAIClient"/> using the OpenAI Chat Completion API.
    /// </summary>
    /// <param name="client">The OpenAI client to use for the agent.</param>
    /// <param name="model">The model identifier to use for chat completions (e.g., "gpt-4", "gpt-3.5-turbo").</param>
    /// <param name="instructions">Optional system instructions that define the agent's behavior and personality.</param>
    /// <param name="name">Optional name for the agent for identification purposes.</param>
    /// <param name="description">Optional description of the agent's capabilities and purpose.</param>
    /// <param name="tools">Optional collection of AI tools that the agent can use during conversations.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Chat Completion service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    /// <remarks>
    /// <para>
    /// This method creates an agent that uses OpenAI's Chat Completion API, which is suitable for most conversational AI scenarios.
    /// The agent will be able to maintain conversation context and use any provided tools to enhance its capabilities.
    /// </para>
    /// <para>
    /// The <paramref name="instructions"/> parameter serves as the system message that guides the agent's behavior.
    /// This should contain clear instructions about the agent's role, personality, and any specific guidelines it should follow.
    /// </para>
    /// <para>
    /// If <paramref name="tools"/> are provided, the agent will be able to call these functions during conversation
    /// to retrieve information, perform calculations, or interact with external systems.
    /// </para>
    /// </remarks>
    public static AIAgent GetChatClientAgent(this OpenAIClient client, string model, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null)
    {
        var chatClient = client.GetChatClient(model).AsIChatClient();
        ChatClientAgent agent = new(chatClient, instructions, name, description, tools, loggerFactory);
        return agent;
    }

    /// <summary>
    /// Creates an AI agent from an OpenAI <see cref="ChatClient"/>.
    /// </summary>
    /// <param name="client">The OpenAI chat client to use for the agent.</param>
    /// <param name="instructions">Optional system instructions that define the agent's behavior and personality.</param>
    /// <param name="name">Optional name for the agent for identification purposes.</param>
    /// <param name="description">Optional description of the agent's capabilities and purpose.</param>
    /// <param name="tools">Optional collection of AI tools that the agent can use during conversations.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the provided chat client.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// <para>
    /// This method is useful when you already have a configured <see cref="ChatClient"/> instance and want to
    /// wrap it in an AI agent. This provides more control over the chat client configuration compared to
    /// <see cref="GetChatClientAgent(OpenAIClient, string, string?, string?, string?, IList{AITool}?, ILoggerFactory?)"/>.
    /// </para>
    /// <para>
    /// The resulting agent will inherit all the configuration and behavior of the underlying chat client,
    /// including any pre-configured options for model selection, temperature, token limits, etc.
    /// </para>
    /// </remarks>
    public static AIAgent GetAgent(this ChatClient client, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null)
    {
        var chatClient = client.AsIChatClient();
        ChatClientAgent agent = new(chatClient, instructions, name, description, tools, loggerFactory);
        return agent;
    }

    /// <summary>
    /// Creates an AI agent from an <see cref="OpenAIClient"/> using the OpenAI Response API.
    /// </summary>
    /// <param name="client">The OpenAI client to use for the agent.</param>
    /// <param name="model">The model identifier to use for responses (e.g., "gpt-4", "gpt-3.5-turbo").</param>
    /// <param name="instructions">Optional system instructions that define the agent's behavior and personality.</param>
    /// <param name="name">Optional name for the agent for identification purposes.</param>
    /// <param name="description">Optional description of the agent's capabilities and purpose.</param>
    /// <param name="tools">Optional collection of AI tools that the agent can use during conversations.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Response service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    /// <remarks>
    /// <para>
    /// This method creates an agent that uses OpenAI's Response API, which provides additional features
    /// and response formats compared to the standard Chat Completion API. This is particularly useful
    /// for scenarios that require structured outputs or specific response formats.
    /// </para>
    /// <para>
    /// The Response API may offer different capabilities than the Chat Completion API, such as
    /// enhanced structured output support, different streaming behaviors, or access to specialized
    /// response formats that are not available through the standard chat completion endpoint.
    /// </para>
    /// <para>
    /// Choose this method over <see cref="GetChatClientAgent(OpenAIClient, string, string?, string?, string?, IList{AITool}?, ILoggerFactory?)"/>
    /// when you specifically need the features provided by the OpenAI Response API.
    /// </para>
    /// </remarks>
    public static AIAgent GetOpenAIResponseClientAgent(this OpenAIClient client, string model, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null)
    {
        var chatClient = client.GetOpenAIResponseClient(model).AsIChatClient();
        ChatClientAgent agent = new(chatClient, instructions, name, description, tools, loggerFactory);
        return agent;
    }

    /// <summary>
    /// Creates an AI agent from an <see cref="OpenAIResponseClient"/>.
    /// </summary>
    /// <param name="client">The OpenAI response client to use for the agent.</param>
    /// <param name="instructions">Optional system instructions that define the agent's behavior and personality.</param>
    /// <param name="name">Optional name for the agent for identification purposes.</param>
    /// <param name="description">Optional description of the agent's capabilities and purpose.</param>
    /// <param name="tools">Optional collection of AI tools that the agent can use during conversations.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the provided response client.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// <para>
    /// This method is useful when you already have a configured <see cref="OpenAIResponseClient"/> instance
    /// and want to wrap it in an AI agent. This provides more control over the response client configuration
    /// compared to <see cref="GetOpenAIResponseClientAgent(OpenAIClient, string, string?, string?, string?, IList{AITool}?, ILoggerFactory?)"/>.
    /// </para>
    /// <para>
    /// The resulting agent will inherit all the configuration and behavior of the underlying response client,
    /// including any pre-configured options for response formats, model parameters, and API-specific settings.
    /// </para>
    /// <para>
    /// Use this method when you need fine-grained control over the OpenAI Response API configuration
    /// or when you want to reuse an existing response client instance across multiple agents.
    /// </para>
    /// </remarks>
    public static AIAgent GetAgent(this OpenAIResponseClient client, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null)
    {
        var chatClient = client.AsIChatClient();
        ChatClientAgent agent = new(chatClient, instructions, name, description, tools, loggerFactory);
        return agent;
    }
}
