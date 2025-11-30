// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.AI;

#pragma warning disable CA1043 // Use Integral Or String Argument For Indexers
#pragma warning disable CA1716 // Identifiers should not match keywords

/// <summary>
/// Represents a collection of Agent features.
/// </summary>
public interface IAgentFeatureCollection : IEnumerable<KeyValuePair<Type, object>>
{
    /// <summary>
    /// Indicates if the collection can be modified.
    /// </summary>
    bool IsReadOnly { get; }

    /// <summary>
    /// Incremented for each modification and can be used to verify cached results.
    /// </summary>
    int Revision { get; }

    /// <summary>
    /// Attempts to retrieve a feature of the specified type.
    /// </summary>
    /// <typeparam name="TFeature">The type of the feature to retrieve.</typeparam>
    /// <param name="feature">When this method returns, contains the feature of type <typeparamref name="TFeature"/> if found; otherwise, the
    /// default value for the type.</param>
    /// <returns>
    /// <see langword="true"/> if the feature of type <typeparamref name="TFeature"/> was successfully retrieved;
    /// otherwise, <see langword="false"/>.
    /// </returns>
    bool TryGet<TFeature>([MaybeNullWhen(false)] out TFeature feature)
        where TFeature : notnull;

    /// <summary>
    /// Attempts to retrieve a feature of the specified type.
    /// </summary>
    /// <param name="type">The type of the feature to get.</param>
    /// <param name="feature">When this method returns, contains the feature of type <paramref name="type"/> if found; otherwise, the
    /// default value for the type.</param>
    /// <returns>
    /// <see langword="true"/> if the feature of type <paramref name="type"/> was successfully retrieved;
    /// otherwise, <see langword="false"/>.
    /// </returns>
    bool TryGet(Type type, [MaybeNullWhen(false)] out object feature);

    /// <summary>
    /// Remove a feature from the collection.
    /// </summary>
    /// <typeparam name="TFeature">The feature key.</typeparam>
    void Remove<TFeature>()
        where TFeature : notnull;

    /// <summary>
    /// Remove a feature from the collection.
    /// </summary>
    /// <param name="type">The type of the feature to remove.</param>
    void Remove(Type type);

    /// <summary>
    /// Sets the given feature in the collection.
    /// </summary>
    /// <typeparam name="TFeature">The feature key.</typeparam>
    /// <param name="instance">The feature value.</param>
    void Set<TFeature>(TFeature instance)
        where TFeature : notnull;
}
