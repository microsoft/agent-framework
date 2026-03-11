// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.ClientModel.Primitives;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Azure.AI.Projects;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.AzureAI;

/// <summary>
/// Provides an <see cref="AIAgent"/> that uses an Microsoft Foundry project as its backing service.
/// </summary>
/// <remarks>
/// This agent internally creates an <see cref="AIProjectClient"/> and a <see cref="ChatClientAgent"/>
/// backed by the project's Responses API. All operations are delegated to the internal <see cref="ChatClientAgent"/>.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public sealed class FoundryAgent : AIAgent
{
    private readonly AIProjectClient _aiProjectClient;
    private readonly ChatClientAgent _innerAgent;
    private readonly AIAgentMetadata _metadata = new("microsoft.foundry");

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryAgent"/> class.
    /// </summary>
    /// <param name="endpoint">The Microsoft Foundry project endpoint.</param>
    /// <param name="tokenProvider">The authentication token provider used to authenticate with the Microsoft Foundry service.</param>
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
    public FoundryAgent(
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
                      ModelId = Throw.IfNullOrWhitespace(model),
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
    /// Initializes a new instance of the <see cref="FoundryAgent"/> class.
    /// </summary>
    /// <param name="endpoint">The Microsoft Foundry project endpoint.</param>
    /// <param name="tokenProvider">The authentication token provider used to authenticate with the Microsoft Foundry service.</param>
    /// <param name="clientOptions">Optional configuration options for the <see cref="AIProjectClient"/>.</param>
    /// <param name="options">Configuration options that control all aspects of the agent's behavior.</param>
    /// <param name="chatClientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for creating loggers used by the agent.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    /// <exception cref="ArgumentNullException"><paramref name="endpoint"/> or <paramref name="tokenProvider"/> is <see langword="null"/>.</exception>
    public FoundryAgent(
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
            ?? (serviceKey is null && serviceType == typeof(AIAgentMetadata) ? this._metadata
            : serviceKey is null && serviceType == typeof(AIProjectClient) ? this._aiProjectClient
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
}
