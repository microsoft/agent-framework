// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class ChatMessageExtensions
{
    public static RecordValue ToRecord(this ChatMessage message) => // %%% CPS - MESSAGETYPE
        RecordValue.NewRecordFromFields(message.GetMessageFields());

    private static IEnumerable<NamedValue> GetMessageFields(this ChatMessage message)
    {
        yield return new NamedValue(nameof(DialogAction.Id), message.MessageId.ToFormulaValue());
        yield return new NamedValue(nameof(ChatMessage.Role), FormulaValue.New(message.Role.Value));
        yield return new NamedValue(nameof(ChatMessage.AuthorName), message.AuthorName.ToFormulaValue());
        yield return new NamedValue(nameof(ChatMessage.Text), message.Text.ToFormulaValue());
    }
}
