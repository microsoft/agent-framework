// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.ClientModel.Primitives;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.AzureAI;

/// <summary>
/// Provides an <see cref="AIAgent"/> that uses an Azure AI Foundry project as its backing service.
/// </summary>
/// <remarks>
/// This agent internally creates an <see cref="AIProjectClient"/> and a <see cref="ChatClientAgent"/>
/// backed by the project's Responses API. All operations are delegated to the internal <see cref="ChatClientAgent"/>.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public sealed class FoundryAgentClient : AIAgent
{
    private const string ProjectEndpointEnvVar = "AZURE_AI_PROJECT_ENDPOINT";
    private const string ModelDeploymentEnvVar = "AZURE_AI_MODEL_DEPLOYMENT_NAME";

    private readonly AIProjectClient _aiProjectClient;
    private readonly ChatClientAgent _innerAgent;

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryAgentClient"/> class using environment variables for configuration.
    /// </summary>
    /// <param name="instructions">Optional system instructions that guide the agent's behavior.</param>
    /// <param name="name">Optional name for the agent.</param>
    /// <param name="description">Optional human-readable description of the agent's purpose and capabilities.</param>
    /// <param name="tools">Optional collection of tools that the agent can invoke during conversations.</param>
    /// <param name="chatClientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for creating loggers used by the agent.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    /// <exception cref="InvalidOperationException">The <c>AZURE_AI_PROJECT_ENDPOINT</c> environment variable is not set.</exception>
    /// <remarks>
    /// <para>
    /// This constructor reads the following environment variables:
    /// <list type="bullet">
    /// <item><c>AZURE_AI_PROJECT_ENDPOINT</c> (required) — The Azure AI Foundry project endpoint URL.</item>
    /// <item><c>AZURE_AI_MODEL_DEPLOYMENT_NAME</c> (optional) — The model deployment name to use.</item>
    /// </list>
    /// </para>
    /// <para>Authentication uses <see cref="DefaultAzureCredential"/>.</para>
    /// </remarks>
    public FoundryAgentClient(
        string? instructions = null,
        string? name = null,
        string? description = null,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? chatClientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null)
        : this(
              new Uri(Environment.GetEnvironmentVariable(ProjectEndpointEnvVar)
                  ?? throw new InvalidOperationException($"Environment variable '{ProjectEndpointEnvVar}' is not set.")),
              new DefaultAzureCredential(),
              Environment.GetEnvironmentVariable(ModelDeploymentEnvVar) ?? string.Empty,
              clientOptions: null,
              instructions,
              name,
              description,
              tools,
              chatClientFactory,
              loggerFactory,
              services)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryAgentClient"/> class.
    /// </summary>
    /// <param name="endpoint">The Azure AI Foundry project endpoint.</param>
    /// <param name="tokenProvider">The authentication token provider used to authenticate with the Azure AI Foundry service.</param>
    /// <param name="model">The model deployment name to use for the agent (e.g., "gpt-4o-mini").</param>
    /// <param name="clientOptions">Optional configuration options for the <see cref="AIProjectClient"/>.</param>
    /// <param name="instructions">Optional system instructions that guide the agent's behavior.</param>
    /// <param name="name">Optional name for the agent.</param>
    /// <param name="description">Optional human-readable description of the agent's purpose and capabilities.</param>
    /// <param name="tools">Optional collection of tools that the agent can invoke during conversations.</param>
    /// <param name="chatClientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for creating loggers used by the agent.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    /// <exception cref="ArgumentNullException"><paramref name="endpoint"/> or <paramref name="tokenProvider"/> is <see langword="null"/>.</exception>
    public FoundryAgentClient(
        Uri endpoint,
        AuthenticationTokenProvider tokenProvider,
        string model,
        AIProjectClientOptions? clientOptions = null,
        string? instructions = null,
        string? name = null,
        string? description = null,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? chatClientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null)
        : this(
              endpoint,
              tokenProvider,
              clientOptions,
              new ChatClientAgentOptions
              {
                  ChatOptions = new ChatOptions
                  {
                      ModelId = model,
                      Tools = tools,
                      Instructions = instructions
                  },
                  Name = name,
                  Description = description
              },
              chatClientFactory,
              loggerFactory,
              services)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryAgentClient"/> class.
    /// </summary>
    /// <param name="endpoint">The Azure AI Foundry project endpoint.</param>
    /// <param name="tokenProvider">The authentication token provider used to authenticate with the Azure AI Foundry service.</param>
    /// <param name="clientOptions">Optional configuration options for the <see cref="AIProjectClient"/>.</param>
    /// <param name="options">Configuration options that control all aspects of the agent's behavior.</param>
    /// <param name="chatClientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for creating loggers used by the agent.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    /// <exception cref="ArgumentNullException"><paramref name="endpoint"/> or <paramref name="tokenProvider"/> is <see langword="null"/>.</exception>
    public FoundryAgentClient(
        Uri endpoint,
        AuthenticationTokenProvider tokenProvider,
        AIProjectClientOptions? clientOptions = null,
        ChatClientAgentOptions? options = null,
        Func<IChatClient, IChatClient>? chatClientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(endpoint);
        Throw.IfNull(tokenProvider);

        clientOptions ??= new AIProjectClientOptions();
        clientOptions.AddPolicy(RequestOptionsExtensions.UserAgentPolicy, PipelinePosition.PerCall);

        this._aiProjectClient = new AIProjectClient(endpoint, tokenProvider, clientOptions);

        IChatClient chatClient = this._aiProjectClient
            .OpenAI
            .GetProjectResponsesClientForModel(options?.ChatOptions?.ModelId ?? string.Empty)
            .AsIChatClient();

        if (chatClientFactory is not null)
        {
            chatClient = chatClientFactory(chatClient);
        }

        this._innerAgent = new ChatClientAgent(chatClient, options, loggerFactory, services);
    }

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
            ?? (serviceKey is null && serviceType == typeof(AIProjectClient) ? this._aiProjectClient
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

    /// <inheritdoc/>
    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => this._innerAgent.SerializeSessionAsync(session, jsonSerializerOptions, cancellationToken);

    /// <inheritdoc/>
    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => this._innerAgent.DeserializeSessionAsync(serializedState, jsonSerializerOptions, cancellationToken);
}
