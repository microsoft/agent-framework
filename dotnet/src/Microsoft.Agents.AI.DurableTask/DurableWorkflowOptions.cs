// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Provides configuration options for managing durable workflows within an application.
/// </summary>
public sealed class DurableWorkflowOptions
{
    private readonly Dictionary<string, Workflow> _workflows = new(StringComparer.OrdinalIgnoreCase);

    /// <summary>
    /// Adds a workflow to the collection for processing or execution.
    /// </summary>
    /// <param name="workflow">The workflow instance to add. Cannot be null.</param>
    public void AddWorkflow(Workflow workflow)
    {
        ArgumentNullException.ThrowIfNull(workflow);

        if (string.IsNullOrEmpty(workflow.Name))
        {
            throw new ArgumentException("Workflow must have a valid Name property.", nameof(workflow));
        }

        this._workflows[workflow.Name] = workflow;
    }

    /// <summary>
    /// Gets the collection of workflows available in the current context, keyed by their unique names.
    /// </summary>
    /// <remarks>The returned dictionary is read-only and reflects the current set of registered workflows.
    /// Changes to the underlying workflow collection are immediately visible through this property. Accessing a
    /// workflow by name that does not exist will result in a KeyNotFoundException.</remarks>
    public IReadOnlyDictionary<string, Workflow> Workflows => this._workflows;
}
