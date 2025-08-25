// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.SystemVariables;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

internal static class SystemScope
{
    public static class Names
    {
        public const string ConversationId = nameof(SystemVariables.ConversationId);
        public const string InternalId = nameof(InternalId);
        public const string LastMessage = nameof(LastMessage);
        public const string LastMessageId = nameof(SystemVariables.LastMessageId);
        public const string LastMessageText = nameof(SystemVariables.LastMessageText);
    }

    public static HashSet<string> AllNames { get; } = [.. GetNames()];

    public static IEnumerable<string> GetNames()
    {
        yield return SystemScope.Names.ConversationId;
        yield return SystemScope.Names.InternalId;
        yield return SystemScope.Names.LastMessage;
        yield return SystemScope.Names.LastMessageId;
        yield return SystemScope.Names.LastMessageText;
    }

    public static FormulaValue GetConversationId(this DeclarativeWorkflowState state) =>
        state.Get(VariableScopeNames.System, SystemScope.Names.ConversationId);

    public static void SetConversationId(this DeclarativeWorkflowState state, string conversationId) =>
        state.Set(VariableScopeNames.System, SystemScope.Names.ConversationId, FormulaValue.New(conversationId));

    public static FormulaValue GetInternalConversationId(this DeclarativeWorkflowState state) => // %%% Workaround until updated OM is available
        state.Get(VariableScopeNames.System, SystemScope.Names.InternalId);

    public static void SetInternalConversationId(this DeclarativeWorkflowState state, string conversationId) => // %%% Workaround until updated OM is available
        state.Set(VariableScopeNames.System, SystemScope.Names.InternalId, FormulaValue.New(conversationId));

    public static void SetLastMessage(this WorkflowScopes scopes, ChatMessage message)
    {
        scopes.Set(SystemScope.Names.LastMessage, VariableScopeNames.System, message.ToRecordValue());
        scopes.Set(SystemScope.Names.LastMessageId, VariableScopeNames.System, message.MessageId is null ? FormulaValue.NewBlank(FormulaType.String) : FormulaValue.New(message.MessageId));
        scopes.Set(SystemScope.Names.LastMessageText, VariableScopeNames.System, FormulaValue.New(message.Text));
    }

    public static void SetLastMessage(this DeclarativeWorkflowState state, ChatMessage message)
    {
        state.Set(VariableScopeNames.System, SystemScope.Names.LastMessage, message.ToRecordValue());
        state.Set(VariableScopeNames.System, SystemScope.Names.LastMessageId, message.MessageId is null ? FormulaValue.NewBlank(FormulaType.String) : FormulaValue.New(message.MessageId));
        state.Set(VariableScopeNames.System, SystemScope.Names.LastMessageText, FormulaValue.New(message.Text));
    }
}
