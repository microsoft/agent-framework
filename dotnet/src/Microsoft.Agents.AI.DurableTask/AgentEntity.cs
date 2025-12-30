// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask.State;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Entities;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask;

internal class AgentEntity(IServiceProvider services, CancellationToken cancellationToken = default) : TaskEntity<DurableAgentState>
{
    private readonly IServiceProvider _services = services;
    private readonly DurableTaskClient _client = services.GetRequiredService<DurableTaskClient>();
    private readonly ILoggerFactory _loggerFactory = services.GetRequiredService<ILoggerFactory>();
    private readonly IAgentResponseHandler? _messageHandler = services.GetService<IAgentResponseHandler>();
    private readonly DurableAgentsOptions _options = services.GetRequiredService<DurableAgentsOptions>();
    private readonly CancellationToken _cancellationToken = cancellationToken != default
        ? cancellationToken
        : services.GetService<IHostApplicationLifetime>()?.ApplicationStopping ?? CancellationToken.None;

    public Task<AgentRunResponse> RunAgentAsync(RunRequest request)
    {
        return this.Run(request);
    }

    // IDE1006 and VSTHRD200 disabled to allow method name to match the common cross-platform entity operation name.
#pragma warning disable IDE1006
#pragma warning disable VSTHRD200
    public async Task<AgentRunResponse> Run(RunRequest request)
#pragma warning restore VSTHRD200
#pragma warning restore IDE1006
    {
        AgentSessionId sessionId = this.Context.Id;
        AIAgent agent = this.GetAgent(sessionId);
        EntityAgentWrapper agentWrapper = new(agent, this.Context, request, this._services);

        // Logger category is Microsoft.DurableTask.Agents.{agentName}.{sessionId}
        ILogger logger = this.GetLogger(agent.Name!, sessionId.Key);

        if (request.Messages.Count == 0)
        {
            logger.LogInformation("Ignoring empty request");
            return new AgentRunResponse();
        }

        this.State.Data.ConversationHistory.Add(DurableAgentStateRequest.FromRunRequest(request));

        foreach (ChatMessage msg in request.Messages)
        {
            logger.LogAgentRequest(sessionId, msg.Role, msg.Text);
        }

        // Set the current agent context for the duration of the agent run. This will be exposed
        // to any tools that are invoked by the agent.
        DurableAgentContext agentContext = new(
            entityContext: this.Context,
            client: this._client,
            lifetime: this._services.GetRequiredService<IHostApplicationLifetime>(),
            services: this._services);
        DurableAgentContext.SetCurrent(agentContext);

        try
        {
            // Start the agent response stream
            IAsyncEnumerable<AgentRunResponseUpdate> responseStream = agentWrapper.RunStreamingAsync(
                this.State.Data.ConversationHistory.SelectMany(e => e.Messages).Select(m => m.ToChatMessage()),
                agentWrapper.GetNewThread(),
                options: null,
                this._cancellationToken);

            AgentRunResponse response;
            if (this._messageHandler is null)
            {
                // If no message handler is provided, we can just get the full response at once.
                // This is expected to be the common case for non-interactive agents.
                response = await responseStream.ToAgentRunResponseAsync(this._cancellationToken);
            }
            else
            {
                List<AgentRunResponseUpdate> responseUpdates = [];

                // To support interactive chat agents, we need to stream the responses to an IAgentMessageHandler.
                // The user-provided message handler can be implemented to send the responses to the user.
                // We assume that only non-empty text updates are useful for the user.
                async IAsyncEnumerable<AgentRunResponseUpdate> StreamResultsAsync()
                {
                    await foreach (AgentRunResponseUpdate update in responseStream)
                    {
                        // We need the full response further down, so we piece it together as we go.
                        responseUpdates.Add(update);

                        // Yield the update to the message handler.
                        yield return update;
                    }
                }

                await this._messageHandler.OnStreamingResponseUpdateAsync(StreamResultsAsync(), this._cancellationToken);
                response = responseUpdates.ToAgentRunResponse();
            }

            // Persist the agent response to the entity state for client polling
            this.State.Data.ConversationHistory.Add(
                DurableAgentStateResponse.FromRunResponse(request.CorrelationId, response));

            string responseText = response.Text;

            if (!string.IsNullOrEmpty(responseText))
            {
                logger.LogAgentResponse(
                    sessionId,
                    response.Messages.FirstOrDefault()?.Role ?? ChatRole.Assistant,
                    responseText,
                    response.Usage?.InputTokenCount,
                    response.Usage?.OutputTokenCount,
                    response.Usage?.TotalTokenCount);
            }

            // Update TTL expiration time. Only schedule deletion check on first interaction.
            // Subsequent interactions just update the expiration time; CheckAndDeleteIfExpiredAsync
            // will reschedule the deletion check when it runs.
            TimeSpan? timeToLive = this._options.GetTimeToLive(sessionId.Name);
            if (timeToLive.HasValue)
            {
                DateTime newExpirationTime = DateTime.UtcNow.Add(timeToLive.Value);
                bool isFirstInteraction = this.State.Data.ExpirationTimeUtc is null;

                this.State.Data.ExpirationTimeUtc = newExpirationTime;
                logger.LogTTLExpirationTimeUpdated(sessionId, newExpirationTime);

                // Only schedule deletion check on the first interaction when entity is created.
                // On subsequent interactions, we just update the expiration time. The scheduled
                // CheckAndDeleteIfExpiredAsync will reschedule itself if the entity hasn't expired.
                if (isFirstInteraction)
                {
                    this.ScheduleDeletionCheck(sessionId, logger, timeToLive.Value);
                }
            }
            else
            {
                // TTL is disabled. Clear the expiration time if it was previously set.
                if (this.State.Data.ExpirationTimeUtc.HasValue)
                {
                    logger.LogTTLExpirationTimeCleared(sessionId);
                    this.State.Data.ExpirationTimeUtc = null;
                }
            }

            return response;
        }
        finally
        {
            // Clear the current agent context
            DurableAgentContext.ClearCurrent();
        }
    }

    /// <summary>
    /// Checks if the entity has expired and deletes it if so, otherwise reschedules the deletion check.
    /// </summary>
    /// <remarks>
    /// This method is called by the durable task runtime when a <c>CheckAndDeleteIfExpired</c> signal is received.
    /// </remarks>
    public void CheckAndDeleteIfExpired()
    {
        AgentSessionId sessionId = this.Context.Id;
        AIAgent agent = this.GetAgent(sessionId);
        ILogger logger = this.GetLogger(agent.Name!, sessionId.Key);

        DateTime currentTime = DateTime.UtcNow;
        DateTime? expirationTime = this.State.Data.ExpirationTimeUtc;

        logger.LogTTLDeletionCheck(sessionId, expirationTime, currentTime);

        if (expirationTime.HasValue)
        {
            if (currentTime >= expirationTime.Value)
            {
                // Entity has expired, delete it
                logger.LogTTLEntityExpired(sessionId, expirationTime.Value);
                this.State = null!;
            }
            else
            {
                // Entity hasn't expired yet, reschedule the deletion check
                TimeSpan? timeToLive = this._options.GetTimeToLive(sessionId.Name);
                if (timeToLive.HasValue)
                {
                    this.ScheduleDeletionCheck(sessionId, logger, timeToLive.Value);
                }
            }
        }
    }

    private void ScheduleDeletionCheck(AgentSessionId sessionId, ILogger logger, TimeSpan timeToLive)
    {
        DateTime currentTime = DateTime.UtcNow;
        DateTime expirationTime = this.State.Data.ExpirationTimeUtc ?? currentTime.Add(timeToLive);
        TimeSpan minimumDelay = this._options.MinimumTimeToLiveSignalDelay;

        // To avoid excessive scheduling, we schedule the deletion check for no less than the minimum delay.
        DateTime scheduledTime = expirationTime > currentTime.Add(minimumDelay)
            ? expirationTime
            : currentTime.Add(minimumDelay);

        logger.LogTTLDeletionScheduled(sessionId, scheduledTime);

        // Schedule a signal to self to check for expiration
        this.Context.SignalEntity(
            this.Context.Id,
            nameof(CheckAndDeleteIfExpired), // self-signal
            options: new SignalEntityOptions { SignalTime = scheduledTime });
    }

    private AIAgent GetAgent(AgentSessionId sessionId)
    {
        IReadOnlyDictionary<string, Func<IServiceProvider, AIAgent>> agents =
            this._services.GetRequiredService<IReadOnlyDictionary<string, Func<IServiceProvider, AIAgent>>>();
        if (!agents.TryGetValue(sessionId.Name, out Func<IServiceProvider, AIAgent>? agentFactory))
        {
            throw new InvalidOperationException($"Agent '{sessionId.Name}' not found");
        }

        return agentFactory(this._services);
    }

    private ILogger GetLogger(string agentName, string sessionKey)
    {
        return this._loggerFactory.CreateLogger($"Microsoft.DurableTask.Agents.{agentName}.{sessionKey}");
    }
}
