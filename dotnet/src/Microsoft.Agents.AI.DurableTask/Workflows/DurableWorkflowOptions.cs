// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Provides configuration options for managing durable workflows within an application.
/// </summary>
[DebuggerDisplay("Workflows = {Workflows.Count}")]
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
    }

    /// <summary>
    /// Gets the collection of workflows available in the current context, keyed by their unique names.
    /// </summary>
    public IReadOnlyDictionary<string, Workflow> Workflows => this._workflows;

    /// <summary>
    /// Gets the executor registry for direct executor lookup.
    /// </summary>
    internal ExecutorRegistry Executors { get; } = new();

    /// <summary>
    /// Adds a workflow to the collection for processing or execution.
    /// </summary>
    /// <param name="workflow">The workflow instance to add. Cannot be null.</param>
    /// <remarks>
    /// When a workflow is added, all executors are registered in the executor registry.
    /// Any AI agent executors will also be automatically registered with the
    /// <see cref="DurableAgentsOptions"/> if available.
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
        this.RegisterWorkflowExecutors(workflow);
    }

    /// <summary>
    /// Adds a collection of workflows to the current instance.
    /// </summary>
    /// <param name="workflows">The collection of <see cref="Workflow"/> objects to add.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="workflows"/> is null.</exception>
    public void AddWorkflows(params Workflow[] workflows)
    {
        ArgumentNullException.ThrowIfNull(workflows);

        foreach (Workflow workflow in workflows)
        {
            this.AddWorkflow(workflow);
        }
    }

    /// <summary>
    /// Registers all executors from a workflow, including AI agents if agent options are available.
    /// Any sub-workflow bindings are automatically discovered and added recursively.
    /// </summary>
    private void RegisterWorkflowExecutors(Workflow workflow)
    {
        DurableAgentsOptions? agentOptions = this._parentOptions?.Agents;

        foreach ((string executorId, ExecutorBinding binding) in workflow.ReflectExecutors())
        {
            string executorName = WorkflowNamingHelper.GetExecutorName(executorId);
            this.Executors.Register(executorName, executorId, workflow);

            TryRegisterAgent(binding, agentOptions);

            // Automatically discover and register sub-workflows
            if (binding is SubworkflowBinding subworkflowBinding)
            {
                Workflow subWorkflow = subworkflowBinding.WorkflowInstance;
                if (subWorkflow.Name is not null && !this._workflows.ContainsKey(subWorkflow.Name))
                {
                    this.AddWorkflow(subWorkflow);
                }
            }
        }
    }

    /// <summary>
    /// Registers an AI agent with the agent options if the binding contains an unregistered agent.
    /// </summary>
    private static void TryRegisterAgent(ExecutorBinding binding, DurableAgentsOptions? agentOptions)
    {
        if (agentOptions is null)
        {
            return;
        }

        if (binding.RawValue is AIAgent { Name: not null } agent
            && !agentOptions.ContainsAgent(agent.Name))
        {
            agentOptions.AddAIAgent(agent);
        }
    }
}
