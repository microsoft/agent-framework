// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class ChatMessageExtensions
{
    public static RecordValue ToRecord(this ChatMessage message) =>
        FormulaValue.NewRecordFromFields(message.GetMessageFields());

    /// <summary>
    /// Merges the user-authored <paramref name="input"/> with the round-tripped
    /// <paramref name="inputMessage"/> returned by <c>AgentProvider.CreateMessageAsync</c>
    /// to produce the value stored in <c>System.LastMessage</c>.
    /// </summary>
    /// <remarks>
    /// The agent service often strips or alters <see cref="TextContent"/> on round-trip,
    /// while replacing inline media (<see cref="DataContent"/>, <see cref="UriContent"/>)
    /// with server-side references (typically <see cref="HostedFileContent"/>).
    /// We want both: the original text (so <c>=System.LastMessage.Text</c> works) and
    /// the server's media references (so subsequent actions don't re-upload large blobs).
    /// <para>
    /// Strategy: keep <paramref name="inputMessage"/> as the base — it has the server-generated
    /// <see cref="ChatMessage.MessageId"/> and any provider-augmented metadata, and is forward-
    /// compatible with new properties added on <see cref="ChatMessage"/> in the abstractions
    /// layer. Only the <see cref="ChatMessage.Contents"/> list is mutated to preserve the
    /// caller's ordering while substituting server-side references using stable identity first,
    /// then the provider-preserved order when all remaining media items correspond one-to-one.
    /// </para>
    /// </remarks>
    public static ChatMessage MergeForLastMessage(this ChatMessage input, ChatMessage? inputMessage)
    {
        if (inputMessage is null)
        {
            return input;
        }

        List<AIContent> inputNonTextContents = [.. input.Contents.Where(content => content is not TextContent)];
        List<AIContent> canonicalNonTextContents = [.. inputMessage.Contents.Where(content => content is not TextContent)];
        AIContent[] replacements = [.. inputNonTextContents];
        bool[] inputContentMatched = new bool[inputNonTextContents.Count];
        bool[] canonicalContentUsed = new bool[canonicalNonTextContents.Count];

        for (int inputIndex = 0; inputIndex < inputNonTextContents.Count; inputIndex++)
        {
            for (int canonicalIndex = 0; canonicalIndex < canonicalNonTextContents.Count; canonicalIndex++)
            {
                if (!canonicalContentUsed[canonicalIndex] &&
                    HasSameStableIdentity(inputNonTextContents[inputIndex], canonicalNonTextContents[canonicalIndex]))
                {
                    replacements[inputIndex] = canonicalNonTextContents[canonicalIndex];
                    inputContentMatched[inputIndex] = true;
                    canonicalContentUsed[canonicalIndex] = true;
                    break;
                }
            }
        }

        List<int> unmatchedInputIndexes = [.. Enumerable.Range(0, inputNonTextContents.Count).Where(index => !inputContentMatched[index])];
        List<int> unmatchedCanonicalIndexes = [.. Enumerable.Range(0, canonicalNonTextContents.Count).Where(index => !canonicalContentUsed[index])];

        if (unmatchedInputIndexes.Count == unmatchedCanonicalIndexes.Count &&
            unmatchedInputIndexes.All(index => IsMediaContent(inputNonTextContents[index])) &&
            unmatchedCanonicalIndexes.All(index => IsMediaContent(canonicalNonTextContents[index])))
        {
            for (int index = 0; index < unmatchedInputIndexes.Count; index++)
            {
                replacements[unmatchedInputIndexes[index]] = canonicalNonTextContents[unmatchedCanonicalIndexes[index]];
            }
        }

        List<AIContent> mergedContents = [];
        int nonTextIndex = 0;

        foreach (AIContent content in input.Contents)
        {
            mergedContents.Add(
                content is TextContent
                    ? content
                    : replacements[nonTextIndex++]);
        }

        if (mergedContents.Count == 0 && !string.IsNullOrEmpty(input.Text))
        {
            mergedContents.Add(new TextContent(input.Text));
        }

        if (mergedContents.Count == 0)
        {
            return inputMessage;
        }

        if (inputNonTextContents.Count == 0)
        {
            mergedContents.AddRange(canonicalNonTextContents);
        }

        inputMessage.Contents.Clear();
        foreach (AIContent content in mergedContents)
        {
            inputMessage.Contents.Add(content);
        }

        return inputMessage;
    }

    private static bool HasSameStableIdentity(AIContent input, AIContent canonical) =>
        ReferenceEquals(input, canonical) ||
        (input, canonical) switch
        {
            (HostedFileContent inputFile, HostedFileContent canonicalFile) =>
                string.Equals(inputFile.FileId, canonicalFile.FileId, StringComparison.Ordinal),
            (UriContent inputUri, UriContent canonicalUri) =>
                inputUri.Uri == canonicalUri.Uri &&
                string.Equals(inputUri.MediaType, canonicalUri.MediaType, StringComparison.OrdinalIgnoreCase),
            (DataContent inputData, DataContent canonicalData) =>
                string.Equals(inputData.Uri, canonicalData.Uri, StringComparison.Ordinal) &&
                string.Equals(inputData.MediaType, canonicalData.MediaType, StringComparison.OrdinalIgnoreCase),
            _ => false
        };

    private static bool IsMediaContent(AIContent content) =>
        content is DataContent or UriContent or HostedFileContent;

    public static TableValue ToTable(this IEnumerable<ChatMessage> messages) =>
        FormulaValue.NewTable(TypeSchema.Message.RecordType, messages.Select(message => message.ToRecord()));

    public static IEnumerable<ChatMessage>? ToChatMessages(this DataValue? messages)
    {
        if (messages is null or BlankDataValue)
        {
            return null;
        }

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

        return null;
    }

    public static IEnumerable<ChatMessage> ToChatMessages(this TableDataValue messages)
    {
        foreach (RecordDataValue record in messages.Values)
        {
            DataValue sourceRecord = record;
            if (record.Properties.Count == 1 && record.Properties.TryGetValue("Value", out DataValue? singleColumn))
            {
                sourceRecord = singleColumn;
            }
            ChatMessage? convertedMessage = sourceRecord.ToChatMessage();
            if (convertedMessage is not null)
            {
                yield return convertedMessage;
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

    public static ChatMessage ToChatMessage(this RecordDataValue message) =>
        new(message.GetRole(), [.. message.GetContent()])
        {
            MessageId = message.GetProperty<StringDataValue>(TypeSchema.Message.Fields.Id)?.Value,
            AdditionalProperties = message.GetProperty<RecordDataValue>(TypeSchema.Message.Fields.Metadata).ToMetadata()
        };

    public static ChatMessage ToChatMessage(this StringDataValue message) => new(ChatRole.User, message.Value);

    public static ChatMessage ToChatMessage(this IEnumerable<FunctionResultContent> functionResults) =>
        new(ChatRole.Tool, [.. functionResults]);

    public static AdditionalPropertiesDictionary? ToMetadata(this RecordDataValue? metadata)
    {
        if (metadata is null)
        {
            return null;
        }

        AdditionalPropertiesDictionary properties = [];

        foreach (KeyValuePair<string, DataValue> property in metadata.Properties)
        {
            properties[property.Key] = property.Value.ToObject();
        }

        return properties;
    }

    public static ChatRole ToChatRole(this AgentMessageRole role) =>
        role switch
        {
            AgentMessageRole.Agent => ChatRole.Assistant,
            AgentMessageRole.User => ChatRole.User,
            _ => ChatRole.User
        };

    public static ChatRole ToChatRole(this AgentMessageRole? role) => role?.ToChatRole() ?? ChatRole.User;

    public static AIContent? ToContent(this AgentMessageContentType contentType, string? contentValue, string? mediaType = null)
    {
        if (string.IsNullOrEmpty(contentValue))
        {
            return null;
        }

        return
            contentType switch
            {
                AgentMessageContentType.ImageUrl => GetImageContent(contentValue, mediaType ?? InferMediaType(contentValue)),
                AgentMessageContentType.ImageFile => new HostedFileContent(contentValue),
                _ => new TextContent(contentValue)
            };
    }

    private static ChatRole GetRole(this RecordDataValue message)
    {
        StringDataValue? roleValue = message.GetProperty<StringDataValue>(TypeSchema.Message.Fields.Role);
        if (string.IsNullOrWhiteSpace(roleValue?.Value))
        {
            return ChatRole.User;
        }

        AgentMessageRole? role = null;
        if (Enum.TryParse(roleValue.Value, out AgentMessageRole parsedRole))
        {
            role = parsedRole;
        }

        return role.ToChatRole();
    }

    private static IEnumerable<AIContent> GetContent(this RecordDataValue message)
    {
        TableDataValue? content = message.GetProperty<TableDataValue>(TypeSchema.Message.Fields.Content);
        if (content is not null)
        {
            foreach (RecordDataValue contentItem in content.Values)
            {
                StringDataValue? contentValue = contentItem.GetProperty<StringDataValue>(TypeSchema.MessageContent.Fields.Value);
                StringDataValue? mediaTypeValue = contentItem.GetProperty<StringDataValue>(TypeSchema.MessageContent.Fields.MediaType);
                if (contentValue is null || string.IsNullOrWhiteSpace(contentValue.Value))
                {
                    continue;
                }

                yield return
                    contentItem.GetProperty<StringDataValue>(TypeSchema.MessageContent.Fields.Type)?.Value switch
                    {
                        TypeSchema.MessageContent.ContentTypes.ImageUrl => GetImageContent(contentValue.Value, mediaTypeValue?.Value ?? InferMediaType(contentValue.Value)),
                        TypeSchema.MessageContent.ContentTypes.ImageFile => new HostedFileContent(contentValue.Value),
                        _ => new TextContent(contentValue.Value)
                    };
            }
        }
    }

    private static string InferMediaType(string value)
    {
        // Base64 encoded content includes media type
        if (value.StartsWith("data:", StringComparison.OrdinalIgnoreCase))
        {
            int semicolonIndex = value.IndexOf(';');
            if (semicolonIndex > 5)
            {
                return value.Substring(5, semicolonIndex - 5);
            }
        }

        // URL based input only supports image
        string fileExtension = Path.GetExtension(value);
        return
            fileExtension.ToUpperInvariant() switch
            {
                ".JPG" or ".JPEG" => "image/jpeg",
                ".PNG" => "image/png",
                ".GIF" => "image/gif",
                ".WEBP" => "image/webp",
                _ => "image/*"
            };
    }

    private static AIContent GetImageContent(string uriText, string mediaType) =>
        uriText.StartsWith("data:", StringComparison.OrdinalIgnoreCase) ?
            new DataContent(uriText, mediaType) :
            new UriContent(uriText, mediaType);

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
        yield return new NamedValue(TypeSchema.Discriminator, nameof(ChatMessage).ToFormula());
        yield return new NamedValue(TypeSchema.Message.Fields.Id, message.MessageId.ToFormula());
        yield return new NamedValue(TypeSchema.Message.Fields.Role, message.Role.Value.ToFormula());
        yield return new NamedValue(TypeSchema.Message.Fields.Author, message.AuthorName.ToFormula());
        yield return new NamedValue(TypeSchema.Message.Fields.Content, FormulaValue.NewTable(TypeSchema.MessageContent.RecordType, message.GetContentRecords()));
        yield return new NamedValue(TypeSchema.Message.Fields.Text, message.Text.ToFormula());
        yield return new NamedValue(TypeSchema.Message.Fields.Metadata, message.AdditionalProperties.ToRecord());
    }

    private static IEnumerable<RecordValue> GetContentRecords(this ChatMessage message) =>
        message.Contents.Select(content => FormulaValue.NewRecordFromFields(content.GetContentFields()));

    private static IEnumerable<NamedValue> GetContentFields(this AIContent content)
    {
        return
            content switch
            {
                UriContent uriContent => CreateContentRecord(TypeSchema.MessageContent.ContentTypes.ImageUrl, uriContent.Uri.ToString()),
                HostedFileContent fileContent => CreateContentRecord(TypeSchema.MessageContent.ContentTypes.ImageFile, fileContent.FileId),
                TextContent textContent => CreateContentRecord(TypeSchema.MessageContent.ContentTypes.Text, textContent.Text),
                DataContent dataContent => CreateContentRecord(TypeSchema.MessageContent.ContentTypes.ImageUrl, dataContent.Uri),
                _ => []
            };

        static IEnumerable<NamedValue> CreateContentRecord(string type, string value, string? mediaType = null)
        {
            yield return new NamedValue(TypeSchema.MessageContent.Fields.Type, type.ToFormula());
            yield return new NamedValue(TypeSchema.MessageContent.Fields.Value, value.ToFormula());
            if (mediaType is not null)
            {
                yield return new NamedValue(TypeSchema.MessageContent.Fields.MediaType, mediaType.ToFormula());
            }
        }
    }

    private static RecordValue ToRecord(this AdditionalPropertiesDictionary? value)
    {
        return FormulaValue.NewRecordFromFields(GetFields());

        IEnumerable<NamedValue> GetFields()
        {
            if (value is not null)
            {
                foreach (string key in value.Keys)
                {
                    yield return new NamedValue(key, value[key].ToFormula());
                }
            }
        }
    }
}
