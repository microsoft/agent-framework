// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

internal enum ExecutionMode
{
    /// <summary>
    /// Normal streaming mode using the new channel-based implementation.
    /// Events stream out immediately as they are created.
    /// </summary>
    OffThread,

    /// <summary>
    /// Lockstep mode where events are batched per superstep.
    /// Events are accumulated and emitted after each superstep completes.
    /// </summary>
    Lockstep,

    /// <summary>
    /// A special execution mode for subworkflows - it functions like OffThread, but without the internal task
    /// running super steps, as they are implemented by being driven directly by the hosting workflow
    /// </summary>
    Subworkflow,
}
