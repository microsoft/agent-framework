// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Provides configuration options for managing durable workflows within an application.
/// </summary>
public sealed class DurableWorkflowOptions
{
    private readonly Dictionary<string, Workflow> _workflows = new(StringComparer.OrdinalIgnoreCase);
    private readonly DurableOptions? _parentOptions;

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableWorkflowOptions"/> class.
    /// </summary>
    /// <param name="parentOptions">Optional parent options container for accessing related configuration.</param>
    internal DurableWorkflowOptions(DurableOptions? parentOptions = null)
    {
        this._parentOptions = parentOptions;
        this.Executors = new ExecutorRegistry();
    }

    /// <summary>
    /// Gets the collection of workflows available in the current context, keyed by their unique names.
    /// </summary>
    /// <remarks>The returned dictionary is read-only and reflects the current set of registered workflows.
    /// Changes to the underlying workflow collection are immediately visible through this property. Accessing a
    /// workflow by name that does not exist will result in a KeyNotFoundException.</remarks>
    public IReadOnlyDictionary<string, Workflow> Workflows => this._workflows;

    /// <summary>
    /// Gets the executor registry.
    /// </summary>
    internal ExecutorRegistry Executors { get; }

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

        // Register executors in the registry for direct lookup
        RegisterExecutors(workflow, this.Executors);

        // Register any agentic executors with DurableAgentsOptions if available through parent
        DurableAgentsOptions? agentOptions = this.TryGetAgentOptions();
        if (agentOptions is not null)
        {
            RegisterAgenticExecutors(workflow, agentOptions);
        }
    }

    private DurableAgentsOptions? TryGetAgentOptions()
    {
        return this._parentOptions?.Agents;
    }

    private static void RegisterAgenticExecutors(Workflow workflow, DurableAgentsOptions agentOptions)
    {
        // Use the public EnumerateAgentExecutors method to get all AIAgent instances
        foreach (AIAgent agent in workflow.EnumerateAgentExecutors())
        {
            try
            {
                // Register the agent as workflow-only (no HTTP trigger)
                agentOptions.AddAIAgent(agent, workflowOnly: true);
            }
            catch (ArgumentException)
            {
                // Agent with this name is already registered, skip it
                // This is expected behavior when multiple workflows use the same agent
            }
        }
    }

    private static void RegisterExecutors(Workflow workflow, ExecutorRegistry registry)
    {
        // Register all executors from the workflow in the registry
        foreach (KeyValuePair<string, Workflows.Checkpointing.ExecutorInfo> executor in workflow.ReflectExecutors())
        {
            // Extract the executor name (without GUID suffix)
            string executorName = executor.Key.Split('_')[0];
            registry.Register(executorName, executor.Key, workflow);
        }
    }
}
