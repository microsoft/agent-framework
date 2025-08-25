// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Globalization;
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
        public const string Activity = nameof(Activity);
        public const string Bot = nameof(Bot);
        public const string Conversation = nameof(Conversation);
        public const string ConversationId = nameof(SystemVariables.ConversationId);
        public const string InternalId = nameof(InternalId);
        public const string LastMessage = nameof(LastMessage);
        public const string LastMessageId = nameof(SystemVariables.LastMessageId);
        public const string LastMessageText = nameof(SystemVariables.LastMessageText);
        public const string Recognizer = nameof(Recognizer);
        public const string User = nameof(User);
        public const string UserLanguage = nameof(UserLanguage);
    }

    public static ImmutableHashSet<string> AllNames { get; } = GetNames().ToImmutableHashSet();

    public static IEnumerable<string> GetNames()
    {
        yield return Names.Activity;
        yield return Names.Bot;
        yield return Names.Conversation;
        yield return Names.ConversationId;
        yield return Names.InternalId;
        yield return Names.LastMessage;
        yield return Names.LastMessageId;
        yield return Names.LastMessageText;
        yield return Names.Recognizer;
        yield return Names.User;
        yield return Names.UserLanguage;
    }

    public static void InitializeSystem(this WorkflowScopes scopes, ChatMessage inputMessage)
    {
        scopes.Set(Names.Activity, VariableScopeNames.System, RecordValue.Empty());

        scopes.Set(Names.LastMessage, VariableScopeNames.System, inputMessage.ToRecord());
        scopes.Set(Names.LastMessageId, VariableScopeNames.System, FormulaType.String.NewBlank());
        scopes.Set(Names.LastMessageText, VariableScopeNames.System, FormulaType.String.NewBlank());

        scopes.Set(
            Names.Conversation,
            VariableScopeNames.System,
            RecordValue.NewRecordFromFields(
                new NamedValue("Id", FormulaType.String.NewBlank()),
                new NamedValue("LocalTimeZone", FormulaValue.New(TimeZoneInfo.Local.StandardName)),
                new NamedValue("LocalTimeZoneOffset", FormulaValue.New(TimeZoneInfo.Local.GetUtcOffset(DateTime.UtcNow))),
                new NamedValue("InTestMode", FormulaValue.New(false))));
        scopes.Set(Names.ConversationId, VariableScopeNames.System, FormulaType.String.NewBlank());
        scopes.Set(Names.InternalId, VariableScopeNames.System, FormulaType.String.NewBlank());

        scopes.Set(
            Names.Recognizer,
            VariableScopeNames.System,
            RecordValue.NewRecordFromFields(
                new NamedValue("Id", FormulaType.String.NewBlank()),
                new NamedValue("Text", FormulaType.String.NewBlank())));

        scopes.Set(
            Names.User,
            VariableScopeNames.System,
            RecordValue.NewRecordFromFields(
                new NamedValue("Language", StringValue.New(CultureInfo.CurrentCulture.TwoLetterISOLanguageName))));
        scopes.Set(Names.UserLanguage, VariableScopeNames.System, StringValue.New(CultureInfo.CurrentCulture.TwoLetterISOLanguageName));
    }

    public static FormulaValue GetConversationId(this DeclarativeWorkflowState state) =>
        state.Get(VariableScopeNames.System, Names.ConversationId);

    public static void SetConversationId(this DeclarativeWorkflowState state, string conversationId)
    {
        RecordValue conversation = (RecordValue)state.Get(VariableScopeNames.System, Names.Conversation);
        conversation.UpdateField("Id", FormulaValue.New(conversationId));
        state.Set(VariableScopeNames.System, Names.Conversation, conversation);
        state.Set(VariableScopeNames.System, Names.ConversationId, FormulaValue.New(conversationId));
    }

    public static FormulaValue GetInternalConversationId(this DeclarativeWorkflowState state) =>
        state.Get(VariableScopeNames.System, Names.InternalId);

    public static void SetInternalConversationId(this DeclarativeWorkflowState state, string conversationId) =>
        state.Set(VariableScopeNames.System, Names.InternalId, FormulaValue.New(conversationId));

    public static void SetLastMessage(this WorkflowScopes scopes, ChatMessage message)
    {
        scopes.Set(Names.LastMessage, VariableScopeNames.System, message.ToRecord());
        scopes.Set(Names.LastMessageId, VariableScopeNames.System, message.MessageId is null ? FormulaValue.NewBlank(FormulaType.String) : FormulaValue.New(message.MessageId));
        scopes.Set(Names.LastMessageText, VariableScopeNames.System, FormulaValue.New(message.Text));
    }

    public static void SetLastMessage(this DeclarativeWorkflowState state, ChatMessage message)
    {
        state.Set(VariableScopeNames.System, Names.LastMessage, message.ToRecord());
        state.Set(VariableScopeNames.System, Names.LastMessageId, message.MessageId is null ? FormulaValue.NewBlank(FormulaType.String) : FormulaValue.New(message.MessageId));
        state.Set(VariableScopeNames.System, Names.LastMessageText, FormulaValue.New(message.Text));
    }
}
