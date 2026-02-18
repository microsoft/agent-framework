// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when a workflow executor yields output.
/// </summary>
public sealed class WorkflowOutputEvent : WorkflowEvent
{
    internal WorkflowOutputEvent(object data, string sourceId) : base(data)
    {
        this.SourceId = sourceId;
    }

    /// <summary>
    /// The unique identifier of the executor that yielded this output.
    /// </summary>
    public string SourceId { get; }

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
