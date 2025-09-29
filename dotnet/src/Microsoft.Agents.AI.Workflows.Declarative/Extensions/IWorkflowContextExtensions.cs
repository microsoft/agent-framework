// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class IWorkflowContextExtensions
{
    public static ValueTask RaiseInvocationEventAsync(this IWorkflowContext context, DialogAction action, string? priorEventId = null) =>
        context.AddEventAsync(new DeclarativeActionInvokedEvent(action, priorEventId));

    public static ValueTask RaiseCompletionEventAsync(this IWorkflowContext context, DialogAction action) =>
        context.AddEventAsync(new DeclarativeActionCompletedEvent(action));

    public static ValueTask SendResultMessageAsync(this IWorkflowContext context, string id, object? result = null, CancellationToken cancellationToken = default) =>
        context.SendMessageAsync(new ActionExecutorResult(id, result));

    public static ValueTask QueueStateResetAsync(this IWorkflowContext context, PropertyPath variablePath) =>
        context.QueueStateUpdateAsync(Throw.IfNull(variablePath.VariableName), UnassignedValue.Instance, Throw.IfNull(variablePath.NamespaceAlias));

    public static ValueTask QueueStateUpdateAsync<TValue>(this IWorkflowContext context, PropertyPath variablePath, TValue? value) =>
        context.QueueStateUpdateAsync(Throw.IfNull(variablePath.VariableName), value, Throw.IfNull(variablePath.NamespaceAlias));

    public static ValueTask QueueSystemUpdateAsync<TValue>(this IWorkflowContext context, string key, TValue? value) =>
        DeclarativeContext(context).QueueSystemUpdateAsync(key, value);

    public static FormulaValue ReadState(this IWorkflowContext context, PropertyPath variablePath) =>
        context.ReadState(Throw.IfNull(variablePath.VariableName), Throw.IfNull(variablePath.NamespaceAlias));

    public static FormulaValue ReadState(this IWorkflowContext context, string key, string? scopeName = null) =>
        DeclarativeContext(context).State.Get(key, scopeName);

    public static async ValueTask QueueConversationUpdateAsync(this IWorkflowContext context, string conversationId)
    {
        RecordValue conversation = (RecordValue)context.ReadState(SystemScope.Names.Conversation, VariableScopeNames.System);
        conversation.UpdateField("Id", FormulaValue.New(conversationId));
        await context.QueueSystemUpdateAsync(SystemScope.Names.Conversation, conversation).ConfigureAwait(false);
        await context.QueueSystemUpdateAsync(SystemScope.Names.ConversationId, FormulaValue.New(conversationId)).ConfigureAwait(false);

        await context.AddEventAsync(new ConversationUpdateEvent(conversationId)).ConfigureAwait(false);
    }

    private static DeclarativeWorkflowContext DeclarativeContext(IWorkflowContext context)
    {
        if (context is not DeclarativeWorkflowContext declarativeContext)
        {
            throw new DeclarativeActionException($"Invalid workflow context: {context.GetType().Name}.");
        }

        return declarativeContext;
    }
}
