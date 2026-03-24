// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.AzureAI;

/// <summary>
/// Provides an <see cref="AIAgent"/> that uses Microsoft Foundry for AI agent capabilities.
/// </summary>
/// <remarks>
/// <para>
/// This class wraps a <see cref="ChatClientAgent"/> and provides convenient access to
/// Foundry-specific features such as server-side conversation management via
/// <see cref="CreateConversationSessionAsync(CancellationToken)"/>.
/// </para>
/// <para>
/// Instances can be created directly via public constructors or through
/// <c>AsAIAgent</c> extension methods on <see cref="AIProjectClient"/>.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public sealed class FoundryAgent : AIAgent
{
    private readonly AIProjectClient _aiProjectClient;
    private readonly ChatClientAgent _innerAgent;

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryAgent"/> class using the direct Responses API path.
    /// </summary>
    /// <param name="projectEndpoint">The Microsoft Foundry project endpoint.</param>
    /// <param name="credential">The authentication credential.</param>
    /// <param name="model">The model deployment name.</param>
    /// <param name="instructions">The instructions that guide the agent's behavior.</param>
    /// <param name="clientOptions">Optional configuration options for the <see cref="AIProjectClient"/>.</param>
    /// <param name="name">Optional name for the agent.</param>
    /// <param name="description">Optional description for the agent.</param>
    /// <param name="tools">Optional tools to use when interacting with the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/>.</param>
    /// <param name="loggerFactory">Optional logger factory for creating loggers used by the agent.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    public FoundryAgent(
        Uri projectEndpoint,
        AuthenticationTokenProvider credential,
        string model,
        string instructions,
        AIProjectClientOptions? clientOptions = null,
        string? name = null,
        string? description = null,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(projectEndpoint);
        Throw.IfNull(credential);
        Throw.IfNullOrWhitespace(model);
        Throw.IfNullOrWhitespace(instructions);

        this._aiProjectClient = CreateProjectClient(projectEndpoint, credential, clientOptions);

        ChatClientAgentOptions options = new()
        {
            Name = name,
            Description = description,
            ChatOptions = new ChatOptions
            {
                ModelId = model,
                Instructions = instructions,
                Tools = tools,
            },
        };

        this._innerAgent = AzureAIProjectChatClientExtensions.CreateResponsesChatClientAgent(this._aiProjectClient, options, clientFactory, loggerFactory, services);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryAgent"/> class from an agent-specific endpoint.
    /// </summary>
    /// <param name="agentEndpoint">The agent-specific endpoint URI (must contain the agent name in the path).</param>
    /// <param name="credential">The authentication credential.</param>
    /// <param name="clientOptions">Optional configuration options for the <see cref="AIProjectClient"/>.</param>
    /// <param name="tools">Optional tools to use when interacting with the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/>.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    public FoundryAgent(
        Uri agentEndpoint,
        AuthenticationTokenProvider credential,
        AIProjectClientOptions? clientOptions = null,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(agentEndpoint);
        Throw.IfNull(credential);

        this._aiProjectClient = CreateProjectClient(agentEndpoint, credential, clientOptions);

        // Extract the agent name from the last non-empty path segment of the URI.
        AgentReference agentReference = agentEndpoint.Segments[^1].TrimEnd('/');

        ChatClientAgentOptions agentOptions = new()
        {
            Name = agentReference.Name,
            ChatOptions = new() { Tools = tools },
        };

        IChatClient chatClient = new AzureAIProjectChatClient(this._aiProjectClient, agentReference, defaultModelId: null, agentOptions.ChatOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        this._innerAgent = new ChatClientAgent(chatClient, agentOptions, services: services);
    }

    /// <summary>
    /// Internal constructor used by <c>AsAIAgent</c> extension methods that already have an <see cref="AIProjectClient"/> and a configured <see cref="ChatClientAgent"/>.
    /// </summary>
    internal FoundryAgent(AIProjectClient aiProjectClient, ChatClientAgent innerAgent)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(innerAgent);

        this._aiProjectClient = aiProjectClient;
        this._innerAgent = innerAgent;
    }

    #region Convenience methods

    /// <summary>
    /// Creates a server-side conversation session that appears in the Foundry Project UI.
    /// </summary>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgentSession"/> linked to the newly created server-side conversation.</returns>
    public async Task<ChatClientAgentSession> CreateConversationSessionAsync(CancellationToken cancellationToken = default)
    {
        var conversationsClient = this._aiProjectClient
            .GetProjectOpenAIClient()
            .GetProjectConversationsClient();

        var conversation = (await conversationsClient.CreateProjectConversationAsync(options: null, cancellationToken).ConfigureAwait(false)).Value;

        return (ChatClientAgentSession)await this._innerAgent.CreateSessionAsync(conversation.Id, cancellationToken).ConfigureAwait(false);
    }

    #endregion

    #region AIAgent overrides

    /// <inheritdoc/>
    public override string? Name => this._innerAgent.Name;

    /// <inheritdoc/>
    public override string? Description => this._innerAgent.Description;

    /// <inheritdoc/>
    protected override string? IdCore => this._innerAgent.Id;

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        if (serviceKey is null && serviceType == typeof(AIProjectClient))
        {
            return this._aiProjectClient;
        }

        if (serviceKey is null && serviceType == typeof(ChatClientAgent))
        {
            return this._innerAgent;
        }

        return this._innerAgent.GetService(serviceType, serviceKey);
    }

    /// <inheritdoc/>
    protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, CancellationToken cancellationToken)
        => this._innerAgent.RunAsync(messages, session, options, cancellationToken);

    /// <inheritdoc/>
    protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, CancellationToken cancellationToken)
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

    #endregion

    private static AIProjectClient CreateProjectClient(Uri endpoint, AuthenticationTokenProvider credential, AIProjectClientOptions? clientOptions = null)
    {
        Throw.IfNull(endpoint);
        Throw.IfNull(credential);

        clientOptions ??= new AIProjectClientOptions();
        clientOptions.AddPolicy(RequestOptionsExtensions.UserAgentPolicy, System.ClientModel.Primitives.PipelinePosition.PerCall);
        return new AIProjectClient(endpoint, credential, clientOptions);
    }
}
