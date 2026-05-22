// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Represents the input to a response request, which can be a simple string, messages, or typed input items.
/// </summary>
[JsonConverter(typeof(ResponseInputJsonConverter))]
internal sealed class ResponseInput : IEquatable<ResponseInput>
{
    private ResponseInput(string text)
    {
        this.Text = text ?? throw new ArgumentNullException(nameof(text));
        this.Messages = null;
        this.Items = null;
    }

    private ResponseInput(List<InputMessage> messages)
    {
        this.Messages = messages ?? throw new ArgumentNullException(nameof(messages));
        this.Text = null;
        this.Items = null;
    }

    private ResponseInput(List<ItemParam> items)
    {
        this.Items = items ?? throw new ArgumentNullException(nameof(items));
        this.Text = null;
        this.Messages = null;
    }

    /// <summary>
    /// Creates a ResponseInput from a text string.
    /// </summary>
    public static ResponseInput FromText(string text) => new(text);

    /// <summary>
    /// Creates a ResponseInput from a list of messages.
    /// </summary>
    public static ResponseInput FromMessages(List<InputMessage> messages) => new(messages);

    /// <summary>
    /// Creates a ResponseInput from a list of messages.
    /// </summary>
    public static ResponseInput FromMessages(params InputMessage[] messages) => new(messages.ToList());

    /// <summary>
    /// Creates a ResponseInput from a list of input items.
    /// </summary>
    public static ResponseInput FromItems(List<ItemParam> items) => new(items);

    /// <summary>
    /// Implicit conversion from string to ResponseInput.
    /// </summary>
    public static implicit operator ResponseInput(string text) => FromText(text);

    /// <summary>
    /// Implicit conversion from InputMessage array to ResponseInput.
    /// </summary>
    public static implicit operator ResponseInput(InputMessage[] messages) => FromMessages(messages);

    /// <summary>
    /// Implicit conversion from List to ResponseInput.
    /// </summary>
    public static implicit operator ResponseInput(List<InputMessage> messages) => FromMessages(messages);

    /// <summary>
    /// Gets whether this input is a text string.
    /// </summary>
    public bool IsText => this.Text is not null;

    /// <summary>
    /// Gets whether this input is a list of messages.
    /// </summary>
    public bool IsMessages => this.Messages is not null;

    /// <summary>
    /// Gets whether this input is a list of typed input items.
    /// </summary>
    public bool IsItems => this.Items is not null;

    /// <summary>
    /// Gets the text value, or null if this is not a text input.
    /// </summary>
    public string? Text { get; }

    /// <summary>
    /// Gets the messages value, or null if this is not a messages input.
    /// </summary>
    public List<InputMessage>? Messages { get; }

    /// <summary>
    /// Gets the input item value, or null if this is not an item input.
    /// </summary>
    public List<ItemParam>? Items { get; }

    /// <summary>
    /// Gets the input as a list of InputMessage objects.
    /// </summary>
    [System.Diagnostics.CodeAnalysis.SuppressMessage("Design", "CA1024:Use properties where appropriate", Justification = "Method performs transformation logic")]
    public List<InputMessage> GetInputMessages()
    {
        if (this.Text is not null)
        {
            return [new InputMessage
            {
                Role = ChatRole.User,
                Content = this.Text
            }];
        }

        if (this.Messages is not null)
        {
            return this.Messages;
        }

        if (this.Items is not null)
        {
            var messages = new List<InputMessage>();
            foreach (ItemParam item in this.Items)
            {
                if (ToInputMessage(item) is { } message)
                {
                    messages.Add(message);
                }
            }

            return messages;
        }

        return [];
    }

    /// <summary>
    /// Gets the input as a list of ChatMessage objects.
    /// </summary>
    [System.Diagnostics.CodeAnalysis.SuppressMessage("Design", "CA1024:Use properties where appropriate", Justification = "Method performs transformation logic")]
    public List<ChatMessage> GetChatMessages()
    {
        if (this.Text is not null)
        {
            return [new ChatMessage(ChatRole.User, this.Text)];
        }

        if (this.Messages is not null)
        {
            return this.Messages.ConvertAll(static message => message.ToChatMessage());
        }

        if (this.Items is not null)
        {
            var messages = new List<ChatMessage>();
            foreach (ItemParam item in this.Items)
            {
                if (ToChatMessage(item) is { } message)
                {
                    messages.Add(message);
                }
            }

            return messages;
        }

        return [];
    }

    private static InputMessage? ToInputMessage(ItemParam item) => item switch
    {
        ResponsesUserMessageItemParam userMessage => new InputMessage { Role = ChatRole.User, Content = userMessage.Content },
        ResponsesAssistantMessageItemParam assistantMessage => new InputMessage { Role = ChatRole.Assistant, Content = assistantMessage.Content },
        ResponsesSystemMessageItemParam systemMessage => new InputMessage { Role = ChatRole.System, Content = systemMessage.Content },
        ResponsesDeveloperMessageItemParam developerMessage => new InputMessage { Role = new ChatRole("developer"), Content = developerMessage.Content },
        _ => null
    };

    private static ChatMessage? ToChatMessage(ItemParam item) => item switch
    {
        ResponsesUserMessageItemParam userMessage => new ChatMessage(ChatRole.User, ToAIContents(userMessage.Content)),
        ResponsesAssistantMessageItemParam assistantMessage => new ChatMessage(ChatRole.Assistant, ToAIContents(assistantMessage.Content)),
        ResponsesSystemMessageItemParam systemMessage => new ChatMessage(ChatRole.System, ToAIContents(systemMessage.Content)),
        ResponsesDeveloperMessageItemParam developerMessage => new ChatMessage(new ChatRole("developer"), ToAIContents(developerMessage.Content)),
        FunctionToolCallItemParam functionCall => new ChatMessage(
            ChatRole.Assistant,
            [new FunctionCallContent(functionCall.CallId, functionCall.Name, ParseFunctionArgumentsObject(functionCall.Arguments))]),
        FunctionToolCallOutputItemParam functionOutput => new ChatMessage(
            ChatRole.Tool,
            [new FunctionResultContent(functionOutput.CallId, functionOutput.Output)]),
        FunctionApprovalResponseItemParam approvalResponse => ToChatMessage(approvalResponse),
        _ => null
    };

    private static ChatMessage ToChatMessage(FunctionApprovalResponseItemParam approvalResponse)
    {
        FunctionCallContent placeholderCall = new(
            approvalResponse.ApprovalRequestId,
            string.Empty,
            arguments: null);
        ToolApprovalResponseContent content = new(approvalResponse.ApprovalRequestId, approvalResponse.Approve, placeholderCall)
        {
            Reason = approvalResponse.Reason
        };

        return new ChatMessage(ChatRole.User, [content]);
    }

    private static List<AIContent> ToAIContents(InputMessageContent content)
    {
        if (content.IsText)
        {
            return [new TextContent(content.Text)];
        }

        if (content.IsContents)
        {
            var result = new List<AIContent>();
            foreach (ItemContent itemContent in content.Contents!)
            {
                if (ItemContentConverter.ToAIContent(itemContent) is { } aiContent)
                {
                    result.Add(aiContent);
                }
            }

            return result;
        }

        return [];
    }

    private static Dictionary<string, object?>? ParseFunctionArgumentsObject(string? arguments)
    {
        if (string.IsNullOrWhiteSpace(arguments))
        {
            return null;
        }

        try
        {
            using var doc = JsonDocument.Parse(arguments);
            var result = new Dictionary<string, object?>();
            foreach (JsonProperty property in doc.RootElement.EnumerateObject())
            {
                result[property.Name] = property.Value.ValueKind switch
                {
                    JsonValueKind.String => property.Value.GetString(),
                    JsonValueKind.Number => property.Value.GetDouble(),
                    JsonValueKind.True => true,
                    JsonValueKind.False => false,
                    JsonValueKind.Null => null,
                    _ => property.Value.GetRawText()
                };
            }

            return result;
        }
        catch (JsonException)
        {
            return new Dictionary<string, object?> { ["_raw"] = arguments };
        }
    }

    /// <inheritdoc/>
    public bool Equals(ResponseInput? other)
    {
        if (other is null)
        {
            return false;
        }

        if (ReferenceEquals(this, other))
        {
            return true;
        }

        // Both text
        if (this.Text is not null && other.Text is not null)
        {
            return this.Text == other.Text;
        }

        // Both messages
        if (this.Messages is not null && other.Messages is not null)
        {
            return this.Messages.SequenceEqual(other.Messages);
        }

        if (this.Items is not null && other.Items is not null)
        {
            return this.Items.SequenceEqual(other.Items);
        }

        // Different input shapes are not equal.
        return false;
    }

    /// <inheritdoc/>
    public override bool Equals(object? obj) => this.Equals(obj as ResponseInput);

    /// <inheritdoc/>
    public override int GetHashCode()
    {
        if (this.Text is not null)
        {
            return this.Text.GetHashCode();
        }

        if (this.Messages is not null)
        {
            return this.Messages.Count > 0 ? this.Messages[0].GetHashCode() : 0;
        }

        if (this.Items is not null)
        {
            return this.Items.Count > 0 ? this.Items[0].GetHashCode() : 0;
        }

        return 0;
    }

    /// <summary>
    /// Equality operator.
    /// </summary>
    public static bool operator ==(ResponseInput? left, ResponseInput? right)
    {
        return Equals(left, right);
    }

    /// <summary>
    /// Inequality operator.
    /// </summary>
    public static bool operator !=(ResponseInput? left, ResponseInput? right)
    {
        return !Equals(left, right);
    }
}

/// <summary>
/// JSON converter for ResponseInput.
/// </summary>
internal sealed class ResponseInputJsonConverter : JsonConverter<ResponseInput>
{
    /// <inheritdoc/>
    public override ResponseInput? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        // Check if it's a string
        if (reader.TokenType == JsonTokenType.String)
        {
            var text = reader.GetString();
            return text is not null ? ResponseInput.FromText(text) : null;
        }

        // Check if it's an array
        if (reader.TokenType == JsonTokenType.StartArray)
        {
            using var doc = JsonDocument.ParseValue(ref reader);
            bool hasTypedItems = doc.RootElement.EnumerateArray().Any(static element =>
                element.ValueKind == JsonValueKind.Object && element.TryGetProperty("type", out _));

            if (!hasTypedItems)
            {
                var messages = doc.RootElement.Deserialize(OpenAIHostingJsonContext.Default.ListInputMessage);
                return messages is not null ? ResponseInput.FromMessages(messages) : null;
            }

            var items = new List<ItemParam>();
            foreach (JsonElement element in doc.RootElement.EnumerateArray())
            {
                if (element.ValueKind == JsonValueKind.Object && element.TryGetProperty("type", out _))
                {
                    ItemParam? item = element.Deserialize(OpenAIHostingJsonContext.Default.ItemParam);
                    if (item is not null)
                    {
                        items.Add(item);
                    }
                }
                else
                {
                    InputMessage? message = element.Deserialize(OpenAIHostingJsonContext.Default.InputMessage);
                    if (message is not null)
                    {
                        items.Add(ToItemParam(message));
                    }
                }
            }

            return ResponseInput.FromItems(items);
        }

        throw new JsonException(
            "ResponseInput must be either a string or an array of messages/input items. " +
            $"Objects are not supported. Received token type: {reader.TokenType}");
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, ResponseInput value, JsonSerializerOptions options)
    {
        if (value.IsText)
        {
            writer.WriteStringValue(value.Text);
        }
        else if (value.IsMessages)
        {
            JsonSerializer.Serialize(writer, value.Messages!, OpenAIHostingJsonContext.Default.ListInputMessage);
        }
        else if (value.IsItems)
        {
            JsonSerializer.Serialize(writer, value.Items!, OpenAIHostingJsonContext.Default.ListItemParam);
        }
        else
        {
            throw new JsonException("ResponseInput has no value");
        }
    }

    private static ItemParam ToItemParam(InputMessage message)
    {
        if (message.Role == ChatRole.User)
        {
            return new ResponsesUserMessageItemParam { Content = message.Content };
        }

        if (message.Role == ChatRole.Assistant)
        {
            return new ResponsesAssistantMessageItemParam { Content = message.Content };
        }

        if (message.Role == ChatRole.System)
        {
            return new ResponsesSystemMessageItemParam { Content = message.Content };
        }

        return new ResponsesDeveloperMessageItemParam { Content = message.Content };
    }
}
