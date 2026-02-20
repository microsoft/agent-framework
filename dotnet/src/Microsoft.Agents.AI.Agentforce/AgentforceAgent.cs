// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Agentforce;

/// <summary>
/// Represents a Salesforce Agentforce agent that can participate in conversations
/// through the Agentforce REST API.
/// </summary>
/// <remarks>
/// This agent integrates with the Salesforce Agentforce (Einstein AI Agent) API to
/// create sessions, send messages, and receive agent responses. It follows the
/// Agent Framework abstraction model, allowing it to be orchestrated alongside
/// other agent types in multi-agent workflows.
/// </remarks>
public class AgentforceAgent : AIAgent, IDisposable
{
    private readonly ILogger _logger;
    private readonly bool _ownsClient;
    private bool _disposed;

    /// <summary>
    /// The client used to interact with the Salesforce Agentforce API.
    /// </summary>
    public AgentforceClient Client { get; }

    private static readonly AIAgentMetadata s_agentMetadata = new("salesforce-agentforce");

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentforceAgent"/> class with a pre-configured client.
    /// </summary>
    /// <param name="client">A client used to interact with the Salesforce Agentforce API.</param>
    /// <param name="loggerFactory">Optional logger factory to use for logging.</param>
    public AgentforceAgent(AgentforceClient client, ILoggerFactory? loggerFactory = null)
    {
        this.Client = Throw.IfNull(client);
        this._ownsClient = false;
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<AgentforceAgent>();
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentforceAgent"/> class with configuration.
    /// </summary>
    /// <param name="config">The Agentforce configuration containing credentials and agent identity.</param>
    /// <param name="loggerFactory">Optional logger factory to use for logging.</param>
    public AgentforceAgent(AgentforceConfig config, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(config);
        this.Client = new AgentforceClient(config);
        this._ownsClient = true;
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<AgentforceAgent>();
    }

    /// <inheritdoc/>
    protected sealed override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        => new(new AgentforceAgentSession());

    /// <inheritdoc/>
    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(session);

        if (session is not AgentforceAgentSession typedSession)
        {
            throw new InvalidOperationException($"The provided session type '{session.GetType().Name}' is not compatible with this agent. Only sessions of type '{nameof(AgentforceAgentSession)}' can be serialized by this agent.");
        }

        return new(typedSession.Serialize(jsonSerializerOptions));
    }

    /// <inheritdoc/>
    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => new(AgentforceAgentSession.Deserialize(serializedState, jsonSerializerOptions));

    /// <inheritdoc/>
    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages);

        // Ensure that we have a valid session to work with.
        session ??= await this.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
        if (session is not AgentforceAgentSession typedSession)
        {
            throw new InvalidOperationException($"The provided session type '{session.GetType().Name}' is not compatible with this agent. Only sessions of type '{nameof(AgentforceAgentSession)}' can be used by this agent.");
        }

        // If no Salesforce session exists, create one.
        if (typedSession.ServiceSessionId is null)
        {
            var createResponse = await this.Client.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
            typedSession.ServiceSessionId = createResponse.SessionId
                ?? throw new InvalidOperationException("Failed to create an Agentforce session.");

            if (this._logger.IsEnabled(LogLevel.Debug))
            {
                this._logger.LogDebug("Created Agentforce session: {SessionId}", typedSession.ServiceSessionId);
            }
        }

        // Send the user's message(s) to the Agentforce agent.
        string question = string.Join("\n", messages.Select(m => m.Text));
        var sendResponse = await this.Client.SendMessageAsync(typedSession.ServiceSessionId, question, cancellationToken).ConfigureAwait(false);

        // Convert Agentforce messages to ChatMessages.
        var responseMessages = ConvertToResponseMessages(sendResponse);

        return new AgentResponse(responseMessages)
        {
            AgentId = this.Id,
            ResponseId = Guid.NewGuid().ToString("N"),
        };
    }

    /// <inheritdoc/>
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages);

        // Ensure that we have a valid session to work with.
        session ??= await this.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
        if (session is not AgentforceAgentSession typedSession)
        {
            throw new InvalidOperationException($"The provided session type '{session.GetType().Name}' is not compatible with this agent. Only sessions of type '{nameof(AgentforceAgentSession)}' can be used by this agent.");
        }

        // If no Salesforce session exists, create one.
        if (typedSession.ServiceSessionId is null)
        {
            var createResponse = await this.Client.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
            typedSession.ServiceSessionId = createResponse.SessionId
                ?? throw new InvalidOperationException("Failed to create an Agentforce session.");
        }

        // Send the user's message(s) to the Agentforce agent.
        string question = string.Join("\n", messages.Select(m => m.Text));
        var sendResponse = await this.Client.SendMessageAsync(typedSession.ServiceSessionId, question, cancellationToken).ConfigureAwait(false);

        // Convert Agentforce messages to streaming response updates.
        var responseMessages = ConvertToResponseMessages(sendResponse);
        string responseId = Guid.NewGuid().ToString("N");

        foreach (ChatMessage message in responseMessages)
        {
            yield return new AgentResponseUpdate(message.Role, message.Contents)
            {
                AgentId = this.Id,
                AdditionalProperties = message.AdditionalProperties,
                AuthorName = message.AuthorName,
                RawRepresentation = message.RawRepresentation,
                ResponseId = responseId,
                MessageId = message.MessageId,
            };
        }
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
        => base.GetService(serviceType, serviceKey)
           ?? (serviceType == typeof(AgentforceClient) ? this.Client
            : serviceType == typeof(AIAgentMetadata) ? s_agentMetadata
            : null);

    /// <summary>
    /// Converts Agentforce API response messages to <see cref="ChatMessage"/> objects.
    /// </summary>
    private static List<ChatMessage> ConvertToResponseMessages(SendMessageResponse response)
    {
        var chatMessages = new List<ChatMessage>();

        if (response.Messages is null)
        {
            return chatMessages;
        }

        foreach (var agentMessage in response.Messages)
        {
            // Only include displayable message types.
            if (agentMessage.Type is not ("Inform" or "Text"))
            {
                continue;
            }

            string? text = agentMessage.DisplayText;
            if (string.IsNullOrWhiteSpace(text))
            {
                continue;
            }

            chatMessages.Add(new ChatMessage(ChatRole.Assistant, text)
            {
                MessageId = Guid.NewGuid().ToString("N"),
                RawRepresentation = agentMessage,
            });
        }

        return chatMessages;
    }

    /// <inheritdoc />
    public void Dispose()
    {
        this.Dispose(true);
        GC.SuppressFinalize(this);
    }

    /// <summary>
    /// Releases unmanaged and (optionally) managed resources.
    /// </summary>
    /// <param name="disposing"><see langword="true"/> to release both managed and unmanaged resources; <see langword="false"/> to release only unmanaged resources.</param>
    protected virtual void Dispose(bool disposing)
    {
        if (!this._disposed)
        {
            if (disposing && this._ownsClient)
            {
                this.Client.Dispose();
            }

            this._disposed = true;
        }
    }
}
