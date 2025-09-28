// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Runtime;

/// <summary>
/// Provides extension methods for the <see cref="RequestStatus"/> enumeration.
/// </summary>
public static class RequestStatusExtensions
{
    /// <summary>
    /// Determines if the request status indicates that the request has terminated.
    /// </summary>
    /// <param name="status">The request status to check.</param>
    /// <returns><see langword="true"/> if the request has terminated; otherwise, <see langword="false"/>.</returns>
    public static bool IsTerminated(this RequestStatus status) => status != RequestStatus.Pending;
}
