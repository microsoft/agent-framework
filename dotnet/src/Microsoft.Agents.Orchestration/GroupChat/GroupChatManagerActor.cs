// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// An <see cref="OrchestrationActor"/> used to manage a <see cref="GroupChatOrchestration{TInput, TOutput}"/>.
/// </summary>
internal sealed class GroupChatManagerActor : OrchestrationActor
{
    /// <summary>
    /// A common description for the manager.
    /// </summary>
    public const string DefaultDescription = "Orchestrates a team of agents to accomplish a defined task.";

    private readonly ActorType _orchestrationType;
    private readonly GroupChatManager _manager;
    private readonly List<ChatMessage> _chat;
    private readonly GroupChatTeam _team;

    /// <summary>
    /// Initializes a new instance of the <see cref="GroupChatManagerActor"/> class.
    /// </summary>
    /// <param name="id">The unique identifier of the agent.</param>
    /// <param name="runtime">The runtime associated with the agent.</param>
    /// <param name="context">The orchestration context.</param>
    /// <param name="manager">The manages the flow of the group-chat.</param>
    /// <param name="team">The team of agents being orchestrated</param>
    /// <param name="orchestrationType">Identifies the orchestration agent.</param>
    /// <param name="logger">The logger to use for the actor</param>
    public GroupChatManagerActor(ActorId id, IAgentRuntime runtime, OrchestrationContext context, GroupChatManager manager, GroupChatTeam team, ActorType orchestrationType, ILogger? logger = null)
        : base(id, runtime, context, DefaultDescription, logger)
    {
        this._chat = [];
        this._manager = manager;
        this._orchestrationType = orchestrationType;
        this._team = team;

        this.RegisterMessageHandler<GroupChatMessages.InputTask>(this.HandleAsync);
        this.RegisterMessageHandler<GroupChatMessages.Group>(this.HandleAsync);
    }

    private async ValueTask HandleAsync(GroupChatMessages.InputTask item, MessageContext messageContext, CancellationToken cancellationToken)
    {
        this.Logger.LogChatManagerInit(this.Id);

        this._chat.AddRange(item.Messages);

        await this.PublishMessageAsync(new GroupChatMessages.Group(item.Messages), this.Context.Topic, cancellationToken: cancellationToken).ConfigureAwait(false);

        await this.ManageAsync(messageContext, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    private async ValueTask HandleAsync(GroupChatMessages.Group item, MessageContext messageContext, CancellationToken cancellationToken)
    {
        this.Logger.LogChatManagerInvoke(this.Id);

        this._chat.AddRange(item.Messages);

        await this.ManageAsync(messageContext, cancellationToken).ConfigureAwait(false);
    }

    private async ValueTask ManageAsync(MessageContext messageContext, CancellationToken cancellationToken)
    {
        if (this._manager.InteractiveCallback != null)
        {
            GroupChatManagerResult<bool> inputResult = await this._manager.ShouldRequestUserInput(this._chat, cancellationToken).ConfigureAwait(false);
            this.Logger.LogChatManagerInput(this.Id, inputResult.Value, inputResult.Reason);
            if (inputResult.Value)
            {
                ChatMessage input = await this._manager.InteractiveCallback.Invoke().ConfigureAwait(false);
                this.Logger.LogChatManagerUserInput(this.Id, input.Text);
                this._chat.Add(input);
                await this.PublishMessageAsync(new GroupChatMessages.Group([input]), this.Context.Topic, cancellationToken: cancellationToken).ConfigureAwait(false);
            }
        }

        GroupChatManagerResult<bool> terminateResult = await this._manager.ShouldTerminate(this._chat, cancellationToken).ConfigureAwait(false);
        this.Logger.LogChatManagerTerminate(this.Id, terminateResult.Value, terminateResult.Reason);
        if (terminateResult.Value)
        {
            GroupChatManagerResult<string> filterResult = await this._manager.FilterResults(this._chat, cancellationToken).ConfigureAwait(false);
            this.Logger.LogChatManagerResult(this.Id, filterResult.Value, filterResult.Reason);
            await this.PublishMessageAsync(new GroupChatMessages.Result(new(ChatRole.Assistant, filterResult.Value)), this._orchestrationType, cancellationToken).ConfigureAwait(false);
            return;
        }

        GroupChatManagerResult<string> selectionResult = await this._manager.SelectNextAgent(this._chat, this._team, cancellationToken).ConfigureAwait(false);
        ActorType selectionType = new(this._team[selectionResult.Value].Type);
        this.Logger.LogChatManagerSelect(this.Id, selectionType);
        await this.PublishMessageAsync(new GroupChatMessages.Speak(), selectionType, cancellationToken: cancellationToken).ConfigureAwait(false);
    }
}
