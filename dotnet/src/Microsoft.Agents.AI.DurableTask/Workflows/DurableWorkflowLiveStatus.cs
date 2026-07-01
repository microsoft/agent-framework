// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Live status payload written to the orchestration via <c>SetCustomStatus</c>.
/// </summary>
/// <remarks>
/// <para>
/// This is the only orchestration state readable by external clients while the workflow
/// is still running. It is written after each superstep so that
/// <see cref="DurableStreamingWorkflowRun"/> can poll for new events.
/// On completion the framework clears it, so events are also
/// embedded in the output via <see cref="DurableWorkflowResult"/>.
/// </para>
/// <para>
/// When the workflow is paused at one or more <see cref="RequestPort"/> nodes,
/// <see cref="PendingEvents"/> contains the request data for each.
/// </para>
/// </remarks>
internal sealed class DurableWorkflowLiveStatus
{
    /// <summary>
    /// Gets or sets the pending request ports the workflow is waiting on. Empty when no input is needed.
    /// </summary>
    public List<PendingRequestPortStatus> PendingEvents { get; set; } = [];

    /// <summary>
    /// Gets or sets the serialized workflow events currently published in the live status.
    /// </summary>
    /// <remarks>
    /// This may be a bounded trailing window of the workflow's full event sequence rather than
    /// every event emitted so far. Durable Functions caps custom status at 16&#160;KB (UTF-16), so
    /// older events are omitted once the cumulative size would exceed that ceiling. <see cref="EventsStartIndex"/>
    /// gives the absolute position of the first element here, and the complete, untrimmed event log
    /// is always available from the workflow output (<see cref="DurableWorkflowResult.Events"/>) at completion.
    /// </remarks>
    public List<string> Events { get; set; } = [];

    /// <summary>
    /// Gets or sets the absolute index, within the workflow's full event sequence, of the first
    /// element of <see cref="Events"/>.
    /// </summary>
    /// <remarks>
    /// This is <c>0</c> when <see cref="Events"/> carries the full log from the beginning. It is greater
    /// than zero when only a trailing window is published (older events trimmed to respect the custom
    /// status size limit). Consumers use it to map window positions back to absolute event indices so
    /// no event is delivered twice or skipped.
    /// </remarks>
    public int EventsStartIndex { get; set; }

    /// <summary>
    /// Attempts to deserialize a serialized custom status string into a <see cref="DurableWorkflowLiveStatus"/>.
    /// </summary>
    [System.Diagnostics.CodeAnalysis.UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing durable workflow status.")]
    [System.Diagnostics.CodeAnalysis.UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing durable workflow status.")]
    internal static bool TryParse(string? serializedStatus, out DurableWorkflowLiveStatus result)
    {
        if (serializedStatus is null)
        {
            result = default!;
            return false;
        }

        try
        {
            result = System.Text.Json.JsonSerializer.Deserialize<DurableWorkflowLiveStatus>(serializedStatus, DurableSerialization.Options)!;
            return result is not null;
        }
        catch (System.Text.Json.JsonException)
        {
            result = default!;
            return false;
        }
    }
}
