// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents the status of a request in the actor system.
/// </summary>
public enum RequestStatus
{
    /// <summary>
    /// The request is pending and has not yet been processed.
    /// </summary>
    [JsonStringEnumMemberName("pending")]
    Pending,

    /// <summary>
    /// The request has been completed successfully.
    /// </summary>
    [JsonStringEnumMemberName("completed")]
    Completed,

    /// <summary>
    /// The request has failed.
    /// </summary>
    [JsonStringEnumMemberName("failed")]
    Failed,

    /// <summary>
    /// The request was not found, possibly due to it being deleted or never existing.
    /// </summary>
    [JsonStringEnumMemberName("not_found")]
    NotFound,
}
