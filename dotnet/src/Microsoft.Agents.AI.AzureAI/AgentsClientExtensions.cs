// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using OpenAI;
using OpenAI.Responses;

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

namespace Azure.AI.Agents;

/// <summary>
/// Provides extension methods for <see cref="AgentsClient"/>.
/// </summary>
public static class AgentsClientExtensions
{
    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AgentsClient"/>.
    /// </summary>
    /// <param name="agentsClient">The <see cref="AgentsClient"/> to create the <see cref="ChatClientAgent"/> with. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name of the server side agent to create a <see cref="ChatClientAgent"/> for. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the named Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentsClient"/> or <paramref name="name"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="name"/> is empty or whitespace, or when the agent with the specified name was not found.</exception>
    /// <exception cref="InvalidOperationException">The agent with the specified name was not found.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static ChatClientAgent GetAIAgent(
        this AgentsClient agentsClient,
        string name,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentsClient);
        Throw.IfNullOrWhitespace(name);

        var agentRecord = agentsClient.GetAgent(name, cancellationToken).Value
            ?? throw new InvalidOperationException($"Agent with name '{name}' not found.");

        return GetAIAgent(
            agentsClient,
            agentRecord,
            tools,
            clientFactory,
            openAIClientOptions,
            cancellationToken);
    }

    /// <summary>
    /// Asynchronously retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AgentsClient"/>.
    /// </summary>
    /// <param name="agentsClient">The <see cref="AgentsClient"/> to create the <see cref="ChatClientAgent"/> with. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name of the server side agent to create a <see cref="ChatClientAgent"/> for. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the named Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentsClient"/> or <paramref name="name"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="name"/> is empty or whitespace, or when the agent with the specified name was not found.</exception>
    /// <exception cref="InvalidOperationException">The agent with the specified name was not found.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this AgentsClient agentsClient,
        string name,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentsClient);
        Throw.IfNullOrWhitespace(name);

        var agentRecord = (await agentsClient.GetAgentAsync(name, cancellationToken).ConfigureAwait(false)).Value
            ?? throw new InvalidOperationException($"Agent with name '{name}' not found.");

        return GetAIAgent(
            agentsClient,
            agentRecord,
            tools,
            clientFactory,
            openAIClientOptions,
            cancellationToken);
    }

    /// <summary>
    /// Gets a runnable agent instance from the provided agent record.
    /// </summary>
    /// <param name="agentsClient">The client used to interact with Azure AI Agents. Cannot be <see langword="null"/>.</param>
    /// <param name="agentRecord">The agent record to be converted. The latest version will be used. Cannot be <see langword="null"/>.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the Azure AI Agent.</returns>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static ChatClientAgent GetAIAgent(
        this AgentsClient agentsClient,
        AgentRecord agentRecord,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentsClient);
        Throw.IfNull(agentRecord);

        return GetAIAgent(
            agentsClient,
            agentRecord.Versions.Latest,
            tools,
            clientFactory,
            openAIClientOptions,
            cancellationToken);
    }

    /// <summary>
    /// Gets a runnable agent instance from a <see cref="AgentVersion"/> containing metadata about an Azure AI Agent.
    /// </summary>
    /// <param name="agentsClient">The client used to interact with Azure AI Agents. Cannot be <see langword="null"/>.</param>
    /// <param name="agentVersion">The agent version to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the provided version of the Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentsClient"/> or <paramref name="agentVersion"/> is <see langword="null"/>.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static ChatClientAgent GetAIAgent(
        this AgentsClient agentsClient,
        AgentVersion agentVersion,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentsClient);
        Throw.IfNull(agentVersion);

        ValidateUsingToolsParameter(agentVersion, tools);

        IChatClient chatClient = new AzureAIAgentChatClient(agentsClient, agentVersion, openAIClientOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        var agentOptions = CreateChatClientAgentOptions(agentVersion, tools);

        return new ChatClientAgent(chatClient, agentOptions);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AgentsClient"/> and options.
    /// </summary>
    /// <param name="agentsClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentsClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent GetAIAgent(
        this AgentsClient agentsClient,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentsClient);
        Throw.IfNull(options);

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        var agentRecord = agentsClient.GetAgent(options.Name, cancellationToken).Value
            ?? throw new InvalidOperationException($"Agent with name '{options.Name}' not found.");

        var agentVersion = agentRecord.Versions.Latest;

        ValidateUsingToolsParameter(agentVersion, options.ChatOptions?.Tools);

        IChatClient chatClient = new AzureAIAgentChatClient(agentsClient, agentVersion, openAIClientOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        ChatClientAgentOptions agentOptions = CreateChatClientAgentOptions(agentVersion, options);

        return new ChatClientAgent(chatClient, agentOptions);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AgentsClient"/> and options.
    /// </summary>
    /// <param name="agentsClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentsClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this AgentsClient agentsClient,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentsClient);
        Throw.IfNull(options);

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        var agentRecord = (await agentsClient.GetAgentAsync(options.Name, cancellationToken).ConfigureAwait(false)).Value
            ?? throw new InvalidOperationException($"Agent with name '{options.Name}' not found.");

        var agentVersion = agentRecord.Versions.Latest;

        ValidateUsingToolsParameter(agentVersion, options.ChatOptions?.Tools);

        IChatClient chatClient = new AzureAIAgentChatClient(agentsClient, agentVersion, openAIClientOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        ChatClientAgentOptions agentOptions = CreateChatClientAgentOptions(agentVersion, options);

        return new ChatClientAgent(chatClient, agentOptions);
    }

    /// <summary>
    /// Creates a new Prompt AI agent using the specified configuration parameters.
    /// </summary>
    /// <param name="agentsClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="model">The name of the model to use for the agent. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="instructions">The instructions that guide the agent's behavior. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="tools">The tools to use when interacting with the agent, this is required when using prompt agent definitions with tools.</param>
    /// <param name="creationOptions">Settings that control the creation of the agent.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentsClient"/>, <paramref name="model"/>, or <paramref name="instructions"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> or <paramref name="instructions"/> is empty or whitespace.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static ChatClientAgent CreateAIAgent(
        this AgentsClient agentsClient,
        string name,
        string model,
        string instructions,
        IList<AITool>? tools = null,
        AgentVersionCreationOptions? creationOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentsClient);
        Throw.IfNullOrWhitespace(name);
        Throw.IfNullOrWhitespace(model);
        Throw.IfNullOrWhitespace(instructions);

        return CreateAIAgent(
            agentsClient,
            name,
            new PromptAgentDefinition(model) { Instructions = instructions },
            tools,
            creationOptions,
            clientFactory,
            openAIClientOptions,
            cancellationToken);
    }

    /// <summary>
    /// Creates a new Prompt AI agent using the specified configuration parameters.
    /// </summary>
    /// <param name="agentsClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="model">The name of the model to use for the agent. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="instructions">The instructions that guide the agent's behavior. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="tools">The tools to use when interacting with the agent, this is required when using prompt agent definitions with tools.</param>
    /// <param name="creationOptions">Settings that control the creation of the agent.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentsClient"/>, <paramref name="model"/>, or <paramref name="instructions"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> or <paramref name="instructions"/> is empty or whitespace.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static Task<ChatClientAgent> CreateAIAgentAsync(
        this AgentsClient agentsClient,
        string name,
        string model,
        string instructions,
        IList<AITool>? tools = null,
        AgentVersionCreationOptions? creationOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentsClient);
        Throw.IfNullOrWhitespace(name);
        Throw.IfNullOrWhitespace(model);
        Throw.IfNullOrWhitespace(instructions);

        return CreateAIAgentAsync(
            agentsClient,
            name,
            new PromptAgentDefinition(model) { Instructions = instructions },
            tools,
            creationOptions,
            clientFactory,
            openAIClientOptions,
            cancellationToken);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AgentsClient"/> and options.
    /// </summary>
    /// <param name="agentsClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="model">The name of the model to use for the agent. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentsClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace, or when the agent name is not provided in the options.</exception>
    public static ChatClientAgent CreateAIAgent(
        this AgentsClient agentsClient,
        string model,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentsClient);
        Throw.IfNull(options);
        Throw.IfNullOrWhitespace(model);

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        PromptAgentDefinition agentDefinition = new(model)
        {
            Instructions = options.Instructions,
        };

        ApplyToolsToAgentDefinition(agentDefinition, options.ChatOptions?.Tools);

        AgentVersionCreationOptions? versionCreationOptions = null;
        if (!string.IsNullOrWhiteSpace(options.Description))
        {
            (versionCreationOptions ??= new()).Description = options.Description;
        }

        AgentVersion agentVersion = agentsClient.CreateAgentVersion(options.Name, agentDefinition, versionCreationOptions, cancellationToken).Value;

        IChatClient chatClient = new AzureAIAgentChatClient(agentsClient, agentVersion, openAIClientOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        ChatClientAgentOptions agentOptions = CreateChatClientAgentOptions(agentVersion, options);

        return new ChatClientAgent(chatClient, agentOptions);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AgentsClient"/> and options.
    /// </summary>
    /// <param name="agentsClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="model">The name of the model to use for the agent. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentsClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace, or when the agent name is not provided in the options.</exception>
    public static async Task<ChatClientAgent> CreateAIAgentAsync(
        this AgentsClient agentsClient,
        string model,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentsClient);
        Throw.IfNull(options);
        Throw.IfNullOrWhitespace(model);

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        PromptAgentDefinition agentDefinition = new(model)
        {
            Instructions = options.Instructions,
        };

        ApplyToolsToAgentDefinition(agentDefinition, options.ChatOptions?.Tools);

        AgentVersionCreationOptions? versionCreationOptions = null;
        if (!string.IsNullOrWhiteSpace(options.Description))
        {
            (versionCreationOptions ??= new()).Description = options.Description;
        }

        AgentVersion agentVersion = (await agentsClient.CreateAgentVersionAsync(options.Name, agentDefinition, versionCreationOptions, cancellationToken).ConfigureAwait(false)).Value;

        IChatClient chatClient = new AzureAIAgentChatClient(agentsClient, agentVersion, openAIClientOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        ChatClientAgentOptions agentOptions = CreateChatClientAgentOptions(agentVersion, options);

        return new ChatClientAgent(chatClient, agentOptions);
    }

    /// <summary>
    /// Creates a new AI agent using the specified agent definition and optional configuration parameters.
    /// </summary>
    /// <param name="agentsClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="agentDefinition">The definition that specifies the configuration and behavior of the agent to create. Cannot be <see langword="null"/>.</param>
    /// <param name="tools">The tools to use when interacting with the agent, this is required when using prompt agent definitions with tools.</param>
    /// <param name="creationOptions">Settings that control the creation of the agent.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentsClient"/> or <paramref name="agentDefinition"/> is <see langword="null"/>.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static ChatClientAgent CreateAIAgent(
        this AgentsClient agentsClient,
        string name,
        AgentDefinition agentDefinition,
        IList<AITool>? tools = null,
        AgentVersionCreationOptions? creationOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentsClient);
        Throw.IfNullOrWhitespace(name);
        Throw.IfNull(agentDefinition);

        ValidateUsingToolsParameter(agentDefinition, tools);
        ApplyToolsToAgentDefinition(agentDefinition, tools);

        AgentVersion agentVersion = agentsClient.CreateAgentVersion(name, agentDefinition, creationOptions, cancellationToken).Value;
        IChatClient chatClient = new AzureAIAgentChatClient(agentsClient, agentVersion, openAIClientOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        ChatClientAgentOptions agentOptions = CreateChatClientAgentOptions(agentVersion, tools);

        return new ChatClientAgent(chatClient, agentOptions);
    }

    /// <summary>
    /// Asynchronously creates a new AI agent using the specified agent definition and optional configuration
    /// parameters.
    /// </summary>
    /// <param name="agentsClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="agentDefinition">The definition that specifies the configuration and behavior of the agent to create. Cannot be <see langword="null"/>.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="agentVersionCreationOptions">Settings that control the creation of the agent.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentsClient"/> or <paramref name="agentDefinition"/> is <see langword="null"/>.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static async Task<ChatClientAgent> CreateAIAgentAsync(
        this AgentsClient agentsClient,
        string name,
        AgentDefinition agentDefinition,
        IList<AITool>? tools = null,
        AgentVersionCreationOptions? agentVersionCreationOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(name);
        Throw.IfNull(agentsClient);
        Throw.IfNull(agentDefinition);

        ValidateUsingToolsParameter(agentDefinition, tools);
        ApplyToolsToAgentDefinition(agentDefinition, tools);

        AgentVersion agentVersion = await agentsClient.CreateAgentVersionAsync(name, agentDefinition, agentVersionCreationOptions, cancellationToken).ConfigureAwait(false);
        IChatClient chatClient = new AzureAIAgentChatClient(agentsClient, agentVersion, openAIClientOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        ChatClientAgentOptions agentOptions = CreateChatClientAgentOptions(agentVersion, tools);

        return new ChatClientAgent(chatClient, agentOptions);
    }

    #region Private

    /// <summary>
    /// This method creates <see cref="ChatClientAgentOptions"/> for the specified <see cref="AgentVersion"/> and the provided tools.
    /// </summary>
    /// <param name="agentVersion">The agent version.</param>
    /// <param name="tools">The tools to use when interacting with the agent.</param>
    /// <returns>The created <see cref="ChatClientAgentOptions"/>.</returns>
    /// <exception cref="InvalidOperationException">Thrown when the agent definition requires in-process tools but none were provided.</exception>
    /// <exception cref="InvalidOperationException">Thrown when the agent definition required tools were not provided.</exception>
    /// <remarks>
    /// This method rebuilds the agent options from the agent definition returned by the version and combine with the in-proc tools when provided
    /// this ensures that all required tools are provided and the definition of the agent options are consistent with the agent definition coming from the server.
    /// </remarks>
    private static ChatClientAgentOptions CreateChatClientAgentOptions(AgentVersion agentVersion, IList<AITool>? tools)
    {
        var agentDefinition = agentVersion.Definition;

        List<AITool>? agentTools = null;
        if (agentDefinition is PromptAgentDefinition { Tools: { Count: > 0 } definitionTools })
        {
            // Check if no tools were provided while the agent definition requires in-proc tools.
            if (tools is null or { Count: 0 } && definitionTools.Any(t => t is FunctionTool))
            {
                throw new ArgumentException("The agent definition in-process tools must be provided in the extension method tools parameter.");
            }

            // Agregate all missing in-proc tools for a single error message.
            List<string>? missingTools = null;

            // Check function tools
            foreach (ResponseTool responseTool in definitionTools)
            {
                if (responseTool is FunctionTool functionTool)
                {
                    // Check if a tool with the same type and name exists in the provided tools.
                    var matchingTool = tools?.FirstOrDefault(t => t is AIFunction tf && functionTool.FunctionName == tf.Name);
                    if (matchingTool is null)
                    {
                        (missingTools ??= []).Add($"Function tool: {functionTool.FunctionName}");
                    }
                    else
                    {
                        (agentTools ??= []).Add(matchingTool!);
                    }
                    continue;
                }

                (agentTools ??= []).Add(responseTool.AsAITool());
            }

            if (missingTools is { Count: > 0 })
            {
                throw new InvalidOperationException($"The following prompt agent definition required tools were not provided: {string.Join(", ", missingTools)}");
            }
        }

        var agentOptions = new ChatClientAgentOptions()
        {
            Id = agentVersion.Id,
            Name = agentVersion.Name,
            Description = agentVersion.Description,
        };

        if (agentDefinition is PromptAgentDefinition promptAgentDefinition)
        {
            agentOptions.Instructions = promptAgentDefinition.Instructions;
            agentOptions.ChatOptions = new()
            {
                Temperature = promptAgentDefinition.Temperature,
                TopP = promptAgentDefinition.TopP,
                Instructions = promptAgentDefinition.Instructions,
            };
        }

        if (agentTools is { Count: > 0 })
        {
            agentOptions.ChatOptions ??= new ChatOptions();
            agentOptions.ChatOptions.Tools = agentTools;
        }

        return agentOptions;
    }

    private static ChatClientAgentOptions CreateChatClientAgentOptions(AgentVersion agentVersion, ChatClientAgentOptions? options)
    {
        var agentOptions = CreateChatClientAgentOptions(agentVersion, options?.ChatOptions?.Tools);
        if (options is not null)
        {
            agentOptions.AIContextProviderFactory = options.AIContextProviderFactory;
            agentOptions.ChatMessageStoreFactory = options.ChatMessageStoreFactory;
            agentOptions.UseProvidedChatClientAsIs = options.UseProvidedChatClientAsIs;
        }

        return agentOptions;
    }

    /// <summary>When creating agents, validates the <paramref name="tools"/> parameter is used instead of providing via <see cref="PromptAgentDefinition"/>.</summary>
    /// <exception cref="ArgumentException">The <paramref name="tools"/> parameter should be used instead of <see cref="PromptAgentDefinition.Tools"/>.</exception>
    /// <remarks>
    /// Because <see cref="PromptAgentDefinition.Tools"/> doesn't support in-proc tools (only declarative/definitions),
    /// the <paramref name="tools"/> parameter needs to be the single source of truth for tools, and must be provided when using tools.
    /// </remarks>
    private static void ValidateUsingToolsParameter(AgentDefinition agentDefinition, IList<AITool>? tools)
    {
        if (agentDefinition is PromptAgentDefinition { Tools.Count: > 0 })
        {
            throw new ArgumentException("When creating agents with prompt agent definitions use the dedicated tools parameter to provide the necessary tools instead of PromptAgentDefinition.Tools.", nameof(tools));
        }
    }

    /// <summary>For already created agent versions, retrieve the definition and validate the tools parameter.</summary>
    /// <exception cref="ArgumentException"><see cref="PromptAgentDefinition.Tools"/> cannot be used. The <paramref name="tools"/> parameter should be used instead.</exception>
    /// <remarks>
    /// Because <see cref="PromptAgentDefinition.Tools"/> doesn't support in-proc tools (only declarative/definitions),
    /// the <paramref name="tools"/> parameter needs to be the single source of truth for tools, and must be provided when using tools.
    /// </remarks>
    private static void ValidateUsingToolsParameter(AgentVersion agentVersion, IList<AITool>? tools)
    {
        if (agentVersion.Definition is PromptAgentDefinition { Tools.Count: > 0 } && tools is null or { Count: 0 })
        {
            throw new ArgumentException("When retrieving prompt agents with tools the tools parameter needs to be provided with the necessary tools.", nameof(tools));
        }
    }

    private static void ApplyToolsToAgentDefinition(AgentDefinition agentDefinition, IList<AITool>? tools)
    {
        if (tools is { Count: > 0 })
        {
            if (agentDefinition is not PromptAgentDefinition promptAgentDefinition)
            {
                throw new ArgumentException("Only prompt agent definitions support tools.", nameof(agentDefinition));
            }

            foreach (var tool in tools)
            {
                // Ensure that any AIFunctions provided are In-Proc, not just the declarations.
                if (tool is AIFunctionDeclaration and not AIFunction)
                {
                    throw new InvalidOperationException("When providing functions, they need to be invokable AIFunctions and not non-invokable AIFunctionDeclarations. AIFunctions can be created correctly using AIFunctionFactory.Create");
                }

                promptAgentDefinition.Tools.Add(
                    // If this is a converted ResponseTool as AITool, we can directly retrieve the ResponseTool instance from GetService.
                    tool.GetService<ResponseTool>()
                    // Otherwise we should be able to convert existing MEAI Tool abstractions into OpenAI ResponseTools
                    ?? tool.AsOpenAIResponseTool()
                    ?? throw new InvalidOperationException("The provided AITool could not be converted to a ResponseTool, ensure that the AITool was created using responseTool.AsAITool() extension."));
            }
        }
    }

    #endregion
}
