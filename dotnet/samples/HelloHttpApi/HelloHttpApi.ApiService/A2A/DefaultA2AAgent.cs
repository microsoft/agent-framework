// Copyright (c) Microsoft. All rights reserved.
using A2A;

namespace HelloHttpApi.ApiService.A2A;

public class DefaultA2AAgent(ILogger<DefaultA2AAgent> logger)
{
    public void Attach(ITaskManager taskManager)
    {
        taskManager.OnMessageReceived = this.ProcessMessageAsync;
        taskManager.OnAgentCardQuery = this.GetAgentCardAsync;
    }

    private Task<Message> ProcessMessageAsync(MessageSendParams sendParams, CancellationToken token)
    {
        logger.LogInformation("Called proces message async on Default A2AAgent");
        return Task.FromResult(new Message());
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
            Name = "Echo Agent",
            Description = "Agent which will echo every message it receives.",
            Url = agentUrl,
            Version = "1.0.0",
            DefaultInputModes = ["text"],
            DefaultOutputModes = ["text"],
            Capabilities = capabilities,
            Skills = [],
        });
    }
}
