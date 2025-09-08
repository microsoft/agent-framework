// Copyright (c) Microsoft. All rights reserved.

using System;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Extension methods for the <see cref="AgentTaskStatus"/> class.
/// </summary>
internal static class A2AAgentTaskStatusExtensions
{
    /// <summary>
    /// Converts an A2A <see cref="AgentTaskStatus"/> to a <see cref="NewResponseStatus"/>.
    /// </summary>
    /// <param name="status">The A2A agent task status to convert.</param>
    /// <returns>The corresponding <see cref="NewResponseStatus"/>.</returns>
    public static NewResponseStatus ToResponseStatus(this AgentTaskStatus status) => status.State switch
    {
        TaskState.Submitted => NewResponseStatus.Submitted,
        TaskState.Working => NewResponseStatus.InProgress,
        TaskState.InputRequired => NewResponseStatus.InputRequired,
        TaskState.Completed => NewResponseStatus.Completed,
        TaskState.Canceled => NewResponseStatus.Canceled,
        TaskState.Failed => NewResponseStatus.Failed,
        TaskState.Rejected => NewResponseStatus.Rejected,
        TaskState.AuthRequired => NewResponseStatus.AuthRequired,
        TaskState.Unknown => NewResponseStatus.Unknown,
        _ => throw new NotSupportedException($"The task state '{status.State}' is not supported."),
    };
}
