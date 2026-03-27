// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Represents a RequestPort the workflow is paused at, waiting for a response.
/// </summary>
/// <param name="EventName">The RequestPort ID identifying which input is needed.</param>
/// <param name="Input">The serialized request data passed to the RequestPort.</param>
internal sealed record PendingRequestPortStatus(
    string EventName,
    string Input);
