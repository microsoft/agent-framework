// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

internal enum ExecutionMode
{
    /// <summary>
    /// Normal streaming mode using the new channel-based implementation.
    /// Events stream out immediately as they are created.
    /// </summary>
    Normal,

    /// <summary>
    /// Lockstep mode where events are batched per superstep.
    /// Events are accumulated and emitted after each superstep completes.
    /// </summary>
    Lockstep
}
