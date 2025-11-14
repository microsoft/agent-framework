// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Represents the content of an input message, which can be either a simple string or a list of ItemContent items.
/// Aligns with the OpenAI typespec: string | InputContent[]
/// </summary>
[JsonConverter(typeof(InputMessageContentJsonConverter))]
internal sealed class InputMessageContent : IEquatable<InputMessageContent>
{
    private InputMessageContent(string text)
    {
        this.Text = text ?? throw new ArgumentNullException(nameof(text));
        this.Contents = null;
    }

    private InputMessageContent(List<ItemContent> contents)
    {
        this.Contents = contents ?? throw new ArgumentNullException(nameof(contents));
        this.Text = null;
    }

    /// <summary>
    /// Creates an InputMessageContent from a text string.
    /// </summary>
    public static InputMessageContent FromText(string text) => new(text);

    /// <summary>
    /// Creates an InputMessageContent from a list of ItemContent items.
    /// </summary>
    public static InputMessageContent FromContents(List<ItemContent> contents) => new(contents);

    /// <summary>
    /// Creates an InputMessageContent from a list of ItemContent items.
    /// </summary>
    public static InputMessageContent FromContents(params ItemContent[] contents) => new([.. contents]);

    /// <summary>
    /// Implicit conversion from string to InputMessageContent.
    /// </summary>
    public static implicit operator InputMessageContent(string text) => FromText(text);

    /// <summary>
    /// Implicit conversion from ItemContent array to InputMessageContent.
    /// </summary>
    public static implicit operator InputMessageContent(ItemContent[] contents) => FromContents(contents);

    /// <summary>
    /// Implicit conversion from List to InputMessageContent.
    /// </summary>
    public static implicit operator InputMessageContent(List<ItemContent> contents) => FromContents(contents);

    /// <summary>
    /// Gets whether this content is text.
    /// </summary>
    [MemberNotNullWhen(true, nameof(Text))]
    [MemberNotNullWhen(false, nameof(Contents))]
    public bool IsText => this.Text is not null;

    /// <summary>
    /// Gets whether this content is a list of ItemContent items.
    /// </summary>
    [MemberNotNullWhen(true, nameof(Contents))]
    [MemberNotNullWhen(false, nameof(Text))]
    public bool IsContents => this.Contents is not null;

    /// <summary>
    /// Gets the text value, or null if this is not text content.
    /// </summary>
    public string? Text { get; }

    /// <summary>
    /// Gets the ItemContent items, or null if this is not a content list.
    /// </summary>
    public List<ItemContent>? Contents { get; }

    /// <inheritdoc/>
    public bool Equals(InputMessageContent? other)
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

        // Both contents
        if (this.Contents is not null && other.Contents is not null)
        {
            return this.Contents.SequenceEqual(other.Contents);
        }

        // One is text, one is contents - not equal
        return false;
    }

    /// <inheritdoc/>
    public override bool Equals(object? obj) => this.Equals(obj as InputMessageContent);

    /// <inheritdoc/>
    public override int GetHashCode()
    {
        if (this.Text is not null)
        {
            return this.Text.GetHashCode();
        }

        if (this.Contents is not null)
        {
            return this.Contents.Count > 0 ? this.Contents[0].GetHashCode() : 0;
        }

        return 0;
    }

    /// <summary>
    /// Equality operator.
    /// </summary>
    public static bool operator ==(InputMessageContent? left, InputMessageContent? right)
    {
        return Equals(left, right);
    }

    /// <summary>
    /// Inequality operator.
    /// </summary>
    public static bool operator !=(InputMessageContent? left, InputMessageContent? right)
    {
        return !Equals(left, right);
    }

    /// <summary>
    /// Converts this instance to a list of ItemContent.
    /// </summary>
    public List<ItemContent> ToItemContents()
    {
        return this.IsText
            ? [new ItemContentInputText { Text = this.Text }]
            : this.Contents;
    }
}

/// <summary>
/// JSON converter for <see cref="InputMessageContent"/>.
/// </summary>
internal sealed class InputMessageContentJsonConverter : JsonConverter<InputMessageContent>
{
    /// <inheritdoc/>
    public override InputMessageContent? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        // Check if it's a string
        if (reader.TokenType == JsonTokenType.String)
        {
            var text = reader.GetString();
            return text is not null ? InputMessageContent.FromText(text) : null;
        }

        // Check if it's an array of ItemContent
        if (reader.TokenType == JsonTokenType.StartArray)
        {
            var contents = JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.ListItemContent);
            return contents?.Count > 0
                ? InputMessageContent.FromContents(contents)
                : InputMessageContent.FromText(string.Empty);
        }

        throw new JsonException($"Unexpected token type for InputMessageContent: {reader.TokenType}");
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, InputMessageContent value, JsonSerializerOptions options)
    {
        if (value.IsText)
        {
            writer.WriteStringValue(value.Text);
        }
        else if (value.IsContents)
        {
            JsonSerializer.Serialize(writer, value.Contents, OpenAIHostingJsonContext.Default.ListItemContent);
        }
        else
        {
            throw new JsonException("InputMessageContent has no value");
        }
    }
}
