// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;

/// <summary>
/// Represents stop sequences for chat completion generation.
/// Up to 4 sequences where the API will stop generating further tokens.
/// </summary>
[JsonConverter(typeof(StopSequencesConverter))]
internal sealed record StopSequences : IEquatable<StopSequences>
{
    private StopSequences(string singleSequence)
    {
        this.SingleSequence = singleSequence ?? throw new ArgumentNullException(nameof(singleSequence));
        this.Sequences = null;
    }

    private StopSequences(IList<string> sequences)
    {
        if (sequences is null || sequences.Count == 0)
        {
            throw new ArgumentException("Sequences cannot be null or empty.", nameof(sequences));
        }

        if (sequences.Count > 4)
        {
            throw new ArgumentException("Maximum of 4 stop sequences are allowed.", nameof(sequences));
        }

        this.Sequences = sequences;
        this.SingleSequence = null;
    }

    /// <summary>
    /// Creates a StopSequences from a single stop sequence string.
    /// </summary>
    public static StopSequences FromString(string sequence) => new(sequence);

    /// <summary>
    /// Creates a StopSequences from a list of stop sequences.
    /// </summary>
    public static StopSequences FromSequences(IList<string> sequences) => new(sequences);

    /// <summary>
    /// Implicit conversion from string to StopSequences.
    /// </summary>
    public static implicit operator StopSequences(string sequence) => FromString(sequence);

    /// <summary>
    /// Implicit conversion from string array to StopSequences.
    /// </summary>
    public static implicit operator StopSequences(string[] sequences) => FromSequences(sequences);

    /// <summary>
    /// Implicit conversion from List to StopSequences.
    /// </summary>
    public static implicit operator StopSequences(List<string> sequences) => FromSequences(sequences);

    /// <summary>
    /// Gets whether this is a single stop sequence.
    /// </summary>
    [MemberNotNullWhen(true, nameof(SingleSequence))]
    public bool IsSingleSequence => this.SingleSequence is not null;

    /// <summary>
    /// Gets whether this contains multiple stop sequences.
    /// </summary>
    [MemberNotNullWhen(true, nameof(Sequences))]
    public bool IsSequences => this.Sequences is not null;

    /// <summary>
    /// Gets the single stop sequence, or null if this contains multiple sequences.
    /// </summary>
    public string? SingleSequence { get; }

    /// <summary>
    /// Gets the list of stop sequences, or null if this is a single sequence.
    /// </summary>
    public IList<string>? Sequences { get; }

    public IList<string> SequenceList =>
        this.IsSingleSequence ? [this.SingleSequence] :
        this.IsSequences ? this.Sequences : [];

    /// <inheritdoc/>
    public bool Equals(StopSequences? other)
    {
        if (other is null)
        {
            return false;
        }

        if (ReferenceEquals(this, other))
        {
            return true;
        }

        // Both single sequences
        if (this.SingleSequence is not null && other.SingleSequence is not null)
        {
            return this.SingleSequence == other.SingleSequence;
        }

        // Both sequences
        if (this.Sequences is not null && other.Sequences is not null)
        {
            return this.Sequences.SequenceEqual(other.Sequences);
        }

        // One is single, one is sequences - not equal
        return false;
    }

    /// <inheritdoc/>
    public override int GetHashCode()
    {
        if (this.SingleSequence is not null)
        {
            return this.SingleSequence.GetHashCode();
        }

        if (this.Sequences is not null)
        {
            return this.Sequences.Count > 0 ? this.Sequences[0].GetHashCode() : 0;
        }

        return 0;
    }
}

/// <summary>
/// JSON converter for <see cref="StopSequences"/> that handles string, array, and null representations.
/// </summary>
internal sealed class StopSequencesConverter : JsonConverter<StopSequences>
{
    /// <inheritdoc/>
    public override StopSequences? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        // Handle null
        if (reader.TokenType == JsonTokenType.Null)
        {
            return null;
        }

        // Handle single string
        if (reader.TokenType == JsonTokenType.String)
        {
            string? sequence = reader.GetString();
            return sequence is not null ? StopSequences.FromString(sequence) : null;
        }

        // Handle array of strings
        if (reader.TokenType == JsonTokenType.StartArray)
        {
            var sequences = JsonSerializer.Deserialize(ref reader, ChatCompletionsJsonContext.Default.IListString);
            return sequences?.Count > 0
                ? StopSequences.FromSequences(sequences)
                : StopSequences.FromString(string.Empty);
        }

        throw new JsonException($"Unexpected token type '{reader.TokenType}' when deserializing StopSequences. Expected String, StartArray, or Null.");
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, StopSequences? value, JsonSerializerOptions options)
    {
        if (value is null)
        {
            writer.WriteNullValue();
            return;
        }

        if (value.IsSingleSequence)
        {
            writer.WriteStringValue(value.SingleSequence);
        }
        else if (value.IsSequences)
        {
            JsonSerializer.Serialize(writer, value.Sequences, ChatCompletionsJsonContext.Default.IReadOnlyListMessageContentPart);
        }
        else
        {
            writer.WriteNullValue();
        }
    }
}
