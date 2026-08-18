// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options for configuring the <see cref="ToolApprovalAgent"/> middleware.
/// </summary>
public class ToolApprovalAgentOptions
{
    /// <summary>
    /// Gets or sets the <see cref="System.Text.Json.JsonSerializerOptions"/> used for serializing argument values
    /// when storing rules and for persisting state.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, <see cref="AgentJsonUtilities.DefaultOptions"/> is used.
    /// </remarks>
    public JsonSerializerOptions? JsonSerializerOptions { get; set; }

    /// <summary>
    /// Gets or sets a collection of heuristic functions that can automatically approve function calls
    /// that would otherwise require user approval.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Each function receives a <see cref="ToolAutoApprovalRuleContext"/> describing the tool call that requires
    /// approval (via <see cref="ToolAutoApprovalRuleContext.FunctionCallContent"/>) along with the surrounding run
    /// context, and returns a <see cref="ValueTask{Boolean}"/> that resolves to <see langword="true"/> to auto-approve
    /// the call, or <see langword="false"/> to continue evaluating the next rule.
    /// </para>
    /// <para>
    /// Auto-approval rules are evaluated after standing rules (derived from prior user approvals) but before
    /// prompting the user. Rules are evaluated in order; the first rule returning <see langword="true"/>
    /// causes the function call to be auto-approved.
    /// </para>
    /// <para>
    /// <b>Security warning:</b> auto-approval rules may match tool calls solely by name. A rule provided for
    /// one feature (for example a provider's read-only rule) may auto-approve <b>any</b> registered tool
    /// whose name matches, not just the tool the rule was designed for. When adding rules here, ensure
    /// no unrelated tools you register collide with a name approved by any rule in this list,
    /// otherwise that tool will be auto-approved without a human prompt, bypassing the approval boundary.
    /// </para>
    /// </remarks>
    public IEnumerable<Func<ToolAutoApprovalRuleContext, ValueTask<bool>>>? AutoApprovalRules { get; set; }

    /// <summary>
    /// Gets or sets the safety cap on how many times the inner agent is re-invoked within a single run
    /// because every surfaced approval request was auto-approved, or <see langword="null"/> to use
    /// <see cref="ToolApprovalAgent.DefaultMaxAutoApprovalIterations"/>.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Each re-invocation is a fresh call to the inner agent, so a per-request cap such as
    /// <c>FunctionInvokingChatClient.MaximumIterationsPerRequest</c> restarts every time and cannot bound this
    /// loop. Without this cap a model that keeps requesting an auto-approved tool, drives an unbounded sequence of
    /// billable model calls.
    /// </para>
    /// <para>
    /// On reaching the cap the agent performs one final inner invocation without auto-approving again, so any
    /// remaining approval request is surfaced to the caller to decide instead of being approved automatically.
    /// Raise this value if you intend to allow longer auto-approval chains.
    /// </para>
    /// </remarks>
    public int? MaxAutoApprovalIterations { get; set; }
}
