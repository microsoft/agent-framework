// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides context for a tool auto-approval rule evaluated by the <see cref="ToolApprovalAgent"/>.
/// </summary>
/// <remarks>
/// This type wraps the <see cref="FunctionCallContent"/> that requires approval together with the
/// surrounding run context (agent, session, request messages, and run options).
/// </remarks>
public sealed class ToolAutoApprovalRuleContext
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ToolAutoApprovalRuleContext"/> class.
    /// </summary>
    /// <param name="functionCallContent">The <see cref="FunctionCallContent"/> representing the tool call that requires approval.</param>
    /// <param name="agent">The <see cref="AIAgent"/> that is evaluating the tool call.</param>
    /// <param name="session">The <see cref="AgentSession"/> that is associated with the current run, if any.</param>
    /// <param name="requestMessages">The request messages passed into the current run.</param>
    /// <param name="agentRunOptions">The <see cref="AgentRunOptions"/> that was passed to the current run, if any.</param>
    public ToolAutoApprovalRuleContext(
        FunctionCallContent functionCallContent,
        AIAgent agent,
        AgentSession? session,
        IReadOnlyCollection<ChatMessage> requestMessages,
        AgentRunOptions? agentRunOptions)
    {
        this.FunctionCallContent = Throw.IfNull(functionCallContent);
        this.Agent = Throw.IfNull(agent);
        this.Session = session;
        this.RequestMessages = Throw.IfNull(requestMessages);
        this.RunOptions = agentRunOptions;
    }

    /// <summary>Gets the <see cref="FunctionCallContent"/> representing the tool call that requires approval.</summary>
    public FunctionCallContent FunctionCallContent { get; }

    /// <summary>Gets the <see cref="AIAgent"/> that is evaluating the tool call.</summary>
    public AIAgent Agent { get; }

    /// <summary>Gets the <see cref="AgentSession"/> that is associated with the current run.</summary>
    public AgentSession? Session { get; }

    /// <summary>Gets the request messages passed into the current run.</summary>
    public IReadOnlyCollection<ChatMessage> RequestMessages { get; }

    /// <summary>Gets the <see cref="AgentRunOptions"/> that was passed to the current run.</summary>
    public AgentRunOptions? RunOptions { get; }
}
