// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Common fluent surface shared by every orchestration-style workflow builder:
/// human-readable name + description, and the
/// <see cref="WithOutputFrom"/> / <see cref="WithIntermediateOutputFrom"/> output-designation
/// pair with memoized defaults-suppression semantics.
/// </summary>
/// <typeparam name="TBuilder">The concrete builder type, for fluent self-return.</typeparam>
public abstract class OrchestrationBuilderBase<TBuilder>
    where TBuilder : OrchestrationBuilderBase<TBuilder>
{
    /// <summary>Optional workflow name; applied to the inner <see cref="WorkflowBuilder"/> at <c>Build()</c>.</summary>
    protected string? Name { get; private set; }

    /// <summary>Optional workflow description; applied to the inner <see cref="WorkflowBuilder"/> at <c>Build()</c>.</summary>
    protected string? Description { get; private set; }

    /// <summary>
    /// Memoized output designations. <see langword="null"/> means the user has not made any
    /// explicit designation, and the orchestration-specific defaults will be applied at
    /// <c>Build()</c> time. A non-<see langword="null"/> (possibly empty) map means the user took
    /// control and only these designations will be replayed onto the inner
    /// <see cref="WorkflowBuilder"/>. An entry's value is the set of tags requested for the
    /// agent — an empty set encodes a terminal-only designation.
    /// </summary>
    protected Dictionary<AIAgent, HashSet<OutputTag>>? OutputDesignations { get; private set; }

    /// <summary>Sets the human-readable name for the workflow.</summary>
    public TBuilder WithName(string name)
    {
        this.Name = name;
        return (TBuilder)this;
    }

    /// <summary>Sets the description for the workflow.</summary>
    public TBuilder WithDescription(string description)
    {
        this.Description = description;
        return (TBuilder)this;
    }

    /// <summary>
    /// Designates the given <paramref name="agents"/> as sources of terminal workflow output.
    /// Calling any output-designation method (this or <see cref="WithIntermediateOutputFrom"/>)
    /// suppresses the orchestration-specific defaults: only the user-specified designations
    /// reach the inner <see cref="WorkflowBuilder"/>.
    /// </summary>
    public TBuilder WithOutputFrom(params IEnumerable<AIAgent> agents)
    {
        Throw.IfNull(agents);
        this.OutputDesignations ??= new(AIAgentIDEqualityComparer.Instance);
        foreach (AIAgent agent in agents)
        {
            Throw.IfNull(agent, nameof(agents));
            if (!this.OutputDesignations.ContainsKey(agent))
            {
                this.OutputDesignations[agent] = [];
            }
        }
        return (TBuilder)this;
    }

    /// <summary>
    /// Designates the given <paramref name="agents"/> as sources of <b>intermediate</b> workflow
    /// output. See <see cref="WithOutputFrom"/> for the defaults-suppression semantics.
    /// </summary>
    public TBuilder WithIntermediateOutputFrom(IEnumerable<AIAgent> agents)
    {
        Throw.IfNull(agents);
        this.OutputDesignations ??= new(AIAgentIDEqualityComparer.Instance);
        foreach (AIAgent agent in agents)
        {
            Throw.IfNull(agent, nameof(agents));
            if (!this.OutputDesignations.TryGetValue(agent, out HashSet<OutputTag>? tags))
            {
                tags = [];
                this.OutputDesignations[agent] = tags;
            }
            tags.Add(OutputTag.Intermediate);
        }
        return (TBuilder)this;
    }

    /// <summary>
    /// Applies the optional <see cref="Name"/> and <see cref="Description"/> to <paramref name="builder"/>.
    /// Subclasses should call this from their <c>Build()</c> implementation.
    /// </summary>
    protected void ApplyMetadata(WorkflowBuilder builder)
    {
        Throw.IfNull(builder);
        if (!string.IsNullOrWhiteSpace(this.Name))
        {
            builder.WithName(this.Name!);
        }
        if (!string.IsNullOrWhiteSpace(this.Description))
        {
            builder.WithDescription(this.Description!);
        }
    }

    /// <summary>
    /// Applies the user's memoized output designations to <paramref name="builder"/>, or invokes
    /// <paramref name="applyDefaults"/> if the user made no explicit designation.
    /// </summary>
    /// <param name="builder">The inner <see cref="WorkflowBuilder"/>.</param>
    /// <param name="agentMap">Map from participating <see cref="AIAgent"/> to its bound executor.</param>
    /// <param name="orchestrationKind">Used in the not-a-participant error message (e.g. "sequential", "group chat").</param>
    /// <param name="applyDefaults">Action invoked when no explicit designation was made.</param>
    protected void ApplyOutputDesignations(
        WorkflowBuilder builder,
        IReadOnlyDictionary<AIAgent, ExecutorBinding> agentMap,
        string orchestrationKind,
        Action applyDefaults)
    {
        Throw.IfNull(builder);
        Throw.IfNull(agentMap);
        Throw.IfNull(applyDefaults);

        if (this.OutputDesignations is null)
        {
            applyDefaults();
            return;
        }

        foreach (AIAgent agent in this.OutputDesignations.Keys)
        {
            if (!agentMap.TryGetValue(agent, out ExecutorBinding? binding))
            {
                throw new InvalidOperationException(
                    $"Output designation references agent '{agent.Name ?? agent.Id}', which is not a participant in this {orchestrationKind} workflow.");
            }

            HashSet<OutputTag> tags = this.OutputDesignations[agent];
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
}
