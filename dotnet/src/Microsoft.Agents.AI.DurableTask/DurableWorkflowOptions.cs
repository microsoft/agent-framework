// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;

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
    public IReadOnlyDictionary<string, Workflow> Workflows => this._workflows;

    /// <summary>
    /// Gets the executor registry for direct executor lookup.
    /// </summary>
    internal ExecutorRegistry Executors { get; }

    /// <summary>
    /// Adds a workflow to the collection for processing or execution.
    /// </summary>
    /// <param name="workflow">The workflow instance to add. Cannot be null.</param>
    /// <remarks>
    /// When a workflow is added, any AI agent executors in the workflow will be automatically
    /// registered with the <see cref="DurableAgentsOptions"/> if it was provided during construction.
    /// </remarks>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="workflow"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when the workflow does not have a valid name.</exception>
    public void AddWorkflow(Workflow workflow)
    {
        ArgumentNullException.ThrowIfNull(workflow);

        if (string.IsNullOrEmpty(workflow.Name))
        {
            throw new ArgumentException("Workflow must have a valid Name property.", nameof(workflow));
        }

        this._workflows[workflow.Name] = workflow;

        RegisterExecutors(workflow, this.Executors);

        DurableAgentsOptions? agentOptions = this._parentOptions?.Agents;
        if (agentOptions is not null)
        {
            RegisterAgenticExecutors(workflow, agentOptions);
        }
    }

    private static void RegisterExecutors(Workflow workflow, ExecutorRegistry registry)
    {
        foreach (KeyValuePair<string, ExecutorInfo> executor in workflow.ReflectExecutors())
        {
            int underscoreIndex = executor.Key.IndexOf('_');
            string executorName = underscoreIndex > 0 ? executor.Key[..underscoreIndex] : executor.Key;
            registry.Register(executorName, executor.Key, workflow);
        }
    }

    private static void RegisterAgenticExecutors(Workflow workflow, DurableAgentsOptions agentOptions)
    {
        foreach (AIAgent agent in workflow.EnumerateAgentExecutors())
        {
            if (agent.Name is not null && !agentOptions.ContainsAgent(agent.Name))
            {
                agentOptions.AddAIAgent(agent, workflowOnly: true);
            }
        }
    }
}
