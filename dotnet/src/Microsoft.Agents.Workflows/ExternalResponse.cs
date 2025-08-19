// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a request from an external input port.
/// </summary>
/// <param name="Port">The port invoked.</param>
/// <param name="RequestId">The unique identifier of the corresponding request.</param>
/// <param name="Data">The data contained in the response.</param>
public record ExternalResponse(InputPort Port, string RequestId, object Data)
{
}
