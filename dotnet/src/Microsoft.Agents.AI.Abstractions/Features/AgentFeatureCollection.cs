// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

#pragma warning disable CA1043 // Use Integral Or String Argument For Indexers

/// <summary>
/// Default implementation for <see cref="IAgentFeatureCollection"/>.
/// </summary>
[DebuggerDisplay("Count = {GetCount()}")]
[DebuggerTypeProxy(typeof(FeatureCollectionDebugView))]
public class AgentFeatureCollection : IAgentFeatureCollection
{
    private readonly IAgentFeatureCollection? _innerCollection;
    private Dictionary<Type, object>? _features;
    private volatile int _containerRevision;

    /// <summary>
    /// Initializes a new instance of <see cref="AgentFeatureCollection"/>.
    /// </summary>
    public AgentFeatureCollection()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="AgentFeatureCollection"/> with the specified initial capacity.
    /// </summary>
    /// <param name="initialCapacity">The initial number of elements that the collection can contain.</param>
    /// <exception cref="ArgumentOutOfRangeException"><paramref name="initialCapacity"/> is less than 0</exception>
    public AgentFeatureCollection(int initialCapacity)
    {
        Throw.IfLessThan(initialCapacity, 0);
        this._features = new(initialCapacity);
    }

    /// <summary>
    /// Initializes a new instance of <see cref="AgentFeatureCollection"/> with the specified inner collection.
    /// </summary>
    /// <param name="innerCollection">The inner collection.</param>
    /// <remarks>
    /// <para>
    /// When providing an inner collection, and if a feature is not found in this collection,
    /// an attempt will be made to retrieve it from the inner collection as a fallback.
    /// </para>
    /// <para>
    /// The <see cref="Remove{TFeature}"/> method will only remove features from this collection
    /// and not from the inner collection. When removing a feature from this collection, and
    /// it exists in the inner collection, it will still be retrievable from the inner collection.
    /// </para>
    /// </remarks>
    public AgentFeatureCollection(IAgentFeatureCollection innerCollection)
    {
        this._innerCollection = Throw.IfNull(innerCollection);
    }

    /// <inheritdoc />
    public int Revision
    {
        get { return this._containerRevision + (this._innerCollection?.Revision ?? 0); }
    }

    /// <inheritdoc />
    public bool IsReadOnly { get { return false; } }

    IEnumerator IEnumerable.GetEnumerator()
    {
        return this.GetEnumerator();
    }

    /// <inheritdoc />
    public IEnumerator<KeyValuePair<Type, object>> GetEnumerator()
    {
        if (this._features is not { Count: > 0 })
        {
            IEnumerable<KeyValuePair<Type, object>> e = ((IEnumerable<KeyValuePair<Type, object>>?)this._innerCollection) ?? [];
            return e.GetEnumerator();
        }

        if (this._innerCollection is null)
        {
            return this._features.GetEnumerator();
        }

        if (this._innerCollection is AgentFeatureCollection innerCollection && innerCollection._features is not { Count: > 0 })
        {
            return this._features.GetEnumerator();
        }

        return YieldAll();

        IEnumerator<KeyValuePair<Type, object>> YieldAll()
        {
            HashSet<Type> set = [];

            foreach (var entry in this._features)
            {
                set.Add(entry.Key);
                yield return entry;
            }

            foreach (var entry in this._innerCollection.Where(x => !set.Contains(x.Key)))
            {
                yield return entry;
            }
        }
    }

    /// <inheritdoc />
    public bool TryGet<TFeature>([MaybeNullWhen(false)] out TFeature feature)
        where TFeature : notnull
    {
        if (this.TryGet(typeof(TFeature), out var obj))
        {
            feature = (TFeature)obj;
            return true;
        }

        feature = default;
        return false;
    }

    /// <inheritdoc />
    public bool TryGet(Type type, [MaybeNullWhen(false)] out object feature)
    {
        if (this._features?.TryGetValue(type, out var obj) is true)
        {
            feature = obj;
            return true;
        }

        if (this._innerCollection?.TryGet(type, out var defaultFeature) is true)
        {
            feature = defaultFeature;
            return true;
        }

        feature = default;
        return false;
    }

    /// <inheritdoc />
    public void Set<TFeature>(TFeature instance)
        where TFeature : notnull
    {
        Throw.IfNull(instance);

        this._features ??= new();
        this._features[typeof(TFeature)] = instance;
        this._containerRevision++;
    }

    /// <inheritdoc />
    public void Remove<TFeature>()
        where TFeature : notnull
        => this.Remove(typeof(TFeature));

    /// <inheritdoc />
    public void Remove(Type type)
    {
        if (this._features?.Remove(type) is true)
        {
            this._containerRevision++;
        }
    }

    // Used by the debugger. Count over enumerable is required to get the correct value.
    private int GetCount() => this.Count();

    private sealed class FeatureCollectionDebugView(AgentFeatureCollection features)
    {
        private readonly AgentFeatureCollection _features = features;

        [DebuggerBrowsable(DebuggerBrowsableState.RootHidden)]
        public DictionaryItemDebugView<Type, object>[] Items => this._features.Select(pair => new DictionaryItemDebugView<Type, object>(pair)).ToArray();
    }

    /// <summary>
    /// Defines a key/value pair for displaying an item of a dictionary by a debugger.
    /// </summary>
    [DebuggerDisplay("{Value}", Name = "[{Key}]")]
    internal readonly struct DictionaryItemDebugView<TKey, TValue>
    {
        public DictionaryItemDebugView(TKey key, TValue value)
        {
            this.Key = key;
            this.Value = value;
        }

        public DictionaryItemDebugView(KeyValuePair<TKey, TValue> keyValue)
        {
            this.Key = keyValue.Key;
            this.Value = keyValue.Value;
        }

        [DebuggerBrowsable(DebuggerBrowsableState.Collapsed)]
        public TKey Key { get; }

        [DebuggerBrowsable(DebuggerBrowsableState.Collapsed)]
        public TValue Value { get; }
    }
}
