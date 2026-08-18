// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Specialized.Magentic;
using Microsoft.Shared.DiagnosticIds;

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
public class MagenticWorkflowBuilder(AIAgent managerAgent) : OrchestrationBuilderBase<MagenticWorkflowBuilder>
{
    private readonly List<AIAgent> _team = new();
    private int _maxStalls = TaskLimits.DefaultMaxStallCount;
    private int? _maxRounds;
    private int? _maxResets;
    private bool _requirePlanSignoff = true;
    private string? _responseLanguage;
    private MagenticPromptOverrides? _promptOverrides;

    /// <inheritdoc cref="GroupChatWorkflowBuilder.AddParticipants(IEnumerable{AIAgent})"/>
    public MagenticWorkflowBuilder AddParticipants(params IEnumerable<AIAgent> agents)
    {
        this._team.AddRange(agents);
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
    /// Set the concrete language (e.g. "English", "Chinese") that the Magentic manager's internally generated
    /// messages - the task ledger, progress ledger, and final answer - must be written in.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When set, the manager is instructed to write all natural-language content in this exact language. This is more
    /// reliable than relying on the model to infer and match the request language, which some models fail to do for the
    /// progress ledger's JSON free-text fields, causing those internal messages to appear in an unexpected language.
    /// </para>
    /// <para>
    /// When left unset (the default), the built-in English prompt templates are used as-is.
    /// </para>
    /// <para>
    /// If a prompt is also overridden via <see cref="WithPromptOverrides(MagenticPromptOverrides)"/>, this language
    /// directive is appended after that override's body, so the two compose.
    /// </para>
    /// <para>
    /// This option is experimental and may change or be removed in a future release.
    /// </para>
    /// </remarks>
    /// <param name="responseLanguage">
    /// The language name to use for internally generated messages, or <see langword="null"/> to use the built-in
    /// English templates as-is.
    /// </param>
    /// <returns>This builder instance, for chaining.</returns>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public MagenticWorkflowBuilder WithResponseLanguage(string? responseLanguage = null)
    {
        this._responseLanguage = string.IsNullOrWhiteSpace(responseLanguage) ? null : responseLanguage!.Trim();
        return this;
    }

    /// <summary>
    /// Override any of the Magentic manager's internal prompt templates (task ledger, progress ledger, final answer).
    /// </summary>
    /// <remarks>
    /// <para>
    /// Any property left <see langword="null"/> on <paramref name="promptOverrides"/> keeps the built-in English
    /// template. Templates use named single-brace placeholders (e.g. <c>{task}</c>) documented on
    /// <see cref="MagenticPromptOverrides"/>; the framework substitutes them at render time.
    /// </para>
    /// <para>
    /// A progress-ledger override must contain the <c>{schema}</c> placeholder (validated at <see cref="Build"/>) so
    /// the framework can inject the JSON schema the response is parsed against.
    /// </para>
    /// <para>
    /// This option is experimental and may change or be removed in a future release.
    /// </para>
    /// </remarks>
    /// <param name="promptOverrides">The prompt overrides to apply, or <see langword="null"/> to clear any overrides.</param>
    /// <returns>This builder instance, for chaining.</returns>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public MagenticWorkflowBuilder WithPromptOverrides(MagenticPromptOverrides? promptOverrides = null)
    {
        this._promptOverrides = promptOverrides;
        return this;
    }

    private WorkflowBuilder ReduceToWorkflowBuilder()
    {
        // Create a copy of the team so that improper modifications by using the builder after .Build() do not affect the
        // workflow in unexpected ways.
        List<AIAgent> team = [.. this._team];

        ExecutorBinding orchestrator = CreateOrchestratorBinding(managerAgent, team, this.Limits, this._requirePlanSignoff, this._responseLanguage, this._promptOverrides);
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

        this.ApplyOutputDesignations(result, teamMap, "Magentic", () =>
        {
            result.WithOutputFrom(orchestrator);
            if (teamMap.Count > 0)
            {
                result.WithIntermediateOutputFrom([.. teamMap.Values]);
            }
        });

        this.ApplyMetadata(result);
        return result;
    }

    /// <inheritdoc cref="WorkflowBuilder.Build"/>
    public Workflow Build()
    {
        if (this._team.Count == 0)
        {
            throw new InvalidOperationException("At least one participant must be added via AddParticipants() before building the workflow.");
        }

        if (this._promptOverrides?.ProgressLedgerPrompt is { } progressLedgerPrompt && !progressLedgerPrompt.Contains("{schema}"))
        {
            throw new InvalidOperationException(
                "A progress-ledger prompt override must contain the '{schema}' placeholder so the required JSON schema can be injected; " +
                "otherwise progress-ledger parsing and next-speaker routing would break.");
        }

        return this.ReduceToWorkflowBuilder().Build();
    }

    private TaskLimits Limits => new(
        MaxRoundCount: this._maxRounds,
        MaxResetCount: this._maxResets,
        MaxStallCount: this._maxStalls);

    private static ExecutorBinding CreateOrchestratorBinding(AIAgent managerAgent, List<AIAgent> team, TaskLimits limits, bool requirePlanSignoff, string? responseLanguage, MagenticPromptOverrides? promptOverrides)
    {
        ExecutorFactoryFunc factory = CreateOrchestratorAsync;
        return factory.BindExecutor(nameof(MagenticOrchestrator));

        ValueTask<MagenticOrchestrator> CreateOrchestratorAsync(ExecutorConfig<ExecutorOptions> options, string sessionId)
        {
            return new(new MagenticOrchestrator(managerAgent, team, limits, requirePlanSignoff, responseLanguage, promptOverrides));
        }
    }
}
