// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Specialized.Magentic;

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
public class MagenticWorkflowBuilder(AIAgent managerAgent)
{
    private readonly List<AIAgent> _team = new();
    private string? _name;
    private string? _description;
    private int _maxStalls = TaskLimits.DefaultMaxStallCount;
    private int? _maxRounds;
    private int? _maxResets;
    private bool _requirePlanSignoff = true;

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

        List<ExecutorBinding> teamBindings = [];
        foreach (AIAgent agent in team)
        {
            ExecutorBinding binding = agent.BindAsExecutor(options);
            teamBindings.Add(binding);

            result.AddEdge(binding, orchestrator);
        }

        result.AddFanOutEdge(orchestrator, teamBindings)
              .WithOutputFrom(orchestrator);

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

    /// <inheritdoc cref="WorkflowBuilder.Build"/>
    public Workflow Build() => this.ReduceToWorkflowBuilder().Build();

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
