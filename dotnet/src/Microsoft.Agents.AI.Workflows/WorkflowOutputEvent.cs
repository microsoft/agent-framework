// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when a workflow executor yields output.
/// </summary>
[JsonDerivedType(typeof(AgentResponseEvent))]
[JsonDerivedType(typeof(AgentResponseUpdateEvent))]
public class WorkflowOutputEvent : WorkflowEvent
{
    private readonly HashSet<OutputTag> _tags;

    /// <summary>
    /// Initializes a new instance of the <see cref="WorkflowOutputEvent"/> class with no tags.
    /// </summary>
    /// <param name="data">The output data.</param>
    /// <param name="executorId">The identifier of the executor that yielded this output.</param>
    public WorkflowOutputEvent(object data, string executorId) : this(data, executorId, tags: null)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="WorkflowOutputEvent"/> class carrying the
    /// given output tag.
    /// </summary>
    /// <param name="data">The output data.</param>
    /// <param name="executorId">The identifier of the executor that yielded this output.</param>
    /// <param name="tag">The single output tag to associate with this event.</param>
    public WorkflowOutputEvent(object data, string executorId, OutputTag tag) : this(data, executorId, tags: new[] { tag })
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="WorkflowOutputEvent"/> class carrying the
    /// given output tags (deduplicated).
    /// </summary>
    /// <param name="data">The output data.</param>
    /// <param name="executorId">The identifier of the executor that yielded this output.</param>
    /// <param name="tags">The output tags to associate with this event. May be <see langword="null"/> or empty (the event is then untagged).</param>
    public WorkflowOutputEvent(object data, string executorId, IEnumerable<OutputTag>? tags) : base(data)
    {
        this.ExecutorId = executorId;
        this._tags = tags is null ? new HashSet<OutputTag>() : new HashSet<OutputTag>(tags);
    }

    /// <summary>
    /// The unique identifier of the executor that yielded this output.
    /// </summary>
    public string ExecutorId { get; }

    /// <summary>
    /// The unique identifier of the executor that yielded this output.
    /// </summary>
    [Obsolete("Use ExecutorId instead.")]
    [JsonIgnore]
    public string SourceId => this.ExecutorId;

    /// <summary>
    /// The set of output tags associated with this event. Never <see langword="null"/>;
    /// empty for terminal/regular outputs. The presence of <see cref="OutputTag.Intermediate"/>
    /// marks this event as an intermediate output.
    /// </summary>
    public IEnumerable<OutputTag> Tags => this._tags;

    /// <summary>
    /// Returns <see langword="true"/> if this event carries the given tag.
    /// </summary>
    public bool HasTag(OutputTag tag) => this._tags.Contains(tag);

    /// <summary>
    /// Determines whether the underlying data is of the specified type or a derived type.
    /// </summary>
    /// <typeparam name="T">The type to compare with the type of the underlying data.</typeparam>
    /// <returns>true if the underlying data is assignable to type T; otherwise, false.</returns>
    public bool Is<T>() => this.IsType(typeof(T));

    /// <summary>
    /// Determines whether the underlying data is of the specified type or a derived type, and
    /// returns it as that type if it is.
    /// </summary>
    /// <typeparam name="T">The type to compare with the type of the underlying data.</typeparam>
    /// <returns>true if the underlying data is assignable to type T; otherwise, false.</returns>
    public bool Is<T>([NotNullWhen(true)] out T? maybeValue)
    {
        if (this.Data is T value)
        {
            maybeValue = value;
            return true;
        }

        maybeValue = default;
        return false;
    }

    /// <summary>
    /// Determines whether the underlying data is of the specified type or a derived type.
    /// </summary>
    /// <param name="type">The type to compare with the type of the underlying data.</param>
    /// <returns>true if the underlying data is assignable to type T; otherwise, false.</returns>
    public bool IsType(Type type) => this.Data is { } data && type.IsInstanceOfType(data);

    /// <summary>
    /// Attempts to retrieve the underlying data as the specified type.
    /// </summary>
    /// <typeparam name="T">The type to which to cast.</typeparam>
    /// <returns>The value of Data as to the target type.</returns>
    public T? As<T>() => this.Data is T value ? value : default;

    /// <summary>
    /// Attempts to retrieve the underlying data as the specified type.
    /// </summary>
    /// <param name="type">The type to which to cast.</param>
    /// <returns>The value of Data as to the target type.</returns>
    public object? AsType(Type type) => this.IsType(type) ? this.Data : null;
}
