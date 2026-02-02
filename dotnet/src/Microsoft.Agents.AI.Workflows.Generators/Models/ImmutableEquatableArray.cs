// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;

namespace Microsoft.Agents.AI.Workflows.Generators.Models;

/// <summary>
/// Provides an immutable list implementation which implements sequence equality.
/// Copied from: https://github.com/dotnet/runtime/blob/main/src/libraries/Common/src/SourceGenerators/ImmutableEquatableArray.cs
/// </summary>
internal sealed class ImmutableEquatableArray<T> : IEquatable<ImmutableEquatableArray<T>>, IReadOnlyList<T>
    where T : IEquatable<T>
{
    /// <summary>
    /// Creates a new empty <see cref="ImmutableEquatableArray{T}"/>.
    /// </summary>
    public static ImmutableEquatableArray<T> Empty { get; } = new ImmutableEquatableArray<T>(Array.Empty<T>());

    private readonly T[] _values;

    /// <summary>
    /// Gets the element at the specified index.
    /// </summary>
    /// <param name="index"></param>
    /// <returns></returns>
    public T this[int index] => this._values[index];

    /// <summary>
    /// Gets the number of elements contained in the collection.
    /// </summary>
    public int Count => this._values.Length;

    /// <summary>
    /// Gets whether the array is empty.
    /// </summary>
    public bool IsEmpty => this._values.Length == 0;

    /// <summary>
    /// Initializes a new instance of the ImmutableEquatableArray{T} class that contains the elements from the specified
    /// collection.
    /// </summary>
    /// <remarks>The elements from the provided collection are copied into the immutable array. Subsequent
    /// changes to the original collection do not affect the contents of this array.</remarks>
    /// <param name="values">The collection of elements to initialize the array with. Cannot be null.</param>
    public ImmutableEquatableArray(IEnumerable<T> values) => this._values = values.ToArray();

    /// <inheritdoc/>
    public bool Equals(ImmutableEquatableArray<T>? other) => other != null && ((ReadOnlySpan<T>)this._values).SequenceEqual(other._values);

    /// <inheritdoc/>
    public override bool Equals(object? obj)
        => obj is ImmutableEquatableArray<T> other && this.Equals(other);

    /// <inheritdoc/>
    public override int GetHashCode()
    {
        int hash = 0;
        foreach (T value in this._values)
        {
            hash = HashHelpers.Combine(hash, value is null ? 0 : value.GetHashCode());
        }

        return hash;
    }

    /// <inheritdoc/>
    public Enumerator GetEnumerator() => new(this._values);

    IEnumerator<T> IEnumerable<T>.GetEnumerator() => ((IEnumerable<T>)this._values).GetEnumerator();

    IEnumerator IEnumerable.GetEnumerator() => this._values.GetEnumerator();

    /// <inheritdoc/>
    public struct Enumerator
    {
        private readonly T[] _values;
        private int _index;

        internal Enumerator(T[] values)
        {
            this._values = values;
            this._index = -1;
        }

        /// <inheritdoc/>
        public bool MoveNext()
        {
            int newIndex = this._index + 1;

            if ((uint)newIndex < (uint)this._values.Length)
            {
                this._index = newIndex;
                return true;
            }

            return false;
        }

        /// <summary>
        /// The element at the current position of the enumerator.
        /// </summary>
        public readonly T Current => this._values[this._index];
    }
}

internal static class ImmutableEquatableArray
{
    public static ImmutableEquatableArray<T> ToImmutableEquatableArray<T>(this IEnumerable<T> values) where T : IEquatable<T>
        => new(values);
}

// Copied from https://github.com/dotnet/runtime/blob/main/src/libraries/System.Private.CoreLib/src/System/Numerics/Hashing/HashHelpers.cs#L6
internal static class HashHelpers
{
    public static int Combine(int h1, int h2)
    {
        // RyuJIT optimizes this to use the ROL instruction
        // Related GitHub pull request: https://github.com/dotnet/coreclr/pull/1830
        uint rol5 = ((uint)h1 << 5) | ((uint)h1 >> 27);
        return ((int)rol5 + h1) ^ h2;
    }
}
