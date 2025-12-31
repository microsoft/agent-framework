// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

/// <summary>
/// Extension methods for <see cref="IAgentFeatureCollection"/>.
/// </summary>
public static class AgentFeatureCollectionExtensions
{
    /// <summary>
    /// Adds the specified feature to the collection and returns the collection.
    /// </summary>
    /// <typeparam name="TFeature">The feature key.</typeparam>
    /// <param name="features">The feature collection to add the new feature to.</param>
    /// <param name="feature">The feature to add to the collection.</param>
    /// <returns>The updated collection.</returns>
    public static IAgentFeatureCollection WithFeature<TFeature>(this IAgentFeatureCollection features, TFeature feature)
        where TFeature : notnull
    {
        features.Set(feature);
        return features;
    }
}
