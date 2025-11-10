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
/// Provides extension methods for <see cref="AgentClient"/>.
/// </summary>
public static class AgentClientExtensions
{
    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AgentClient"/>.
    /// </summary>
    /// <param name="AgentClient">The <see cref="AgentClient"/> to create the <see cref="ChatClientAgent"/> with. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name of the server side agent to create a <see cref="ChatClientAgent"/> for. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the named Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="AgentClient"/> or <paramref name="name"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="name"/> is empty or whitespace, or when the agent with the specified name was not found.</exception>
    /// <exception cref="InvalidOperationException">The agent with the specified name was not found.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static ChatClientAgent GetAIAgent(
        this AgentClient AgentClient,
        string name,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(AgentClient);
        Throw.IfNullOrWhitespace(name);

        var agentRecord = AgentClient.GetAgent(name, cancellationToken).Value
            ?? throw new InvalidOperationException($"Agent with name '{name}' not found.");

        return GetAIAgent(
            AgentClient,
            agentRecord,
            tools,
            clientFactory,
            openAIClientOptions,
            services,
            cancellationToken);
    }

    /// <summary>
    /// Asynchronously retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AgentClient"/>.
    /// </summary>
    /// <param name="AgentClient">The <see cref="AgentClient"/> to create the <see cref="ChatClientAgent"/> with. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name of the server side agent to create a <see cref="ChatClientAgent"/> for. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the named Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="AgentClient"/> or <paramref name="name"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="name"/> is empty or whitespace, or when the agent with the specified name was not found.</exception>
    /// <exception cref="InvalidOperationException">The agent with the specified name was not found.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this AgentClient AgentClient,
        string name,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(AgentClient);
        Throw.IfNullOrWhitespace(name);

        var agentRecord = (await AgentClient.GetAgentAsync(name, cancellationToken).ConfigureAwait(false)).Value
            ?? throw new InvalidOperationException($"Agent with name '{name}' not found.");

        return GetAIAgent(
            AgentClient,
            agentRecord,
            tools,
            clientFactory,
            openAIClientOptions,
            services,
            cancellationToken);
    }

    /// <summary>
    /// Gets a runnable agent instance from the provided agent record.
    /// </summary>
    /// <param name="AgentClient">The client used to interact with Azure AI Agents. Cannot be <see langword="null"/>.</param>
    /// <param name="agentRecord">The agent record to be converted. The latest version will be used. Cannot be <see langword="null"/>.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the Azure AI Agent.</returns>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static ChatClientAgent GetAIAgent(
        this AgentClient AgentClient,
        AgentRecord agentRecord,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(AgentClient);
        Throw.IfNull(agentRecord);

        return GetAIAgent(
            AgentClient,
            agentRecord.Versions.Latest,
            tools,
            clientFactory,
            openAIClientOptions,
            services,
            cancellationToken);
    }

    /// <summary>
    /// Gets a runnable agent instance from a <see cref="AgentVersion"/> containing metadata about an Azure AI Agent.
    /// </summary>
    /// <param name="AgentClient">The client used to interact with Azure AI Agents. Cannot be <see langword="null"/>.</param>
    /// <param name="agentVersion">The agent version to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the provided version of the Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="AgentClient"/> or <paramref name="agentVersion"/> is <see langword="null"/>.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static ChatClientAgent GetAIAgent(
        this AgentClient AgentClient,
        AgentVersion agentVersion,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(AgentClient);
        Throw.IfNull(agentVersion);

        ValidateUsingToolsParameter(agentVersion, tools);

        return CreateChatClientAgent(
            AgentClient,
            agentVersion,
            tools,
            clientFactory,
            openAIClientOptions,
            requireInvocableTools: true,
            services);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AgentClient"/> and options.
    /// </summary>
    /// <param name="AgentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="AgentClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent GetAIAgent(
        this AgentClient AgentClient,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(AgentClient);
        Throw.IfNull(options);

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        var agentRecord = AgentClient.GetAgent(options.Name, cancellationToken).Value
            ?? throw new InvalidOperationException($"Agent with name '{options.Name}' not found.");

        var agentVersion = agentRecord.Versions.Latest;

        var agentOptions = CreateChatClientAgentOptions(agentVersion, options, requireInvocableTools: true);

        return CreateChatClientAgent(
            AgentClient,
            agentVersion,
            agentOptions,
            clientFactory,
            openAIClientOptions,
            requireInvocableTools: true,
            services);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AgentClient"/> and options.
    /// </summary>
    /// <param name="AgentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="AgentClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this AgentClient AgentClient,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(AgentClient);
        Throw.IfNull(options);

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        var agentRecord = (await AgentClient.GetAgentAsync(options.Name, cancellationToken).ConfigureAwait(false)).Value
            ?? throw new InvalidOperationException($"Agent with name '{options.Name}' not found.");

        var agentVersion = agentRecord.Versions.Latest;

        var agentOptions = CreateChatClientAgentOptions(agentVersion, options, requireInvocableTools: true);

        return CreateChatClientAgent(
            AgentClient,
            agentVersion,
            agentOptions,
            clientFactory,
            openAIClientOptions,
            requireInvocableTools: true,
            services);
    }

    /// <summary>
    /// Creates a new Prompt AI agent using the specified configuration parameters.
    /// </summary>
    /// <param name="AgentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="model">The name of the model to use for the agent. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="instructions">The instructions that guide the agent's behavior. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="description">The description for the agent.</param>
    /// <param name="tools">The tools to use when interacting with the agent, this is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="AgentClient"/>, <paramref name="model"/>, or <paramref name="instructions"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> or <paramref name="instructions"/> is empty or whitespace.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static ChatClientAgent CreateAIAgent(
        this AgentClient AgentClient,
        string name,
        string model,
        string instructions,
        string? description = null,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(AgentClient);
        Throw.IfNullOrWhitespace(name);
        Throw.IfNullOrWhitespace(model);
        Throw.IfNullOrWhitespace(instructions);

        return CreateAIAgent(
            AgentClient,
            name,
            tools,
            new AgentVersionCreationOptions(new PromptAgentDefinition(model) { Instructions = instructions }) { Description = description },
            clientFactory,
            openAIClientOptions,
            requireInvocableTools: true,
            services,
            cancellationToken);
    }

    /// <summary>
    /// Creates a new Prompt AI agent using the specified configuration parameters.
    /// </summary>
    /// <param name="AgentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="model">The name of the model to use for the agent. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="instructions">The instructions that guide the agent's behavior. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="description">The description for the agent.</param>
    /// <param name="tools">The tools to use when interacting with the agent, this is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="AgentClient"/>, <paramref name="model"/>, or <paramref name="instructions"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> or <paramref name="instructions"/> is empty or whitespace.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static Task<ChatClientAgent> CreateAIAgentAsync(
        this AgentClient AgentClient,
        string name,
        string model,
        string instructions,
        string? description = null,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(AgentClient);
        Throw.IfNullOrWhitespace(name);
        Throw.IfNullOrWhitespace(model);
        Throw.IfNullOrWhitespace(instructions);

        return CreateAIAgentAsync(
            AgentClient,
            name,
            tools,
            new AgentVersionCreationOptions(new PromptAgentDefinition(model) { Instructions = instructions }) { Description = description },
            clientFactory,
            openAIClientOptions,
            requireInvocableTools: true,
            services,
            cancellationToken);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AgentClient"/> and options.
    /// </summary>
    /// <param name="AgentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="model">The name of the model to use for the agent. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="AgentClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace, or when the agent name is not provided in the options.</exception>
    public static ChatClientAgent CreateAIAgent(
        this AgentClient AgentClient,
        string model,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(AgentClient);
        Throw.IfNull(options);
        Throw.IfNullOrWhitespace(model);
        const bool RequireInvocableTools = true;

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        PromptAgentDefinition agentDefinition = new(model)
        {
            Instructions = options.Instructions,
        };

        ApplyToolsToAgentDefinition(agentDefinition, options.ChatOptions?.Tools, RequireInvocableTools);

        AgentVersionCreationOptions? versionCreationOptions = new(agentDefinition);
        if (!string.IsNullOrWhiteSpace(options.Description))
        {
            versionCreationOptions.Description = options.Description;
        }

        AgentVersion agentVersion = AgentClient.CreateAgentVersion(options.Name, versionCreationOptions, cancellationToken).Value;

        var agentOptions = CreateChatClientAgentOptions(agentVersion, options, RequireInvocableTools);

        return CreateChatClientAgent(
            AgentClient,
            agentVersion,
            agentOptions,
            clientFactory,
            openAIClientOptions,
            RequireInvocableTools,
            services);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AgentClient"/> and options.
    /// </summary>
    /// <param name="AgentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="model">The name of the model to use for the agent. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="AgentClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace, or when the agent name is not provided in the options.</exception>
    public static async Task<ChatClientAgent> CreateAIAgentAsync(
        this AgentClient AgentClient,
        string model,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(AgentClient);
        Throw.IfNull(options);
        Throw.IfNullOrWhitespace(model);
        const bool RequireInvocableTools = true;

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        PromptAgentDefinition agentDefinition = new(model)
        {
            Instructions = options.Instructions,
        };

        ApplyToolsToAgentDefinition(agentDefinition, options.ChatOptions?.Tools, RequireInvocableTools);

        AgentVersionCreationOptions? versionCreationOptions = new(agentDefinition);
        if (!string.IsNullOrWhiteSpace(options.Description))
        {
            versionCreationOptions.Description = options.Description;
        }

        AgentVersion agentVersion = await AgentClient.CreateAgentVersionAsync(options.Name, versionCreationOptions, cancellationToken).ConfigureAwait(false);

        var agentOptions = CreateChatClientAgentOptions(agentVersion, options, RequireInvocableTools);

        return CreateChatClientAgent(
            AgentClient,
            agentVersion,
            agentOptions,
            clientFactory,
            openAIClientOptions,
            RequireInvocableTools,
            services);
    }

    /// <summary>
    /// Creates a new AI agent using the specified agent definition and optional configuration parameters.
    /// </summary>
    /// <param name="AgentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="creationOptions">Settings that control the creation of the agent.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="AgentClient"/> or <paramref name="creationOptions"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// When using this extension method with a <see cref="PromptAgentDefinition"/> the tools are only declarative and not invocable.
    /// Invocation of any in-process tools will need to be handled manually.
    /// </remarks>
    public static ChatClientAgent CreateAIAgent(
        this AgentClient AgentClient,
        string name,
        AgentVersionCreationOptions creationOptions,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(AgentClient);
        Throw.IfNullOrWhitespace(name);
        Throw.IfNull(creationOptions);

        var tools = (creationOptions.Definition as PromptAgentDefinition)?.Tools.Select(t => t.AsAITool()).ToList();

        return CreateAIAgent(
            AgentClient,
            name,
            tools,
            creationOptions,
            clientFactory,
            openAIClientOptions,
            requireInvocableTools: false,
            services: null,
            cancellationToken);
    }

    /// <summary>
    /// Asynchronously creates a new AI agent using the specified agent definition and optional configuration
    /// parameters.
    /// </summary>
    /// <param name="AgentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="creationOptions">Settings that control the creation of the agent.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="AgentClient"/> or <paramref name="creationOptions"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// When using this extension method with a <see cref="PromptAgentDefinition"/> the tools are only declarative and not invocable.
    /// Invocation of any in-process tools will need to be handled manually.
    /// </remarks>
    public static Task<ChatClientAgent> CreateAIAgentAsync(
        this AgentClient AgentClient,
        string name,
        AgentVersionCreationOptions creationOptions,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(name);
        Throw.IfNull(AgentClient);
        Throw.IfNull(creationOptions);

        var tools = (creationOptions.Definition as PromptAgentDefinition)?.Tools.Select(t => t.AsAITool()).ToList();

        return CreateAIAgentAsync(
            AgentClient,
            name,
            tools,
            creationOptions,
            clientFactory,
            openAIClientOptions,
            requireInvocableTools: false,
            services: null,
            cancellationToken);
    }

    #region Private

    private static ChatClientAgent CreateAIAgent(
        this AgentClient AgentClient,
        string name,
        IList<AITool>? tools,
        AgentVersionCreationOptions creationOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        OpenAIClientOptions? openAIClientOptions,
        bool requireInvocableTools,
        IServiceProvider? services,
        CancellationToken cancellationToken)
    {
        Throw.IfNull(AgentClient);
        Throw.IfNullOrWhitespace(name);
        Throw.IfNull(creationOptions);

        tools ??= (creationOptions.Definition as PromptAgentDefinition)?.Tools.Select(t => t.AsAITool()).ToList();

        ApplyToolsToAgentDefinition(creationOptions.Definition, tools, requireInvocableTools);

        AgentVersion agentVersion = AgentClient.CreateAgentVersion(name, creationOptions, cancellationToken).Value;

        return CreateChatClientAgent(
            AgentClient,
            agentVersion,
            tools,
            clientFactory,
            openAIClientOptions,
            requireInvocableTools,
            services);
    }

    private static async Task<ChatClientAgent> CreateAIAgentAsync(
        this AgentClient AgentClient,
        string name,
        IList<AITool>? tools,
        AgentVersionCreationOptions creationOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        OpenAIClientOptions? openAIClientOptions,
        bool requireInvocableTools,
        IServiceProvider? services,
        CancellationToken cancellationToken)
    {
        Throw.IfNullOrWhitespace(name);
        Throw.IfNull(AgentClient);
        Throw.IfNull(creationOptions);

        tools ??= (creationOptions.Definition as PromptAgentDefinition)?.Tools.Select(t => t.AsAITool()).ToList();

        ApplyToolsToAgentDefinition(creationOptions.Definition, tools, requireInvocableTools);

        AgentVersion agentVersion = await AgentClient.CreateAgentVersionAsync(name, creationOptions, cancellationToken).ConfigureAwait(false);

        return CreateChatClientAgent(
            AgentClient,
            agentVersion,
            tools,
            clientFactory,
            openAIClientOptions,
            requireInvocableTools,
            services);
    }

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with the specified ChatClientAgentOptions.</summary>
    private static ChatClientAgent CreateChatClientAgent(
        AgentClient AgentClient,
        AgentVersion agentVersion,
        ChatClientAgentOptions agentOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        OpenAIClientOptions? openAIClientOptions,
        bool requireInvocableTools,
        IServiceProvider? services)
    {
        IChatClient chatClient = new AzureAIAgentChatClient(AgentClient, agentVersion, agentOptions.ChatOptions, openAIClientOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return new ChatClientAgent(chatClient, agentOptions, services: services);
    }

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with a auto-generated ChatClientAgentOptions from the specified configuration parameters.</summary>
    private static ChatClientAgent CreateChatClientAgent(
        AgentClient AgentClient,
        AgentVersion agentVersion,
        IList<AITool>? tools,
        Func<IChatClient, IChatClient>? clientFactory,
        OpenAIClientOptions? openAIClientOptions,
        bool requireInvocableTools,
        IServiceProvider? services)
        => CreateChatClientAgent(
            AgentClient,
            agentVersion,
            CreateChatClientAgentOptions(agentVersion, new ChatOptions() { Tools = tools }, requireInvocableTools),
            clientFactory,
            openAIClientOptions,
            requireInvocableTools,
            services);

    /// <summary>
    /// This method creates <see cref="ChatClientAgentOptions"/> for the specified <see cref="AgentVersion"/> and the provided tools.
    /// </summary>
    /// <param name="agentVersion">The agent version.</param>
    /// <param name="chatOptions">The <see cref="ChatOptions"/> to use when interacting with the agent.</param>
    /// <param name="requireInvocableTools">Indicates whether to enforce the presence of invocable tools when the AIAgent is created with an agent definition that uses them.</param>
    /// <returns>The created <see cref="ChatClientAgentOptions"/>.</returns>
    /// <exception cref="InvalidOperationException">Thrown when the agent definition requires in-process tools but none were provided.</exception>
    /// <exception cref="InvalidOperationException">Thrown when the agent definition required tools were not provided.</exception>
    /// <remarks>
    /// This method rebuilds the agent options from the agent definition returned by the version and combine with the in-proc tools when provided
    /// this ensures that all required tools are provided and the definition of the agent options are consistent with the agent definition coming from the server.
    /// </remarks>
    private static ChatClientAgentOptions CreateChatClientAgentOptions(AgentVersion agentVersion, ChatOptions? chatOptions, bool requireInvocableTools)
    {
        var agentDefinition = agentVersion.Definition;

        List<AITool>? agentTools = null;
        if (agentDefinition is PromptAgentDefinition { Tools: { Count: > 0 } definitionTools })
        {
            // Check if no tools were provided while the agent definition requires in-proc tools.
            if (requireInvocableTools && chatOptions?.Tools is not { Count: > 0 } && definitionTools.Any(t => t is FunctionTool))
            {
                throw new ArgumentException("The agent definition in-process tools must be provided in the extension method tools parameter.");
            }

            // Agregate all missing tools for a single error message.
            List<string>? missingTools = null;

            // Check function tools
            foreach (ResponseTool responseTool in definitionTools)
            {
                if (responseTool is FunctionTool functionTool)
                {
                    // Check if a tool with the same type and name exists in the provided tools.
                    var matchingTool = chatOptions?.Tools?.FirstOrDefault(t =>
                        requireInvocableTools
                            ? t is AIFunction tf && functionTool.FunctionName == tf.Name // When invocable tools are required, match only AIFunction.
                            : (t is AIFunctionDeclaration tfd && functionTool.FunctionName == tfd.Name) ? true // When not required, match AIFunctionDeclaration OR
                            : (t.GetService<FunctionTool>() is FunctionTool ft && functionTool.FunctionName == ft.FunctionName)); // Match a FunctionTool converted AsAITool.

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
            agentOptions.ChatOptions ??= chatOptions?.Clone() ?? new();
            agentOptions.Instructions = promptAgentDefinition.Instructions;
            agentOptions.ChatOptions.Temperature = promptAgentDefinition.Temperature;
            agentOptions.ChatOptions.TopP = promptAgentDefinition.TopP;
            agentOptions.ChatOptions.Instructions = promptAgentDefinition.Instructions;
        }

        if (agentTools is { Count: > 0 })
        {
            agentOptions.ChatOptions ??= chatOptions?.Clone() ?? new();
            agentOptions.ChatOptions.Tools = agentTools;
        }

        return agentOptions;
    }

    /// <summary>
    /// Creates a new instance of <see cref="ChatClientAgentOptions"/> configured for the specified agent version and
    /// optional base options.
    /// </summary>
    /// <param name="agentVersion">The agent version to use when configuring the chat client agent options.</param>
    /// <param name="options">An optional <see cref="ChatClientAgentOptions"/> instance whose relevant properties will be copied to the
    /// returned options. If <see langword="null"/>, only default values are used.</param>
    /// <param name="requireInvocableTools">Specifies whether the returned options must include invocable tools. Set to <see langword="true"/> to require
    /// invocable tools; otherwise, <see langword="false"/>.</param>
    /// <returns>A <see cref="ChatClientAgentOptions"/> instance configured according to the specified parameters.</returns>
    private static ChatClientAgentOptions CreateChatClientAgentOptions(AgentVersion agentVersion, ChatClientAgentOptions? options, bool requireInvocableTools)
    {
        var agentOptions = CreateChatClientAgentOptions(agentVersion, options?.ChatOptions, requireInvocableTools);
        if (options is not null)
        {
            agentOptions.AIContextProviderFactory = options.AIContextProviderFactory;
            agentOptions.ChatMessageStoreFactory = options.ChatMessageStoreFactory;
            agentOptions.UseProvidedChatClientAsIs = options.UseProvidedChatClientAsIs;
        }

        return agentOptions;
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

    /// <summary>
    /// Adds the specified AI tools to a prompt agent definition, ensuring that all tools are compatible and, if required, invocable.
    /// </summary>
    /// <remarks>This method ensures that only compatible and properly constructed tools are added to the agent definition.
    /// When <paramref name="requireInvocableTools"/> is <see langword="true"/>, all tools must be
    /// invocable AIFunctions, which can be created using AIFunctionFactory.Create. Tools are converted to ResponseTool
    /// instances before being added.</remarks>
    /// <param name="agentDefinition">The agent definition to which the tools will be applied. Must be a PromptAgentDefinition to support tools.</param>
    /// <param name="tools">A list of AI tools to add to the agent definition. If null or empty, no tools are added.</param>
    /// <param name="requireInvocableTools">Indicates whether all provided tools must be invocable AI functions. If set to <see langword="true"/>, only
    /// invocable AIFunctions are accepted.</param>
    /// <exception cref="ArgumentException">Thrown if <paramref name="agentDefinition"/> is not a <see cref="PromptAgentDefinition"/>.</exception>
    /// <exception cref="InvalidOperationException">Thrown if <paramref name="requireInvocableTools"/> is <see langword="true"/> and a tool is an
    /// <see cref="AIFunctionDeclaration"/> that is not invocable, or if a tool cannot be converted to a <see cref="ResponseTool"/>.</exception>
    private static void ApplyToolsToAgentDefinition(AgentDefinition agentDefinition, IList<AITool>? tools, bool requireInvocableTools)
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
                if (requireInvocableTools && tool is not AIFunction && (
                    tool.GetService<FunctionTool>() is not null // Declarative FunctionTool converted as AsAITool()
                    || tool is AIFunctionDeclaration)) // AIFunctionDeclaration type
                {
                    throw new InvalidOperationException("When providing functions, they need to be invokable AIFunctions. AIFunctions can be created correctly using AIFunctionFactory.Create");
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
