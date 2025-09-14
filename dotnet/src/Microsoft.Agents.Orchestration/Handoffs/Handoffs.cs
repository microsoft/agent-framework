// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

#pragma warning disable CA1710 // Identifiers should have correct suffix

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Defines the orchestration handoff relationships for all agents in the system.
/// </summary>
public sealed class Handoffs :
    IReadOnlyDictionary<AIAgent, IEnumerable<Handoffs.HandoffTarget>>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="Handoffs"/> class with no handoff relationships.
    /// </summary>
    /// <param name="initialAgent">The first agent to be invoked (prior to any handoff).</param>
    private Handoffs(AIAgent initialAgent)
    {
        Throw.IfNull(initialAgent);

        this.Agents.Add(initialAgent);
        this.InitialAgent = initialAgent;
    }

    /// <summary>Gets the initial agent to which the first messages will be sent.</summary>
    public AIAgent InitialAgent { get; }

    /// <summary>Gets a collection of all handoff targets, indexed by the source of the handoffs.</summary>
    internal Dictionary<AIAgent, HashSet<HandoffTarget>> Targets { get; } = [];

    /// <summary>Gets a set of all agents involved in the handoffs, sources and targets.</summary>
    internal HashSet<AIAgent> Agents { get; } = [];

    /// <summary>
    /// Creates a new collection of handoffs that start with the specified agent.
    /// </summary>
    /// <param name="initialAgent">The initial agent.</param>
    /// <returns>The new <see cref="Handoffs"/> instance.</returns>
    public static Handoffs StartWith(AIAgent initialAgent) => new(initialAgent);

    /// <summary>Creates a new <see cref="HandoffOrchestration"/> from the described handoffs.</summary>
    /// <param name="name">An optional name for this orchestrating agent.</param>
    /// <returns>The new <see cref="HandoffOrchestration"/>.</returns>
    public HandoffOrchestration Build(string? name = null) => new(this, name);

    /// <summary>
    /// Adds handoff relationships from a source agent to one or more target agents.
    /// </summary>
    /// <param name="source">The source agent.</param>
    /// <param name="targets">The target agents to add as handoff targets for the source agent.</param>
    /// <returns>The updated <see cref="Handoffs"/> instance.</returns>
    /// <remarks>The handoff reason for each target is derived from its description or name.</remarks>
    public Handoffs Add(AIAgent source, AIAgent[] targets)
    {
        Throw.IfNull(source);
        Throw.IfNull(targets);
        if (Array.IndexOf(targets, null) >= 0)
        {
            Throw.ArgumentNullException(nameof(targets), "One or more target agents are null.");
        }

        foreach (var target in targets)
        {
            this.Add(source, target);
        }

        return this;
    }

    /// <summary>
    /// Adds a handoff relationship from a source agent to a target agent with a custom handoff reason.
    /// </summary>
    /// <param name="source">The source agent.</param>
    /// <param name="target">The target agent.</param>
    /// <param name="handoffReason">The reason the <paramref name="source"/> should hand off to the <paramref name="target"/>.</param>
    /// <returns>The updated <see cref="Handoffs"/> instance.</returns>
    public Handoffs Add(AIAgent source, AIAgent target, string? handoffReason = null)
    {
        Throw.IfNull(source);
        Throw.IfNull(target);

        this.Agents.Add(source);
        this.Agents.Add(target);

        if (!this.Targets.TryGetValue(source, out var handoffs))
        {
            this.Targets[source] = handoffs = [];
        }

        if (!handoffs.Add(new(target, handoffReason)))
        {
            Throw.InvalidOperationException($"A handoff from agent '{source.DisplayName}' to agent '{target.DisplayName}' has already been registered.");
        }

        return this;
    }

    /// <inheritdoc />
    IEnumerable<HandoffTarget> IReadOnlyDictionary<AIAgent, IEnumerable<HandoffTarget>>.this[AIAgent key] => this.Targets[key];

    /// <inheritdoc />
    IEnumerable<AIAgent> IReadOnlyDictionary<AIAgent, IEnumerable<HandoffTarget>>.Keys => this.Targets.Keys;

    /// <inheritdoc />
    IEnumerable<IEnumerable<HandoffTarget>> IReadOnlyDictionary<AIAgent, IEnumerable<HandoffTarget>>.Values => this.Targets.Values;

    /// <inheritdoc />
    int IReadOnlyCollection<KeyValuePair<AIAgent, IEnumerable<HandoffTarget>>>.Count => this.Targets.Count;

    /// <inheritdoc />
    bool IReadOnlyDictionary<AIAgent, IEnumerable<HandoffTarget>>.ContainsKey(AIAgent key) => this.Targets.ContainsKey(key);

    /// <inheritdoc />
    IEnumerator<KeyValuePair<AIAgent, IEnumerable<HandoffTarget>>> IEnumerable<KeyValuePair<AIAgent, IEnumerable<HandoffTarget>>>.GetEnumerator()
    {
        foreach (var kvp in this.Targets)
        {
            yield return new(kvp.Key, kvp.Value);
        }
    }

    /// <inheritdoc />
    IEnumerator IEnumerable.GetEnumerator() =>
        ((IReadOnlyDictionary<AIAgent, IEnumerable<HandoffTarget>>)this).GetEnumerator();

    /// <inheritdoc />
    bool IReadOnlyDictionary<AIAgent, IEnumerable<HandoffTarget>>.TryGetValue(AIAgent key, out IEnumerable<HandoffTarget> value)
    {
        if (this.Targets.TryGetValue(key, out var handoffs))
        {
            value = handoffs;
            return true;
        }

        value = [];
        return false;
    }

    /// <summary>Describes a handoff to a specific target <see cref="AIAgent"/>.</summary>
    public readonly struct HandoffTarget : IEquatable<HandoffTarget>
    {
        internal HandoffTarget(AIAgent target, string? reason = null)
        {
            this.Target = Throw.IfNull(target);

            if (string.IsNullOrWhiteSpace(reason))
            {
                reason = target.Description ?? target.Name;
                if (string.IsNullOrWhiteSpace(reason))
                {
                    Throw.InvalidOperationException(
                        $"The provided target agent with Id '{target.Id}' has no description or name, and no handoff description has been provided. " +
                        "At least one of these are required to register a handoff so that the appropriate target agent can be chosen.");
                }
            }

            this.Reason = reason!;
        }

        /// <summary>Gets the target <see cref="AIAgent"/> of the handoff.</summary>
        public AIAgent Target { get; }

        /// <summary>Gets the reason a handoff to <see cref="Target"/> should be performed.</summary>
        public string Reason { get; }

        /// <inheritdoc />
        public bool Equals(HandoffTarget other) => this.Target == other.Target;

        /// <inheritdoc />
        public override bool Equals(object? obj) => obj is HandoffTarget other && this.Equals(other);

        /// <inheritdoc />
        public override int GetHashCode() => this.Target.GetHashCode();

        /// <inheritdoc />
        public static bool operator ==(HandoffTarget left, HandoffTarget right) => left.Equals(right);

        /// <inheritdoc />
        public static bool operator !=(HandoffTarget left, HandoffTarget right) => !left.Equals(right);
    }
}
