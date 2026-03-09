// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.ClientModel.Primitives;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.AzureAI;

/// <summary>
/// Provides an <see cref="AIAgent"/> that uses a server-side versioned agent in Microsoft Foundry.
/// </summary>
/// <remarks>
/// <para>
/// Unlike <see cref="FoundryAgent"/> (which uses the Responses API directly), this class works with
/// server-side agent definitions that are created, versioned, and managed in the Foundry service.
/// </para>
/// <para>
/// This class has a private constructor and can only be instantiated via the static
/// <see cref="CreateAIAgentAsync(string, string, string, string?, IList{AITool}?, AIProjectClientOptions?, Func{IChatClient, IChatClient}?, IServiceProvider?, CancellationToken)">CreateAIAgentAsync</see>
/// or <see cref="GetAIAgentAsync(string, IList{AITool}?, AIProjectClientOptions?, Func{IChatClient, IChatClient}?, IServiceProvider?, CancellationToken)">GetAIAgentAsync</see> factory methods.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public sealed class FoundryVersionedAgent : AIAgent
{
    private const string ProjectEndpointEnvVar = "AZURE_AI_PROJECT_ENDPOINT";
    private const string ModelDeploymentEnvVar = "AZURE_AI_MODEL_DEPLOYMENT_NAME";

    private readonly AIProjectClient _aiProjectClient;
    private readonly ChatClientAgent _innerAgent;
    private readonly AgentVersion? _agentVersion;
    private readonly AIAgentMetadata _metadata = new("microsoft.foundry");

    private FoundryVersionedAgent(
        AIProjectClient aiProjectClient,
        ChatClientAgent innerAgent,
        AgentVersion? agentVersion = null)
    {
        this._aiProjectClient = aiProjectClient;
        this._innerAgent = innerAgent;
        this._agentVersion = agentVersion;
    }

    #region CreateAIAgentAsync

    /// <summary>
    /// Creates a new versioned agent in the Foundry service using environment variables for connection settings.
    /// </summary>
    /// <param name="name">The name for the agent.</param>
    /// <param name="instructions">The instructions that guide the agent's behavior.</param>
    /// <param name="model">The model deployment name. When not provided, resolved from the <c>AZURE_AI_MODEL_DEPLOYMENT_NAME</c> environment variable.</param>
    /// <param name="description">Optional description for the agent.</param>
    /// <param name="tools">Optional tools to use when interacting with the agent.</param>
    /// <param name="clientOptions">Optional configuration options for the <see cref="AIProjectClient"/>.</param>
    /// <param name="chatClientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/>.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="FoundryVersionedAgent"/> wrapping the newly created agent.</returns>
    /// <remarks>
    /// <para>
    /// This method reads the following environment variables:
    /// <list type="bullet">
    /// <item><c>AZURE_AI_PROJECT_ENDPOINT</c> (required) — The Microsoft Foundry project endpoint URL.</item>
    /// <item><c>AZURE_AI_MODEL_DEPLOYMENT_NAME</c> (optional) — The model deployment name, used when <paramref name="model"/> is not provided.</item>
    /// </list>
    /// </para>
    /// <para>Authentication uses <see cref="DefaultAzureCredential"/>.</para>
    /// </remarks>
    public static Task<FoundryVersionedAgent> CreateAIAgentAsync(
        string name,
        string instructions,
        string? model = null,
        string? description = null,
        IList<AITool>? tools = null,
        AIProjectClientOptions? clientOptions = null,
        Func<IChatClient, IChatClient>? chatClientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
        => CreateAIAgentAsync(
            GetRequiredEndpoint(),
            new DefaultAzureCredential(),
            name, ResolveModel(model), instructions, description, tools, clientOptions, chatClientFactory, services, cancellationToken);

    /// <summary>
    /// Creates a new versioned agent in the Foundry service using the specified endpoint and credentials.
    /// </summary>
    /// <param name="endpoint">The Microsoft Foundry project endpoint.</param>
    /// <param name="tokenProvider">The authentication token provider.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="model">The model deployment name to use for the agent.</param>
    /// <param name="instructions">The instructions that guide the agent's behavior.</param>
    /// <param name="description">Optional description for the agent.</param>
    /// <param name="tools">Optional tools to use when interacting with the agent.</param>
    /// <param name="clientOptions">Optional configuration options for the <see cref="AIProjectClient"/>.</param>
    /// <param name="chatClientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/>.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="FoundryVersionedAgent"/> wrapping the newly created agent.</returns>
    public static async Task<FoundryVersionedAgent> CreateAIAgentAsync(
        Uri endpoint,
        AuthenticationTokenProvider tokenProvider,
        string name,
        string model,
        string instructions,
        string? description = null,
        IList<AITool>? tools = null,
        AIProjectClientOptions? clientOptions = null,
        Func<IChatClient, IChatClient>? chatClientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(endpoint);
        Throw.IfNull(tokenProvider);
        Throw.IfNullOrWhitespace(model);
        Throw.IfNullOrWhitespace(instructions);
        AzureAIProjectChatClientExtensions.ThrowIfInvalidAgentName(name);

        var aiProjectClient = CreateProjectClient(endpoint, tokenProvider, clientOptions);

        AgentVersion agentVersion = await AzureAIProjectChatClientExtensions.CreateAgentVersionWithProtocolAsync(
            aiProjectClient,
            name,
            new AgentVersionCreationOptions(new PromptAgentDefinition(model) { Instructions = instructions }) { Description = description },
            tools,
            cancellationToken).ConfigureAwait(false);

        var agentOptions = AzureAIProjectChatClientExtensions.CreateChatClientAgentOptions(
            agentVersion,
            new ChatOptions() { Tools = tools },
            requireInvocableTools: tools is { Count: > 0 });

        var innerAgent = AzureAIProjectChatClientExtensions.CreateChatClientAgent(aiProjectClient, agentVersion, agentOptions, chatClientFactory, services);
        return new FoundryVersionedAgent(aiProjectClient, innerAgent, agentVersion);
    }

    /// <summary>
    /// Creates a new versioned agent in the Foundry service using environment variables and the specified options.
    /// </summary>
    /// <param name="options">Configuration options for the agent, including name, tools, instructions, etc.</param>
    /// <param name="model">The model deployment name. When not provided, resolved from the <c>AZURE_AI_MODEL_DEPLOYMENT_NAME</c> environment variable.</param>
    /// <param name="clientOptions">Optional configuration options for the <see cref="AIProjectClient"/>.</param>
    /// <param name="chatClientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/>.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="FoundryVersionedAgent"/> wrapping the newly created agent.</returns>
    /// <remarks>
    /// <para>
    /// This method reads the following environment variables:
    /// <list type="bullet">
    /// <item><c>AZURE_AI_PROJECT_ENDPOINT</c> (required) — The Microsoft Foundry project endpoint URL.</item>
    /// <item><c>AZURE_AI_MODEL_DEPLOYMENT_NAME</c> (optional) — The model deployment name, used when <paramref name="model"/> is not provided.</item>
    /// </list>
    /// </para>
    /// <para>Authentication uses <see cref="DefaultAzureCredential"/>.</para>
    /// </remarks>
    public static Task<FoundryVersionedAgent> CreateAIAgentAsync(
        ChatClientAgentOptions options,
        string? model = null,
        AIProjectClientOptions? clientOptions = null,
        Func<IChatClient, IChatClient>? chatClientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
        => CreateAIAgentAsync(
            GetRequiredEndpoint(),
            new DefaultAzureCredential(),
            ResolveModel(model), options, clientOptions, chatClientFactory, services, cancellationToken);

    /// <summary>
    /// Creates a new versioned agent in the Foundry service using the specified endpoint, credentials, and options.
    /// </summary>
    /// <param name="endpoint">The Microsoft Foundry project endpoint.</param>
    /// <param name="tokenProvider">The authentication token provider.</param>
    /// <param name="model">The model deployment name to use for the agent.</param>
    /// <param name="options">Configuration options for the agent, including name, tools, instructions, etc.</param>
    /// <param name="clientOptions">Optional configuration options for the <see cref="AIProjectClient"/>.</param>
    /// <param name="chatClientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/>.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="FoundryVersionedAgent"/> wrapping the newly created agent.</returns>
    public static async Task<FoundryVersionedAgent> CreateAIAgentAsync(
        Uri endpoint,
        AuthenticationTokenProvider tokenProvider,
        string model,
        ChatClientAgentOptions options,
        AIProjectClientOptions? clientOptions = null,
        Func<IChatClient, IChatClient>? chatClientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(endpoint);
        Throw.IfNull(tokenProvider);
        Throw.IfNullOrWhitespace(model);
        Throw.IfNull(options);

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        AzureAIProjectChatClientExtensions.ThrowIfInvalidAgentName(options.Name);

        var aiProjectClient = CreateProjectClient(endpoint, tokenProvider, clientOptions);

        AgentVersion agentVersion = await AzureAIProjectChatClientExtensions.CreateAgentVersionFromOptionsAsync(
            aiProjectClient, model, options, cancellationToken).ConfigureAwait(false);

        var agentOptions = AzureAIProjectChatClientExtensions.CreateChatClientAgentOptions(agentVersion, options, requireInvocableTools: true);
        var innerAgent = AzureAIProjectChatClientExtensions.CreateChatClientAgent(aiProjectClient, agentVersion, agentOptions, chatClientFactory, services);
        return new FoundryVersionedAgent(aiProjectClient, innerAgent, agentVersion);
    }

    /// <summary>
    /// Creates a new versioned agent in the Foundry service using environment variables and native SDK creation options.
    /// </summary>
    /// <param name="name">The name for the agent.</param>
    /// <param name="creationOptions">Settings that control the creation of the agent.</param>
    /// <param name="clientOptions">Optional configuration options for the <see cref="AIProjectClient"/>.</param>
    /// <param name="chatClientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/>.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="FoundryVersionedAgent"/> wrapping the newly created agent.</returns>
    /// <remarks>
    /// <para>
    /// This method reads the <c>AZURE_AI_PROJECT_ENDPOINT</c> environment variable (required) and
    /// uses <see cref="DefaultAzureCredential"/> for authentication.
    /// </para>
    /// <para>
    /// When using this method with a <see cref="PromptAgentDefinition"/> the tools are only declarative and not invocable.
    /// Invocation of any in-process tools will need to be handled manually.
    /// </para>
    /// </remarks>
    public static Task<FoundryVersionedAgent> CreateAIAgentAsync(
        string name,
        AgentVersionCreationOptions creationOptions,
        AIProjectClientOptions? clientOptions = null,
        Func<IChatClient, IChatClient>? chatClientFactory = null,
        CancellationToken cancellationToken = default)
        => CreateAIAgentAsync(
            GetRequiredEndpoint(),
            new DefaultAzureCredential(),
            name, creationOptions, clientOptions, chatClientFactory, cancellationToken);

    /// <summary>
    /// Creates a new versioned agent in the Foundry service using the specified endpoint, credentials, and native SDK creation options.
    /// </summary>
    /// <param name="endpoint">The Microsoft Foundry project endpoint.</param>
    /// <param name="tokenProvider">The authentication token provider.</param>
    /// <param name="name">The name for the agent.</param>
    /// <param name="creationOptions">Settings that control the creation of the agent.</param>
    /// <param name="clientOptions">Optional configuration options for the <see cref="AIProjectClient"/>.</param>
    /// <param name="chatClientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/>.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="FoundryVersionedAgent"/> wrapping the newly created agent.</returns>
    /// <remarks>
    /// When using this method with a <see cref="PromptAgentDefinition"/> the tools are only declarative and not invocable.
    /// Invocation of any in-process tools will need to be handled manually.
    /// </remarks>
    public static async Task<FoundryVersionedAgent> CreateAIAgentAsync(
        Uri endpoint,
        AuthenticationTokenProvider tokenProvider,
        string name,
        AgentVersionCreationOptions creationOptions,
        AIProjectClientOptions? clientOptions = null,
        Func<IChatClient, IChatClient>? chatClientFactory = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(endpoint);
        Throw.IfNull(tokenProvider);
        Throw.IfNull(creationOptions);
        AzureAIProjectChatClientExtensions.ThrowIfInvalidAgentName(name);

        var aiProjectClient = CreateProjectClient(endpoint, tokenProvider, clientOptions);

        AgentVersion agentVersion = await AzureAIProjectChatClientExtensions.CreateAgentVersionWithProtocolAsync(
            aiProjectClient, name, creationOptions, tools: null, cancellationToken).ConfigureAwait(false);

        var agentOptions = AzureAIProjectChatClientExtensions.CreateChatClientAgentOptions(
            agentVersion,
            chatOptions: (ChatOptions?)null,
            requireInvocableTools: false);

        var innerAgent = AzureAIProjectChatClientExtensions.CreateChatClientAgent(aiProjectClient, agentVersion, agentOptions, chatClientFactory, services: null);
        return new FoundryVersionedAgent(aiProjectClient, innerAgent, agentVersion);
    }

    #endregion

    #region GetAIAgentAsync

    /// <summary>
    /// Retrieves an existing versioned agent from the Foundry service using environment variables for connection settings.
    /// </summary>
    /// <param name="name">The name of the server-side agent to retrieve.</param>
    /// <param name="tools">Optional tools to use when interacting with the agent.</param>
    /// <param name="clientOptions">Optional configuration options for the <see cref="AIProjectClient"/>.</param>
    /// <param name="chatClientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/>.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="FoundryVersionedAgent"/> wrapping the retrieved agent.</returns>
    /// <remarks>
    /// <para>
    /// This method reads the <c>AZURE_AI_PROJECT_ENDPOINT</c> environment variable (required) and
    /// uses <see cref="DefaultAzureCredential"/> for authentication.
    /// </para>
    /// </remarks>
    public static Task<FoundryVersionedAgent> GetAIAgentAsync(
        string name,
        IList<AITool>? tools = null,
        AIProjectClientOptions? clientOptions = null,
        Func<IChatClient, IChatClient>? chatClientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
        => GetAIAgentAsync(
            GetRequiredEndpoint(),
            new DefaultAzureCredential(),
            name, tools, clientOptions, chatClientFactory, services, cancellationToken);

    /// <summary>
    /// Retrieves an existing versioned agent from the Foundry service using the specified endpoint and credentials.
    /// </summary>
    /// <param name="endpoint">The Microsoft Foundry project endpoint.</param>
    /// <param name="tokenProvider">The authentication token provider.</param>
    /// <param name="name">The name of the server-side agent to retrieve.</param>
    /// <param name="tools">Optional tools to use when interacting with the agent.</param>
    /// <param name="clientOptions">Optional configuration options for the <see cref="AIProjectClient"/>.</param>
    /// <param name="chatClientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/>.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="FoundryVersionedAgent"/> wrapping the retrieved agent.</returns>
    public static async Task<FoundryVersionedAgent> GetAIAgentAsync(
        Uri endpoint,
        AuthenticationTokenProvider tokenProvider,
        string name,
        IList<AITool>? tools = null,
        AIProjectClientOptions? clientOptions = null,
        Func<IChatClient, IChatClient>? chatClientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(endpoint);
        Throw.IfNull(tokenProvider);
        AzureAIProjectChatClientExtensions.ThrowIfInvalidAgentName(name);

        var aiProjectClient = CreateProjectClient(endpoint, tokenProvider, clientOptions);

        AgentRecord agentRecord = await AzureAIProjectChatClientExtensions.GetAgentRecordByNameAsync(aiProjectClient, name, cancellationToken).ConfigureAwait(false);
        var agentVersion = agentRecord.Versions.Latest;

        var allowDeclarativeMode = tools is not { Count: > 0 };
        var agentOptions = AzureAIProjectChatClientExtensions.CreateChatClientAgentOptions(
            agentVersion,
            new ChatOptions() { Tools = tools },
            requireInvocableTools: !allowDeclarativeMode);

        var innerAgent = AzureAIProjectChatClientExtensions.CreateChatClientAgent(aiProjectClient, agentVersion, agentOptions, chatClientFactory, services);
        return new FoundryVersionedAgent(aiProjectClient, innerAgent, agentVersion);
    }

    /// <summary>
    /// Retrieves an existing versioned agent from the Foundry service using environment variables and the specified options.
    /// </summary>
    /// <param name="options">Configuration options for the agent. The <see cref="ChatClientAgentOptions.Name"/> property must be set.</param>
    /// <param name="clientOptions">Optional configuration options for the <see cref="AIProjectClient"/>.</param>
    /// <param name="chatClientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/>.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="FoundryVersionedAgent"/> wrapping the retrieved agent.</returns>
    /// <remarks>
    /// <para>
    /// This method reads the <c>AZURE_AI_PROJECT_ENDPOINT</c> environment variable (required) and
    /// uses <see cref="DefaultAzureCredential"/> for authentication.
    /// </para>
    /// </remarks>
    public static Task<FoundryVersionedAgent> GetAIAgentAsync(
        ChatClientAgentOptions options,
        AIProjectClientOptions? clientOptions = null,
        Func<IChatClient, IChatClient>? chatClientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
        => GetAIAgentAsync(
            GetRequiredEndpoint(),
            new DefaultAzureCredential(),
            options, clientOptions, chatClientFactory, services, cancellationToken);

    /// <summary>
    /// Retrieves an existing versioned agent from the Foundry service using the specified endpoint, credentials, and options.
    /// </summary>
    /// <param name="endpoint">The Microsoft Foundry project endpoint.</param>
    /// <param name="tokenProvider">The authentication token provider.</param>
    /// <param name="options">Configuration options for the agent. The <see cref="ChatClientAgentOptions.Name"/> property must be set.</param>
    /// <param name="clientOptions">Optional configuration options for the <see cref="AIProjectClient"/>.</param>
    /// <param name="chatClientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/>.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="FoundryVersionedAgent"/> wrapping the retrieved agent.</returns>
    public static async Task<FoundryVersionedAgent> GetAIAgentAsync(
        Uri endpoint,
        AuthenticationTokenProvider tokenProvider,
        ChatClientAgentOptions options,
        AIProjectClientOptions? clientOptions = null,
        Func<IChatClient, IChatClient>? chatClientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(endpoint);
        Throw.IfNull(tokenProvider);
        Throw.IfNull(options);

        if (string.IsNullOrWhiteSpace(options.Name))
        {
            throw new ArgumentException("Agent name must be provided in the options.Name property", nameof(options));
        }

        AzureAIProjectChatClientExtensions.ThrowIfInvalidAgentName(options.Name);

        var aiProjectClient = CreateProjectClient(endpoint, tokenProvider, clientOptions);

        AgentRecord agentRecord = await AzureAIProjectChatClientExtensions.GetAgentRecordByNameAsync(aiProjectClient, options.Name, cancellationToken).ConfigureAwait(false);
        var agentVersion = agentRecord.Versions.Latest;

        var agentOptions = AzureAIProjectChatClientExtensions.CreateChatClientAgentOptions(agentVersion, options, requireInvocableTools: !options.UseProvidedChatClientAsIs);
        var innerAgent = AzureAIProjectChatClientExtensions.CreateChatClientAgent(aiProjectClient, agentVersion, agentOptions, chatClientFactory, services);
        return new FoundryVersionedAgent(aiProjectClient, innerAgent, agentVersion);
    }

    #endregion

    #region DeleteAIAgentAsync

    /// <summary>
    /// Deletes the server-side agent associated with the specified <see cref="FoundryVersionedAgent"/>.
    /// </summary>
    /// <param name="agent">The agent to delete. Cannot be <see langword="null"/>.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A task representing the asynchronous delete operation.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="agent"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">The agent does not have a name.</exception>
    public static async Task DeleteAIAgentAsync(FoundryVersionedAgent agent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);

        if (string.IsNullOrWhiteSpace(agent.Name))
        {
            throw new InvalidOperationException("The agent does not have a name and cannot be deleted.");
        }

        await agent._aiProjectClient.Agents.DeleteAgentAsync(agent.Name, cancellationToken).ConfigureAwait(false);
    }

    #endregion

    #region AIAgent overrides

    /// <inheritdoc/>
    protected override string? IdCore => this._innerAgent.Id;

    /// <inheritdoc/>
    public override string? Name => this._innerAgent.Name;

    /// <inheritdoc/>
    public override string? Description => this._innerAgent.Description;

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        return base.GetService(serviceType, serviceKey)
            ?? (serviceKey is null && serviceType == typeof(AIAgentMetadata) ? this._metadata
            : serviceKey is null && serviceType == typeof(AIProjectClient) ? this._aiProjectClient
            : serviceKey is null && serviceType == typeof(AgentVersion) ? this._agentVersion
            : serviceKey is null && serviceType == typeof(ChatClientAgent) ? this._innerAgent
            : this._innerAgent.GetService(serviceType, serviceKey));
    }

    /// <inheritdoc/>
    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
        => this._innerAgent.RunAsync(messages, session, options, cancellationToken);

    /// <inheritdoc/>
    protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
        => this._innerAgent.RunStreamingAsync(messages, session, options, cancellationToken);

    /// <inheritdoc/>
    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        => this._innerAgent.CreateSessionAsync(cancellationToken);

    /// <summary>
    /// Creates a new server-side conversation in the Foundry project and returns a <see cref="ChatClientAgentSession"/>
    /// linked to it.
    /// </summary>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgentSession"/> associated with the newly created conversation.</returns>
    /// <remarks>
    /// <para>
    /// This method combines two steps into one: creating a server-side <c>ProjectConversation</c> and
    /// creating a <see cref="ChatClientAgentSession"/> linked to its conversation ID. Sessions created this way
    /// will appear in the Foundry Project UI under conversations.
    /// </para>
    /// <para>
    /// For sessions that do not need to appear in the Foundry UI, use
    /// <see cref="AIAgent.CreateSessionAsync(CancellationToken)"/> instead, which works based on <c>PreviousResponseId</c> only.
    /// </para>
    /// </remarks>
    public async Task<ChatClientAgentSession> CreateConversationSessionAsync(CancellationToken cancellationToken = default)
    {
        var conversationsClient = this._aiProjectClient
            .GetProjectOpenAIClient()
            .GetProjectConversationsClient();

        var conversation = (await conversationsClient.CreateProjectConversationAsync(options: null, cancellationToken).ConfigureAwait(false)).Value;

        return (ChatClientAgentSession)await this._innerAgent.CreateSessionAsync(conversation.Id, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => this._innerAgent.SerializeSessionAsync(session, jsonSerializerOptions, cancellationToken);

    /// <inheritdoc/>
    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => this._innerAgent.DeserializeSessionAsync(serializedState, jsonSerializerOptions, cancellationToken);

    #endregion

    #region Private helpers

    private static Uri GetRequiredEndpoint()
        => new(Environment.GetEnvironmentVariable(ProjectEndpointEnvVar)
            ?? throw new InvalidOperationException($"Environment variable '{ProjectEndpointEnvVar}' is not set."));

    private static string ResolveModel(string? model)
        => model ?? Environment.GetEnvironmentVariable(ModelDeploymentEnvVar)
            ?? throw new InvalidOperationException($"Model deployment name must be provided or set via the '{ModelDeploymentEnvVar}' environment variable.");

    private static AIProjectClient CreateProjectClient(Uri endpoint, AuthenticationTokenProvider tokenProvider, AIProjectClientOptions? clientOptions)
    {
        clientOptions ??= new AIProjectClientOptions();
        clientOptions.AddPolicy(RequestOptionsExtensions.UserAgentPolicy, PipelinePosition.PerCall);
        return new AIProjectClient(endpoint, tokenProvider, clientOptions);
    }

    #endregion
}
