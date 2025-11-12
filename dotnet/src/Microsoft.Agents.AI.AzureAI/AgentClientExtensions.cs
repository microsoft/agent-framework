// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.ClientModel.Primitives;
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
    /// <param name="agentClient">The <see cref="AgentClient"/> to create the <see cref="ChatClientAgent"/> with. Cannot be <see langword="null"/>.</param>
    /// <param name="agentReference">The <see cref="AgentReference"/> representing the name and version of the server side agent to create a <see cref="ChatClientAgent"/> for. Cannot be <see langword="null"/>.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the named Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentClient"/> or <paramref name="agentReference"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">The agent with the specified name was not found.</exception>
    /// <remarks>
    /// When retrieving an agent by using an <see cref="AgentReference"/>, minimal information will be available about the agent in the instance level, and any logic that relies
    /// on <see cref="AIAgent.GetService(Type, object?)"/> to retrieve information about the agent like <see cref="AgentVersion" /> will receive <see langword="null"/> as the result.
    /// </remarks>
    public static ChatClientAgent GetAIAgent(
        this AgentClient agentClient,
        AgentReference agentReference,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(agentClient);
        Throw.IfNull(agentReference);

        return CreateChatClientAgent(
            agentClient,
            agentReference,
            new ChatClientAgentOptions()
            {
                Id = $"{agentReference.Name}:{agentReference.Version}",
                Name = agentReference.Name,
                ChatOptions = new() { Tools = tools },
            },
            clientFactory,
            openAIClientOptions,
            services);
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AgentClient"/>.
    /// </summary>
    /// <param name="agentClient">The <see cref="AgentClient"/> to create the <see cref="ChatClientAgent"/> with. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name of the server side agent to create a <see cref="ChatClientAgent"/> for. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the named Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentClient"/> or <paramref name="name"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="name"/> is empty or whitespace, or when the agent with the specified name was not found.</exception>
    /// <exception cref="InvalidOperationException">The agent with the specified name was not found.</exception>
    public static ChatClientAgent GetAIAgent(
        this AgentClient agentClient,
        string name,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentClient);
        Throw.IfNullOrWhitespace(name);

        AgentRecord agentRecord = GetAgentRecordByName(agentClient, name, cancellationToken);

        return GetAIAgent(
            agentClient,
            agentRecord,
            tools,
            clientFactory,
            openAIClientOptions,
            services);
    }

    /// <summary>
    /// Asynchronously retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AgentClient"/>.
    /// </summary>
    /// <param name="agentClient">The <see cref="AgentClient"/> to create the <see cref="ChatClientAgent"/> with. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name of the server side agent to create a <see cref="ChatClientAgent"/> for. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the named Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentClient"/> or <paramref name="name"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="name"/> is empty or whitespace, or when the agent with the specified name was not found.</exception>
    /// <exception cref="InvalidOperationException">The agent with the specified name was not found.</exception>
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this AgentClient agentClient,
        string name,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentClient);
        Throw.IfNullOrWhitespace(name);

        AgentRecord agentRecord = await GetAgentRecordByNameAsync(agentClient, name, cancellationToken).ConfigureAwait(false);

        return GetAIAgent(
            agentClient,
            agentRecord,
            tools,
            clientFactory,
            openAIClientOptions,
            services);
    }

    /// <summary>
    /// Gets a runnable agent instance from the provided agent record.
    /// </summary>
    /// <param name="agentClient">The client used to interact with Azure AI Agents. Cannot be <see langword="null"/>.</param>
    /// <param name="agentRecord">The agent record to be converted. The latest version will be used. Cannot be <see langword="null"/>.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentClient"/> or <paramref name="agentRecord"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent GetAIAgent(
        this AgentClient agentClient,
        AgentRecord agentRecord,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(agentClient);
        Throw.IfNull(agentRecord);

        var allowDeclarativeMode = tools is not { Count: > 0 };

        return CreateChatClientAgent(
            agentClient,
            agentRecord,
            tools,
            clientFactory,
            openAIClientOptions,
            !allowDeclarativeMode,
            services);
    }

    /// <summary>
    /// Gets a runnable agent instance from a <see cref="AgentVersion"/> containing metadata about an Azure AI Agent.
    /// </summary>
    /// <param name="agentClient">The client used to interact with Azure AI Agents. Cannot be <see langword="null"/>.</param>
    /// <param name="agentVersion">The agent version to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="tools">In-process invocable tools to be provided. If no tools are provided manual handling will be necessary to invoke in-process tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the provided version of the Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentClient"/> or <paramref name="agentVersion"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent GetAIAgent(
        this AgentClient agentClient,
        AgentVersion agentVersion,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(agentClient);
        Throw.IfNull(agentVersion);

        var allowDeclarativeMode = tools is not { Count: > 0 };

        return CreateChatClientAgent(
            agentClient,
            agentVersion,
            tools,
            clientFactory,
            openAIClientOptions,
            !allowDeclarativeMode,
            services);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AgentClient"/> and options.
    /// </summary>
    /// <param name="agentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent GetAIAgent(
        this AgentClient agentClient,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentClient);
        Throw.IfNull(options);

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        AgentRecord agentRecord = GetAgentRecordByName(agentClient, options.Name, cancellationToken);
        var agentVersion = agentRecord.Versions.Latest;

        var agentOptions = CreateChatClientAgentOptions(agentVersion, options, requireInvocableTools: true);

        return CreateChatClientAgent(
            agentClient,
            agentVersion,
            agentOptions,
            clientFactory,
            openAIClientOptions,
            services);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AgentClient"/> and options.
    /// </summary>
    /// <param name="agentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this AgentClient agentClient,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentClient);
        Throw.IfNull(options);

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        AgentRecord agentRecord = await GetAgentRecordByNameAsync(agentClient, options.Name, cancellationToken).ConfigureAwait(false);
        var agentVersion = agentRecord.Versions.Latest;

        var agentOptions = CreateChatClientAgentOptions(agentVersion, options, requireInvocableTools: true);

        return CreateChatClientAgent(
            agentClient,
            agentVersion,
            agentOptions,
            clientFactory,
            openAIClientOptions,
            services);
    }

    /// <summary>
    /// Creates a new Prompt AI agent using the specified configuration parameters.
    /// </summary>
    /// <param name="agentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
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
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentClient"/>, <paramref name="model"/>, or <paramref name="instructions"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> or <paramref name="instructions"/> is empty or whitespace.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static ChatClientAgent CreateAIAgent(
        this AgentClient agentClient,
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
        Throw.IfNull(agentClient);
        Throw.IfNullOrWhitespace(name);
        Throw.IfNullOrWhitespace(model);
        Throw.IfNullOrWhitespace(instructions);

        return CreateAIAgent(
            agentClient,
            name,
            tools,
            new AgentVersionCreationOptions(new PromptAgentDefinition(model) { Instructions = instructions }) { Description = description },
            clientFactory,
            openAIClientOptions,
            services,
            cancellationToken);
    }

    /// <summary>
    /// Creates a new Prompt AI agent using the specified configuration parameters.
    /// </summary>
    /// <param name="agentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
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
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentClient"/>, <paramref name="model"/>, or <paramref name="instructions"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> or <paramref name="instructions"/> is empty or whitespace.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static Task<ChatClientAgent> CreateAIAgentAsync(
        this AgentClient agentClient,
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
        Throw.IfNull(agentClient);
        Throw.IfNullOrWhitespace(name);
        Throw.IfNullOrWhitespace(model);
        Throw.IfNullOrWhitespace(instructions);

        return CreateAIAgentAsync(
            agentClient,
            name,
            tools,
            new AgentVersionCreationOptions(new PromptAgentDefinition(model) { Instructions = instructions }) { Description = description },
            clientFactory,
            openAIClientOptions,
            services,
            cancellationToken);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AgentClient"/> and options.
    /// </summary>
    /// <param name="agentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="model">The name of the model to use for the agent. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace, or when the agent name is not provided in the options.</exception>
    public static ChatClientAgent CreateAIAgent(
        this AgentClient agentClient,
        string model,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentClient);
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

        ApplyToolsToAgentDefinition(agentDefinition, options.ChatOptions?.Tools);

        AgentVersionCreationOptions? creationOptions = new(agentDefinition);
        if (!string.IsNullOrWhiteSpace(options.Description))
        {
            creationOptions.Description = options.Description;
        }

        AgentVersion agentVersion = CreateAgentVersionWithProtocol(agentClient, options.Name, creationOptions, cancellationToken);

        var agentOptions = CreateChatClientAgentOptions(agentVersion, options, RequireInvocableTools);

        return CreateChatClientAgent(
            agentClient,
            agentVersion,
            agentOptions,
            clientFactory,
            openAIClientOptions,
            services);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AgentClient"/> and options.
    /// </summary>
    /// <param name="agentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="model">The name of the model to use for the agent. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace, or when the agent name is not provided in the options.</exception>
    public static async Task<ChatClientAgent> CreateAIAgentAsync(
        this AgentClient agentClient,
        string model,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentClient);
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

        ApplyToolsToAgentDefinition(agentDefinition, options.ChatOptions?.Tools);

        AgentVersionCreationOptions? creationOptions = new(agentDefinition);
        if (!string.IsNullOrWhiteSpace(options.Description))
        {
            creationOptions.Description = options.Description;
        }

        AgentVersion agentVersion = await CreateAgentVersionWithProtocolAsync(agentClient, options.Name, creationOptions, cancellationToken).ConfigureAwait(false);

        var agentOptions = CreateChatClientAgentOptions(agentVersion, options, RequireInvocableTools);

        return CreateChatClientAgent(
            agentClient,
            agentVersion,
            agentOptions,
            clientFactory,
            openAIClientOptions,
            services);
    }

    /// <summary>
    /// Creates a new AI agent using the specified agent definition and optional configuration parameters.
    /// </summary>
    /// <param name="agentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="creationOptions">Settings that control the creation of the agent.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentClient"/> or <paramref name="creationOptions"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// When using this extension method with a <see cref="PromptAgentDefinition"/> the tools are only declarative and not invocable.
    /// Invocation of any in-process tools will need to be handled manually.
    /// </remarks>
    public static ChatClientAgent CreateAIAgent(
        this AgentClient agentClient,
        string name,
        AgentVersionCreationOptions creationOptions,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentClient);
        Throw.IfNullOrWhitespace(name);
        Throw.IfNull(creationOptions);

        return CreateAIAgent(
            agentClient,
            name,
            tools: null,
            creationOptions,
            clientFactory,
            openAIClientOptions,
            services: null,
            cancellationToken);
    }

    /// <summary>
    /// Asynchronously creates a new AI agent using the specified agent definition and optional configuration
    /// parameters.
    /// </summary>
    /// <param name="agentClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="creationOptions">Settings that control the creation of the agent.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agentClient"/> or <paramref name="creationOptions"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// When using this extension method with a <see cref="PromptAgentDefinition"/> the tools are only declarative and not invocable.
    /// Invocation of any in-process tools will need to be handled manually.
    /// </remarks>
    public static Task<ChatClientAgent> CreateAIAgentAsync(
        this AgentClient agentClient,
        string name,
        AgentVersionCreationOptions creationOptions,
        Func<IChatClient, IChatClient>? clientFactory = null,
        OpenAIClientOptions? openAIClientOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(name);
        Throw.IfNull(agentClient);
        Throw.IfNull(creationOptions);

        return CreateAIAgentAsync(
            agentClient,
            name,
            tools: null,
            creationOptions,
            clientFactory,
            openAIClientOptions,
            services: null,
            cancellationToken);
    }

    #region Private

    /// <summary>
    /// Retrieves an agent record by name using the Protocol method with user-agent header.
    /// </summary>
    private static AgentRecord GetAgentRecordByName(AgentClient agentClient, string agentName, CancellationToken cancellationToken)
    {
        ClientResult protocolResponse = agentClient.GetAgent(agentName, cancellationToken.ToRequestOptions(false));
        return ClientResult.FromOptionalValue((AgentRecord)protocolResponse, protocolResponse.GetRawResponse()).Value
            ?? throw new InvalidOperationException($"Agent with name '{agentName}' not found.");
    }

    /// <summary>
    /// Asynchronously retrieves an agent record by name using the Protocol method with user-agent header.
    /// </summary>
    private static async Task<AgentRecord> GetAgentRecordByNameAsync(AgentClient agentClient, string agentName, CancellationToken cancellationToken)
    {
        ClientResult protocolResponse = await agentClient.GetAgentAsync(agentName, cancellationToken.ToRequestOptions(false)).ConfigureAwait(false);
        return ClientResult.FromOptionalValue((AgentRecord)protocolResponse, protocolResponse.GetRawResponse()).Value
            ?? throw new InvalidOperationException($"Agent with name '{agentName}' not found.");
    }

    /// <summary>
    /// Creates an agent version using the Protocol method with user-agent header.
    /// </summary>
    private static AgentVersion CreateAgentVersionWithProtocol(AgentClient agentClient, string agentName, AgentVersionCreationOptions creationOptions, CancellationToken cancellationToken)
    {
        using BinaryContent protocolRequest = BinaryContent.Create(ModelReaderWriter.Write(creationOptions, ModelReaderWriterOptions.Json, AzureAIAgentsContext.Default));
        ClientResult protocolResponse = agentClient.CreateAgentVersion(agentName, protocolRequest, cancellationToken.ToRequestOptions(false));
        return ClientResult.FromValue((AgentVersion)protocolResponse, protocolResponse.GetRawResponse()).Value;
    }

    /// <summary>
    /// Asynchronously creates an agent version using the Protocol method with user-agent header.
    /// </summary>
    private static async Task<AgentVersion> CreateAgentVersionWithProtocolAsync(AgentClient agentClient, string agentName, AgentVersionCreationOptions creationOptions, CancellationToken cancellationToken)
    {
        using BinaryContent protocolRequest = BinaryContent.Create(ModelReaderWriter.Write(creationOptions, ModelReaderWriterOptions.Json, AzureAIAgentsContext.Default));
        ClientResult protocolResponse = await agentClient.CreateAgentVersionAsync(agentName, protocolRequest, cancellationToken.ToRequestOptions(false)).ConfigureAwait(false);
        return ClientResult.FromValue((AgentVersion)protocolResponse, protocolResponse.GetRawResponse()).Value;
    }

    private static ChatClientAgent CreateAIAgent(
        this AgentClient agentClient,
        string name,
        IList<AITool>? tools,
        AgentVersionCreationOptions creationOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        OpenAIClientOptions? openAIClientOptions,
        IServiceProvider? services,
        CancellationToken cancellationToken)
    {
        Throw.IfNull(agentClient);
        Throw.IfNullOrWhitespace(name);
        Throw.IfNull(creationOptions);

        var allowDeclarativeMode = tools is not { Count: > 0 };

        if (!allowDeclarativeMode)
        {
            ApplyToolsToAgentDefinition(creationOptions.Definition, tools);
        }

        AgentVersion agentVersion = CreateAgentVersionWithProtocol(agentClient, name, creationOptions, cancellationToken);

        return CreateChatClientAgent(
            agentClient,
            agentVersion,
            tools,
            clientFactory,
            openAIClientOptions,
            !allowDeclarativeMode,
            services);
    }

    private static async Task<ChatClientAgent> CreateAIAgentAsync(
        this AgentClient agentClient,
        string name,
        IList<AITool>? tools,
        AgentVersionCreationOptions creationOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        OpenAIClientOptions? openAIClientOptions,
        IServiceProvider? services,
        CancellationToken cancellationToken)
    {
        Throw.IfNullOrWhitespace(name);
        Throw.IfNull(agentClient);
        Throw.IfNull(creationOptions);

        var allowDeclarativeMode = tools is not { Count: > 0 };

        if (!allowDeclarativeMode)
        {
            ApplyToolsToAgentDefinition(creationOptions.Definition, tools);
        }

        AgentVersion agentVersion = await CreateAgentVersionWithProtocolAsync(agentClient, name, creationOptions, cancellationToken).ConfigureAwait(false);

        return CreateChatClientAgent(
            agentClient,
            agentVersion,
            tools,
            clientFactory,
            openAIClientOptions,
            !allowDeclarativeMode,
            services);
    }

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with the specified ChatClientAgentOptions.</summary>
    private static ChatClientAgent CreateChatClientAgent(
        AgentClient agentClient,
        AgentVersion agentVersion,
        ChatClientAgentOptions agentOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        OpenAIClientOptions? openAIClientOptions,
        IServiceProvider? services)
    {
        IChatClient chatClient = new AzureAIAgentChatClient(agentClient, agentVersion, agentOptions.ChatOptions, openAIClientOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return new ChatClientAgent(chatClient, agentOptions, services: services);
    }

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with the specified ChatClientAgentOptions.</summary>
    private static ChatClientAgent CreateChatClientAgent(
        AgentClient agentClient,
        AgentRecord agentRecord,
        ChatClientAgentOptions agentOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        OpenAIClientOptions? openAIClientOptions,
        IServiceProvider? services)
    {
        IChatClient chatClient = new AzureAIAgentChatClient(agentClient, agentRecord, agentOptions.ChatOptions, openAIClientOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return new ChatClientAgent(chatClient, agentOptions, services: services);
    }

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with the specified ChatClientAgentOptions.</summary>
    private static ChatClientAgent CreateChatClientAgent(
        AgentClient agentClient,
        AgentReference agentReference,
        ChatClientAgentOptions agentOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        OpenAIClientOptions? openAIClientOptions,
        IServiceProvider? services)
    {
        IChatClient chatClient = new AzureAIAgentChatClient(agentClient, agentReference, defaultModelId: null, agentOptions.ChatOptions, openAIClientOptions);

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
            services);

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with a auto-generated ChatClientAgentOptions from the specified configuration parameters.</summary>
    private static ChatClientAgent CreateChatClientAgent(
        AgentClient AgentClient,
        AgentRecord agentRecord,
        IList<AITool>? tools,
        Func<IChatClient, IChatClient>? clientFactory,
        OpenAIClientOptions? openAIClientOptions,
        bool requireInvocableTools,
        IServiceProvider? services)
        => CreateChatClientAgent(
            AgentClient,
            agentRecord,
            CreateChatClientAgentOptions(agentRecord.Versions.Latest, new ChatOptions() { Tools = tools }, requireInvocableTools),
            clientFactory,
            openAIClientOptions,
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
                if (requireInvocableTools && responseTool is FunctionTool functionTool)
                {
                    // Check if a tool with the same type and name exists in the provided tools.
                    // When invocable tools are required, match only AIFunction.
                    var matchingTool = chatOptions?.Tools?.FirstOrDefault(t => t is AIFunction tf && functionTool.FunctionName == tf.Name);

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

            if (requireInvocableTools && missingTools is { Count: > 0 })
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

    /// <summary>
    /// Adds the specified AI tools to a prompt agent definition, while also ensuring that all invocable tools are provided.
    /// </summary>
    /// <param name="agentDefinition">The agent definition to which the tools will be applied. Must be a PromptAgentDefinition to support tools.</param>
    /// <param name="tools">A list of AI tools to add to the agent definition. If null or empty, no tools are added.</param>
    /// <exception cref="ArgumentException">Thrown if tools were provided but <paramref name="agentDefinition"/> is not a <see cref="PromptAgentDefinition"/>.</exception>
    /// <exception cref="InvalidOperationException">When providing functions, they need to be invokable AIFunctions.</exception>
    private static void ApplyToolsToAgentDefinition(AgentDefinition agentDefinition, IList<AITool>? tools)
    {
        if (tools is { Count: > 0 })
        {
            if (agentDefinition is not PromptAgentDefinition promptAgentDefinition)
            {
                throw new ArgumentException("Only prompt agent definitions support tools.", nameof(agentDefinition));
            }

            // When tools are provided, those should represent the complete set of tools for the agent definition.
            // This is particularly important for existing agents so no duplication happens for what was already defined.
            promptAgentDefinition.Tools.Clear();

            foreach (var tool in tools)
            {
                // Ensure that any AIFunctions provided are In-Proc, not just the declarations.
                if (tool is not AIFunction && (
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
