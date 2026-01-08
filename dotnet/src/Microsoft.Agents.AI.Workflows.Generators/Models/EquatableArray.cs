// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Collections.Immutable;

namespace Microsoft.Agents.AI.Workflows.Generators.Models;

/// <summary>
/// A wrapper around <see cref="ImmutableArray{T}"/> that provides value-based equality.
/// This is necessary for incremental generator caching since ImmutableArray uses reference equality.
/// </summary>
/// <remarks>
/// Creates a new <see cref="EquatableArray{T}"/> from an <see cref="ImmutableArray{T}"/>.
/// </remarks>
internal readonly struct EquatableArray<T>(ImmutableArray<T> array) : IEquatable<EquatableArray<T>>, IEnumerable<T>
    where T : IEquatable<T>
{
    private readonly ImmutableArray<T> _array = array.IsDefault ? ImmutableArray<T>.Empty : array;

    /// <summary>
    /// Gets the underlying array.
    /// </summary>
    public ImmutableArray<T> AsImmutableArray() => this._array;

    /// <summary>
    /// Gets the number of elements in the array.
    /// </summary>
    public int Length => this._array.Length;

    /// <summary>
    /// Gets the element at the specified index.
    /// </summary>
    public T this[int index] => this._array[index];

    /// <summary>
    /// Gets whether the array is empty.
    /// </summary>
    public bool IsEmpty => this._array.IsEmpty;

    /// <inheritdoc/>
    public bool Equals(EquatableArray<T> other)
    {
        if (this._array.Length != other._array.Length)
        {
            return false;
        }

        for (int i = 0; i < this._array.Length; i++)
        {
            if (!this._array[i].Equals(other._array[i]))
            {
                return false;
            }
        }

        return true;
    }

    /// <inheritdoc/>
    public override bool Equals(object? obj)
    {
        return obj is EquatableArray<T> other && this.Equals(other);
    }

    /// <inheritdoc/>
    public override int GetHashCode()
    {
        if (this._array.IsEmpty)
        {
            return 0;
        }

        var hashCode = 17;
        foreach (var item in this._array)
        {
            hashCode = hashCode * 31 + (item?.GetHashCode() ?? 0);
        }

        return hashCode;
    }

    /// <inheritdoc/>
    public IEnumerator<T> GetEnumerator()
    {
        return ((IEnumerable<T>)this._array).GetEnumerator();
    }

    /// <inheritdoc/>
    IEnumerator IEnumerable.GetEnumerator()
    {
        return this.GetEnumerator();
    }

    /// <summary>
    /// Equality operator.
    /// </summary>
    public static bool operator ==(EquatableArray<T> left, EquatableArray<T> right)
    {
        return left.Equals(right);
    }

    /// <summary>
    /// Inequality operator.
    /// </summary>
    public static bool operator !=(EquatableArray<T> left, EquatableArray<T> right)
    {
        return !left.Equals(right);
    }

    /// <summary>
    /// Creates an empty <see cref="EquatableArray{T}"/>.
    /// </summary>
    public static EquatableArray<T> Empty => new(ImmutableArray<T>.Empty);

    /// <summary>
    /// Implicit conversion from <see cref="ImmutableArray{T}"/>.
    /// </summary>
    public static implicit operator EquatableArray<T>(ImmutableArray<T> array) => new(array);
}
