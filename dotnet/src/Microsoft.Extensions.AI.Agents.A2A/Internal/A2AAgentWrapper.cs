// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI.Agents.A2A.Converters;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Extensions.AI.Agents.A2A.Internal;

/// <summary>
/// A2A agent that wraps an existing AIAgent and provides A2A-specific thread wrapping.
/// </summary>
internal sealed class A2AAgentWrapper
{
    private readonly ILogger _logger;
    private readonly TaskManager _taskManager;
    private readonly AIAgent _innerAgent;

    public A2AAgentWrapper(AIAgent innerAgent, TaskManager taskManager, ILoggerFactory? loggerFactory = null)
    {
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<A2AAgentWrapper>();

        this._taskManager = taskManager ?? throw new ArgumentNullException(nameof(taskManager));
        this._innerAgent = innerAgent ?? throw new ArgumentNullException(nameof(innerAgent));
    }

    public async Task<Message> ProcessMessageAsync(MessageSendParams messageSendParams, CancellationToken cancellationToken)
    {
        // this is the simplest scenario for A2A agent processing - a single message conversation.
        this._logger.LogInformation("Processing message {ContextId}::{MessageId} for {AgentName} agent", messageSendParams.Message.ContextId, messageSendParams.Message.MessageId, this._innerAgent.Name);

        try
        {
            var chatMessages = messageSendParams.ToChatMessages();
            var result = await this._innerAgent.RunAsync(messages: chatMessages, cancellationToken: cancellationToken).ConfigureAwait(false);

            var responseMessage = new Message
            {
                Role = MessageRole.Agent,
                ContextId = messageSendParams.Message.ContextId,
                MessageId = Guid.NewGuid().ToString(),
                Parts = [new TextPart { Text = result.Text }]
            };

            this._logger.LogInformation("Agent {AgentKey} returning response: {Response}", this._innerAgent.Name, result.Text);
            return responseMessage;
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Error processing message {ContextId}::{MessageId} for {AgentName} agent", messageSendParams.Message.ContextId, messageSendParams.Message.MessageId, this._innerAgent.Name);
            throw; // A2A SDK handles the exception under the hood, so we can just throw the exception
        }
    }

    public Task<AgentCard> GetAgentCardAsync(string agentPath, CancellationToken cancellationToken = default)
    {
        if (cancellationToken.IsCancellationRequested)
        {
            return Task.FromCanceled<AgentCard>(cancellationToken);
        }

        return Task.FromResult(new AgentCard()
        {
            Name = this._innerAgent.Name ?? string.Empty,
            Description = this._innerAgent.Description ?? string.Empty,
            Url = agentPath,
            Version = this._innerAgent.Id,
            DefaultInputModes = ["text"],
            DefaultOutputModes = ["text"],
            Capabilities = new()
            {
                Streaming = true,
                PushNotifications = false,
            },
            Skills = [],
        });
    }
}
