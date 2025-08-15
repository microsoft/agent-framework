// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class ChatMessageExtensions
{
    public static RecordValue ToRecord(this ChatMessage message) =>
        RecordValue.NewRecordFromFields(
            new NamedValue(nameof(ChatMessage.MessageId), FormulaValue.New(message.MessageId)),
            new NamedValue(nameof(ChatMessage.Role), FormulaValue.New(message.Role.Value)),
            new NamedValue(nameof(ChatMessage.AuthorName), FormulaValue.New(message.AuthorName)),
            new NamedValue(nameof(ChatMessage.Text), FormulaValue.New(message.Text)));
}
