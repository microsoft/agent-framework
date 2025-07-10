// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Text.RegularExpressions;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Provides a topic identifier that defines the scope of a broadcast message.
/// </summary>
/// <remarks>
/// The agent runtime implements a publish-subscribe model through its broadcast API,
/// where messages must be published with a specific topic.
/// </remarks>
public readonly partial struct TopicId : IEquatable<TopicId>
{
    private const string TypePattern = @"^[\w-.:=]+$";

#if NET
    [GeneratedRegex(TypePattern)]
    private static partial Regex TypeRegex();
#else
    private static Regex TypeRegex() => s_typeRegex;
    private static readonly Regex s_typeRegex = new(TypePattern, RegexOptions.Compiled);
#endif

    /// <summary>
    /// Initializes a new instance of the <see cref="TopicId"/> struct.
    /// </summary>
    /// <param name="type">The type of the topic. Must match the pattern: <c>^[\w-.:=]+$</c></param>
    /// <param name="source">The source of the event.</param>
    public TopicId(string type, string? source = null)
    {
        if (type is null)
        {
            throw new ArgumentNullException(nameof(type));
        }

        if (!TypeRegex().IsMatch(type))
        {
            throw new ArgumentException("Invalid type format.", nameof(type));
        }

        // TODO: What validation should be performed on source? The cited cloudevents spec suggests it should be a URI reference.

        this.Type = type;
        this.Source = source ?? "default";
    }

    /// <summary>
    /// Gets the type of the event that this <see cref="TopicId"/> represents.
    /// </summary>
    /// <remarks>
    /// This adheres to the CloudEvents specification.
    /// <see href="https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md#type">CloudEvents Type</see>.
    /// </remarks>
    public string Type { get; }

    /// <summary>
    /// Gets the source that identifies the context in which an event happened.
    /// </summary>
    /// <remarks>
    /// This adheres to the CloudEvents specification.
    /// <see href="https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md#source-1">CloudEvents Source</see>.
    /// </remarks>
    public string Source { get; }

    /// <summary>
    /// Convert a string of the format "type/key" into an <see cref="TopicId"/>.
    /// </summary>
    /// <param name="TopicId">The actor ID string.</param>
    /// <returns>An instance of <see cref="TopicId"/>.</returns>
    public static TopicId Parse(string TopicId)
    {
        if (!KeyValueParser.TryParse(TopicId, out string? type, out string? key))
        {
            throw new FormatException($"Invalid TopicId format: '{TopicId}'. Expected format is 'type/key'.");
        }

        return new TopicId(type, key);
    }

    /// <inheritdoc />
    public override readonly string ToString() => $"{this.Type}/{this.Source}";

    /// <inheritdoc />
    public override readonly bool Equals([NotNullWhen(true)] object? obj) =>
        obj is TopicId other && this.Equals(other);

    /// <inheritdoc/>
    public readonly bool Equals(TopicId other) =>
        this.Type == other.Type && this.Source == other.Source;

    /// <inheritdoc />
    public override readonly int GetHashCode() =>
        HashCode.Combine(this.Type, this.Source);

    /// <inheritdoc />
    public static bool operator ==(TopicId left, TopicId right) =>
        left.Equals(right);

    /// <inheritdoc />
    public static bool operator !=(TopicId left, TopicId right) =>
        !left.Equals(right);

    // TODO: Implement < for wildcard matching (type, *)
    //public readonly bool IsWildcardMatch(TopicId other)
    //{
    //    return this.Type == other.Type;
    //}
}
