// Copyright (c) Microsoft. All rights reserved.

using System.Collections;
using System.Collections.Generic;
using System.Linq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction.Internal;

/// <summary>
/// An IList&lt;T&gt; that does NOT implement IReadOnlyList&lt;T&gt;,
/// used to test the defensive <c>as IReadOnlyList&lt;T&gt; ?? fallback</c> patterns.
/// </summary>
internal sealed class NonReadOnlyList<T> : IList<T>
{
    private readonly List<T> _inner;

    public NonReadOnlyList(IEnumerable<T> items)
    {
        this._inner = items.ToList();
    }

    public T this[int index]
    {
        get => this._inner[index];
        set => this._inner[index] = value;
    }

    public int Count => this._inner.Count;
    public bool IsReadOnly => false;
    public void Add(T item) => this._inner.Add(item);
    public void Clear() => this._inner.Clear();
    public bool Contains(T item) => this._inner.Contains(item);
    public void CopyTo(T[] array, int arrayIndex) => this._inner.CopyTo(array, arrayIndex);
    public IEnumerator<T> GetEnumerator() => this._inner.GetEnumerator();
    public int IndexOf(T item) => this._inner.IndexOf(item);
    public void Insert(int index, T item) => this._inner.Insert(index, item);
    public bool Remove(T item) => this._inner.Remove(item);
    public void RemoveAt(int index) => this._inner.RemoveAt(index);
    IEnumerator IEnumerable.GetEnumerator() => this.GetEnumerator();
}
