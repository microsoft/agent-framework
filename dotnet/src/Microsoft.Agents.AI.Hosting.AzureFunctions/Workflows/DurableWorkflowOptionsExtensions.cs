// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Extension methods for <see cref="DurableWorkflowOptions"/> to configure Azure Functions HTTP trigger options.
/// </summary>
public static class DurableWorkflowOptionsExtensions
{
    /// <summary>
    /// Adds a workflow and optionally exposes a status HTTP endpoint for querying pending HITL requests.
    /// </summary>
    /// <param name="options">The workflow options to add the workflow to.</param>
    /// <param name="workflow">The workflow instance to add.</param>
    /// <param name="exposeStatusEndpoint">If <see langword="true"/>, a GET endpoint is generated at <c>workflows/{name}/status/{runId}</c>.</param>
    public static void AddWorkflow(this DurableWorkflowOptions options, Workflow workflow, bool exposeStatusEndpoint)
    {
        ArgumentNullException.ThrowIfNull(options);

        options.AddWorkflow(workflow);

        if (exposeStatusEndpoint && options.ParentOptions is FunctionsDurableOptions functionsOptions)
        {
            functionsOptions.EnableStatusEndpoint(workflow.Name!);
        }
    }

    /// <summary>
    /// Adds a workflow and configures whether to expose a status HTTP endpoint and/or an MCP tool trigger.
    /// </summary>
    /// <param name="options">The workflow options to add the workflow to.</param>
    /// <param name="workflow">The workflow instance to add.</param>
    /// <param name="exposeStatusEndpoint">If <see langword="true"/>, a GET endpoint is generated at <c>workflows/{name}/status/{runId}</c>.</param>
    /// <param name="exposeMcpToolTrigger">If <see langword="true"/>, an MCP tool trigger is generated for the workflow.</param>
    public static void AddWorkflow(this DurableWorkflowOptions options, Workflow workflow, bool exposeStatusEndpoint, bool exposeMcpToolTrigger)
    {
        ArgumentNullException.ThrowIfNull(options);

        options.AddWorkflow(workflow);

        if (options.ParentOptions is FunctionsDurableOptions functionsOptions)
        {
            if (exposeStatusEndpoint)
            {
                functionsOptions.EnableStatusEndpoint(workflow.Name!);
            }

            if (exposeMcpToolTrigger)
            {
                functionsOptions.EnableMcpToolTrigger(workflow.Name!);
            }
        }
    }
}
