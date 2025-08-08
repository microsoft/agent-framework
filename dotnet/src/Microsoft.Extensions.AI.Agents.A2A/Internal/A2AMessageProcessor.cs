// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI.Agents.A2A.Converters;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.A2A.Internal;

internal sealed class A2AMessageProcessor : A2AAgentCardProvider, IA2AMessageProcessor
{
    public A2AMessageProcessor(ILogger<A2AMessageProcessor> logger, AIAgent agent)
        : base(logger, agent)
    {
    }

    public async Task<Message> ProcessMessageAsync(MessageSendParams messageSendParams, CancellationToken cancellationToken)
    {
        // this is the simplest scenario for A2A agent processing - a single message conversation.

        this._logger.LogInformation("Processing message in DefaultA2AAgent for agent: {AgentKey}", this._agent.Name);

        try
        {
            var chatMessages = messageSendParams.ToChatMessages();
            var result = await this._agent.RunAsync(messages: chatMessages, cancellationToken: cancellationToken).ConfigureAwait(false);

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
            this._logger.LogError(ex, "Error processing message in DefaultA2AAgent for agent: {AgentKey}", this._agent.Name);

            // A2A SDK handles the exception under the hood, so we can just throw the exception
            throw;
        }
    }
}
