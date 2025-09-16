// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Frozen;
using System.Collections.Generic;
using System.Globalization;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.SystemVariables;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

internal static class SystemScope
{
    private static readonly RecordValue s_emptyMessage = new ChatMessage(ChatRole.User, string.Empty).ToRecord();

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

    public static FrozenSet<string> AllNames { get; } = GetNames().ToFrozenSet();

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

    public static void InitializeSystem(this WorkflowFormulaState scopes)
    {
        scopes.Set(Names.Activity, RecordValue.Empty(), VariableScopeNames.System);
        scopes.Set(Names.Bot, RecordValue.Empty(), VariableScopeNames.System);

        scopes.Set(Names.LastMessage, s_emptyMessage, VariableScopeNames.System);
        Set(Names.LastMessageId);
        Set(Names.LastMessageText);

        scopes.Set(
            Names.Conversation,
            RecordValue.NewRecordFromFields(
                new NamedValue("Id", FormulaType.String.NewBlank()),
                new NamedValue("LocalTimeZone", FormulaValue.New(TimeZoneInfo.Local.StandardName)),
                new NamedValue("LocalTimeZoneOffset", FormulaValue.New(TimeZoneInfo.Local.GetUtcOffset(DateTime.UtcNow))),
                new NamedValue("InTestMode", FormulaValue.New(false))),
            VariableScopeNames.System);
        scopes.Set(Names.ConversationId, FormulaType.String.NewBlank(), VariableScopeNames.System);
        scopes.Set(Names.InternalId, FormulaType.String.NewBlank(), VariableScopeNames.System);

        scopes.Set(
            Names.Recognizer,
            RecordValue.NewRecordFromFields(
                new NamedValue("Id", FormulaType.String.NewBlank()),
                new NamedValue("Text", FormulaType.String.NewBlank())),
            VariableScopeNames.System);

        scopes.Set(
            Names.User,
            RecordValue.NewRecordFromFields(
                new NamedValue("Language", StringValue.New(CultureInfo.CurrentCulture.TwoLetterISOLanguageName))),
            VariableScopeNames.System);
        scopes.Set(Names.UserLanguage, StringValue.New(CultureInfo.CurrentCulture.TwoLetterISOLanguageName), VariableScopeNames.System);

        void Set(string key, string? value = null)
        {
            if (string.IsNullOrEmpty(value))
            {
                scopes.Set(key, FormulaType.String.NewBlank(), VariableScopeNames.System);
            }
            else
            {
                scopes.Set(key, FormulaValue.New(value), VariableScopeNames.System);
            }
        }
    }

    public static FormulaValue GetConversationId(this WorkflowFormulaState state) =>
        state.Get(Names.ConversationId, VariableScopeNames.System);

    public static void SetConversationId(this WorkflowFormulaState state, string conversationId)
    {
        RecordValue conversation = (RecordValue)state.Get(Names.Conversation, VariableScopeNames.System);
        conversation.UpdateField("Id", FormulaValue.New(conversationId));
        state.Set(Names.Conversation, conversation, VariableScopeNames.System);
        state.Set(Names.ConversationId, FormulaValue.New(conversationId), VariableScopeNames.System);
    }

    public static void SetLastMessage(this WorkflowFormulaState state, ChatMessage message)
    {
        state.Set(Names.LastMessage, message.ToRecord(), VariableScopeNames.System);
        state.Set(Names.LastMessageId, message.MessageId is null ? FormulaValue.NewBlank(FormulaType.String) : FormulaValue.New(message.MessageId), VariableScopeNames.System);
        state.Set(Names.LastMessageText, FormulaValue.New(message.Text), VariableScopeNames.System);
    }
}
