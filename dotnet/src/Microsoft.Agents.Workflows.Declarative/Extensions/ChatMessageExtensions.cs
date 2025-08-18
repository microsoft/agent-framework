// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class ChatMessageExtensions
{
    public static RecordValue ToRecordValue(this ChatMessage message) => // %%% CPS - MESSAGETYPE
        RecordValue.NewRecordFromFields(
            new NamedValue(nameof(ChatMessage.MessageId), message.MessageId.ToFormulaValue()),
            new NamedValue(nameof(ChatMessage.Role), FormulaValue.New(message.Role.Value)),
            new NamedValue(nameof(ChatMessage.AuthorName), message.AuthorName.ToFormulaValue()),
            new NamedValue(nameof(ChatMessage.Text), message.Text.ToFormulaValue()));
            ////new NamedValue(nameof(ChatMessage.AdditionalProperties), message.AdditionalProperties?.ToRecordValue()));
}
