// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;

using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

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
    /// </remarks>
    /// <typeparam name="TValue">The type to which the value should be cast or deserialized.</typeparam>
    /// <returns>The value cast or deserialized to type TValue if possible; otherwise, the default value for type TValue.</returns>
    public TValue? As<TValue>() => this.Is(out TValue? value) ? value : default;

    /// <summary>
    /// Determines whether the current value can be represented as the specified type.
    /// </summary>
    /// <typeparam name="TValue">The type to test for compatibility with the current value.</typeparam>
    /// <returns>true if the current value can be represented as type TValue; otherwise, false.</returns>
    public bool Is<TValue>() => this.Is<TValue>(out _);

    /// <summary>
    /// Determines whether the current value can be represented as the specified type.
    /// </summary>
    /// <typeparam name="TValue">The type to test for compatibility with the current value.</typeparam>
    /// <param name="value">When this method returns, contains the value cast or deserialized to type TValue
    /// if the conversion succeeded, or null if the conversion failed.</param>
    /// <returns>true if the current value can be represented as type TValue; otherwise, false.</returns>
    public bool Is<TValue>([NotNullWhen(true)] out TValue? value)
    {
        if (this.Value is IDelayedDeserialization delayedDeserialization)
        {
            this._deserializedValueCache ??= delayedDeserialization.Deserialize<TValue>();
        }

        if (this.Value is TValue typedValue)
        {
            value = typedValue;
            return true;
        }

        value = default;
        return false;
    }

    /// <summary>
    /// Attempts to retrieve the underlying value as the specified type, deserializing if necessary.
    /// </summary>
    /// <param name="targetType">The type to which the value should be cast or deserialized.</param>
    /// <returns>The value cast or deserialized to type targetType if possible; otherwise, null.</returns>
    public object? AsType(Type targetType) => this.IsType(targetType, out object? value) ? value : null;

    /// <summary>
    /// Determines whether the current instance can be assigned to the specified target type.
    /// </summary>
    /// <param name="targetType">The type to compare with the current instance. Cannot be null.</param>
    /// <returns>true if the current instance can be assigned to targetType; otherwise, false.</returns>
    public bool IsType(Type targetType) => this.IsType(targetType, out _);

    /// <summary>
    /// Determines whether the current instance can be assigned to the specified target type.
    /// </summary>
    /// <param name="targetType">The type to compare with the current instance. Cannot be null.</param>
    /// <param name="value">When this method returns, contains the value cast or deserialized to type TValue
    /// if the conversion succeeded, or null if the conversion failed.</param>
    /// <returns>true if the current instance can be assigned to targetType; otherwise, false.</returns>
    public bool IsType(Type targetType, [NotNullWhen(true)] out object? value)
    {
        Throw.IfNull(targetType);
        if (this.Value is IDelayedDeserialization delayedDeserialization)
        {
            this._deserializedValueCache ??= delayedDeserialization.Deserialize(targetType);
        }

        if (this.Value is not null && targetType.IsInstanceOfType(this.Value))
        {
            value = this.Value;
            return true;
        }

        value = null;
        return false;
    }
}
