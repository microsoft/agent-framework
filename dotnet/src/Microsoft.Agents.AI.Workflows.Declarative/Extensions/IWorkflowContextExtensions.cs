// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class IWorkflowContextExtensions
{
    public static ValueTask RaiseInvocationEventAsync(this IWorkflowContext context, DialogAction action, string? priorEventId = null, CancellationToken cancellationToken = default) =>
        context.AddEventAsync(new DeclarativeActionInvokedEvent(action, priorEventId), cancellationToken);

    public static ValueTask RaiseCompletionEventAsync(this IWorkflowContext context, DialogAction action, CancellationToken cancellationToken = default) =>
        context.AddEventAsync(new DeclarativeActionCompletedEvent(action), cancellationToken);

    public static FormulaValue ReadState(this IWorkflowContext context, PropertyPath variablePath) =>
        context.ReadState(Throw.IfNull(GetVariableName(variablePath)), GetNamespaceAlias(variablePath));

    public static FormulaValue ReadState(this IWorkflowContext context, string key, string? scopeName = null) =>
        DeclarativeContext(context).State.Get(key, scopeName);

    public static ValueTask SendResultMessageAsync(this IWorkflowContext context, string id, CancellationToken cancellationToken = default) =>
        context.SendResultMessageAsync(id, result: null, cancellationToken);

    public static ValueTask SendResultMessageAsync(this IWorkflowContext context, string id, object? result, CancellationToken cancellationToken = default) =>
        context.SendMessageAsync(new ActionExecutorResult(id, result), targetId: null, cancellationToken);

    public static ValueTask QueueStateResetAsync(this IWorkflowContext context, PropertyPath variablePath, CancellationToken cancellationToken = default) =>
        context.QueueStateUpdateAsync(Throw.IfNull(GetVariableName(variablePath)), UnassignedValue.Instance, GetNamespaceAlias(variablePath), cancellationToken);

    public static ValueTask QueueStateUpdateAsync<TValue>(this IWorkflowContext context, PropertyPath variablePath, TValue? value, CancellationToken cancellationToken = default) =>
        context.QueueStateUpdateAsync(Throw.IfNull(GetVariableName(variablePath)), value, GetNamespaceAlias(variablePath), cancellationToken);

    // Workaround for ObjectModel 2026.2.4.1 regression: PropertyPath built from a dotted
    // reference such as "Local.Triage" returns null for both NamespaceAlias and VariableName
    // even when SegmentCount==2 and IsValid==true. Reconstruct from Segments() in that case.
    private static string? GetVariableName(PropertyPath variablePath) =>
        variablePath.VariableName ?? (variablePath.SegmentCount >= 2 ? variablePath.Segments().ElementAtOrDefault(1).PropertyName : variablePath.SegmentCount == 1 ? variablePath.Segments().ElementAtOrDefault(0).PropertyName : null);

    // Workaround for ObjectModel 2026.2.4.1 regression: in addition to the parser bug above,
    // the framework's user-facing scope alias "Local" is no longer recognized by
    // VariableScopeNames.IsValidName / GetNamespaceFromName (they only accept the canonical
    // names "Topic", "Global", "System", "Env"). Translate the "Local" alias back to its
    // canonical "Topic" form so downstream IsManagedScope checks succeed.
    private static string? GetNamespaceAlias(PropertyPath variablePath)
    {
        string? alias = variablePath.NamespaceAlias
            ?? (variablePath.SegmentCount >= 2 ? variablePath.Segments().ElementAtOrDefault(0).PropertyName : null);
        return string.Equals(alias, "Local", StringComparison.Ordinal) ? VariableScopeNames.Topic : alias;
    }

    public static async ValueTask QueueEnvironmentUpdateAsync<TValue>(this IWorkflowContext context, string key, TValue? value, CancellationToken cancellationToken = default)
    {
        DeclarativeWorkflowContext declarativeContext = DeclarativeContext(context);
        await declarativeContext.UpdateStateAsync(key, value, VariableScopeNames.Environment, allowSystem: true, cancellationToken).ConfigureAwait(false);
        declarativeContext.State.Bind();
    }

    public static async ValueTask QueueSystemUpdateAsync<TValue>(this IWorkflowContext context, string key, TValue? value, CancellationToken cancellationToken = default)
    {
        DeclarativeWorkflowContext declarativeContext = DeclarativeContext(context);
        await declarativeContext.UpdateStateAsync(key, value, VariableScopeNames.System, allowSystem: true, cancellationToken).ConfigureAwait(false);
        declarativeContext.State.Bind();
    }

    public static ValueTask QueueConversationUpdateAsync(this IWorkflowContext context, string conversationId, CancellationToken cancellationToken = default) =>
        context.QueueConversationUpdateAsync(conversationId, isExternal: false, cancellationToken);

    public static async ValueTask QueueConversationUpdateAsync(this IWorkflowContext context, string conversationId, bool isExternal = false, CancellationToken cancellationToken = default)
    {
        RecordValue conversation = (RecordValue)context.ReadState(SystemScope.Names.Conversation, VariableScopeNames.System);

        if (isExternal)
        {
            conversation.UpdateField("Id", FormulaValue.New(conversationId));
            await context.QueueSystemUpdateAsync(SystemScope.Names.Conversation, conversation, cancellationToken).ConfigureAwait(false);
            await context.QueueSystemUpdateAsync(SystemScope.Names.ConversationId, FormulaValue.New(conversationId), cancellationToken).ConfigureAwait(false);
        }

        await context.AddEventAsync(new ConversationUpdateEvent(conversationId) { IsWorkflow = isExternal }, cancellationToken).ConfigureAwait(false);
    }

    public static string? GetWorkflowConversation(this IWorkflowContext context) =>
        context.ReadState(SystemScope.Names.ConversationId, VariableScopeNames.System) switch
        {
            StringValue stringValue when stringValue.Value.Length > 0 => stringValue.Value,
            _ => null,
        };

    public static bool IsWorkflowConversation(
        this IWorkflowContext context,
        string? conversationId,
        out string? workflowConversationId)
    {
        workflowConversationId = context.GetWorkflowConversation();
        return workflowConversationId?.Equals(conversationId, StringComparison.Ordinal) ?? false;
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
