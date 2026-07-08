// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

using ExecutorFactoryFunc = System.Func<Microsoft.Agents.AI.Workflows.ExecutorConfig<Microsoft.Agents.AI.Workflows.ExecutorOptions>,
                                        string,
                                        System.Threading.Tasks.ValueTask<Microsoft.Agents.AI.Workflows.Specialized.HandoffAgentExecutor>>;

namespace Microsoft.Agents.AI.Workflows;

/// <inheritdoc/>
[ExcludeFromCodeCoverage] // This is obsolete, and 1:1 equivalent to HandoffWorkflowBuilder (no "s")
[Obsolete("Prefer HandoffWorkflowBuilder (no 's') instead, which has the same API but the preferred name. This will be removed in a future release before GA.")]
#pragma warning disable MAAIW001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
public sealed class HandoffsWorkflowBuilder(AIAgent initialAgent) : HandoffWorkflowBuilderCore<HandoffsWorkflowBuilder>(initialAgent)
#pragma warning restore MAAIW001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
{
}

/// <inheritdoc/>
public sealed class HandoffWorkflowBuilder(AIAgent initialAgent) : HandoffWorkflowBuilderCore<HandoffWorkflowBuilder>(initialAgent)
{
}

/// <summary>
/// Provides a builder for specifying the handoff relationships between agents and building the resulting workflow.
/// </summary>
public class HandoffWorkflowBuilderCore<TBuilder> : OrchestrationBuilderBase<TBuilder>
    where TBuilder : HandoffWorkflowBuilderCore<TBuilder>
{
    /// <summary>
    /// The prefix for function calls that trigger handoffs to other agents; the full name is then `{FunctionPrefix}&lt;agent_id&gt;`,
    /// where `&lt;agent_id&gt;` is the ID of the target agent to hand off to.
    /// </summary>
    public const string FunctionPrefix = "handoff_to_";

    private readonly AIAgent _initialAgent;
    private readonly Dictionary<AIAgent, HashSet<HandoffTarget>> _targets = [];
    private readonly HashSet<AIAgent> _allAgents = new(AIAgentIDEqualityComparer.Instance);

    private bool _emitAgentResponseEvents;
    private bool _emitAgentResponseUpdateEvents;
    private HandoffToolCallFilteringBehavior _toolCallFilteringBehavior = HandoffToolCallFilteringBehavior.HandoffOnly;
    private bool _returnToPrevious;

    // Autonomous mode configuration. When enabled, an agent's response that doesn't include a
    // handoff triggers another invocation of that same agent with the continuation prompt, up to
    // the configured turn limit per workflow turn. Optional per-agent overrides may further restrict
    // which agents have autonomous mode enabled, or override the turn limit / continuation prompt
    // on a per-agent basis.
    private bool _autonomousMode;
    private int _autonomousTurnLimit = HandoffWorkflowBuilderDefaults.DefaultAutonomousTurnLimit;
    private string _autonomousContinuationPrompt = HandoffWorkflowBuilderDefaults.DefaultAutonomousContinuationPrompt;
    private HashSet<string>? _autonomousEnabledAgentIds;
    private readonly Dictionary<string, int> _autonomousTurnLimitsByAgentId = [];
    private readonly Dictionary<string, string> _autonomousContinuationPromptsByAgentId = [];

    // Termination condition. Evaluated after an agent response that does not request a handoff;
    // if true, the workflow ends (and the autonomous loop, if any, terminates).
    private Func<IReadOnlyList<ChatMessage>, ValueTask<bool>>? _terminationCondition;

    /// <summary>
    /// Initializes a new instance of the <see cref="HandoffsWorkflowBuilder"/> class with no handoff relationships.
    /// </summary>
    /// <param name="initialAgent">The first agent to be invoked (prior to any handoff).</param>
    internal HandoffWorkflowBuilderCore(AIAgent initialAgent)
    {
        this._initialAgent = initialAgent;
        this._allAgents.Add(initialAgent);
    }

    /// <summary>
    /// Gets or sets additional instructions to provide to an agent that has handoffs about how and when to perform them.
    /// </summary>
    /// <remarks>
    /// By default, simple instructions are included. This may be set to <see langword="null"/> to avoid including
    /// any additional instructions, or may be customized to provide more specific guidance.
    /// </remarks>
    public string? HandoffInstructions { get; private set; } = DefaultHandoffInstructions;

    private const string DefaultHandoffInstructions =
        $"""
              You are one agent in a multi-agent system. You can hand off the conversation to another agent if appropriate. Handoffs are achieved
              by calling a handoff function, named in the form `{FunctionPrefix}<agent_id>`; the description of the function provides details on the
              target agent of that handoff. Handoffs between agents are handled seamlessly in the background; never mention or narrate these handoffs
              in your conversation with the user.
              """;

    /// <summary>
    /// Sets instructions to provide to each agent that has handoffs about how and when to perform them.
    /// </summary>
    /// <remarks>
    /// In the vast majority of cases, the <see cref="DefaultHandoffInstructions"/> will be sufficient, and there will be no need to customize.
    /// If you do provide alternate instructions, remember to explain the mechanics of the handoff function tool call, using see
    /// <see cref="FunctionPrefix"/> constant.
    /// </remarks>
    /// <param name="instructions">The instructions to provide, or <see langword="null"/> to restore the default instructions.</param>
    public TBuilder WithHandoffInstructions(string? instructions)
    {
        this.HandoffInstructions = instructions ?? DefaultHandoffInstructions;
        return (TBuilder)this;
    }

    /// <summary>
    /// Sets a value indicating whether agent streaming update events should be emitted during execution.
    /// If <see langword="null"/>, the value will be taken from the <see cref="TurnToken"/>
    /// </summary>
    /// <param name="emitAgentResponseUpdateEvents"></param>
    /// <returns></returns>
    public TBuilder EmitAgentResponseUpdateEvents(bool emitAgentResponseUpdateEvents = true)
    {
        this._emitAgentResponseUpdateEvents = emitAgentResponseUpdateEvents;
        return (TBuilder)this;
    }

    /// <summary>
    /// Sets a value indicating whether aggregated agent response events should be emitted during execution.
    /// </summary>
    /// <param name="emitAgentResponseEvents"></param>
    /// <returns></returns>
    public TBuilder EmitAgentResponseEvents(bool emitAgentResponseEvents = true)
    {
        this._emitAgentResponseEvents = emitAgentResponseEvents;
        return (TBuilder)this;
    }

    /// <summary>
    /// Sets the behavior for filtering <see cref="FunctionCallContent"/> and <see cref="ChatRole.Tool"/> contents from
    /// <see cref="ChatMessage"/>s flowing through the handoff workflow. Defaults to <see cref="HandoffToolCallFilteringBehavior.HandoffOnly"/>.
    /// </summary>
    /// <param name="behavior">The filtering behavior to apply.</param>
    public TBuilder WithToolCallFilteringBehavior(HandoffToolCallFilteringBehavior behavior)
    {
        this._toolCallFilteringBehavior = behavior;
        return (TBuilder)this;
    }

    /// <summary>
    /// Configures the workflow so that subsequent user turns route directly back to the specialist agent
    /// that handled the previous turn, rather than always routing through the initial (coordinator) agent.
    /// </summary>
    /// <returns>The updated <see cref="HandoffsWorkflowBuilder"/> instance.</returns>
    public TBuilder EnableReturnToPrevious()
    {
        this._returnToPrevious = true;
        return (TBuilder)this;
    }

    /// <summary>
    /// Adds handoff relationships from a source agent to one or more target agents.
    /// </summary>
    /// <param name="from">The source agent.</param>
    /// <param name="to">The target agents to add as handoff targets for the source agent.</param>
    /// <returns>The updated <see cref="HandoffsWorkflowBuilder"/> instance.</returns>
    /// <remarks>The handoff reason for each target in <paramref name="to"/> is derived from that agent's description or name.</remarks>
    public TBuilder WithHandoffs(AIAgent from, IEnumerable<AIAgent> to)
    {
        Throw.IfNull(from);
        Throw.IfNull(to);

        foreach (var target in to)
        {
            if (target is null)
            {
                Throw.ArgumentNullException(nameof(to), "One or more target agents are null.");
            }

            this.WithHandoff(from, target);
        }

        return (TBuilder)this;
    }

    /// <summary>
    /// Adds handoff relationships from one or more sources agent to a target agent.
    /// </summary>
    /// <param name="from">The source agents.</param>
    /// <param name="to">The target agent to add as a handoff target for each source agent.</param>
    /// <param name="handoffReason">
    /// The reason the <paramref name="from"/> should hand off to the <paramref name="to"/>.
    /// If <see langword="null"/>, the reason is derived from <paramref name="to"/>'s description or name.
    /// </param>
    /// <returns>The updated <see cref="HandoffsWorkflowBuilder"/> instance.</returns>
    public TBuilder WithHandoffs(IEnumerable<AIAgent> from, AIAgent to, string? handoffReason = null)
    {
        Throw.IfNull(from);
        Throw.IfNull(to);

        foreach (var source in from)
        {
            if (source is null)
            {
                Throw.ArgumentNullException(nameof(from), "One or more source agents are null.");
            }

            this.WithHandoff(source, to, handoffReason);
        }

        return (TBuilder)this;
    }

    /// <summary>
    /// Adds a handoff relationship from a source agent to a target agent with a custom handoff reason.
    /// </summary>
    /// <param name="from">The source agent.</param>
    /// <param name="to">The target agent.</param>
    /// <param name="handoffReason">
    /// The reason the <paramref name="from"/> should hand off to the <paramref name="to"/>.
    /// If <see langword="null"/>, the reason is derived from <paramref name="to"/>'s description or name.
    /// </param>
    /// <returns>The updated <see cref="HandoffsWorkflowBuilder"/> instance.</returns>
    public TBuilder WithHandoff(AIAgent from, AIAgent to, string? handoffReason = null)
    {
        Throw.IfNull(from);
        Throw.IfNull(to);

        this._allAgents.Add(from);
        this._allAgents.Add(to);

        if (!this._targets.TryGetValue(from, out var handoffs))
        {
            this._targets[from] = handoffs = [];
        }

        if (string.IsNullOrWhiteSpace(handoffReason))
        {
            handoffReason = (string.IsNullOrWhiteSpace(to.Description) ? null : to.Description)
                         ?? (string.IsNullOrWhiteSpace(to.Name) ? null : $"handoff to {to.Name}")
                         ?? to.GetService<ChatClientAgent>()?.Instructions;

            if (string.IsNullOrWhiteSpace(handoffReason))
            {
                Throw.ArgumentException(
                    nameof(to),
                    $"The provided target agent '{(string.IsNullOrWhiteSpace(to.Name) ? to.Id : to.Name)}' has no description, name, or instructions, and no " +
                    "handoff description has been provided. At least one of these is required to register a handoff so that the appropriate target agent can " +
                    "be chosen.");
            }
        }

        if (!handoffs.Add(new(to, handoffReason)))
        {
            Throw.InvalidOperationException($"A handoff from agent '{from.Name ?? from.Id}' to agent '{to.Name ?? to.Id}' has already been registered.");
        }

        return (TBuilder)this;
    }

    /// <summary>
    /// Adds the specified <paramref name="agents"/> as participants in the handoff workflow without
    /// defining handoff relationships for them.
    /// </summary>
    /// <param name="agents">The agents to add as participants.</param>
    /// <returns>The updated builder instance.</returns>
    /// <remarks>
    /// Use this method when you want a participant to be part of the workflow but you have not
    /// explicitly defined handoff edges via <see cref="WithHandoff(AIAgent, AIAgent, string?)"/>.
    /// When no handoffs are explicitly defined (default handoffs), all registered participants are
    /// automatically wired so that every agent can hand off to every other agent.
    /// </remarks>
    public TBuilder AddParticipants(params IEnumerable<AIAgent> agents)
    {
        Throw.IfNull(agents);

        foreach (AIAgent agent in agents)
        {
            if (agent is null)
            {
                Throw.ArgumentNullException(nameof(agents), "One or more agents are null.");
            }

            this._allAgents.Add(agent);
        }

        return (TBuilder)this;
    }

    /// <summary>
    /// Enables autonomous mode for the handoff workflow.
    /// </summary>
    /// <remarks>
    /// <para>
    /// In autonomous mode, an agent whose response does not include a handoff is invoked again with
    /// a continuation prompt, up to a configured turn limit. The autonomous loop for a given agent
    /// ends when the agent invokes a handoff tool, the configured termination condition fires, or
    /// the per-agent turn limit is reached — at which point the workflow yields control back to the
    /// caller.
    /// </para>
    /// <para>
    /// <b>Per-agent turn counting.</b> Autonomous-turn counters are tracked independently per agent
    /// in the shared handoff state. A counter is incremented each time the End executor loops
    /// control back to its source agent, and reset to zero in three cases: (1) when that agent
    /// requests a handoff, (2) when its autonomous loop terminates (limit reached, termination
    /// fires, or autonomous mode disabled for that agent), and (3) at the start of every fresh user
    /// turn. As a consequence, if agent A loops twice and then hands off to B, A's counter resets
    /// to zero; should control later return to A within the same user turn, A starts a new
    /// autonomous run from zero.
    /// </para>
    /// </remarks>
    /// <param name="turnLimit">
    /// The default maximum number of autonomous continuation iterations per agent per workflow
    /// turn. Applies to agents not listed in <paramref name="agentTurnLimits"/>. If
    /// <see langword="null"/>, defaults to
    /// <see cref="HandoffWorkflowBuilderDefaults.DefaultAutonomousTurnLimit"/> (50).
    /// </param>
    /// <param name="continuationPrompt">
    /// The default user-role prompt fed to an agent on each autonomous continuation. Applies to
    /// agents not listed in <paramref name="agentContinuationPrompts"/>. If <see langword="null"/>,
    /// defaults to <see cref="HandoffWorkflowBuilderDefaults.DefaultAutonomousContinuationPrompt"/>.
    /// </param>
    /// <param name="agents">
    /// Optional allow-list restricting autonomous mode to a specific subset of agents. If
    /// <see langword="null"/> or empty, autonomous mode is enabled for <i>every</i> participant.
    /// Agents not in the allow-list always yield control back to the caller after a single
    /// invocation (when they do not request a handoff).
    /// </param>
    /// <param name="agentTurnLimits">
    /// Optional per-agent turn-limit overrides. Each entry's key is the agent and its value the
    /// turn limit that overrides <paramref name="turnLimit"/> for that agent. Agents not present
    /// fall back to the default.
    /// </param>
    /// <param name="agentContinuationPrompts">
    /// Optional per-agent continuation-prompt overrides. Each entry's key is the agent and its
    /// value the continuation prompt used for that agent. Agents not present fall back to the
    /// default.
    /// </param>
    /// <returns>The updated builder instance.</returns>
    public TBuilder WithAutonomousMode(
        int? turnLimit = null,
        string? continuationPrompt = null,
        IEnumerable<AIAgent>? agents = null,
        IReadOnlyDictionary<AIAgent, int>? agentTurnLimits = null,
        IReadOnlyDictionary<AIAgent, string>? agentContinuationPrompts = null)
    {
        if (turnLimit is { } limit && limit <= 0)
        {
            Throw.ArgumentOutOfRangeException(nameof(turnLimit), "Turn limit must be greater than zero.");
        }

        this._autonomousMode = true;
        this._autonomousTurnLimit = turnLimit ?? HandoffWorkflowBuilderDefaults.DefaultAutonomousTurnLimit;
        this._autonomousContinuationPrompt = continuationPrompt ?? HandoffWorkflowBuilderDefaults.DefaultAutonomousContinuationPrompt;

        // Allow-list: null or empty means every participant has autonomous mode enabled. A non-empty
        // list restricts autonomous mode to exactly those agents.
        this._autonomousEnabledAgentIds = null;
        if (agents is not null)
        {
            HashSet<string> ids = [];
            foreach (AIAgent agent in agents)
            {
                Throw.IfNull(agent, $"{nameof(agents)} element");
                ids.Add(agent.Id);
            }

            if (ids.Count > 0)
            {
                this._autonomousEnabledAgentIds = ids;
            }
        }

        this._autonomousTurnLimitsByAgentId.Clear();
        if (agentTurnLimits is not null)
        {
            foreach (KeyValuePair<AIAgent, int> kvp in agentTurnLimits)
            {
                Throw.IfNull(kvp.Key, $"{nameof(agentTurnLimits)} key");
                if (kvp.Value <= 0)
                {
                    Throw.ArgumentOutOfRangeException(
                        nameof(agentTurnLimits),
                        $"Turn limit for agent '{kvp.Key.Name ?? kvp.Key.Id}' must be greater than zero.");
                }

                this._autonomousTurnLimitsByAgentId[kvp.Key.Id] = kvp.Value;
            }
        }

        this._autonomousContinuationPromptsByAgentId.Clear();
        if (agentContinuationPrompts is not null)
        {
            foreach (KeyValuePair<AIAgent, string> kvp in agentContinuationPrompts)
            {
                Throw.IfNull(kvp.Key, $"{nameof(agentContinuationPrompts)} key");
                Throw.IfNullOrEmpty(kvp.Value, $"{nameof(agentContinuationPrompts)} value");

                this._autonomousContinuationPromptsByAgentId[kvp.Key.Id] = kvp.Value;
            }
        }

        return (TBuilder)this;
    }

    /// <summary>
    /// Sets a synchronous termination condition for the handoff workflow.
    /// </summary>
    /// <param name="terminationCondition">
    /// A predicate that receives the current conversation and returns <see langword="true"/> if the
    /// workflow should terminate (preventing further autonomous continuation). The synchronous
    /// predicate is wrapped and forwarded to the async overload.
    /// </param>
    /// <returns>The updated builder instance.</returns>
    /// <remarks>
    /// The termination condition is evaluated after the agent produces a response that does not
    /// request a handoff. When it returns <see langword="true"/>, the workflow ends without invoking
    /// another autonomous continuation.
    /// </remarks>
    public TBuilder WithTerminationCondition(Func<IReadOnlyList<ChatMessage>, bool> terminationCondition)
    {
        Throw.IfNull(terminationCondition);

        return this.WithTerminationCondition(
            messages => new ValueTask<bool>(terminationCondition(messages)));
    }

    /// <summary>
    /// Sets an asynchronous termination condition for the handoff workflow.
    /// </summary>
    /// <param name="terminationCondition">
    /// A predicate that receives the current conversation and asynchronously returns
    /// <see langword="true"/> if the workflow should terminate (preventing further autonomous
    /// continuation).
    /// </param>
    /// <returns>The updated builder instance.</returns>
    /// <remarks>
    /// The termination condition is evaluated after the agent produces a response that does not
    /// request a handoff. When it returns <see langword="true"/>, the workflow ends without invoking
    /// another autonomous continuation.
    /// </remarks>
    public TBuilder WithTerminationCondition(Func<IReadOnlyList<ChatMessage>, ValueTask<bool>> terminationCondition)
    {
        Throw.IfNull(terminationCondition);

        this._terminationCondition = terminationCondition;
        return (TBuilder)this;
    }

    private Dictionary<string, ExecutorBinding> CreateExecutorBindings(WorkflowBuilder builder, Dictionary<AIAgent, HashSet<HandoffTarget>> effectiveTargets)
    {
        HandoffAgentExecutorOptions options = new(this.HandoffInstructions,
                                                  this._emitAgentResponseEvents,
                                                  this._emitAgentResponseUpdateEvents,
                                                  this._toolCallFilteringBehavior)
        {
            TerminationCondition = this._terminationCondition,
        };

        // There are two types of ids being used in this method, and it is critical that we are clear about
        // which one we are using, and where.
        // AgentId...: comes from AIAgent.Id, is often an unreadable machine identifier (e.g. a Guid), and is used to address
        //             the handoffs
        // ExecutorId: uses AIAgent.GetDescriptiveId() to use a friendlier name in telemetry, and is used for ExecutorBinding,
        //             which are subsequently used in building the workflow

        // The outgoing dictionary maps from AgentId => ExecutorBinding
        return this._allAgents.ToDictionary(keySelector: a => a.Id, elementSelector: CreateFactoryBinding);

        ExecutorBinding CreateFactoryBinding(AIAgent agent)
        {
            if (!effectiveTargets.TryGetValue(agent, out HashSet<HandoffTarget>? handoffs))
            {
                handoffs = new();
            }

            // Use the ExecutorId as the placeholder id for a (possibly) future-bound factory
            builder.AddSwitch(HandoffAgentExecutor.IdFor(agent), (SwitchBuilder sb) =>
            {
                foreach (HandoffTarget handoff in handoffs)
                {
                    // Each handoff case also requires the turn to NOT be terminated; otherwise the
                    // turn falls through to the default branch, which routes to HandoffEndExecutor.
                    string targetAgentId = handoff.Target.Id;
                    sb.AddCase<HandoffState>(state => state?.RequestedHandoffTargetAgentId == targetAgentId // Use AgentId for target matching
                                                  && state.IsTerminated != true,
                                             HandoffAgentExecutor.IdFor(handoff.Target)); // Use ExecutorId in for routing at the workflow level
                }

                // Default branch catches: (a) turns with no handoff requested, and (b) terminated turns
                // (whose handoff cases have been excluded above via the !IsTerminated guard).
                sb.WithDefault(HandoffEndExecutor.ExecutorId);
            });

            ExecutorFactoryFunc factory =
                (config, sessionId) => new(
                    new HandoffAgentExecutor(agent,
                                             handoffs,
                                             options));

            // Make sure to use ExecutorId when binding the executor, not AgentId
            ExecutorBinding binding = factory.BindExecutor(HandoffAgentExecutor.IdFor(agent));

            builder.BindExecutor(binding);

            return binding;
        }
    }

    private Dictionary<AIAgent, HashSet<HandoffTarget>> BuildDefaultHandoffTargets()
    {
        // Default handoffs: when the caller has not explicitly registered any handoffs via
        // WithHandoff/WithHandoffs, every registered participant is wired to hand off to every other
        // participant.
        // The handoff "reason" is derived from the target agent's description/name/instructions,
        // matching the resolution rules used in WithHandoff(). If no reason can be derived, we throw —
        // same contract as the explicit handoff path.
        Dictionary<AIAgent, HashSet<HandoffTarget>> defaultTargets = [];

        foreach (AIAgent source in this._allAgents)
        {
            HashSet<HandoffTarget> targets = [];
            foreach (AIAgent target in this._allAgents)
            {
                if (AIAgentIDEqualityComparer.Instance.Equals(source, target))
                {
                    continue;
                }

                string? reason = (string.IsNullOrWhiteSpace(target.Description) ? null : target.Description)
                              ?? (string.IsNullOrWhiteSpace(target.Name) ? null : $"handoff to {target.Name}")
                              ?? target.GetService<ChatClientAgent>()?.Instructions;

                if (string.IsNullOrWhiteSpace(reason))
                {
                    Throw.InvalidOperationException(
                        $"Cannot build default handoffs: target agent '{(string.IsNullOrWhiteSpace(target.Name) ? target.Id : target.Name)}' " +
                        "has no description, name, or instructions from which to derive a handoff reason. Either provide one of these " +
                        "on the agent, or define handoffs explicitly via WithHandoff/WithHandoffs.");
                }

                targets.Add(new HandoffTarget(target, reason));
            }

            defaultTargets[source] = targets;
        }

        return defaultTargets;
    }

    /// <summary>
    /// Builds a <see cref="Workflow"/> composed of agents that operate via handoffs, with the next
    /// agent to process messages selected by the current agent.
    /// </summary>
    /// <returns>The workflow built based on the handoffs in the builder.</returns>
    public Workflow Build()
    {
        HandoffStartExecutor start = new(this._returnToPrevious);
        HandoffEndExecutor end = new(
            returnToPrevious: this._returnToPrevious,
            autonomousMode: this._autonomousMode,
            autonomousTurnLimit: this._autonomousTurnLimit,
            autonomousContinuationPrompt: this._autonomousContinuationPrompt,
            autonomousEnabledAgentIds: this._autonomousEnabledAgentIds,
            autonomousTurnLimitsByAgentId: this._autonomousTurnLimitsByAgentId,
            autonomousContinuationPromptsByAgentId: this._autonomousContinuationPromptsByAgentId);
        WorkflowBuilder builder = new(start);

        // Default handoffs: when the caller has not explicitly registered any handoffs via
        // WithHandoff/WithHandoffs, every registered participant is wired to hand off to every other
        // participant.
        Dictionary<AIAgent, HashSet<HandoffTarget>> effectiveTargets = this._targets.Count == 0
            ? this.BuildDefaultHandoffTargets()
            : this._targets;

        // Create an factory-based ExecutorBinding for each agent.
        Dictionary<string, ExecutorBinding> executors = this.CreateExecutorBindings(builder, effectiveTargets);

        // Connect the start executor to the initial agent (or use dynamic routing when ReturnToPrevious is enabled).
        if (this._returnToPrevious)
        {
            string initialAgentId = this._initialAgent.Id;
            builder.AddSwitch(start, sb =>
            {
                foreach (var agent in this._allAgents)
                {
                    if (agent.Id != initialAgentId)
                    {
                        string agentId = agent.Id;
                        sb.AddCase<HandoffState>(state => state?.PreviousAgentId == agentId, executors[agentId]);
                    }
                }

                sb.WithDefault(executors[initialAgentId]);
            });
        }
        else
        {
            builder.AddEdge(start, executors[this._initialAgent.Id]);
        }

        // Autonomous-mode loop-back: when enabled, the End executor may emit a HandoffState targeting
        // the source agent (carrying the synthesized continuation prompt in the shared conversation).
        // A switch downstream of End routes that message back to the matching agent executor.
        if (this._autonomousMode)
        {
            builder.AddSwitch(end, sb =>
            {
                foreach (AIAgent agent in this._allAgents)
                {
                    string agentId = agent.Id;
                    sb.AddCase<HandoffState>(state => state?.RequestedHandoffTargetAgentId == agentId, executors[agentId]);
                }
            });
        }

        // Ensure the end executor is bound regardless of whether it ends up as an output
        // designation source — the user may take full control of output designations.
        builder.BindExecutor(end);

        // Build the AIAgent -> ExecutorBinding map the base helper expects.
        Dictionary<AIAgent, ExecutorBinding> agentMap = new(AIAgentIDEqualityComparer.Instance);
        foreach (AIAgent agent in this._allAgents)
        {
            agentMap[agent] = executors[agent.Id];
        }

        this.ApplyMetadata(builder);
        this.ApplyOutputDesignations(builder, agentMap, "handoff", () =>
        {
            // Defaults (matches Python's Handoff orchestration):
            //   end                  -> terminal output
            //   every handoff agent  -> intermediate output
            builder.WithOutputFrom(end);
            List<ExecutorBinding> agentBindings = [.. executors.Values];
            if (agentBindings.Count > 0)
            {
                builder.WithIntermediateOutputFrom(agentBindings);
            }
        });

        return builder.Build();
    }
}
