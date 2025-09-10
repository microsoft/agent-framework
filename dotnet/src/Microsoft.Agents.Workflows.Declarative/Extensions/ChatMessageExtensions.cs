// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.Workflows.Declarative.PowerFx.Functions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class ChatMessageExtensions
{
    public static RecordValue ToRecord(this ChatMessage message) =>
        RecordValue.NewRecordFromFields(message.GetMessageFields());

    public static IEnumerable<ChatMessage> ToChatMessages(this DataValue messages)
    {
        if (messages is TableDataValue table)
        {
            return table.ToChatMessages();
        }

        if (messages is RecordDataValue record)
        {
            return [record.ToChatMessage()];
        }

        if (messages is StringDataValue text)
        {
            return [text.ToChatMessage()];
        }

        return [];
    }

    public static IEnumerable<ChatMessage> ToChatMessages(this TableDataValue messages)
    {
        foreach (DataValue message in messages.Values)
        {
            if (message is RecordDataValue record)
            {
                ChatMessage? convertedMessage = record.Properties["Value"].ToChatMessage();
                if (convertedMessage is not null)
                {
                    yield return convertedMessage;
                }
            }
            else if (message is StringDataValue text)
            {
                yield return ToChatMessage(text);
            }
        }
    }

    public static ChatMessage? ToChatMessage(this DataValue message)
    {
        if (message is RecordDataValue record)
        {
            return record.ToChatMessage();
        }

        if (message is StringDataValue text)
        {
            return text.ToChatMessage();
        }

        if (message is BlankDataValue)
        {
            return null;
        }

        throw new DeclarativeActionException($"Unable to convert {message.GetDataType()} to {nameof(ChatMessage)}.");
    }

    public static ChatMessage ToChatMessage(this RecordDataValue message)
    {
        StringDataValue? role = message.GetProperty<StringDataValue>(UserMessage.Fields.Role);
        TableDataValue? content = message.GetProperty<TableDataValue>(UserMessage.Fields.Content);
        RecordDataValue? item = content?.Values.Where(record => record.IsTextContent()).FirstOrDefault();
        StringDataValue? text = item?.GetProperty<StringDataValue>(UserMessage.Fields.ContentValue);

        return new(ChatRole.User, text?.Value);
    }

    public static ChatMessage ToChatMessage(this StringDataValue message) => new(ChatRole.User, message.Value);

    private static bool IsTextContent(this RecordDataValue content)
    {
        StringDataValue? type = content?.GetProperty<StringDataValue>(UserMessage.Fields.ContentType);
        return type?.Value?.Equals(UserMessage.ContentTypes.Text, StringComparison.OrdinalIgnoreCase) ?? true;
    }

    private static TValue? GetProperty<TValue>(this RecordDataValue record, string name)
        where TValue : DataValue
    {
        if (record.Properties.TryGetValue(name, out DataValue? value) && value is TValue dataValue)
        {
            return dataValue;
        }

        return null;
    }

    private static IEnumerable<NamedValue> GetMessageFields(this ChatMessage message)
    {
        yield return new NamedValue(nameof(DialogAction.Id), message.MessageId.ToFormulaValue());
        yield return new NamedValue(nameof(ChatMessage.Role), FormulaValue.New(message.Role.Value));
        yield return new NamedValue(nameof(ChatMessage.AuthorName), message.AuthorName.ToFormulaValue());
        yield return new NamedValue(nameof(ChatMessage.Text), message.Text.ToFormulaValue());
    }
}
