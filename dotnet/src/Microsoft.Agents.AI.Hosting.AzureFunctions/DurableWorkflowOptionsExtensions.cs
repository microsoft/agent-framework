// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Provides extension methods for registering and configuring workflows in the context of the Azure Functions hosting environment.
/// </summary>
public static class DurableWorkflowOptionsExtensions
{
    // Registry of workflow options.
    private static readonly Dictionary<string, FunctionsWorkflowOptions> s_workflowOptions = new(StringComparer.OrdinalIgnoreCase);

    /// <summary>
    /// Adds a workflow to the specified <see cref="DurableWorkflowOptions"/> instance and optionally configures
    /// workflow-specific options.
    /// </summary>
    /// <param name="options">The <see cref="DurableWorkflowOptions"/> instance to which the workflow will be added.</param>
    /// <param name="workflow">The workflow to add. The workflow's Name property must not be null or empty.</param>
    /// <param name="configure">An optional delegate to configure workflow-specific options. If null, default options are used.</param>
    /// <returns>The updated <see cref="DurableWorkflowOptions"/> instance containing the added workflow.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="options"/> or <paramref name="workflow"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when the workflow does not have a valid name.</exception>
    public static DurableWorkflowOptions AddWorkflow(
        this DurableWorkflowOptions options,
        Workflow workflow,
        Action<FunctionsWorkflowOptions>? configure)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(workflow);

        if (string.IsNullOrEmpty(workflow.Name))
        {
            throw new ArgumentException("Workflow must have a valid Name property.", nameof(workflow));
        }

        // Initialize with default behavior (MCP trigger disabled)
        FunctionsWorkflowOptions workflowOptions = new();
        configure?.Invoke(workflowOptions);

        options.AddWorkflow(workflow);
        s_workflowOptions[workflow.Name] = workflowOptions;

        return options;
    }

    /// <summary>
    /// Adds a workflow to the specified <see cref="DurableWorkflowOptions"/> instance and configures
    /// trigger support for MCP tool invocations.
    /// </summary>
    /// <param name="options">The <see cref="DurableWorkflowOptions"/> instance to which the workflow will be added.</param>
    /// <param name="workflow">The workflow to add. The workflow's Name property must not be null or empty.</param>
    /// <param name="enableMcpToolTrigger">true to enable an MCP tool trigger for the workflow; otherwise, false.</param>
    /// <returns>The updated <see cref="DurableWorkflowOptions"/> instance with the specified workflow and trigger configuration applied.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="options"/> or <paramref name="workflow"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when the workflow does not have a valid name.</exception>
    public static DurableWorkflowOptions AddWorkflow(
        this DurableWorkflowOptions options,
        Workflow workflow,
        bool enableMcpToolTrigger)
    {
        return AddWorkflow(options, workflow, workflowOptions => workflowOptions.McpToolTrigger.IsEnabled = enableMcpToolTrigger);
    }

    /// <summary>
    /// Tries to get the <see cref="FunctionsWorkflowOptions"/> for a workflow by name.
    /// </summary>
    /// <param name="workflowName">The name of the workflow.</param>
    /// <param name="workflowOptions">When this method returns, contains the workflow options if found; otherwise, null.</param>
    /// <returns><c>true</c> if the workflow options were found; otherwise, <c>false</c>.</returns>
    internal static bool TryGetWorkflowOptions(string workflowName, out FunctionsWorkflowOptions? workflowOptions)
    {
        return s_workflowOptions.TryGetValue(workflowName, out workflowOptions);
    }

    /// <summary>
    /// Builds the workflow options used for dependency injection (read-only copy).
    /// </summary>
    internal static IReadOnlyDictionary<string, FunctionsWorkflowOptions> GetWorkflowOptionsSnapshot()
    {
        return new Dictionary<string, FunctionsWorkflowOptions>(s_workflowOptions, StringComparer.OrdinalIgnoreCase);
    }
}
