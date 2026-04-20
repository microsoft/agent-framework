// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

using ExecutorFactoryFunc = System.Func<Microsoft.Agents.AI.Workflows.ExecutorConfig<Microsoft.Agents.AI.Workflows.ExecutorOptions>,
                                        string,
                                        System.Threading.Tasks.ValueTask<Microsoft.Agents.AI.Workflows.Specialized.HandoffAgentExecutor>>;

namespace Microsoft.Agents.AI.Workflows;

internal static class DiagnosticConstants
{
    public const string ExperimentalFeatureDiagnostic = "MAAIW001";
}

/// <inheritdoc/>
[Obsolete("Prefer HandoffWorkflowBuilder (no 's') instead, which has the same API but the preferred name. This will be removed in a future release before GA.")]
#pragma warning disable MAAIW001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
public sealed class HandoffsWorkflowBuilder(AIAgent initialAgent) : HandoffWorkflowBuilderCore<HandoffsWorkflowBuilder>(initialAgent)
#pragma warning restore MAAIW001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
{
}

/// <inheritdoc/>
[Experimental(DiagnosticConstants.ExperimentalFeatureDiagnostic)]
public sealed class HandoffWorkflowBuilder(AIAgent initialAgent) : HandoffWorkflowBuilderCore<HandoffWorkflowBuilder>(initialAgent)
{
}

/// <summary>
/// Provides a builder for specifying the handoff relationships between agents and building the resulting workflow.
/// </summary>
[Experimental(DiagnosticConstants.ExperimentalFeatureDiagnostic)]
public class HandoffWorkflowBuilderCore<TBuilder> where TBuilder : HandoffWorkflowBuilderCore<TBuilder>
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

    private Dictionary<string, ExecutorBinding> CreateExecutorBindings(WorkflowBuilder builder)
    {
        HandoffAgentExecutorOptions options = new(this.HandoffInstructions,
                                                  this._emitAgentResponseEvents,
                                                  this._emitAgentResponseUpdateEvents,
                                                  this._toolCallFilteringBehavior);

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
            if (!this._targets.TryGetValue(agent, out HashSet<HandoffTarget>? handoffs))
            {
                handoffs = new();
            }

            // Use the ExecutorId as the placeholder id for a (possibly) future-bound factory
            builder.AddSwitch(HandoffAgentExecutor.IdFor(agent), (SwitchBuilder sb) =>
            {
                foreach (HandoffTarget handoff in handoffs)
                {
                    sb.AddCase<HandoffState>(state => state?.RequestedHandoffTargetAgentId == handoff.Target.Id, // Use AgentId for target matching
                                             HandoffAgentExecutor.IdFor(handoff.Target)); // Use ExecutorId in for routing at the workflow level
                }

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

    /// <summary>
    /// Builds a <see cref="Workflow"/> composed of agents that operate via handoffs, with the next
    /// agent to process messages selected by the current agent.
    /// </summary>
    /// <returns>The workflow built based on the handoffs in the builder.</returns>
    public Workflow Build()
    {
        HandoffStartExecutor start = new(this._returnToPrevious);
        HandoffEndExecutor end = new(this._returnToPrevious);
        WorkflowBuilder builder = new(start);

        // Create an factory-based ExecutorBinding for each agent.
        Dictionary<string, ExecutorBinding> executors = this.CreateExecutorBindings(builder);

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

        // Build the workflow.
        return builder.WithOutputFrom(end).Build();
    }
}
