// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
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
    private static readonly KeyComparer s_featureKeyComparer = new();
    private readonly IAgentFeatureCollection? _defaults;
    private readonly int _initialCapacity;
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

        this._initialCapacity = initialCapacity;
    }

    /// <summary>
    /// Initializes a new instance of <see cref="AgentFeatureCollection"/> with the specified defaults.
    /// </summary>
    /// <param name="defaults">The feature defaults.</param>
    public AgentFeatureCollection(IAgentFeatureCollection defaults)
    {
        this._defaults = defaults;
    }

    /// <inheritdoc />
    public virtual int Revision
    {
        get { return this._containerRevision + (this._defaults?.Revision ?? 0); }
    }

    /// <inheritdoc />
    public bool IsReadOnly { get { return false; } }

    /// <inheritdoc />
    public object? this[Type key]
    {
        get
        {
            Throw.IfNull(key);

            return this._features != null && this._features.TryGetValue(key, out var result) ? result : this._defaults?[key];
        }
        set
        {
            Throw.IfNull(key);

            if (value == null)
            {
                if (this._features?.Remove(key) is true)
                {
                    this._containerRevision++;
                }
                return;
            }

            if (this._features == null)
            {
                this._features = new Dictionary<Type, object>(this._initialCapacity);
            }
            this._features[key] = value;
            this._containerRevision++;
        }
    }

    IEnumerator IEnumerable.GetEnumerator()
    {
        return this.GetEnumerator();
    }

    /// <inheritdoc />
    public IEnumerator<KeyValuePair<Type, object>> GetEnumerator()
    {
        if (this._features != null)
        {
            foreach (var pair in this._features)
            {
                yield return pair;
            }
        }

        if (this._defaults != null)
        {
            // Don't return features masked by the wrapper.
            foreach (var pair in this._features == null ? this._defaults : this._defaults.Except(this._features, s_featureKeyComparer))
            {
                yield return pair;
            }
        }
    }

    /// <inheritdoc />
    public TFeature? Get<TFeature>()
    {
        if (typeof(TFeature).IsValueType)
        {
            var feature = this[typeof(TFeature)];
            if (feature is null && Nullable.GetUnderlyingType(typeof(TFeature)) is null)
            {
                throw new InvalidOperationException(
                    $"{typeof(TFeature).FullName} does not exist in the feature collection " +
                    $"and because it is a struct the method can't return null. Use 'AgentFeatureCollection[typeof({typeof(TFeature).FullName})] is not null' to check if the feature exists.");
            }
            return (TFeature?)feature;
        }
        return (TFeature?)this[typeof(TFeature)];
    }

    /// <inheritdoc />
    public void Set<TFeature>(TFeature? instance)
    {
        this[typeof(TFeature)] = instance;
    }

    // Used by the debugger. Count over enumerable is required to get the correct value.
    private int GetCount() => this.Count();

    private sealed class KeyComparer : IEqualityComparer<KeyValuePair<Type, object>>
    {
        public bool Equals(KeyValuePair<Type, object> x, KeyValuePair<Type, object> y)
        {
            return x.Key.Equals(y.Key);
        }

        public int GetHashCode(KeyValuePair<Type, object> obj)
        {
            return obj.Key.GetHashCode();
        }
    }

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
