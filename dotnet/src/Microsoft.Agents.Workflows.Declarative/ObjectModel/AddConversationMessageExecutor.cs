﻿// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class AddConversationMessageExecutor(AddConversationMessage model, WorkflowAgentProvider agentProvider, WorkflowFormulaState state) :
    DeclarativeActionExecutor<AddConversationMessage>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        StringExpression conversationExpression = Throw.IfNull(this.Model.ConversationId, $"{nameof(this.Model)}.{nameof(this.Model.ConversationId)}");
        string conversationId = this.State.Evaluator.GetValue(conversationExpression).Value;

        ChatMessage newMessage = new(this.GetRole(), [.. this.GetContent()]) { AdditionalProperties = this.GetMetadata() };

        await agentProvider.CreateMessageAsync(conversationId, newMessage, cancellationToken).ConfigureAwait(false);

        await this.AssignAsync(this.Model.Message?.Path, newMessage.ToRecord(), context).ConfigureAwait(false);

        return default;
    }

    private IEnumerable<AIContent> GetContent()
    {
        foreach (AddConversationMessageContent content in this.Model.Content)
        {
            AIContent? messageContent = content.Type.Value.ToContent(this.State.Engine.Format(content.Value));
            if (messageContent is not null)
            {
                yield return messageContent;
            }
        }
    }

    private ChatRole GetRole()
    {
        if (this.Model.Role is null)
        {
            return ChatRole.User;
        }

        AgentMessageRoleWrapper roleWrapper = this.State.Evaluator.GetValue(this.Model.Role).Value;

        return roleWrapper.Value.ToChatRole();
    }

    private AdditionalPropertiesDictionary? GetMetadata()
    {
        if (this.Model.Metadata is null)
        {
            return null;
        }

        RecordDataValue? metadataValue = this.State.Evaluator.GetValue(this.Model.Metadata).Value;

        return metadataValue.ToMetadata();
    }
}
