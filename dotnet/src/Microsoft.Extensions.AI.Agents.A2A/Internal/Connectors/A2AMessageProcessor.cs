// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI.Agents.A2A.Converters;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.A2A.Internal.Connectors;

internal sealed class A2AMessageProcessor : A2AProviderBase, IA2AMessageProcessor
{
    public A2AMessageProcessor(AIAgent agent, TaskManager taskManager, ILoggerFactory? loggerFactory)
        : base(agent, taskManager, loggerFactory)
    {
    }

    public async Task<Message> ProcessMessageAsync(MessageSendParams messageSendParams, CancellationToken cancellationToken)
    {
        // this is the simplest scenario for A2A agent processing - a single message conversation.

        this._logger.LogInformation("Processing message in DefaultA2AAgent for agent: {AgentKey}", this._a2aAgent.InnerAgent.Name);

        try
        {
            var chatMessages = messageSendParams.ToChatMessages();
            var options = A2AAgentRunOptions.CreateA2AMessagingOptions();
            var result = await this._a2aAgent.RunAsync(messages: chatMessages, options: options, cancellationToken: cancellationToken).ConfigureAwait(false);

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

            this._logger.LogInformation("Agent {AgentKey} returning response: {Response}", this._a2aAgent.InnerAgent.Name, result.Text);
            return responseMessage;
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Error processing message in DefaultA2AAgent for agent: {AgentKey}", this._a2aAgent.InnerAgent.Name);

            // A2A SDK handles the exception under the hood, so we can just throw the exception
            throw;
        }
    }
}
