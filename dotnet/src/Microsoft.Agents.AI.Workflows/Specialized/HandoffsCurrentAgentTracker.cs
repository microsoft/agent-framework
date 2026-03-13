// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Specialized;

/// <summary>Tracks the current agent ID across turns when return-to-previous routing is enabled.</summary>
internal sealed class HandoffsCurrentAgentTracker
{
    public string? CurrentAgentId { get; set; }
}
