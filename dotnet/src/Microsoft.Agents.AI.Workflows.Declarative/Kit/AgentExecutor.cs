// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Kit;

/// <summary>
/// Base class for agent invokcation.
/// </summary>
/// <param name="id">The executor id</param>
/// <param name="session">Session to support formula expressions.</param>
/// <param name="agentProvider">Provider for accessing and manipulating agents and conversations.</param>
public abstract class AgentExecutor(string id, FormulaSession session, WorkflowAgentProvider agentProvider) : ActionExecutor(id, session)
{
    /// <summary>
    /// Invokes an agent using the provided <see cref="WorkflowAgentProvider"/>.
    /// </summary>
    /// <param name="context">The workflow execution context providing messaging and state services.</param>
    /// <param name="agentName">The name or identifier of the agent.</param>
    /// <param name="conversationId">The identifier of the conversation.</param>
    /// <param name="autoSend">Send the agent's response as workflow output. (default: true).</param>
    /// <param name="inputMessages">Optional messages to add to the conversation prior to invocation.</param>
    /// <param name="cancellationToken">A token that can be used to observe cancellation.</param>
    /// <returns></returns>
    protected ValueTask<AgentRunResponse> InvokeAgentAsync(
        IWorkflowContext context,
        string agentName,
        string? conversationId,
        bool autoSend,
        IEnumerable<ChatMessage>? inputMessages = null,
        CancellationToken cancellationToken = default)
        => agentProvider.InvokeAgentAsync(this.Id, context, agentName, conversationId, autoSend, inputMessages, inputArguments: null, cancellationToken);
}
