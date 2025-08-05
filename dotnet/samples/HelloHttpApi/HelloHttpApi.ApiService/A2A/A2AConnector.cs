// Copyright (c) Microsoft. All rights reserved.

using A2A;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace HelloHttpApi.ApiService.A2A;

internal interface IA2AConnector
{
    /// <summary>
    /// Attaches the A2A connector to the specified task manager.
    /// </summary>
    /// <param name="taskManager">The task manager to attach to.</param>
    void Attach(ITaskManager taskManager);
}

internal sealed class A2AConnector : IA2AConnector
{
    private readonly ILogger<A2AConnector> _logger;
    private readonly AIAgent _agent;

    public A2AConnector(ILogger<A2AConnector> _logger, AIAgent agent)
    {
        this._logger = _logger;
        this._agent = agent;
    }

    public void Attach(ITaskManager taskManager)
    {
        taskManager.OnMessageReceived = this.ProcessMessageAsync;
        taskManager.OnAgentCardQuery = this.GetAgentCardAsync;
    }

    private async Task<Message> ProcessMessageAsync(MessageSendParams sendParams, CancellationToken token)
    {
        this._logger.LogInformation("Processing message in DefaultA2AAgent for agent: {AgentKey}", this._agent.Name);

        try
        {
            // Convert A2A message to AI message
            var userMessage = sendParams.Message.Parts.OfType<TextPart>().FirstOrDefault()?.Text ?? string.Empty;
            var chatMessages = new List<ChatMessage>
            {
                new(ChatRole.User, userMessage)
            };

            // Run the agent
            var result = await this._agent.RunAsync(chatMessages, cancellationToken: token);

            // Convert response back to A2A format
            var responseMessage = new Message
            {
                Role = MessageRole.Agent,
                MessageId = Guid.NewGuid().ToString(),
                Parts = new List<Part>
                {
                    new TextPart { Text = result.Text }
                }
            };

            this._logger.LogInformation("Agent {AgentKey} returning response: {Response}", this._agent.Name, result.Text);
            return responseMessage;
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Error processing message for agent {AgentKey}", this._agent.Name);

            return new Message
            {
                Role = MessageRole.Agent,
                MessageId = Guid.NewGuid().ToString(),
                Parts = new List<Part>
                {
                    new TextPart { Text = "Something went wrong with the response" }
                }
            };
        }
    }

    private Task<AgentCard> GetAgentCardAsync(string agentUrl, CancellationToken cancellationToken)
    {
        if (cancellationToken.IsCancellationRequested)
        {
            return Task.FromCanceled<AgentCard>(cancellationToken);
        }

        var capabilities = new AgentCapabilities()
        {
            Streaming = true,
            PushNotifications = false,
        };

        return Task.FromResult(new AgentCard()
        {
            Name = this._agent.Name ?? "Unnamed Agent",
            Description = this._agent.Description ?? string.Empty,
            Url = agentUrl,
            Version = "1.0.0",
            DefaultInputModes = ["text"],
            DefaultOutputModes = ["text"],
            Capabilities = capabilities,
            Skills = [],
        });
    }
}
