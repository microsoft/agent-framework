// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Represents a Jev entry: text, a JSON object or array, or <see langword="null"/>.
/// </summary>
/// <remarks>
/// This type mirrors <c>EntryType</c> of the official TypeSafe SDK. The state of a <see cref="JevRequest"/>, the
/// instructions of a <see cref="JevQuestion"/>, and every criterion description are entries, so each can be plain
/// text or structured data that questions refer to by field name. A <see cref="string"/> converts implicitly, a
/// <see cref="JsonElement"/> converts explicitly because a JSON number or Boolean is not an entry, and
/// <see langword="default"/> is the <see langword="null"/> entry.
/// </remarks>
[JsonConverter(typeof(JevEntryJsonConverter))]
public readonly struct JevEntry : IEquatable<JevEntry>
{
    private readonly JsonElement _value;

    /// <summary>
    /// Initializes a new instance of the <see cref="JevEntry"/> struct from JSON.
    /// </summary>
    /// <param name="value">A JSON string, object, array, or null.</param>
    /// <exception cref="ArgumentException"><paramref name="value"/> is a JSON number or Boolean.</exception>
    public JevEntry(JsonElement value)
    {
        if (value.ValueKind is not (JsonValueKind.String or JsonValueKind.Object or JsonValueKind.Array or JsonValueKind.Null or JsonValueKind.Undefined))
        {
            Throw.ArgumentException(nameof(value), "A Jev entry must be text, a JSON object or array, or null.");
        }

        // Cloning detaches the value from the document it came from, which may be disposed after this call.
        this._value = value.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined ? default : value.Clone();
    }

    /// <summary>
    /// Gets the <see langword="null"/> entry, which leaves a criterion undescribed.
    /// </summary>
    public static JevEntry Null => default;

    /// <summary>
    /// Gets the kind of the entry: <see cref="JsonValueKind.String"/>, <see cref="JsonValueKind.Object"/>,
    /// <see cref="JsonValueKind.Array"/>, or <see cref="JsonValueKind.Null"/>.
    /// </summary>
    public JsonValueKind Kind => this._value.ValueKind == JsonValueKind.Undefined ? JsonValueKind.Null : this._value.ValueKind;

    /// <summary>
    /// Gets a value indicating whether the entry is <see langword="null"/>.
    /// </summary>
    public bool IsNull => this.Kind == JsonValueKind.Null;

    /// <summary>
    /// Gets the text of an entry whose <see cref="Kind"/> is <see cref="JsonValueKind.String"/>, or <see langword="null"/> otherwise.
    /// </summary>
    public string? Text => this.Kind == JsonValueKind.String ? this._value.GetString() : null;

    /// <summary>
    /// Gets the entry as JSON, or <see langword="null"/> for the <see langword="null"/> entry.
    /// </summary>
    public JsonElement? Json => this.IsNull ? null : this._value;

    /// <summary>
    /// Creates an entry from text.
    /// </summary>
    /// <param name="text">The text, or <see langword="null"/> for the <see langword="null"/> entry.</param>
    /// <returns>The entry.</returns>
    public static JevEntry FromString(string? text) =>
        text is null ? default : new JevEntry(JsonSerializer.SerializeToElement(text, JevJsonContext.Default.String));

    /// <summary>
    /// Creates an entry from JSON.
    /// </summary>
    /// <param name="value">A JSON string, object, array, or null.</param>
    /// <returns>The entry.</returns>
    public static JevEntry FromJsonElement(JsonElement value) => new(value);

    /// <summary>
    /// Converts text to an entry.
    /// </summary>
    /// <param name="text">The text, or <see langword="null"/> for the <see langword="null"/> entry.</param>
    public static implicit operator JevEntry(string? text) => FromString(text);

    /// <summary>
    /// Converts JSON to an entry.
    /// </summary>
    /// <param name="value">A JSON string, object, array, or null.</param>
    /// <exception cref="ArgumentException"><paramref name="value"/> is a JSON number or Boolean.</exception>
    /// <remarks>
    /// The conversion is explicit because it fails for JSON numbers and Booleans, which are not entries.
    /// </remarks>
    public static explicit operator JevEntry(JsonElement value) => FromJsonElement(value);

    /// <summary>Determines whether two entries have the same JSON value.</summary>
    /// <param name="left">The first entry.</param>
    /// <param name="right">The second entry.</param>
    /// <returns><see langword="true"/> when the entries are equal.</returns>
    public static bool operator ==(JevEntry left, JevEntry right) => left.Equals(right);

    /// <summary>Determines whether two entries have different JSON values.</summary>
    /// <param name="left">The first entry.</param>
    /// <param name="right">The second entry.</param>
    /// <returns><see langword="true"/> when the entries differ.</returns>
    public static bool operator !=(JevEntry left, JevEntry right) => !left.Equals(right);

    /// <inheritdoc />
    public bool Equals(JevEntry other) =>
        this.Kind == other.Kind && (this.IsNull || JsonElement.DeepEquals(this._value, other._value));

    /// <inheritdoc />
    public override bool Equals(object? obj) => obj is JevEntry other && this.Equals(other);

    /// <inheritdoc />
    /// <remarks>
    /// Objects are equal regardless of property order, so only the kind (and the text of a string) is hashed.
    /// </remarks>
    public override int GetHashCode() =>
        this.Kind == JsonValueKind.String
            ? HashCode.Combine(this.Kind, this._value.GetString())
            : this.Kind.GetHashCode();

    /// <summary>
    /// Returns the text of a string entry, the JSON of an object or array entry, or an empty string for the
    /// <see langword="null"/> entry.
    /// </summary>
    /// <returns>The entry as a string.</returns>
    public override string ToString() =>
        this.Kind switch
        {
            JsonValueKind.String => this._value.GetString()!,
            JsonValueKind.Null => string.Empty,
            _ => this._value.GetRawText(),
        };
}
