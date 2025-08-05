// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB;

/// <summary>
/// Root document for each actor that provides actor-level ETag semantics.
/// Every write operation updates this document to ensure a single ETag represents
/// the entire actor's state for optimistic concurrency control.
/// This document contains no actor state data. It only serves to track last modified
/// time and provide a single ETag for the actor's state.
///
/// Example structure:
/// {
///   "id": "rootdoc",                       // Root document ID (constant per actor partition)
///   "actorId": "actor-123",                // Partition key (actor ID)
///   "lastModified": "2024-...",            // Timestamp
/// }
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
/// Document Structure (one per actor key):
/// {
///   "id": "state_sanitizedkey",            // Unique document ID for the state entry
///   "actorId": "actor-123",                // Partition key (actor ID)
///   "key": "foo",                          // Logical key for the state entry
///   "value": { "bar": 42, "baz": "hello" } // Arbitrary JsonElement payload
/// }
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
