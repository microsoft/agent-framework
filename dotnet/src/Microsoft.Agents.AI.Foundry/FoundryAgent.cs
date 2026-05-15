// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry;

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
    /// <summary>
    /// The cached <see cref="AIProjectClient"/> supplied to or constructed by the active constructor.
    /// </summary>
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
    /// <param name="agentEndpoint">
    /// The agent-specific endpoint URI. Must be of the shape
    /// <c>https://&lt;host&gt;/.../projects/&lt;project&gt;/agents/&lt;agentName&gt;/endpoint/protocols/openai</c>.
    /// </param>
    /// <param name="credential">The authentication credential.</param>
    /// <param name="clientOptions">
    /// Optional configuration for the underlying <see cref="ProjectResponsesClient"/>. When supplied:
    /// <list type="bullet">
    ///   <item><description>The instance is passed through to the per-agent client; pipeline policies added via <c>AddPolicy(...)</c> on it execute on the per-agent traffic.</description></item>
    /// </list>
    /// </param>
    /// <param name="tools">Optional tools to use when interacting with the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/>.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    /// <exception cref="ArgumentNullException"><paramref name="agentEndpoint"/> or <paramref name="credential"/> is null.</exception>
    /// <exception cref="ArgumentException"><paramref name="agentEndpoint"/> does not match the expected agent-endpoint shape.</exception>
    /// <remarks>
    /// This is the lightweight constructor for invoking an existing Foundry hosted agent when the
    /// caller already has the per-agent endpoint URL. It populates <see cref="ChatClientAgentOptions.Id"/>
    /// and <see cref="ChatClientAgentOptions.Name"/> from the agent name parsed out of the endpoint
    /// path; <c>Description</c>, <c>Instructions</c>, <c>Temperature</c>, and <c>TopP</c> are not
    /// populated. Callers that need those fields hydrated from server-side state should use
    /// <c>AIProjectClient.AsAIAgent(ProjectsAgentVersion)</c> or
    /// <c>AIProjectClient.AsAIAgent(ProjectsAgentRecord)</c> instead.
    /// </remarks>
    public FoundryAgent(
        Uri agentEndpoint,
        AuthenticationTokenProvider credential,
        ProjectOpenAIClientOptions? clientOptions = null,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
        : base(CreateInnerAgentFromAgentEndpoint(agentEndpoint, credential, clientOptions, tools, clientFactory, services, out var aiProjectClient))
    {
        this._aiProjectClient = aiProjectClient;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryAgent"/> class from an agent-specific
    /// endpoint while reusing an existing <see cref="AIProjectClient"/>.
    /// </summary>
    /// <param name="aiProjectClient">An existing <see cref="AIProjectClient"/> rooted at the same project as <paramref name="agentEndpoint"/>.</param>
    /// <param name="agentEndpoint">
    /// The agent-specific endpoint URI. Must be of the shape
    /// <c>https://&lt;host&gt;/.../projects/&lt;project&gt;/agents/&lt;agentName&gt;/endpoint/protocols/openai</c>.
    /// </param>
    /// <param name="tools">Optional tools to use when interacting with the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/>.</param>
    /// <param name="services">Optional service provider for resolving dependencies required by AI functions.</param>
    /// <exception cref="ArgumentNullException"><paramref name="aiProjectClient"/> or <paramref name="agentEndpoint"/> is null.</exception>
    /// <exception cref="ArgumentException"><paramref name="agentEndpoint"/> does not match the expected agent-endpoint shape.</exception>
    internal FoundryAgent(
        AIProjectClient aiProjectClient,
        Uri agentEndpoint,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
        : base(BuildAgentEndpointInnerAgent(aiProjectClient, agentEndpoint, clientOptions: null, tools, clientFactory, services))
    {
        this._aiProjectClient = Throw.IfNull(aiProjectClient);
    }

    /// <summary>
    /// Internal constructor used by <c>AsAIAgent</c> extension methods that already have an <see cref="AIProjectClient"/> and a configured <see cref="ChatClientAgent"/>.
    /// </summary>
    internal FoundryAgent(AIProjectClient aiProjectClient, ChatClientAgent innerAgent)
        : base(WireClientHeaders(Throw.IfNull(innerAgent)))
    {
        this._aiProjectClient = Throw.IfNull(aiProjectClient);
    }

    #region Convenience methods

    /// <summary>
    /// Creates a new agent session instance using an existing conversation identifier to continue that conversation.
    /// </summary>
    /// <param name="conversationId">The identifier of an existing conversation to continue.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A value task representing the asynchronous operation. The task result contains a new <see cref="AgentSession"/> instance configured to work with the specified conversation.
    /// </returns>
    /// <remarks>
    /// <para>
    /// This method creates an <see cref="AgentSession"/> that relies on server-side chat history storage, where the chat history
    /// is maintained by the underlying AI service rather than by a local <see cref="ChatHistoryProvider"/>.
    /// </para>
    /// <para>
    /// Agent sessions created with this method will only work with <see cref="FoundryAgent"/>
    /// instances that support server-side conversation storage through their underlying <see cref="IChatClient"/>.
    /// </para>
    /// </remarks>
    public ValueTask<AgentSession> CreateSessionAsync(string conversationId, CancellationToken cancellationToken = default)
        => this.GetInnerChatClientAgent().CreateSessionAsync(conversationId, cancellationToken);

    /// <summary>
    /// Creates a server-side conversation session that appears in the Foundry Project UI.
    /// </summary>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A <see cref="ChatClientAgentSession"/> linked to the newly created server-side conversation.</returns>
    public async Task<ChatClientAgentSession> CreateConversationSessionAsync(CancellationToken cancellationToken = default)
    {
        var conversationsClient = this._aiProjectClient.ProjectOpenAIClient.GetProjectConversationsClient();

        var conversation = (await conversationsClient.CreateProjectConversationAsync(options: null, cancellationToken).ConfigureAwait(false)).Value;

        return (ChatClientAgentSession)await this.GetInnerChatClientAgent().CreateSessionAsync(conversation.Id, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>Walks the delegating chain to find the inner <see cref="ChatClientAgent"/>.</summary>
    private ChatClientAgent GetInnerChatClientAgent() =>
        this.GetService<ChatClientAgent>()
        ?? throw new InvalidOperationException("FoundryAgent inner chain does not contain a ChatClientAgent.");

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

    private static AIAgent CreateInnerAgent(
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

        return CreateResponsesChatClientAgent(aiProjectClient, options, clientFactory, loggerFactory, services);
    }

    private static AIAgent CreateResponsesChatClientAgent(
        AIProjectClient aiProjectClient,
        ChatClientAgentOptions agentOptions,
        Func<IChatClient, IChatClient>? clientFactory,
        ILoggerFactory? loggerFactory,
        IServiceProvider? services)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(agentOptions);
        Throw.IfNull(agentOptions.ChatOptions);
        Throw.IfNullOrWhitespace(agentOptions.ChatOptions.ModelId);

        IChatClient chatClient = new AzureAIProjectResponsesChatClient(aiProjectClient, agentOptions.ChatOptions.ModelId);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return WireClientHeaders(new ChatClientAgent(chatClient, agentOptions, loggerFactory, services));
    }

    /// <summary>
    /// Registers <see cref="ClientHeadersPolicy"/> on the agent's underlying chat client (if it
    /// exposes <see cref="OpenAIRequestPolicies"/>) and wraps the agent in a
    /// <see cref="ClientHeadersAgent"/> so per-call <c>x-client-*</c> headers stamped via
    /// <see cref="ClientHeadersExtensions.WithClientHeader(ChatOptions, string, string)"/> reach
    /// the wire. Idempotent: if the chain already contains a <see cref="ClientHeadersAgent"/>,
    /// the original instance is returned unchanged.
    /// </summary>
    private static AIAgent WireClientHeaders(ChatClientAgent innerAgent)
    {
        if (innerAgent.GetService<ClientHeadersAgent>() is not null)
        {
            return innerAgent;
        }

        if (innerAgent.ChatClient.GetService<OpenAIRequestPolicies>() is { } policies)
        {
            OpenAIRequestPoliciesReflection.AddPolicyIfMissing(
                policies,
                ClientHeadersPolicy.Instance,
                PipelinePosition.PerCall);
        }

        return new ClientHeadersAgent(innerAgent);
    }

    /// <summary>
    /// Builds the inner <see cref="ChatClientAgent"/> for the agent-endpoint constructor by
    /// constructing a project-scoped <see cref="ProjectOpenAIClient"/> and using
    /// <see cref="ProjectOpenAIClient.GetProjectResponsesClientForAgentEndpoint(string, string?, ProjectOpenAIClientOptions?)"/>.
    /// This routes the outbound URL through the per-agent endpoint shape that the Foundry service
    /// expects for hosted agents and lets the SDK auto-append the <c>api-version</c> query string.
    /// Caller-supplied <paramref name="clientOptions"/> are passed through to the per-agent
    /// client with <c>Endpoint</c> and
    /// <see cref="ProjectOpenAIClientOptions.AgentName"/> overridden by values derived from
    /// <paramref name="agentEndpoint"/>; any policies the caller added via <c>AddPolicy</c>
    /// remain in effect on the per-agent pipeline. The MEAI user-agent policy is appended last.
    /// </summary>
    private static AIAgent CreateInnerAgentFromAgentEndpoint(
        Uri agentEndpoint,
        AuthenticationTokenProvider credential,
        ProjectOpenAIClientOptions? clientOptions,
        IList<AITool>? tools,
        Func<IChatClient, IChatClient>? clientFactory,
        IServiceProvider? services,
        out AIProjectClient outClient)
    {
        Throw.IfNull(agentEndpoint);
        Throw.IfNull(credential);

        var (_, projectRoot) = ParseAgentEndpoint(agentEndpoint);
        outClient = CreateProjectClient(projectRoot, credential, CreateProjectClientOptions(clientOptions));

        return BuildAgentEndpointInnerAgent(outClient, agentEndpoint, clientOptions, tools, clientFactory, services);
    }

    /// <summary>
    /// Builds the inner <see cref="ChatClientAgent"/> for an agent endpoint against a pre-built
    /// <see cref="AIProjectClient"/>. The caller is responsible for ensuring the supplied client
    /// is rooted at the same project as <paramref name="agentEndpoint"/>; the agent name is
    /// parsed from the endpoint URI and passed to
    /// <see cref="ProjectOpenAIClient.GetProjectResponsesClientForAgentEndpoint(string, string?, ProjectOpenAIClientOptions?)"/>.
    /// </summary>
    private static AIAgent BuildAgentEndpointInnerAgent(
        AIProjectClient aiProjectClient,
        Uri agentEndpoint,
        ProjectOpenAIClientOptions? clientOptions,
        IList<AITool>? tools,
        Func<IChatClient, IChatClient>? clientFactory,
        IServiceProvider? services)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(agentEndpoint);

        var (agentName, _) = ParseAgentEndpoint(agentEndpoint);

        var perAgentOptions = clientOptions ?? new ProjectOpenAIClientOptions();
        perAgentOptions.AddPolicy(RequestOptionsExtensions.UserAgentPolicy, PipelinePosition.PerCall);

        IChatClient chatClient = aiProjectClient.ProjectOpenAIClient
            .GetProjectResponsesClientForAgentEndpoint(agentName, options: perAgentOptions)
            .AsIChatClient();
        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        ChatClientAgentOptions agentOptions = new()
        {
            Id = agentName,
            Name = agentName,
            ChatOptions = new() { Tools = tools },
        };

        return WireClientHeaders(new ChatClientAgent(chatClient, agentOptions, services: services));
    }

    /// <summary>
    /// Parses an agent endpoint URI of shape
    /// <c>https://&lt;host&gt;/.../projects/&lt;project&gt;/agents/&lt;agentName&gt;/endpoint/protocols/openai</c>
    /// and returns the agent name and the derived project-root URI.
    /// </summary>
    /// <remarks>
    /// Single source of truth for both agent-name extraction and project-root derivation.
    /// Tolerates trailing slash, casing variants on <c>/agents/</c> and the suffix segment, and
    /// strips query string and fragment. Throws <see cref="ArgumentException"/> for inputs that
    /// do not match the expected shape.
    /// </remarks>
    /// <exception cref="ArgumentException">
    /// The endpoint is missing the <c>/agents/</c> segment, has an empty agent name, or has a
    /// suffix other than <c>/endpoint/protocols/openai</c>.
    /// </exception>
    internal static (string AgentName, Uri ProjectRoot) ParseAgentEndpoint(Uri agentEndpoint)
    {
        Throw.IfNull(agentEndpoint);

        const string AgentsSegment = "/agents/";
        const string ExpectedSuffix = "/endpoint/protocols/openai";

        var path = agentEndpoint.AbsolutePath.TrimEnd('/');
        var idx = path.IndexOf(AgentsSegment, StringComparison.OrdinalIgnoreCase);
        if (idx < 0)
        {
            throw new ArgumentException(
                $"Expected an agent endpoint of shape 'https://<host>/.../projects/<project>/agents/<agentName>/endpoint/protocols/openai' but got '{agentEndpoint}'.",
                nameof(agentEndpoint));
        }

        var afterAgents = path.Substring(idx + AgentsSegment.Length);
        var nextSlash = afterAgents.IndexOf('/');
        if (nextSlash <= 0)
        {
            throw new ArgumentException(
                $"Agent endpoint '{agentEndpoint}' is missing the '<agentName>{ExpectedSuffix}' suffix.",
                nameof(agentEndpoint));
        }

        var agentName = afterAgents.Substring(0, nextSlash);
        var suffix = afterAgents.Substring(nextSlash);
        if (!string.Equals(suffix, ExpectedSuffix, StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException(
                $"Agent endpoint '{agentEndpoint}' has an unexpected suffix '{suffix}'. Expected '{ExpectedSuffix}'.",
                nameof(agentEndpoint));
        }

        var rootPath = path.Substring(0, idx);
        var projectRoot = new UriBuilder(agentEndpoint)
        {
            Path = rootPath,
            Query = string.Empty,
            Fragment = string.Empty,
        }.Uri;

        return (agentName, projectRoot);
    }

    private static AIProjectClient CreateProjectClient(Uri endpoint, AuthenticationTokenProvider credential, AIProjectClientOptions? clientOptions = null)
    {
        Throw.IfNull(endpoint);
        Throw.IfNull(credential);

        clientOptions ??= new AIProjectClientOptions();
        clientOptions.AddPolicy(RequestOptionsExtensions.UserAgentPolicy, PipelinePosition.PerCall);
        return new AIProjectClient(endpoint, credential, clientOptions);
    }

    private static AIProjectClientOptions? CreateProjectClientOptions(ProjectOpenAIClientOptions? clientOptions)
    {
        if (clientOptions is null)
        {
            return null;
        }

        return new AIProjectClientOptions
        {
            Transport = clientOptions.Transport,
            UserAgentApplicationId = clientOptions.UserAgentApplicationId,
        };
    }

    #endregion
}
