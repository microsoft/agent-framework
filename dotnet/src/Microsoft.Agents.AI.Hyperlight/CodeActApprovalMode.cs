// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hyperlight;

/// <summary>
/// Controls the approval behavior for the <c>execute_code</c> tool exposed by
/// <see cref="HyperlightCodeActProvider"/> and <see cref="HyperlightExecuteCodeFunction"/>.
/// </summary>
public enum CodeActApprovalMode
{
    /// <summary>
    /// <c>execute_code</c> always requires user approval before invocation.
    /// </summary>
    AlwaysRequire,

    /// <summary>
    /// Approval is derived from the provider-owned CodeAct tool registry.
    /// If any configured tool is an
    /// <see cref="Microsoft.Extensions.AI.ApprovalRequiredAIFunction"/>,
    /// <c>execute_code</c> also requires approval. Otherwise it does not.
    /// </summary>
    NeverRequire,
}
