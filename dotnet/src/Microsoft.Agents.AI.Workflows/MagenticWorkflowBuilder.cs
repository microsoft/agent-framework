// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Specialized.Magentic;
using Microsoft.Shared.Diagnostics;

using ExecutorFactoryFunc = System.Func<Microsoft.Agents.AI.Workflows.ExecutorConfig<Microsoft.Agents.AI.Workflows.ExecutorOptions>,
                                        string,
                                        System.Threading.Tasks.ValueTask<Microsoft.Agents.AI.Workflows.Specialized.Magentic.MagenticOrchestrator>>;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Fluent builder for creating Magentic One multi-agent orchestration workflows.
///
/// Magentic One workflows use an LLM-powered manager to coordinate multiple agents through dynamic task planning, progress tracking,
/// and adaptive replanning.The manager creates plans, selects agents, monitors progress, and determines when to replan or complete.
///
/// The builder provides a fluent API for configuring participants, the manager, optional plan review, checkpointing, and event
/// callbacks.
///
/// Human-in-the-loop Support: Magentic provides specialized HITL mechanisms via:
/// - `RequirePlanSignoff` - Review and approve/revise plans before execution
/// - Tool approval via `function_approval_request`: Approve individual tool calls on participating agents. Note that tool calls are
///   not supported on the ManagerAgent.
/// </summary>
/// <param name="managerAgent"></param>
[Experimental(DiagnosticConstants.ExperimentalFeatureDiagnostic)]
public class MagenticWorkflowBuilder(AIAgent managerAgent)
{
    private readonly List<AIAgent> _team = new();
    private string? _name;
    private string? _description;
    private int _maxStalls = TaskLimits.DefaultMaxStallCount;
    private int? _maxRounds;
    private int? _maxResets;
    private bool _requirePlanSignoff = true;

    private Dictionary<AIAgent, HashSet<OutputTag>>? _outputDesignations;

    /// <inheritdoc cref="GroupChatWorkflowBuilder.AddParticipants(IEnumerable{AIAgent})"/>
    public MagenticWorkflowBuilder AddParticipants(params IEnumerable<AIAgent> agents)
    {
        this._team.AddRange(agents);
        return this;
    }

    /// <inheritdoc cref="WorkflowBuilder.WithName(string)"/>
    public MagenticWorkflowBuilder WithName(string name)
    {
        this._name = name;
        return this;
    }

    /// <inheritdoc cref="WorkflowBuilder.WithDescription(string)"/>
    public MagenticWorkflowBuilder WithDescription(string description)
    {
        this._description = description;
        return this;
    }

    /// <summary>
    /// Set the maximum number of coordination rounds. <see langword="null"/> means unlimited.
    /// </summary>
    /// <returns></returns>
    public MagenticWorkflowBuilder WithMaxRounds(int? maxRounds = null)
    {
        this._maxRounds = maxRounds;
        return this;
    }

    /// <summary>
    /// Set the maximum number ofnumber of resets allowed. <see langword="null"/> means unlimited.
    /// </summary>
    /// <returns></returns>
    public MagenticWorkflowBuilder WithMaxResets(int? maxResets = null)
    {
        this._maxResets = maxResets;
        return this;
    }

    /// <summary>
    /// Set the maximum number of consecutive rounds without progress before replan (default 3).
    /// </summary>
    /// <returns></returns>
    public MagenticWorkflowBuilder WithMaxStalls(int maxStalls = TaskLimits.DefaultMaxStallCount)
    {
        this._maxStalls = maxStalls;
        return this;
    }

    /// <summary>
    /// If <see langword="true"/>, requires human approval of the initial plan or any updates before proceeding. True by default.
    /// </summary>
    /// <param name="requirePlanSignoff"></param>
    /// <returns></returns>
    public MagenticWorkflowBuilder RequirePlanSignoff(bool requirePlanSignoff = true)
    {
        this._requirePlanSignoff = requirePlanSignoff;
        return this;
    }

    /// <summary>
    /// Designates the given <paramref name="agents"/> as sources of terminal workflow output.
    /// Calling any output-designation method (this or <see cref="WithIntermediateOutputFrom"/>)
    /// suppresses the orchestration-specific defaults: only the user-specified designations
    /// reach the inner <see cref="WorkflowBuilder"/>.
    /// </summary>
    public MagenticWorkflowBuilder WithOutputFrom(params IEnumerable<AIAgent> agents)
    {
        Throw.IfNull(agents);
        this._outputDesignations ??= new(AIAgentIDEqualityComparer.Instance);
        foreach (AIAgent agent in agents)
        {
            Throw.IfNull(agent, nameof(agents));
            if (!this._outputDesignations.ContainsKey(agent))
            {
                this._outputDesignations[agent] = [];
            }
        }
        return this;
    }

    /// <summary>
    /// Designates the given <paramref name="agents"/> as sources of <b>intermediate</b> workflow output.
    /// See <see cref="WithOutputFrom"/> for the defaults-suppression semantics.
    /// </summary>
    public MagenticWorkflowBuilder WithIntermediateOutputFrom(IEnumerable<AIAgent> agents)
    {
        Throw.IfNull(agents);
        this._outputDesignations ??= new(AIAgentIDEqualityComparer.Instance);
        foreach (AIAgent agent in agents)
        {
            Throw.IfNull(agent, nameof(agents));
            if (!this._outputDesignations.TryGetValue(agent, out HashSet<OutputTag>? tags))
            {
                tags = [];
                this._outputDesignations[agent] = tags;
            }
            tags.Add(OutputTag.Intermediate);
        }
        return this;
    }

    private WorkflowBuilder ReduceToWorkflowBuilder()
    {
        // Create a copy of the team so that improper modifications by using the builder after .Build() do not affect the
        // workflow in unexpected ways.
        List<AIAgent> team = [.. this._team];

        ExecutorBinding orchestrator = CreateOrchestratorBinding(managerAgent, team, this.Limits, this._requirePlanSignoff);
        WorkflowBuilder result = new(orchestrator);

        AIAgentHostOptions options = new()
        {
            ReassignOtherAgentsAsUsers = true,
            ForwardIncomingMessages = false
        };

        Dictionary<AIAgent, ExecutorBinding> teamMap = new(AIAgentIDEqualityComparer.Instance);
        List<ExecutorBinding> teamBindings = [];
        foreach (AIAgent agent in team)
        {
            ExecutorBinding binding = agent.BindAsExecutor(options);
            teamBindings.Add(binding);
            teamMap[agent] = binding;

            result.AddEdge(binding, orchestrator);
        }

        result.AddFanOutEdge(orchestrator, teamBindings);
        this.ApplyOutputDesignations(result, orchestrator, teamMap);

        if (!string.IsNullOrWhiteSpace(this._name))
        {
            result.WithName(this._name);
        }

        if (!string.IsNullOrWhiteSpace(this._description))
        {
            result.WithDescription(this._description);
        }

        return result;
    }

    private void ApplyOutputDesignations(
        WorkflowBuilder builder,
        ExecutorBinding orchestrator,
        Dictionary<AIAgent, ExecutorBinding> teamMap)
    {
        if (this._outputDesignations is null)
        {
            // Defaults (matches Python Magentic orchestration):
            //   orchestrator -> terminal output
            //   team members -> intermediate output
            builder.WithOutputFrom(orchestrator);
            if (teamMap.Count > 0)
            {
                builder.WithIntermediateOutputFrom([.. teamMap.Values]);
            }
            return;
        }

        foreach (AIAgent agent in this._outputDesignations.Keys)
        {
            if (!teamMap.TryGetValue(agent, out ExecutorBinding? binding))
            {
                throw new InvalidOperationException(
                    $"Output designation references agent '{agent.Name ?? agent.Id}', which is not a participant in this Magentic workflow.");
            }

            HashSet<OutputTag> tags = this._outputDesignations[agent];
            if (tags.Count == 0)
            {
                builder.WithOutputFrom(binding);
            }
            else
            {
                foreach (OutputTag tag in tags)
                {
                    builder.WithOutputFrom(binding, tag);
                }
            }
        }
    }

    /// <inheritdoc cref="WorkflowBuilder.Build"/>
    public Workflow Build()
    {
        if (this._team.Count == 0)
        {
            throw new InvalidOperationException("At least one participant must be added via AddParticipants() before building the workflow.");
        }

        return this.ReduceToWorkflowBuilder().Build();
    }

    private TaskLimits Limits => new(
        MaxRoundCount: this._maxRounds,
        MaxResetCount: this._maxResets,
        MaxStallCount: this._maxStalls);

    private static ExecutorBinding CreateOrchestratorBinding(AIAgent managerAgent, List<AIAgent> team, TaskLimits limits, bool requirePlanSignoff)
    {
        ExecutorFactoryFunc factory = CreateOrchestratorAsync;
        return factory.BindExecutor(nameof(MagenticOrchestrator));

        ValueTask<MagenticOrchestrator> CreateOrchestratorAsync(ExecutorConfig<ExecutorOptions> options, string sessionId)
        {
            return new(new MagenticOrchestrator(managerAgent, team, limits, requirePlanSignoff));
        }
    }
}
