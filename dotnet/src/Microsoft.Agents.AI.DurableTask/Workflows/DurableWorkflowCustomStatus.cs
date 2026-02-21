// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Represents the custom status written by the orchestration for streaming consumption.
/// </summary>
/// <remarks>
/// The Durable Task framework exposes <c>SerializedCustomStatus</c> on orchestration metadata,
/// which is the only orchestration state readable by external clients while the orchestration
/// is still running. The orchestrator writes this object via <c>SetCustomStatus</c> after each
/// superstep so that <see cref="DurableStreamingWorkflowRun"/> can poll for new events.
/// On orchestration completion the framework clears custom status, so events are also
/// embedded in the output via <see cref="DurableWorkflowResult"/>.
/// </remarks>
internal sealed class DurableWorkflowCustomStatus
{
    /// <summary>
    /// Gets or sets the serialized workflow events emitted so far.
    /// </summary>
    public List<string> Events { get; set; } = [];
}
