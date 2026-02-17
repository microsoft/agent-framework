// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Specifies the behavior for filtering <see cref="FunctionCallContent"/> and <see cref="ChatRole.Tool"/> contents from
/// <see cref="ChatMessage"/>s flowing through a handoff workflow. This can be used to prevent agents from seeing external
/// tool calls.
/// </summary>
public enum HandoffToolCallFilteringBehavior
{
    /// <summary>
    /// Do not filter <see cref="FunctionCallContent"/> and <see cref="ChatRole.Tool"/> contents.
    /// </summary>
    None,

    /// <summary>
    /// Filter only handoff-related <see cref="FunctionCallContent"/> and <see cref="ChatRole.Tool"/> contents.
    /// </summary>
    HandoffOnly,

    /// <summary>
    /// Filter all <see cref="FunctionCallContent"/> and <see cref="ChatRole.Tool"/> contents.
    /// </summary>
    All
}
