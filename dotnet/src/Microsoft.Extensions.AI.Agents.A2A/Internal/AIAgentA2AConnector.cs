// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.A2A.Internal;

internal sealed class AIAgentA2AConnector : IA2AConnector
{
    private readonly ILogger _logger;
    private readonly AIAgent _agent;

    public AIAgentA2AConnector(ILogger<AIAgentA2AConnector> logger, AIAgent agent)
    {
        this._logger = logger;
        this._agent = agent;
    }

    public Task<AgentCard> GetAgentCardAsync(string agentPath, CancellationToken cancellationToken)
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
            Name = this._agent.Name ?? string.Empty,
            Description = this._agent.Description ?? string.Empty,
            Url = agentPath,
            Version = this._agent.Id,
            DefaultInputModes = ["text"],
            DefaultOutputModes = ["text"],
            Capabilities = capabilities,
            Skills = [],
        });
    }

    public async Task<Message> ProcessMessageAsync(MessageSendParams messageSendParams, CancellationToken cancellationToken)
    {
        throw new NotImplementedException();

        //this._logger.LogInformation("Processing message in DefaultA2AAgent for agent: {AgentKey}", this._agent.Name);

        //try
        //{
        //    // Convert A2A message to AI message
        //    var userMessage = messageSendParams.Message.Parts.OfType<TextPart>().FirstOrDefault()?.Text ?? string.Empty;
        //    var chatMessages = new List<ChatMessage>
        //    {
        //        new(ChatRole.User, userMessage)
        //    };

        //    // Run the agent
        //    var result = await this._agent.RunAsync(chatMessages, cancellationToken).ConfigureAwait(false);

        //    // Convert response back to A2A format
        //    var responseMessage = new Message
        //    {
        //        Role = MessageRole.Agent,
        //        MessageId = Guid.NewGuid().ToString(),
        //        Parts = new List<Part>
        //        {
        //            new TextPart { Text = result.Text }
        //        }
        //    };

        //    this._logger.LogInformation("Agent {AgentKey} returning response: {Response}", this._agent.Name, result.Text);
        //    return responseMessage;
        //}
        //catch (Exception ex)
        //{
        //    this._logger.LogError(ex, "Error processing message in DefaultA2AAgent for agent: {AgentKey}", this._agent.Name);

        //    // A2A SDK handles the exception under the hood, so we can just throw the exception
        //    throw;
        //}
    }
}
