// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal sealed record class HandoffState(
    TurnToken TurnToken,
    string? RequestedHandoffTargetAgentId,
    string? PreviousAgentId = null);
