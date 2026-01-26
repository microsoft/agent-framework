// Copyright (c) Microsoft. All rights reserved.

using System;
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
    /// <summary>
    /// Initializes a new instance of the <see cref="WorkflowOutputEvent"/> class.
    /// </summary>
    /// <param name="data">The output data.</param>
    /// <param name="executorId">The identifier of the executor that yielded this output.</param>
    public WorkflowOutputEvent(object data, string executorId) : base(data)
    {
        this.ExecutorId = executorId;
    }

    /// <summary>
    /// The unique identifier of the executor that yielded this output.
    /// </summary>
    public string ExecutorId { get; }

    /// <summary>
    /// The unique identifier of the executor that yielded this output.
    /// </summary>
    [Obsolete("Use ExecutorId instead.")]
    public string SourceId => this.ExecutorId;

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
