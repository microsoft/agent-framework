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
    private readonly CancellationToken _cancellationToken = cancellationToken != default
        ? cancellationToken
        : services.GetService<IHostApplicationLifetime>()?.ApplicationStopping ?? CancellationToken.None;

    public async Task<AgentRunResponse> RunAgentAsync(RunRequest request)
    {
        AgentSessionId sessionId = this.Context.Id;
        IReadOnlyDictionary<string, Func<IServiceProvider, AIAgent>> agents =
            this._services.GetRequiredService<IReadOnlyDictionary<string, Func<IServiceProvider, AIAgent>>>();
        if (!agents.TryGetValue(sessionId.Name, out Func<IServiceProvider, AIAgent>? agentFactory))
        {
            throw new InvalidOperationException($"Agent '{sessionId.Name}' not found");
        }

        AIAgent agent = agentFactory(this._services);
        EntityAgentWrapper agentWrapper = new(agent, this.Context, request, this._services);

        // Logger category is Microsoft.DurableTask.Agents.{agentName}.{sessionId}
        ILogger logger = this._loggerFactory.CreateLogger($"Microsoft.DurableTask.Agents.{agent.Name}.{sessionId.Key}");

        if (request.Messages.Count == 0)
        {
            logger.LogInformation("Ignoring empty request");
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

            return response;
        }
        finally
        {
            // Clear the current agent context
            DurableAgentContext.ClearCurrent();
        }
    }
}
