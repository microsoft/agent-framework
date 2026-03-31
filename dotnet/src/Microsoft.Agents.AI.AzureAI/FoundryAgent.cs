// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.Diagnostics.CodeAnalysis;
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
/// <see cref="FoundryAgent"/> connects to a pre-configured server-side agent in Microsoft Foundry,
/// wrapping it as an <see cref="AIAgent"/> for use with Agent Framework. Unlike the direct
/// <c>AIProjectClient.AsAIAgent(model, instructions)</c> approach (which creates a local agent
/// backed by the Responses API without any server-side agent definition), <see cref="FoundryAgent"/>
/// works with agents that are managed and versioned in the Foundry service.
/// </para>
/// <para>
/// This class provides convenient access to Foundry-specific features such as server-side
/// conversation management via <see cref="CreateConversationSessionAsync(CancellationToken)"/>.
/// </para>
/// <para>
/// Instances can be created directly via public constructors or through
/// <c>AsAIAgent</c> extension methods on <see cref="AIProjectClient"/>.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public sealed class FoundryAgent : DelegatingAIAgent
{
    private readonly AIProjectClient _aiProjectClient;

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
        : base(CreateInnerAgent(
            CreateProjectClient(projectEndpoint, credential, clientOptions),
            model, instructions, name, description, tools, clientFactory, loggerFactory, services,
            out var aiProjectClient))
    {
        this._aiProjectClient = aiProjectClient;
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
        : base(CreateInnerAgentFromEndpoint(
            CreateProjectClient(agentEndpoint, credential, clientOptions),
            agentEndpoint, tools, clientFactory, services,
            out var aiProjectClient))
    {
        this._aiProjectClient = aiProjectClient;
    }

    /// <summary>
    /// Internal constructor used by <c>AsAIAgent</c> extension methods that already have an <see cref="AIProjectClient"/> and a configured <see cref="ChatClientAgent"/>.
    /// </summary>
    internal FoundryAgent(AIProjectClient aiProjectClient, ChatClientAgent innerAgent)
        : base(Throw.IfNull(innerAgent))
    {
        this._aiProjectClient = Throw.IfNull(aiProjectClient);
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

        return (ChatClientAgentSession)await ((ChatClientAgent)this.InnerAgent).CreateSessionAsync(conversation.Id, cancellationToken).ConfigureAwait(false);
    }

    #endregion

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        if (serviceKey is null && serviceType == typeof(AIProjectClient))
        {
            return this._aiProjectClient;
        }

        return base.GetService(serviceType, serviceKey);
    }

    #region Private helpers

    private static ChatClientAgent CreateInnerAgent(
        AIProjectClient aiProjectClient,
        string model, string instructions,
        string? name, string? description,
        IList<AITool>? tools,
        Func<IChatClient, IChatClient>? clientFactory,
        ILoggerFactory? loggerFactory,
        IServiceProvider? services,
        out AIProjectClient outClient)
    {
        Throw.IfNullOrWhitespace(model);
        Throw.IfNullOrWhitespace(instructions);

        outClient = aiProjectClient;

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

        return AzureAIProjectChatClientExtensions.CreateResponsesChatClientAgent(aiProjectClient, options, clientFactory, loggerFactory, services);
    }

    private static ChatClientAgent CreateInnerAgentFromEndpoint(
        AIProjectClient aiProjectClient,
        Uri agentEndpoint,
        IList<AITool>? tools,
        Func<IChatClient, IChatClient>? clientFactory,
        IServiceProvider? services,
        out AIProjectClient outClient)
    {
        outClient = aiProjectClient;

        AgentReference agentReference = agentEndpoint.Segments[^1].TrimEnd('/');

        ChatClientAgentOptions agentOptions = new()
        {
            Name = agentReference.Name,
            ChatOptions = new() { Tools = tools },
        };

        IChatClient chatClient = new AzureAIProjectChatClient(aiProjectClient, agentReference, defaultModelId: null, agentOptions.ChatOptions);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return new ChatClientAgent(chatClient, agentOptions, services: services);
    }

    private static AIProjectClient CreateProjectClient(Uri endpoint, AuthenticationTokenProvider credential, AIProjectClientOptions? clientOptions = null)
    {
        Throw.IfNull(endpoint);
        Throw.IfNull(credential);

        clientOptions ??= new AIProjectClientOptions();
        clientOptions.AddPolicy(RequestOptionsExtensions.UserAgentPolicy, System.ClientModel.Primitives.PipelinePosition.PerCall);
        return new AIProjectClient(endpoint, credential, clientOptions);
    }

    #endregion
}
