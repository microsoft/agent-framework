// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Optional interface implemented by response payload types that need correlation
/// with the request payload that produced them.
/// </summary>
public interface IExternalResponseEnvelope
{
    /// <summary>
    /// Creates a response envelope correlated to the specified request id.
    /// </summary>
    /// <param name="requestId">The request id that produced this response.</param>
    /// <returns>A response envelope correlated to <paramref name="requestId"/>.</returns>
    object WithRequestId(string requestId);
}
