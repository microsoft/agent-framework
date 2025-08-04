// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB;

/// <summary>
/// Root document for each actor that provides actor-level ETag semantics.
/// </summary>
public sealed class ActorRootDocument
{
    /// <summary>
    /// The document ID.
    /// </summary>
    public string Id { get; set; } = default!;

    /// <summary>
    /// The actor ID.
    /// </summary>
    public string ActorId { get; set; } = default!;

    /// <summary>
    /// The last modified timestamp.
    /// </summary>
    public DateTimeOffset LastModified { get; set; }
}

/// <summary>
/// Actor state document that represents a single key-value pair in the actor's state.
/// </summary>
public sealed class ActorStateDocument
{
    /// <summary>
    /// The document ID.
    /// </summary>
    public string Id { get; set; } = default!;

    /// <summary>
    /// The actor ID.
    /// </summary>
    public string ActorId { get; set; } = default!;

    /// <summary>
    /// The logical key for the state entry.
    /// </summary>
    public string Key { get; set; } = default!;

    /// <summary>
    /// The value payload.
    /// </summary>
    public JsonElement Value { get; set; } = default!;
}

/// <summary>
/// Projection class for Cosmos DB queries to retrieve keys.
/// </summary>
public sealed class KeyProjection
{
    /// <summary>
    /// The key value.
    /// </summary>
    public string Key { get; set; } = default!;
}
