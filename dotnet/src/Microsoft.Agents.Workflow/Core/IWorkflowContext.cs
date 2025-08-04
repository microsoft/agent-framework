// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// Provides services for an <see cref="Executor"/> during the execution of a workflow.
/// </summary>
public interface IWorkflowContext
{
    /// <summary>
    /// .
    /// </summary>
    /// <param name="workflowEvent"></param>
    /// <returns></returns>
    ValueTask AddEventAsync(WorkflowEvent workflowEvent);

    /// <summary>
    /// .
    /// </summary>
    /// <param name="message"></param>
    /// <returns></returns>
    ValueTask SendMessageAsync(object message);

    // TODO: State management
}
