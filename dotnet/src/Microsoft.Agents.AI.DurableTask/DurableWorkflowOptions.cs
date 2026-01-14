// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Provides configuration options for managing durable workflows within an application.
/// </summary>
public sealed class DurableWorkflowOptions
{
    private readonly Dictionary<string, Workflow> _workflows = new(StringComparer.OrdinalIgnoreCase);
    private readonly object? _parentOptions;

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableWorkflowOptions"/> class.
    /// </summary>
    /// <param name="parentOptions">Optional parent options container for accessing related configuration.</param>
    public DurableWorkflowOptions(object? parentOptions = null)
    {
        this._parentOptions = parentOptions;
    }

    /// <summary>
    /// Adds a workflow to the collection for processing or execution.
    /// </summary>
    /// <param name="workflow">The workflow instance to add. Cannot be null.</param>
    /// <remarks>
    /// When a workflow is added, any AI agent executors in the workflow will be automatically
    /// registered with the DurableAgentsOptions if it was provided during construction.
    /// </remarks>
    public void AddWorkflow(Workflow workflow)
    {
        ArgumentNullException.ThrowIfNull(workflow);

        if (string.IsNullOrEmpty(workflow.Name))
        {
            throw new ArgumentException("Workflow must have a valid Name property.", nameof(workflow));
        }

        this._workflows[workflow.Name] = workflow;

        // Register any agentic executors with DurableAgentsOptions if available through parent
        DurableAgentsOptions? agentOptions = this.TryGetAgentOptions();
        if (agentOptions is not null)
        {
            RegisterAgenticExecutors(workflow, agentOptions);
        }
    }

    /// <summary>
    /// Gets the collection of workflows available in the current context, keyed by their unique names.
    /// </summary>
    /// <remarks>The returned dictionary is read-only and reflects the current set of registered workflows.
    /// Changes to the underlying workflow collection are immediately visible through this property. Accessing a
    /// workflow by name that does not exist will result in a KeyNotFoundException.</remarks>
    public IReadOnlyDictionary<string, Workflow> Workflows => this._workflows;

    [System.Diagnostics.CodeAnalysis.UnconditionalSuppressMessage("ReflectionAnalysis", "IL2075",
        Justification = "Reflection is used to access Agents property from parent options container for automatic agent registration.")]
    private DurableAgentsOptions? TryGetAgentOptions()
    {
        // Try to extract DurableAgentsOptions from the parent container
        // This uses reflection to access the Agents property if available
        if (this._parentOptions is null)
        {
            return null;
        }

        // Check if parent has an Agents property (DurableOptions pattern)
        System.Reflection.PropertyInfo? agentsProperty = this._parentOptions.GetType()
            .GetProperty("Agents", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);

        if (agentsProperty?.PropertyType == typeof(DurableAgentsOptions))
        {
            return agentsProperty.GetValue(this._parentOptions) as DurableAgentsOptions;
        }

        // If parent is directly DurableAgentsOptions (for backward compatibility)
        return this._parentOptions as DurableAgentsOptions;
    }

    private static void RegisterAgenticExecutors(Workflow workflow, DurableAgentsOptions agentOptions)
    {
        // Use the public EnumerateAgentExecutors method to get all AIAgent instances
        foreach (AIAgent agent in workflow.EnumerateAgentExecutors())
        {
            try
            {
                // Register the agent with DurableAgentsOptions
                agentOptions.AddAIAgent(agent);
            }
            catch (ArgumentException)
            {
                // Agent with this name is already registered, skip it
                // This is expected behavior when multiple workflows use the same agent
            }
        }
    }
}
