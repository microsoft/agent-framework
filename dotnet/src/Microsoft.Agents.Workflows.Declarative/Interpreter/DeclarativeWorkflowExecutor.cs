// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

/// <summary>
/// The root executor for a declarative workflow.
/// </summary>
/// <param name="workflowId">The unique identifier for the workflow.</param>
internal sealed class DeclarativeWorkflowExecutor<TInput>(string workflowId) :
    ReflectingExecutor<DeclarativeWorkflowExecutor<TInput>>(workflowId),
    IMessageHandler<TInput>
    where TInput : notnull
{
    public async ValueTask HandleAsync(TInput message, IWorkflowContext context)
    {
        ChatMessage input =
            message switch
            {
                ChatMessage chatMessage => chatMessage,
                string stringMessage => new ChatMessage(ChatRole.User, stringMessage),
                _ => new(ChatRole.User, $"{message}")
            };

        WorkflowScopes scopes = await context.GetScopedStateAsync(default).ConfigureAwait(false);

        scopes.Set("LastMessage", VariableScopeNames.System, input.ToRecordValue());
        scopes.Set("Activity", VariableScopeNames.System, new ChatMessage(ChatRole.User, string.Empty).ToRecordValue());

        await context.SetScopedStateAsync(scopes, default).ConfigureAwait(false);
        await context.SendMessageAsync(new ExecutionResultMessage(this.Id)).ConfigureAwait(false);
    }
}
