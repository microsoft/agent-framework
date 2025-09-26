// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Frozen;
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
        public const string LastMessage = nameof(LastMessage);
        public const string LastMessageId = nameof(SystemVariables.LastMessageId);
        public const string LastMessageText = nameof(SystemVariables.LastMessageText);
        public const string Recognizer = nameof(Recognizer);
        public const string User = nameof(User);
        public const string UserLanguage = nameof(UserLanguage);
    }

    public static FrozenSet<string> AllNames { get; } =
    [
        Names.Activity,
        Names.Bot,
        Names.Conversation,
        Names.ConversationId,
        Names.LastMessage,
        Names.LastMessageId,
        Names.LastMessageText,
        Names.Recognizer,
        Names.User,
        Names.UserLanguage,
    ];

    public static void InitializeSystem(this WorkflowFormulaState state)
    {
        state.Set(Names.Activity, RecordValue.Empty(), VariableScopeNames.System);
        state.Set(Names.Bot, RecordValue.Empty(), VariableScopeNames.System);

        state.Set(Names.LastMessage, s_emptyMessage, VariableScopeNames.System);
        Set(Names.LastMessageId);
        Set(Names.LastMessageText);

        state.Set(
            Names.Conversation,
            FormulaValue.NewRecordFromFields(
                new NamedValue("Id", FormulaType.String.NewBlank()),
                new NamedValue("LocalTimeZone", FormulaValue.New(TimeZoneInfo.Local.StandardName)),
                new NamedValue("LocalTimeZoneOffset", FormulaValue.New(TimeZoneInfo.Local.GetUtcOffset(DateTime.UtcNow))),
                new NamedValue("InTestMode", FormulaValue.New(false))),
            VariableScopeNames.System);
        state.Set(Names.ConversationId, FormulaType.String.NewBlank(), VariableScopeNames.System);

        state.Set(
            Names.Recognizer,
            FormulaValue.NewRecordFromFields(
                new NamedValue("Id", FormulaType.String.NewBlank()),
                new NamedValue("Text", FormulaType.String.NewBlank())),
            VariableScopeNames.System);

        state.Set(
            Names.User,
            FormulaValue.NewRecordFromFields(
                new NamedValue("Language", FormulaValue.New(CultureInfo.CurrentCulture.TwoLetterISOLanguageName))),
            VariableScopeNames.System);
        state.Set(Names.UserLanguage, FormulaValue.New(CultureInfo.CurrentCulture.TwoLetterISOLanguageName), VariableScopeNames.System);

        void Set(string key, string? value = null)
        {
            if (string.IsNullOrEmpty(value))
            {
                state.Set(key, FormulaType.String.NewBlank(), VariableScopeNames.System);
            }
            else
            {
                state.Set(key, FormulaValue.New(value), VariableScopeNames.System);
            }
        }
    }

    public static void SetLastMessage(this WorkflowFormulaState state, ChatMessage message)
    {
        state.Set(Names.LastMessage, message.ToRecord(), VariableScopeNames.System);
        state.Set(Names.LastMessageId, message.MessageId is null ? FormulaValue.NewBlank(FormulaType.String) : FormulaValue.New(message.MessageId), VariableScopeNames.System);
        state.Set(Names.LastMessageText, FormulaValue.New(message.Text), VariableScopeNames.System);
        state.Bind();
    }
}
