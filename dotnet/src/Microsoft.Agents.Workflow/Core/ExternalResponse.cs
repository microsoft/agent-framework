// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// .
/// </summary>
/// <param name="Port"></param>
/// <param name="RequestId"></param>
/// <param name="Data"></param>
public record ExternalResponse(InputPort Port, string RequestId, object Data)
{
}
