// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.A2A;

/// <summary>
/// Host which will attach an <see cref="AIAgent"/> to a <see cref="ITaskManager"/>
/// </summary>
/// <remarks>
/// This implementation only handles:
/// <list type="bullet">
/// <item><description>TaskManager.OnMessageReceived</description></item>
/// <item><description>TaskManager.OnAgentCardQuery</description></item>
/// </list>
/// Support for task management will be added later as part of the long-running task execution work.
/// </remarks>
public sealed class A2AHostAgent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="A2AHostAgent"/> class.
    /// </summary>
    /// <param name="agent">The <see cref="AIAgent"/> to host.</param>
    /// <param name="agentCard">The <see cref="AgentCard"/> for the hosted agent.</param>
    /// <param name="taskManager">The <see cref="ITaskManager"/> for handling agent tasks.</param>
    public A2AHostAgent(AIAgent agent, AgentCard agentCard, TaskManager? taskManager = null)
    {
        Throw.IfNull(agent);
        Throw.IfNull(agentCard);

        this.Agent = agent;
        this._agentCard = agentCard;

        this.Attach(taskManager ?? new TaskManager());
    }

    /// <summary>
    /// Gets the associated <see cref="AIAgent"/>.
    /// </summary>
    public AIAgent? Agent { get; }

    /// <summary>
    /// Gets the associated <see cref="ITaskManager"/> for handling agent tasks.
    /// </summary>
    public TaskManager? TaskManager { get; private set; }

    /// <summary>
    /// Attaches the <see cref="A2AAgent"/> to the provided <see cref="ITaskManager"/>.
    /// </summary>
    /// <param name="taskManager">The <see cref="ITaskManager"/> to attach to.</param>
    public void Attach(TaskManager taskManager)
    {
        Throw.IfNull(taskManager);

        this.TaskManager = taskManager;
        taskManager.OnMessageReceived = this.OnMessageReceivedAsync;
        taskManager.OnAgentCardQuery = this.GetAgentCardAsync;
    }

    /// <summary>
    /// Handles a received message.
    /// </summary>
    /// <param name="messageSend">The <see cref="MessageSendParams"/> to handle.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    public async Task<A2AResponse> OnMessageReceivedAsync(MessageSendParams messageSend, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messageSend);
        Throw.IfNull(this.Agent);

        if (this.TaskManager is null)
        {
            throw new InvalidOperationException("TaskManager must be attached before handling an agent message.");
        }

        // Get message from the user
        var userMessage = messageSend.Message.ToChatMessage();

        // Get the response from the agent
        var message = new AgentMessage();
        var agentResponse = await this.Agent.RunAsync(userMessage, cancellationToken: cancellationToken).ConfigureAwait(false);
        foreach (var chatMessage in agentResponse.Messages)
        {
            var content = chatMessage.Text;
            message.Parts.Add(new TextPart() { Text = content! });
        }

        return message;
    }

    /// <summary>
    /// Gets the <see cref="AgentCard"/> associated with this hosted agent.
    /// </summary>
    /// <param name="agentUrl">Current URL for the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    public Task<AgentCard> GetAgentCardAsync(string agentUrl, CancellationToken cancellationToken = default)
    {
        // Ensure the URL is in the correct format
        Uri uri = new(agentUrl);
        agentUrl = $"{uri.Scheme}://{uri.Host}:{uri.Port}/";

        this._agentCard.Url = agentUrl;
        return Task.FromResult(this._agentCard);
    }

    #region private
    private readonly AgentCard _agentCard;
    #endregion
}
