// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides extension methods for treating workflows as <see cref="AIAgent"/>
/// </summary>
public static class WorkflowHostingExtensions
{
    /// <summary>
    /// Convert a workflow with the appropriate primary input type to an <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="workflow">The workflow to be hosted by the resulting <see cref="AIAgent"/></param>
    /// <param name="id">A unique id for the hosting <see cref="AIAgent"/>.</param>
    /// <param name="name">A name for the hosting <see cref="AIAgent"/>.</param>
    /// <param name="description">A description for the hosting <see cref="AIAgent"/>.</param>
    /// <param name="executionEnvironment">Specify the execution environment to use when running the workflows. See
    /// <see cref="InProcessExecution.OffThread"/>, <see cref="InProcessExecution.Concurrent"/> and
    /// <see cref="InProcessExecution.Lockstep"/> for the in-process environments.</param>
    /// <param name="includeExceptionDetails">If <see langword="true"/>, will include <see cref="System.Exception.Message"/>
    /// in the <see cref="ErrorContent"/> representing the workflow error.</param>
    /// <param name="includeWorkflowOutputsInResponse">If <see langword="true"/>, will transform outgoing workflow outputs
    /// into content in <see cref="AgentResponseUpdate"/>s or the <see cref="AgentResponse"/> as appropriate.</param>
    /// <returns></returns>
    public static AIAgent AsAIAgent(
        this Workflow workflow,
        string? id = null,
        string? name = null,
        string? description = null,
        IWorkflowExecutionEnvironment? executionEnvironment = null,
        bool includeExceptionDetails = false,
        bool includeWorkflowOutputsInResponse = false)
    {
        return new WorkflowHostAgent(workflow, id, name, description, executionEnvironment, includeExceptionDetails, includeWorkflowOutputsInResponse);
    }

    /// <summary>
    /// Returns a copy of a workflow-hosting agent that writes its checkpoints to the supplied
    /// <see cref="CheckpointManager"/>, so a host can redirect checkpoint storage on an agent that
    /// has already been built.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This exists for hosts that receive a finished <see cref="AIAgent"/> and need to decide where
    /// its checkpoints live, which is something only the host knows. The agent itself cannot be
    /// changed in place, because the execution environment is fixed when the agent is constructed,
    /// so a copy is returned instead. Everything else about the agent is preserved, including its
    /// identifier, name, description and the workflow it runs.
    /// </para>
    /// <para>
    /// The call leaves the agent untouched and returns it as-is in three cases: when it does not
    /// host a workflow, when it was built with an execution environment that already names a
    /// checkpoint manager, and when the workflow-hosting agent sits behind a wrapper such as
    /// middleware. The last case is a limitation rather than a choice: only the innermost agent can
    /// be copied, and returning it alone would silently throw the wrapper away.
    /// </para>
    /// <para>
    /// The returned copy is a distinct agent, so a host that calls this on every request should
    /// keep the result rather than rebuilding it each time.
    /// </para>
    /// </remarks>
    /// <param name="agent">The agent whose checkpoint storage should be redirected.</param>
    /// <param name="checkpointManager">The checkpoint manager the copy should write to.</param>
    /// <returns>The redirected copy, or <paramref name="agent"/> itself when nothing was changed.</returns>
    public static AIAgent WithCheckpointing(this AIAgent agent, CheckpointManager checkpointManager)
    {
        Throw.IfNull(agent);
        Throw.IfNull(checkpointManager);

        return agent is WorkflowHostAgent workflowAgent
            ? workflowAgent.WithCheckpointing(checkpointManager)
            : agent;
    }

    internal static FunctionCallContent ToFunctionCall(this ExternalRequest request)
    {
        Dictionary<string, object?> parameters = new()
        {
            { "data", request.Data }
        };

        return new FunctionCallContent(request.RequestId, request.PortInfo.PortId, parameters);
    }
}
