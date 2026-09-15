// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// Controls the approval behavior for the <c>execute_code</c> tool exposed by
/// <see cref="LocalCodeActProvider"/> and <see cref="LocalExecuteCodeFunction"/>.
/// </summary>
public enum LocalCodeActApprovalMode
{
    /// <summary>
    /// <c>execute_code</c> always requires user approval before invocation.
    /// </summary>
    AlwaysRequire,

    /// <summary>
    /// Approval is derived from the provider-owned CodeAct tool registry.
    /// If any configured tool is an
    /// <see cref="ApprovalRequiredAIFunction"/>,
    /// <c>execute_code</c> also requires approval. Otherwise it does not.
    /// </summary>
    NeverRequire,
}
