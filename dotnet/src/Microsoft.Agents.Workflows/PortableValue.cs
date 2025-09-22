// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;

using Microsoft.Agents.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a value that can be exported / imported to a workflow, e.g. through an external request/response, or
/// through checkpointing. Abstracts away delayed deserialization and type conversion where appropriate.
/// </summary>
public sealed class PortableValue
{
    internal PortableValue(object value)
    {
        this._value = value;
        this.TypeId = new(value.GetType());
    }

    [JsonConstructor]
    internal PortableValue(TypeId typeId, object value)
    {
        this.TypeId = Throw.IfNull(typeId);
        this._value = value;
    }

    /// <inheritdoc />
    public override bool Equals(object? obj)
    {
        if (obj is null)
        {
            return false;
        }

        if (obj is not PortableValue other)
        {
            Type targetType = obj.GetType();
            return this.AsType(targetType)?.Equals(obj) is true;
        }

        return this.TypeId == other.TypeId
            && ((this.Value is null && other.Value is null)
                 || this.Value?.Equals(other.Value) is true);
    }

    /// <inheritdoc />
    public override int GetHashCode()
    {
        return HashCode.Combine(this.TypeId, this.Value);
    }

    /// <inheritdoc />
    public static bool operator ==(PortableValue? left, PortableValue? right)
    {
        if (left is null)
        {
            return right is null;
        }

        return left.Equals(right);
    }

    /// <inheritdoc />
    public static bool operator !=(PortableValue? left, PortableValue? right) => !(left == right);

    /// <summary>
    /// The identifier of the type of the instance in <see cref="Value"/>.
    /// </summary>
    public TypeId TypeId { get; }

    [JsonIgnore]
    internal bool IsDelayedDeserialization => this.Value is IDelayedDeserialization;

    [JsonIgnore]
    internal bool IsDeserialized => this._deserializedValueCache is not null;

    private readonly object _value;
    private object? _deserializedValueCache;

    /// <summary>
    /// Gets the raw underlying value represented by this instance.
    /// </summary>
    [JsonInclude]
    internal object Value => this._deserializedValueCache ?? Throw.IfNull(this._value);

    /// <summary>
    /// Attempts to retrieve the underlying value as the specified type, deserializing if necessary.
    /// </summary>
    /// <remarks>If the underlying value implements delayed deserialization, this method will attempt to
    /// deserialize it to the specified type. If the value is already of the requested type, it is returned directly.
    /// Otherwise, the default value for TValue is returned.
    ///
    /// For nullable value types, make sure to make <typeparamref name="TValue"/> be nullable, e.g. <c>int?</c>,
    /// otherwise the default non-null value of the type is returned when the value is missing. Use <see cref="AsValue{TValue}"/>
    /// to get the correct behavior when unable to pass in the explicit-nullable type.
    /// </remarks>
    /// <typeparam name="TValue">The type to which the value should be cast or deserialized.</typeparam>
    /// <returns>The value cast or deserialized to type TValue if possible; otherwise, the default value for type TValue.</returns>
    public TValue? As<TValue>()
    {
        if (this.Value is IDelayedDeserialization delayedDeserialization)
        {
            this._deserializedValueCache ??= delayedDeserialization.Deserialize<TValue>();
        }

        if (this.Value is TValue typedValue)
        {
            return typedValue;
        }

        return default;
    }

    /// <summary>
    /// Attempts to retrieve the underlying value as the specified nullable value type, deserializing if
    /// necessary.
    /// </summary>
    /// <remarks>If the underlying value implements delayed deserialization, this method will attempt to
    /// deserialize it to the specified type. If the value is already of the requested type, it is returned directly.
    /// Otherwise, null is returned.</remarks>
    /// <typeparam name="TValue">The value type to which the value should be cast or deserialized.</typeparam>
    /// <returns>The value cast or deserialized to type TValue if possible; otherwise, null.</returns>
    public TValue? AsValue<TValue>() where TValue : struct
    {
        if (this.Value is IDelayedDeserialization delayedDeserialization)
        {
            this._deserializedValueCache ??= delayedDeserialization.Deserialize<TValue>();
        }

        if (this.Value is TValue typedValue)
        {
            return typedValue;
        }

        return default;
    }

    /// <summary>
    /// Determines whether the current value can be represented as the specified type.
    /// </summary>
    /// <typeparam name="TValue">The type to test for compatibility with the current value.</typeparam>
    /// <returns>true if the current value can be represented as type TValue; otherwise, false.</returns>
    public bool Is<TValue>() => this.IsType(typeof(TValue));

    /// <summary>
    /// Attempts to retrieve the underlying value as the specified type, deserializing if necessary.
    /// </summary>
    /// <param name="targetType">The type to which the value should be cast or deserialized.</param>
    /// <returns>The value cast or deserialized to type targetType if possible; otherwise, null.</returns>
    public object? AsType(Type targetType)
    {
        Throw.IfNull(targetType);

        if (this.Value is IDelayedDeserialization delayedDeserialization)
        {
            this._deserializedValueCache ??= delayedDeserialization.Deserialize(targetType);
        }

        return this.Value is not null && targetType.IsAssignableFrom(this.Value.GetType())
            ? this.Value
            : this._deserializedValueCache = null;
    }

    /// <summary>
    /// Determines whether the current instance can be assigned to the specified target type.
    /// </summary>
    /// <param name="targetType">The type to compare with the current instance. Cannot be null.</param>
    /// <returns>true if the current instance can be assigned to targetType; otherwise, false.</returns>
    public bool IsType(Type targetType) => this.AsType(targetType) is not null;
}
