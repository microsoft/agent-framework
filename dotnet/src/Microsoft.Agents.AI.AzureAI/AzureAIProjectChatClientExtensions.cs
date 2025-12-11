// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.ClientModel.Primitives;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Azure.AI.Projects.OpenAI;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using OpenAI;
using OpenAI.Responses;

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

namespace Azure.AI.Projects;

/// <summary>
/// Provides extension methods for <see cref="AIProjectClient"/>.
/// </summary>
public static partial class AzureAIProjectChatClientExtensions
{
    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AIProjectClient"/>.
    /// </summary>
    /// <param name="aiProjectClient">The <see cref="AIProjectClient"/> to create the <see cref="ChatClientAgent"/> with. Cannot be <see langword="null"/>.</param>
    /// <param name="agentReference">The <see cref="AgentReference"/> representing the name and version of the server side agent to create a <see cref="ChatClientAgent"/> for. Cannot be <see langword="null"/>.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the named Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> or <paramref name="agentReference"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">The agent with the specified name was not found.</exception>
    /// <remarks>
    /// When retrieving an agent by using an <see cref="AgentReference"/>, minimal information will be available about the agent in the instance level, and any logic that relies
    /// on <see cref="AIAgent.GetService(Type, object?)"/> to retrieve information about the agent like <see cref="AgentVersion" /> will receive <see langword="null"/> as the result.
    /// </remarks>
    public static ChatClientAgent GetAIAgent(
        this AIProjectClient aiProjectClient,
        AgentReference agentReference,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(agentReference);
        ThrowIfInvalidAgentName(agentReference.Name);

        return CreateChatClientAgent(
            aiProjectClient,
            agentReference,
            new ChatClientAgentOptions()
            {
                Id = $"{agentReference.Name}:{agentReference.Version}",
                Name = agentReference.Name,
                ChatOptions = new() { Tools = tools },
            },
            clientFactory,
            services);
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AIProjectClient"/>.
    /// </summary>
    /// <param name="aiProjectClient">The <see cref="AIProjectClient"/> to create the <see cref="ChatClientAgent"/> with. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name of the server side agent to create a <see cref="ChatClientAgent"/> for. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the named Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> or <paramref name="name"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="name"/> is empty or whitespace, or when the agent with the specified name was not found.</exception>
    /// <exception cref="InvalidOperationException">The agent with the specified name was not found.</exception>
    public static ChatClientAgent GetAIAgent(
        this AIProjectClient aiProjectClient,
        string name,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(aiProjectClient);
        ThrowIfInvalidAgentName(name);

        AgentRecord agentRecord = GetAgentRecordByName(aiProjectClient, name, cancellationToken);

        return GetAIAgent(
            aiProjectClient,
            agentRecord,
            tools,
            clientFactory,
            services);
    }

    /// <summary>
    /// Asynchronously retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AIProjectClient"/>.
    /// </summary>
    /// <param name="aiProjectClient">The <see cref="AIProjectClient"/> to create the <see cref="ChatClientAgent"/> with. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name of the server side agent to create a <see cref="ChatClientAgent"/> for. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the named Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> or <paramref name="name"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="name"/> is empty or whitespace, or when the agent with the specified name was not found.</exception>
    /// <exception cref="InvalidOperationException">The agent with the specified name was not found.</exception>
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this AIProjectClient aiProjectClient,
        string name,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(aiProjectClient);
        ThrowIfInvalidAgentName(name);

        AgentRecord agentRecord = await GetAgentRecordByNameAsync(aiProjectClient, name, cancellationToken).ConfigureAwait(false);

        return GetAIAgent(
            aiProjectClient,
            agentRecord,
            tools,
            clientFactory,
            services);
    }

    /// <summary>
    /// Gets a runnable agent instance from the provided agent record.
    /// </summary>
    /// <param name="aiProjectClient">The client used to interact with Azure AI Agents. Cannot be <see langword="null"/>.</param>
    /// <param name="agentRecord">The agent record to be converted. The latest version will be used. Cannot be <see langword="null"/>.</param>
    /// <param name="tools">The tools to use when interacting with the agent. This is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the latest version of the Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> or <paramref name="agentRecord"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent GetAIAgent(
        this AIProjectClient aiProjectClient,
        AgentRecord agentRecord,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(agentRecord);

        var allowDeclarativeMode = tools is not { Count: > 0 };

        return CreateChatClientAgent(
            aiProjectClient,
            agentRecord,
            tools,
            clientFactory,
            !allowDeclarativeMode,
            services);
    }

    /// <summary>
    /// Gets a runnable agent instance from a <see cref="AgentVersion"/> containing metadata about an Azure AI Agent.
    /// </summary>
    /// <param name="aiProjectClient">The client used to interact with Azure AI Agents. Cannot be <see langword="null"/>.</param>
    /// <param name="agentVersion">The agent version to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="tools">In-process invocable tools to be provided. If no tools are provided manual handling will be necessary to invoke in-process tools.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations based on the provided version of the Azure AI Agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> or <paramref name="agentVersion"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent GetAIAgent(
        this AIProjectClient aiProjectClient,
        AgentVersion agentVersion,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(agentVersion);

        var allowDeclarativeMode = tools is not { Count: > 0 };

        return CreateChatClientAgent(
            aiProjectClient,
            agentVersion,
            tools,
            clientFactory,
            !allowDeclarativeMode,
            services);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AIProjectClient"/> and options.
    /// </summary>
    /// <param name="aiProjectClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent GetAIAgent(
        this AIProjectClient aiProjectClient,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(options);

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        ThrowIfInvalidAgentName(options.Name);

        AgentRecord agentRecord = GetAgentRecordByName(aiProjectClient, options.Name, cancellationToken);
        var agentVersion = agentRecord.Versions.Latest;

        var agentOptions = CreateChatClientAgentOptions(agentVersion, options, requireInvocableTools: true);

        return CreateChatClientAgent(
            aiProjectClient,
            agentVersion,
            agentOptions,
            clientFactory,
            services);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AIProjectClient"/> and options.
    /// </summary>
    /// <param name="aiProjectClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this AIProjectClient aiProjectClient,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(options);

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        ThrowIfInvalidAgentName(options.Name);

        AgentRecord agentRecord = await GetAgentRecordByNameAsync(aiProjectClient, options.Name, cancellationToken).ConfigureAwait(false);
        var agentVersion = agentRecord.Versions.Latest;

        var agentOptions = CreateChatClientAgentOptions(agentVersion, options, requireInvocableTools: true);

        return CreateChatClientAgent(
            aiProjectClient,
            agentVersion,
            agentOptions,
            clientFactory,
            services);
    }

    /// <summary>
    /// Creates a new Prompt AI agent using the specified configuration parameters.
    /// </summary>
    /// <param name="aiProjectClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="model">The name of the model to use for the agent. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="instructions">The instructions that guide the agent's behavior. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="description">The description for the agent.</param>
    /// <param name="tools">The tools to use when interacting with the agent, this is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/>, <paramref name="model"/>, or <paramref name="instructions"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> or <paramref name="instructions"/> is empty or whitespace.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static ChatClientAgent CreateAIAgent(
        this AIProjectClient aiProjectClient,
        string name,
        string model,
        string instructions,
        string? description = null,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(aiProjectClient);
        ThrowIfInvalidAgentName(name);
        Throw.IfNullOrWhitespace(model);
        Throw.IfNullOrWhitespace(instructions);

        return CreateAIAgent(
            aiProjectClient,
            name,
            tools,
            new AgentVersionCreationOptions(new PromptAgentDefinition(model) { Instructions = instructions }) { Description = description },
            clientFactory,
            services,
            cancellationToken);
    }

    /// <summary>
    /// Creates a new Prompt AI agent using the specified configuration parameters.
    /// </summary>
    /// <param name="aiProjectClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="model">The name of the model to use for the agent. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="instructions">The instructions that guide the agent's behavior. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="description">The description for the agent.</param>
    /// <param name="tools">The tools to use when interacting with the agent, this is required when using prompt agent definitions with tools.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/>, <paramref name="model"/>, or <paramref name="instructions"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> or <paramref name="instructions"/> is empty or whitespace.</exception>
    /// <remarks>When using prompt agent definitions with tools the parameter <paramref name="tools"/> needs to be provided.</remarks>
    public static Task<ChatClientAgent> CreateAIAgentAsync(
        this AIProjectClient aiProjectClient,
        string name,
        string model,
        string instructions,
        string? description = null,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(aiProjectClient);
        ThrowIfInvalidAgentName(name);
        Throw.IfNullOrWhitespace(model);
        Throw.IfNullOrWhitespace(instructions);

        return CreateAIAgentAsync(
            aiProjectClient,
            name,
            tools,
            new AgentVersionCreationOptions(new PromptAgentDefinition(model) { Instructions = instructions }) { Description = description },
            clientFactory,
            services,
            cancellationToken);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AIProjectClient"/> and options.
    /// </summary>
    /// <param name="aiProjectClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="model">The name of the model to use for the agent. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace, or when the agent name is not provided in the options.</exception>
    public static ChatClientAgent CreateAIAgent(
        this AIProjectClient aiProjectClient,
        string model,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(options);
        Throw.IfNullOrWhitespace(model);
        const bool RequireInvocableTools = true;

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        ThrowIfInvalidAgentName(options.Name);

        PromptAgentDefinition agentDefinition = new(model)
        {
            Instructions = options.ChatOptions?.Instructions,
            Temperature = options.ChatOptions?.Temperature,
            TopP = options.ChatOptions?.TopP,
            TextOptions = new() { TextFormat = ToOpenAIResponseTextFormat(options.ChatOptions?.ResponseFormat, options.ChatOptions) }
        };

        // Attempt to capture breaking glass options from the raw representation factory that match the agent definition.
        if (options.ChatOptions?.RawRepresentationFactory?.Invoke(new NoOpChatClient()) is ResponseCreationOptions respCreationOptions)
        {
            agentDefinition.ReasoningOptions = respCreationOptions.ReasoningOptions;
        }

        ApplyToolsToAgentDefinition(agentDefinition, options.ChatOptions?.Tools);

        AgentVersionCreationOptions? creationOptions = new(agentDefinition);
        if (!string.IsNullOrWhiteSpace(options.Description))
        {
            creationOptions.Description = options.Description;
        }

        AgentVersion agentVersion = CreateAgentVersionWithProtocol(aiProjectClient, options.Name, creationOptions, cancellationToken);

        var agentOptions = CreateChatClientAgentOptions(agentVersion, options, RequireInvocableTools);

        return CreateChatClientAgent(
            aiProjectClient,
            agentVersion,
            agentOptions,
            clientFactory,
            services);
    }

    /// <summary>
    /// Creates a new Prompt AI Agent using the provided <see cref="AIProjectClient"/> and options.
    /// </summary>
    /// <param name="aiProjectClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="model">The name of the model to use for the agent. Cannot be <see langword="null"/> or whitespace.</param>
    /// <param name="options">The options for creating the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation if needed.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace, or when the agent name is not provided in the options.</exception>
    public static async Task<ChatClientAgent> CreateAIAgentAsync(
        this AIProjectClient aiProjectClient,
        string model,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(options);
        Throw.IfNullOrWhitespace(model);
        const bool RequireInvocableTools = true;

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        ThrowIfInvalidAgentName(options.Name);

        PromptAgentDefinition agentDefinition = new(model)
        {
            Instructions = options.ChatOptions?.Instructions,
            Temperature = options.ChatOptions?.Temperature,
            TopP = options.ChatOptions?.TopP,
            TextOptions = new() { TextFormat = ToOpenAIResponseTextFormat(options.ChatOptions?.ResponseFormat, options.ChatOptions) }
        };

        // Attempt to capture breaking glass options from the raw representation factory that match the agent definition.
        if (options.ChatOptions?.RawRepresentationFactory?.Invoke(new NoOpChatClient()) is ResponseCreationOptions respCreationOptions)
        {
            agentDefinition.ReasoningOptions = respCreationOptions.ReasoningOptions;
        }

        ApplyToolsToAgentDefinition(agentDefinition, options.ChatOptions?.Tools);

        AgentVersionCreationOptions? creationOptions = new(agentDefinition);
        if (!string.IsNullOrWhiteSpace(options.Description))
        {
            creationOptions.Description = options.Description;
        }

        AgentVersion agentVersion = await CreateAgentVersionWithProtocolAsync(aiProjectClient, options.Name, creationOptions, cancellationToken).ConfigureAwait(false);

        var agentOptions = CreateChatClientAgentOptions(agentVersion, options, RequireInvocableTools);

        return CreateChatClientAgent(
            aiProjectClient,
            agentVersion,
            agentOptions,
            clientFactory,
            services);
    }

    /// <summary>
    /// Creates a new AI agent using the specified agent definition and optional configuration parameters.
    /// </summary>
    /// <param name="aiProjectClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="creationOptions">Settings that control the creation of the agent.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> or <paramref name="creationOptions"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// When using this extension method with a <see cref="PromptAgentDefinition"/> the tools are only declarative and not invocable.
    /// Invocation of any in-process tools will need to be handled manually.
    /// </remarks>
    public static ChatClientAgent CreateAIAgent(
        this AIProjectClient aiProjectClient,
        string name,
        AgentVersionCreationOptions creationOptions,
        Func<IChatClient, IChatClient>? clientFactory = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(aiProjectClient);
        ThrowIfInvalidAgentName(name);
        Throw.IfNull(creationOptions);

        return CreateAIAgent(
            aiProjectClient,
            name,
            tools: null,
            creationOptions,
            clientFactory,
            services: null,
            cancellationToken);
    }

    /// <summary>
    /// Asynchronously creates a new AI agent using the specified agent definition and optional configuration
    /// parameters.
    /// </summary>
    /// <param name="aiProjectClient">The client used to manage and interact with AI agents. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="creationOptions">Settings that control the creation of the agent.</param>
    /// <param name="clientFactory">A factory function to customize the creation of the chat client used by the agent.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="aiProjectClient"/> or <paramref name="creationOptions"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// When using this extension method with a <see cref="PromptAgentDefinition"/> the tools are only declarative and not invocable.
    /// Invocation of any in-process tools will need to be handled manually.
    /// </remarks>
    public static Task<ChatClientAgent> CreateAIAgentAsync(
        this AIProjectClient aiProjectClient,
        string name,
        AgentVersionCreationOptions creationOptions,
        Func<IChatClient, IChatClient>? clientFactory = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(aiProjectClient);
        ThrowIfInvalidAgentName(name);
        Throw.IfNull(creationOptions);

        return CreateAIAgentAsync(
            aiProjectClient,
            name,
            tools: null,
            creationOptions,
            clientFactory,
            services: null,
            cancellationToken);
    }

    #region Private

    private static readonly ModelReaderWriterOptions s_modelWriterOptionsWire = new("W");

    /// <summary>
    /// Retrieves an agent record by name using the Protocol method with user-agent header.
    /// </summary>
    private static AgentRecord GetAgentRecordByName(AIProjectClient aiProjectClient, string agentName, CancellationToken cancellationToken)
    {
        ClientResult protocolResponse = aiProjectClient.Agents.GetAgent(agentName, cancellationToken.ToRequestOptions(false));
        var rawResponse = protocolResponse.GetRawResponse();
        AgentRecord? result = ModelReaderWriter.Read<AgentRecord>(rawResponse.Content, s_modelWriterOptionsWire, AzureAIProjectsOpenAIContext.Default);
        return ClientResult.FromOptionalValue(result, rawResponse).Value!
            ?? throw new InvalidOperationException($"Agent with name '{agentName}' not found.");
    }

    /// <summary>
    /// Asynchronously retrieves an agent record by name using the Protocol method with user-agent header.
    /// </summary>
    private static async Task<AgentRecord> GetAgentRecordByNameAsync(AIProjectClient aiProjectClient, string agentName, CancellationToken cancellationToken)
    {
        ClientResult protocolResponse = await aiProjectClient.Agents.GetAgentAsync(agentName, cancellationToken.ToRequestOptions(false)).ConfigureAwait(false);
        var rawResponse = protocolResponse.GetRawResponse();
        AgentRecord? result = ModelReaderWriter.Read<AgentRecord>(rawResponse.Content, s_modelWriterOptionsWire, AzureAIProjectsOpenAIContext.Default);
        return ClientResult.FromOptionalValue(result, rawResponse).Value!
            ?? throw new InvalidOperationException($"Agent with name '{agentName}' not found.");
    }

    /// <summary>
    /// Creates an agent version using the Protocol method with user-agent header.
    /// </summary>
    private static AgentVersion CreateAgentVersionWithProtocol(AIProjectClient aiProjectClient, string agentName, AgentVersionCreationOptions creationOptions, CancellationToken cancellationToken)
    {
        using BinaryContent protocolRequest = BinaryContent.Create(ModelReaderWriter.Write(creationOptions, ModelReaderWriterOptions.Json, AzureAIProjectsContext.Default));
        ClientResult protocolResponse = aiProjectClient.Agents.CreateAgentVersion(agentName, protocolRequest, cancellationToken.ToRequestOptions(false));

        var rawResponse = protocolResponse.GetRawResponse();
        AgentVersion? result = ModelReaderWriter.Read<AgentVersion>(rawResponse.Content, s_modelWriterOptionsWire, AzureAIProjectsOpenAIContext.Default);
        return ClientResult.FromValue(result, rawResponse).Value!;
    }

    /// <summary>
    /// Asynchronously creates an agent version using the Protocol method with user-agent header.
    /// </summary>
    private static async Task<AgentVersion> CreateAgentVersionWithProtocolAsync(AIProjectClient aiProjectClient, string agentName, AgentVersionCreationOptions creationOptions, CancellationToken cancellationToken)
    {
        using BinaryContent protocolRequest = BinaryContent.Create(ModelReaderWriter.Write(creationOptions, ModelReaderWriterOptions.Json, AzureAIProjectsContext.Default));
        ClientResult protocolResponse = await aiProjectClient.Agents.CreateAgentVersionAsync(agentName, protocolRequest, cancellationToken.ToRequestOptions(false)).ConfigureAwait(false);

        var rawResponse = protocolResponse.GetRawResponse();
        AgentVersion? result = ModelReaderWriter.Read<AgentVersion>(rawResponse.Content, s_modelWriterOptionsWire, AzureAIProjectsOpenAIContext.Default);
        return ClientResult.FromValue(result, rawResponse).Value!;
    }

    private static ChatClientAgent CreateAIAgent(
        this AIProjectClient aiProjectClient,
        string name,
        IList<AITool>? tools,
        AgentVersionCreationOptions creationOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        IServiceProvider? services,
        CancellationToken cancellationToken)
    {
        var allowDeclarativeMode = tools is not { Count: > 0 };

        if (!allowDeclarativeMode)
        {
            ApplyToolsToAgentDefinition(creationOptions.Definition, tools);
        }

        AgentVersion agentVersion = CreateAgentVersionWithProtocol(aiProjectClient, name, creationOptions, cancellationToken);

        return CreateChatClientAgent(
            aiProjectClient,
            agentVersion,
            tools,
            clientFactory,
            !allowDeclarativeMode,
            services);
    }

    private static async Task<ChatClientAgent> CreateAIAgentAsync(
        this AIProjectClient aiProjectClient,
        string name,
        IList<AITool>? tools,
        AgentVersionCreationOptions creationOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        IServiceProvider? services,
        CancellationToken cancellationToken)
    {
        var allowDeclarativeMode = tools is not { Count: > 0 };

        if (!allowDeclarativeMode)
        {
            ApplyToolsToAgentDefinition(creationOptions.Definition, tools);
        }

        AgentVersion agentVersion = await CreateAgentVersionWithProtocolAsync(aiProjectClient, name, creationOptions, cancellationToken).ConfigureAwait(false);

        return CreateChatClientAgent(
            aiProjectClient,
            agentVersion,
            tools,
            clientFactory,
            !allowDeclarativeMode,
            services);
    }

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with the specified ChatClientAgentOptions.</summary>
    private static ChatClientAgent CreateChatClientAgent(
        AIProjectClient aiProjectClient,
        AgentVersion agentVersion,
        ChatClientAgentOptions agentOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        IServiceProvider? services)
    {
        IChatClient chatClient = new AzureAIProjectChatClient(aiProjectClient, agentVersion, agentOptions.ChatOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return new ChatClientAgent(chatClient, agentOptions, services: services);
    }

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with the specified ChatClientAgentOptions.</summary>
    private static ChatClientAgent CreateChatClientAgent(
        AIProjectClient aiProjectClient,
        AgentRecord agentRecord,
        ChatClientAgentOptions agentOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        IServiceProvider? services)
    {
        IChatClient chatClient = new AzureAIProjectChatClient(aiProjectClient, agentRecord, agentOptions.ChatOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return new ChatClientAgent(chatClient, agentOptions, services: services);
    }

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with the specified ChatClientAgentOptions.</summary>
    private static ChatClientAgent CreateChatClientAgent(
        AIProjectClient aiProjectClient,
        AgentReference agentReference,
        ChatClientAgentOptions agentOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        IServiceProvider? services)
    {
        IChatClient chatClient = new AzureAIProjectChatClient(aiProjectClient, agentReference, defaultModelId: null, agentOptions.ChatOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return new ChatClientAgent(chatClient, agentOptions, services: services);
    }

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with a auto-generated ChatClientAgentOptions from the specified configuration parameters.</summary>
    private static ChatClientAgent CreateChatClientAgent(
        AIProjectClient AIProjectClient,
        AgentVersion agentVersion,
        IList<AITool>? tools,
        Func<IChatClient, IChatClient>? clientFactory,
        bool requireInvocableTools,
        IServiceProvider? services)
        => CreateChatClientAgent(
            AIProjectClient,
            agentVersion,
            CreateChatClientAgentOptions(agentVersion, new ChatOptions() { Tools = tools }, requireInvocableTools),
            clientFactory,
            services);

    /// <summary>This method creates an <see cref="ChatClientAgent"/> with a auto-generated ChatClientAgentOptions from the specified configuration parameters.</summary>
    private static ChatClientAgent CreateChatClientAgent(
        AIProjectClient AIProjectClient,
        AgentRecord agentRecord,
        IList<AITool>? tools,
        Func<IChatClient, IChatClient>? clientFactory,
        bool requireInvocableTools,
        IServiceProvider? services)
        => CreateChatClientAgent(
            AIProjectClient,
            agentRecord,
            CreateChatClientAgentOptions(agentRecord.Versions.Latest, new ChatOptions() { Tools = tools }, requireInvocableTools),
            clientFactory,
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
            agentOptions.ChatOptions.Instructions = promptAgentDefinition.Instructions;
            agentOptions.ChatOptions.Temperature = promptAgentDefinition.Temperature;
            agentOptions.ChatOptions.TopP = promptAgentDefinition.TopP;
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

    private static ResponseTextFormat? ToOpenAIResponseTextFormat(ChatResponseFormat? format, ChatOptions? options = null) =>
        format switch
        {
            ChatResponseFormatText => ResponseTextFormat.CreateTextFormat(),

            ChatResponseFormatJson jsonFormat when StrictSchemaTransformCache.GetOrCreateTransformedSchema(jsonFormat) is { } jsonSchema =>
                ResponseTextFormat.CreateJsonSchemaFormat(
                    jsonFormat.SchemaName ?? "json_schema",
                    BinaryData.FromBytes(JsonSerializer.SerializeToUtf8Bytes(jsonSchema, AgentClientJsonContext.Default.JsonElement)),
                    jsonFormat.SchemaDescription,
                    HasStrict(options?.AdditionalProperties)),

            ChatResponseFormatJson => ResponseTextFormat.CreateJsonObjectFormat(),

            _ => null,
        };

    /// <summary>Key into AdditionalProperties used to store a strict option.</summary>
    private const string StrictKey = "strictJsonSchema";

    /// <summary>Gets whether the properties specify that strict schema handling is desired.</summary>
    private static bool? HasStrict(IReadOnlyDictionary<string, object?>? additionalProperties) =>
        additionalProperties?.TryGetValue(StrictKey, out object? strictObj) is true &&
        strictObj is bool strictValue ?
        strictValue : null;

    /// <summary>
    /// Gets the JSON schema transformer cache conforming to OpenAI <b>strict</b> / structured output restrictions per
    /// https://platform.openai.com/docs/guides/structured-outputs?api-mode=responses#supported-schemas.
    /// </summary>
    private static AIJsonSchemaTransformCache StrictSchemaTransformCache { get; } = new(new()
    {
        DisallowAdditionalProperties = true,
        ConvertBooleanSchemas = true,
        MoveDefaultKeywordToDescription = true,
        RequireAllProperties = true,
        TransformSchemaNode = (ctx, node) =>
        {
            // Move content from common but unsupported properties to description. In particular, we focus on properties that
            // the AIJsonUtilities schema generator might produce and/or that are explicitly mentioned in the OpenAI documentation.

            if (node is JsonObject schemaObj)
            {
                StringBuilder? additionalDescription = null;

                ReadOnlySpan<string> unsupportedProperties =
                [
                    // Produced by AIJsonUtilities but not in allow list at https://platform.openai.com/docs/guides/structured-outputs#supported-properties:
                    "contentEncoding", "contentMediaType", "not",

                    // Explicitly mentioned at https://platform.openai.com/docs/guides/structured-outputs?api-mode=responses#key-ordering as being unsupported with some models:
                    "minLength", "maxLength", "pattern", "format",
                    "minimum", "maximum", "multipleOf",
                    "patternProperties",
                    "minItems", "maxItems",

                    // Explicitly mentioned at https://learn.microsoft.com/azure/ai-services/openai/how-to/structured-outputs?pivots=programming-language-csharp&tabs=python-secure%2Cdotnet-entra-id#unsupported-type-specific-keywords
                    // as being unsupported with Azure OpenAI:
                    "unevaluatedProperties", "propertyNames", "minProperties", "maxProperties",
                    "unevaluatedItems", "contains", "minContains", "maxContains", "uniqueItems",
                ];

                foreach (string propName in unsupportedProperties)
                {
                    if (schemaObj[propName] is { } propNode)
                    {
                        _ = schemaObj.Remove(propName);
                        AppendLine(ref additionalDescription, propName, propNode);
                    }
                }

                if (additionalDescription is not null)
                {
                    schemaObj["description"] = schemaObj["description"] is { } descriptionNode && descriptionNode.GetValueKind() == JsonValueKind.String ?
                        $"{descriptionNode.GetValue<string>()}{Environment.NewLine}{additionalDescription}" :
                        additionalDescription.ToString();
                }

                return node;

                static void AppendLine(ref StringBuilder? sb, string propName, JsonNode propNode)
                {
                    sb ??= new();

                    if (sb.Length > 0)
                    {
                        _ = sb.AppendLine();
                    }

                    _ = sb.Append(propName).Append(": ").Append(propNode);
                }
            }

            return node;
        },
    });

    /// <summary>
    /// This class is a no-op implementation of <see cref="IChatClient"/> to be used to honor the argument passed
    /// while triggering <see cref="ChatOptions.RawRepresentationFactory"/> avoiding any unexpected exception on the caller implementation.
    /// </summary>
    private sealed class NoOpChatClient : IChatClient
    {
        public void Dispose() { }

        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => Task.FromResult(new ChatResponse());

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            yield return new ChatResponseUpdate();
        }
    }
    #endregion

#if NET
    [GeneratedRegex("^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")]
    private static partial Regex AgentNameValidationRegex();
#else
    private static Regex AgentNameValidationRegex() => new("^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$");
#endif

    private static string ThrowIfInvalidAgentName(string? name)
    {
        Throw.IfNullOrWhitespace(name);
        if (!AgentNameValidationRegex().IsMatch(name))
        {
            throw new ArgumentException("Agent name must be 1-63 characters long, start and end with an alphanumeric character, and can only contain alphanumeric characters or hyphens.", nameof(name));
        }
        return name;
    }
}

[JsonSerializable(typeof(JsonElement))]
internal sealed partial class AgentClientJsonContext : JsonSerializerContext;
