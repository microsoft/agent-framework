// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// A class that represents a workflow that can be executed.
/// </summary>
public class Workflow
{
    /// <summary>
    /// A dictionary of executor providers, keyed by executor ID.
    /// </summary>
    internal Dictionary<string, ExecutorRegistration> Registrations { get; init; } = [];

    internal Dictionary<string, HashSet<Edge>> Edges { get; init; } = [];
    internal HashSet<string> OutputExecutors { get; init; } = [];

    /// <summary>
    /// Gets the collection of edges grouped by their source node identifier.
    /// </summary>
    public Dictionary<string, HashSet<EdgeInfo>> ReflectEdges()
    {
        return this.Edges.Keys.ToDictionary(
            keySelector: key => key,
            elementSelector: key => new HashSet<EdgeInfo>(this.Edges[key].Select(RepresentationExtensions.ToEdgeInfo))
        );
    }

    internal Dictionary<string, RequestPort> Ports { get; init; } = [];

    /// <summary>
    /// Gets the collection of external request ports, keyed by their ID.
    /// </summary>
    /// <remarks>
    /// Each port has a corresponding entry in the <see cref="Registrations"/> dictionary.
    /// </remarks>
    public Dictionary<string, RequestPortInfo> ReflectPorts()
    {
        return this.Ports.Keys.ToDictionary(
            keySelector: key => key,
            elementSelector: key => this.Ports[key].ToPortInfo()
        );
    }

    /// <summary>
    /// Gets the identifier of the starting executor of the workflow.
    /// </summary>
    public string StartExecutorId { get; }

    /// <summary>
    /// Gets the optional human-readable name of the workflow.
    /// </summary>
    public string? Name { get; internal init; }

    /// <summary>
    /// Gets the optional description of what the workflow does.
    /// </summary>
    public string? Description { get; internal init; }

    internal bool AllowConcurrent => this.Registrations.Values.All(registration => registration.SupportsConcurrent);

    internal IEnumerable<string> NonConcurrentExecutorIds =>
        this.Registrations.Values.Where(r => !r.SupportsConcurrent).Select(r => r.Id);

    /// <summary>
    /// Initializes a new instance of the <see cref="Workflow"/> class with the specified starting executor identifier
    /// and input type.
    /// </summary>
    /// <param name="startExecutorId">The unique identifier of the starting executor for the workflow. Cannot be <c>null</c>.</param>
    /// <param name="name">Optional human-readable name for the workflow.</param>
    /// <param name="description">Optional description of what the workflow does.</param>
    internal Workflow(string startExecutorId, string? name = null, string? description = null)
    {
        this.StartExecutorId = Throw.IfNull(startExecutorId);
        this.Name = name;
        this.Description = description;
    }

    /// <summary>
    /// Attempts to promote the current workflow to a type pre-checked instance that can handle input of type <typeparamref name="TInput"/>.
    /// </summary>
    /// <typeparam name="TInput">The desired input type.</typeparam>
    /// <returns>A type-parametrized workflow definitely able to process input of type <typeparamref name="TInput"/> or
    /// <see langword="null" /> if the workflow does not accept that type of input.</returns>
    /// <exception cref="InvalidOperationException"></exception>
    internal async ValueTask<Workflow<TInput>?> TryPromoteAsync<TInput>()
    {
        // Grab the start node, and make sure it has the right type?
        if (!this.Registrations.TryGetValue(this.StartExecutorId, out ExecutorRegistration? startRegistration))
        {
            // TODO: This should never be able to be hit
            throw new InvalidOperationException($"Start executor with ID '{this.StartExecutorId}' is not bound.");
        }

        // TODO: Can we cache this somehow to avoid having to instantiate a new one when running?
        // Does that break some user expectations?
        Executor startExecutor = await startRegistration.CreateInstanceAsync(string.Empty).ConfigureAwait(false);

        if (!startExecutor.InputTypes.Any(t => t.IsAssignableFrom(typeof(TInput))))
        {
            // We have no handlers for the input type T, which means the built workflow will not be able to
            // process messages of the desired type
            return null;
        }

        return new Workflow<TInput>(this.StartExecutorId)
        {
            Registrations = this.Registrations,
            Edges = this.Edges,
            Ports = this.Ports,
            OutputExecutors = this.OutputExecutors
        };
    }

    private bool _needsReset;
    private bool IsResettable => this.Registrations.Values.All(registration => !registration.IsUnresettableSharedInstance);

    private async ValueTask<bool> TryResetExecutorRegistrationsAsync()
    {
        if (this.IsResettable)
        {
            foreach (ExecutorRegistration registration in this.Registrations.Values)
            {
                if (!await registration.TryResetAsync().ConfigureAwait(false))
                {
                    return false;
                }
            }

            this._needsReset = false;
            return true;
        }

        return false;
    }

    private object? _ownerToken;
    private bool _ownedAsSubworkflow;

    internal void CheckOwnership(object? existingOwnershipSignoff = null)
    {
        object? maybeOwned = Volatile.Read(ref this._ownerToken);
        if (!ReferenceEquals(maybeOwned, existingOwnershipSignoff))
        {
            throw new InvalidOperationException($"Existing ownership does not match check value. {Summarize(maybeOwned)} vs. {Summarize(existingOwnershipSignoff)}");
        }

        string Summarize(object? maybeOwnerToken) => maybeOwnerToken switch
        {
            string s => $"'{s}'",
            null => "<null>",
            _ => $"{maybeOwnerToken.GetType().Name}@{maybeOwnerToken.GetHashCode()}",
        };
    }

    internal void TakeOwnership(object ownerToken, bool subworkflow = false, object? existingOwnershipSignoff = null)
    {
        object? maybeToken = Interlocked.CompareExchange(ref this._ownerToken, ownerToken, existingOwnershipSignoff);
        if (maybeToken == null && existingOwnershipSignoff != null)
        {
            // We expected to already be owned, but we were not
            throw new InvalidOperationException("Existing ownership token was provided, but the workflow is unowned.");
        }

        if (maybeToken == null && this._needsReset)
        {
            // There is no owner, but the workflow failed to reset on ownership release (because there are
            // shared executors).
            throw new InvalidOperationException(
                "Cannot reuse Workflow with shared Executor instances that do not implement IResettableExecutor."
                );
        }

        if (!ReferenceEquals(maybeToken, existingOwnershipSignoff) && !ReferenceEquals(maybeToken, ownerToken))
        {
            // Someone else owns the workflow
            Debug.Assert(maybeToken != null);
            throw new InvalidOperationException(
                (subworkflow, this._ownedAsSubworkflow) switch
                {
                    (true, true) => "Cannot use a Workflow as a subworkflow of multiple parent workflows.",
                    (true, false) => "Cannot use a running Workflow as a subworkflow.",
                    (false, true) => "Cannot directly run a Workflow that is a subworkflow of another workflow.",
                    (false, false) => "Cannot use a Workflow that is already owned by another runner or parent workflow.",
                });
        }

        this._needsReset = true;
        this._ownedAsSubworkflow = subworkflow;
    }

    [System.Diagnostics.CodeAnalysis.SuppressMessage("Maintainability", "CA1513:Use ObjectDisposedException throw helper",
            Justification = "Does not exist in NetFx 4.7.2")]
    internal async ValueTask ReleaseOwnershipAsync(object ownerToken)
    {
        object? originalToken = Interlocked.CompareExchange(ref this._ownerToken, null, ownerToken);
        if (originalToken == null)
        {
            throw new InvalidOperationException("Attempting to release ownership of a Workflow that is not owned.");
        }

        if (!ReferenceEquals(originalToken, ownerToken))
        {
            throw new InvalidOperationException("Attempt to release ownership of a Workflow by non-owner.");
        }

        await this.TryResetExecutorRegistrationsAsync().ConfigureAwait(false);
    }
}

/// <summary>
/// Represents a workflow that operates on data of type <typeparamref name="T"/>.
/// </summary>
/// <typeparam name="T">The type of input to the workflow.</typeparam>
public class Workflow<T> : Workflow
{
    /// <summary>
    /// Initializes a new instance of the <see cref="Workflow{T}"/> class with the specified starting executor identifier
    /// </summary>
    /// <param name="startExecutorId">The unique identifier of the starting executor for the workflow. Cannot be <c>null</c>.</param>
    /// <param name="name">Optional human-readable name for the workflow.</param>
    /// <param name="description">Optional description of what the workflow does.</param>
    public Workflow(string startExecutorId, string? name = null, string? description = null)
        : base(startExecutorId, name, description)
    {
    }

    /// <summary>
    /// Gets the type of input expected by the starting executor of the workflow.
    /// </summary>
    public Type InputType => typeof(T);
}
