// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
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
public sealed class FoundryAgent : DelegatingAIAgent
{
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
            out _))
    {
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
    /// Optional configuration for the underlying <see cref="ProjectOpenAIClient"/>. When supplied:
    /// <list type="bullet">
    ///   <item><description>The instance is passed through to the per-agent client; pipeline policies added via <c>AddPolicy(...)</c> on it execute on the per-agent traffic.</description></item>
    ///   <item><description><c>Endpoint</c> and <see cref="ProjectOpenAIClientOptions.AgentName"/> are owned by this constructor and are overwritten with values derived from <paramref name="agentEndpoint"/>; any caller value is replaced.</description></item>
    ///   <item><description>For the project-level conversations client a separate fresh options bag is built that copies only <see cref="ClientPipelineOptions.RetryPolicy"/>, <see cref="ClientPipelineOptions.NetworkTimeout"/>, <see cref="ClientPipelineOptions.Transport"/>, and <c>UserAgentApplicationId</c>; pipeline policies added via <c>AddPolicy(...)</c> do <strong>not</strong> propagate to the conversations pipeline.</description></item>
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
        : base(CreateInnerAgentFromAgentEndpoint(agentEndpoint, credential, clientOptions, tools, clientFactory, services))
    {
    }

    /// <summary>
    /// Internal constructor used by the <c>AsAIAgent(this AIProjectClient, Uri, ...)</c>
    /// extension where the caller already has an <see cref="AIProjectClient"/> and the agent
    /// endpoint URI. Reuses the supplied client's pipeline (no new credential or transport is
    /// stamped) and surfaces the agent through a <see cref="FoundryChatClient"/> just like the
    /// public agent-endpoint ctor.
    /// </summary>
    internal FoundryAgent(
        AIProjectClient aiProjectClient,
        Uri agentEndpoint,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
        : base(CreateInnerAgentFromAgentEndpointReusingProjectClient(aiProjectClient, agentEndpoint, tools, clientFactory, services))
    {
    }

    /// <summary>
    /// Internal constructor used by <c>AsAIAgent</c> extension methods that already have a
    /// configured <see cref="ChatClientAgent"/>. The inner agent already routes through a
    /// <see cref="FoundryChatClient"/> whose <c>GetService&lt;AIProjectClient&gt;()</c> surfaces
    /// the project client to downstream callers, so the agent does not also need a private
    /// <see cref="AIProjectClient"/> reference here.
    /// </summary>
    internal FoundryAgent(ChatClientAgent innerAgent)
        : base(WireClientHeaders(Throw.IfNull(innerAgent)))
    {
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
        // The inner FoundryChatClient surfaces an AIProjectClient via GetService for all
        // three construction modes (Plan #2 Agent Endpoint mode materialization). Resolve it through the
        // delegating chain at call time instead of caching a private reference on this agent.
        var aiProjectClient = this.GetService<AIProjectClient>()
            ?? throw new InvalidOperationException(
                "FoundryAgent inner chain does not expose an AIProjectClient; cannot create a project-level conversation session.");
        var conversationsClient = aiProjectClient.GetProjectOpenAIClient().GetProjectConversationsClient();

        var conversation = (await conversationsClient.CreateProjectConversationAsync(options: null, cancellationToken).ConfigureAwait(false)).Value;

        return (ChatClientAgentSession)await this.GetInnerChatClientAgent().CreateSessionAsync(conversation.Id, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>Walks the delegating chain to find the inner <see cref="ChatClientAgent"/>.</summary>
    private ChatClientAgent GetInnerChatClientAgent() =>
        this.GetService<ChatClientAgent>()
        ?? throw new InvalidOperationException("FoundryAgent inner chain does not contain a ChatClientAgent.");

    #endregion

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

        IChatClient chatClient = new FoundryChatClient(aiProjectClient, agentOptions.ChatOptions.ModelId);

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

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
        if (innerAgent.ChatClient.GetService<OpenAIRequestPolicies>() is { } policies)
        {
            OpenAIRequestPoliciesReflection.AddPolicyIfMissing(
                policies,
                ClientHeadersPolicy.Instance,
                PipelinePosition.PerCall);
        }
#pragma warning restore MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

        return new ClientHeadersAgent(innerAgent);
    }

    /// <summary>
    /// Builds the inner <see cref="ChatClientAgent"/> for the agent-endpoint constructor. The
    /// per-agent <see cref="ProjectOpenAIClient"/> shape and URL parsing are owned by
    /// <see cref="FoundryChatClient"/>; we just construct it in the Agent Endpoint mode (Mode 3)
    /// and pass the inner chat client through any caller-provided <paramref name="clientFactory"/>.
    /// </summary>
    private static AIAgent CreateInnerAgentFromAgentEndpoint(
        Uri agentEndpoint,
        AuthenticationTokenProvider credential,
        ProjectOpenAIClientOptions? clientOptions,
        IList<AITool>? tools,
        Func<IChatClient, IChatClient>? clientFactory,
        IServiceProvider? services)
    {
        Throw.IfNull(agentEndpoint);
        Throw.IfNull(credential);

        IChatClient chatClient = new FoundryChatClient(agentEndpoint, credential, clientOptions);
        var agentName = ((FoundryChatClient)chatClient).AgentName!;

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
    /// Variant of <see cref="CreateInnerAgentFromAgentEndpoint"/> that reuses an existing
    /// <see cref="AIProjectClient"/>'s pipeline instead of stamping a fresh credential. Used by
    /// the <c>AsAIAgent(AIProjectClient, Uri agentEndpoint, ...)</c> extension overload.
    /// </summary>
    private static AIAgent CreateInnerAgentFromAgentEndpointReusingProjectClient(
        AIProjectClient aiProjectClient,
        Uri agentEndpoint,
        IList<AITool>? tools,
        Func<IChatClient, IChatClient>? clientFactory,
        IServiceProvider? services)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(agentEndpoint);

        IChatClient chatClient = new FoundryChatClient(aiProjectClient, agentEndpoint, clientOptions: null);
        var agentName = ((FoundryChatClient)chatClient).AgentName!;

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
    /// Parses an agent endpoint URI. Delegates to <see cref="FoundryChatClient.ParseAgentEndpoint(Uri)"/>
    /// so the chat client and the agent share a single source of truth for the URL shape.
    /// </summary>
    internal static (string AgentName, Uri ProjectRoot) ParseAgentEndpoint(Uri agentEndpoint)
        => FoundryChatClient.ParseAgentEndpoint(agentEndpoint);

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
    private static AIProjectClient CreateProjectClient(Uri endpoint, AuthenticationTokenProvider credential, AIProjectClientOptions? clientOptions = null)
    {
        Throw.IfNull(endpoint);
        Throw.IfNull(credential);

        return new AIProjectClient(endpoint, credential, clientOptions ?? new AIProjectClientOptions());
    }

    #endregion
}
