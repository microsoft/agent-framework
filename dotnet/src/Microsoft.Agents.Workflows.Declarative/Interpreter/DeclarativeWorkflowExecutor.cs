// Copyright (c) Microsoft. All rights reserved.

using System;
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
internal sealed class DeclarativeWorkflowExecutor<TInput>(string workflowId, AdaptiveDialog workflowElement, Func<TInput, ChatMessage> inputTransform) :
    ReflectingExecutor<DeclarativeWorkflowExecutor<TInput>>(workflowId),
    IMessageHandler<TInput>
    where TInput : notnull
{
    public async ValueTask HandleAsync(TInput message, IWorkflowContext context)
    {
        WorkflowScopes scopes = await context.GetScopedStateAsync(default).ConfigureAwait(false);

        scopes.InitializeModel(workflowElement);

        ChatMessage input = inputTransform.Invoke(message);

        scopes.Set("LastMessage", VariableScopeNames.System, input.ToRecordValue());

        await context.SetScopedStateAsync(scopes, default).ConfigureAwait(false);
        await context.SendMessageAsync(new ExecutionResultMessage(this.Id)).ConfigureAwait(false);
    }
}
