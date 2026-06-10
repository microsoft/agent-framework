// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Microsoft.Agents.AI.AGUI.A2UI;

/// <summary>
/// Builders for the A2UI v0.9 operations that make up a surface lifecycle:
/// <c>createSurface</c>, <c>updateComponents</c>, and <c>updateDataModel</c>.
/// </summary>
/// <remarks>
/// Each builder returns a single operation object of the shape
/// <c>{ "version": "v0.9", "&lt;operation&gt;": { ... } }</c>, matching the A2UI v0.9
/// envelope specification and the sibling TypeScript/Python toolkit implementations.
/// </remarks>
public static class A2UIOperationBuilder
{
    /// <summary>
    /// Builds a <c>createSurface</c> operation.
    /// </summary>
    /// <param name="surfaceId">The identifier of the surface to create.</param>
    /// <param name="catalogId">The identifier of the component catalog the surface renders against.</param>
    /// <returns>The operation as a <see cref="JsonObject"/>.</returns>
    public static JsonObject CreateSurface(string surfaceId, string catalogId)
        => throw new NotImplementedException();

    /// <summary>
    /// Builds an <c>updateComponents</c> operation carrying a flat component array.
    /// </summary>
    /// <param name="surfaceId">The identifier of the target surface.</param>
    /// <param name="components">The flat A2UI component array.</param>
    /// <returns>The operation as a <see cref="JsonObject"/>.</returns>
    public static JsonObject UpdateComponents(string surfaceId, IEnumerable<JsonNode?> components)
        => throw new NotImplementedException();

    /// <summary>
    /// Builds an <c>updateDataModel</c> operation that writes <paramref name="value"/> at <paramref name="path"/>.
    /// </summary>
    /// <param name="surfaceId">The identifier of the target surface.</param>
    /// <param name="value">The value to write into the surface data model.</param>
    /// <param name="path">The JSON-pointer-style path to write at. Defaults to the root path <c>"/"</c>.</param>
    /// <returns>The operation as a <see cref="JsonObject"/>.</returns>
    public static JsonObject UpdateDataModel(string surfaceId, JsonNode? value, string path = "/")
        => throw new NotImplementedException();
}
