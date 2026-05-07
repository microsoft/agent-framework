// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Notifies an AIAgent-hosting executor that it should reset its conversation state, and start a new session, if appropriate.
/// Note that for Agent Orchestrations, only Magentic makes use of this functionality.
/// </summary>
public sealed record ResetChatSignal();
