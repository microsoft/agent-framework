// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents the binding information for a workflow executor, including its identifier, factory method, type, and
/// optional raw value.
/// </summary>
/// <param name="Id">The unique identifier for the executor in the workflow.</param>
/// <param name="FactoryAsync">A factory function that creates an instance of the executor. The function accepts two string parameters and returns
/// a ValueTask containing the created Executor instance.</param>
/// <param name="ExecutorType">The type of the executor. Must be a type derived from Executor.</param>
/// <param name="RawValue">An optional raw value associated with the binding.</param>
public abstract record class ExecutorBinding(string Id, Func<string, ValueTask<Executor>>? FactoryAsync, Type ExecutorType, object? RawValue = null)
    : IIdentified,
      IEquatable<IIdentified>,
      IEquatable<string>
{
    /// <summary>
    /// Gets a value indicating whether the binding is a placeholder (i.e., does not have a factory method defined).
    /// </summary>
    [MemberNotNullWhen(false, nameof(FactoryAsync))]
    public bool IsPlaceholder => this.FactoryAsync == null;

    /// <summary>
    /// Gets a value whether the executor created from this binding is a shared instance across all runs.
    /// </summary>
    public abstract bool IsSharedInstance { get; }

    /// <summary>
    /// Gets a value whether instances of the executor created from this binding can be used in concurrent runs
    /// from the same <see cref="Workflow"/> instance.
    /// </summary>
    public abstract bool SupportsConcurrentSharedExecution { get; }

    /// <summary>
    /// Gets a value whether instances of the executor created from this binding can be reset between subsequent
    /// runs from the same <see cref="Workflow"/> instance. This value is not relevant for executors that <see
    /// cref="SupportsConcurrentSharedExecution"/>.
    /// </summary>
    public abstract bool SupportsResetting { get; }

    /// <inheritdoc/>
    public override string ToString() => $"{this.Id}:{(this.IsPlaceholder ? ":<unbound>" : this.ExecutorType.Name)}";

    private Executor CheckId(Executor executor)
    {
        if (executor.Id != this.Id)
        {
            throw new InvalidOperationException(
                $"Executor ID mismatch: expected '{this.Id}', but got '{executor.Id}'.");
        }

        return executor;
    }

    internal async ValueTask<Executor> CreateInstanceAsync(string runId)
        => !this.IsPlaceholder
         ? this.CheckId(await this.FactoryAsync(runId).ConfigureAwait(false))
         : throw new InvalidOperationException(
                $"Cannot create executor with ID '{this.Id}': Binding ({this.GetType().Name}) is a placeholder.");

    /// <inheritdoc/>
    public virtual bool Equals(ExecutorBinding? other) =>
        other is not null && other.Id == this.Id;

    /// <inheritdoc/>
    public bool Equals(IIdentified? other) =>
        other is not null && other.Id == this.Id;

    /// <inheritdoc/>
    public bool Equals(string? other) =>
        other is not null && other == this.Id;

    internal ValueTask<bool> TryResetAsync()
    {
        // Non-shared instances do not need resetting
        if (!this.IsSharedInstance)
        {
            return new(true);
        }

        // If the executor supports concurrent use, then resetting is a no-op.
        if (!this.SupportsResetting)
        {
            return new(false);
        }

        return this.ResetCoreAsync();
    }

    /// <summary>
    /// Resets the executor's shared resources to their initial state. Must be overridden by bindings that support
    /// resetting.
    /// </summary>
    /// <exception cref="InvalidOperationException"></exception>
    protected virtual ValueTask<bool> ResetCoreAsync() => throw new InvalidOperationException("ExecutorBindings that support resetting must override ResetCoreAsync()");

    /// <inheritdoc/>
    public override int GetHashCode() => this.Id.GetHashCode();

    /// <summary>
    /// Defines an implicit conversion from an Executor to a <see cref="ExecutorBinding"/>.
    /// </summary>
    /// <param name="executor">The Executor instance to convert.</param>
    public static implicit operator ExecutorBinding(Executor executor) => executor.BindExecutor();

    /// <summary>
    /// Defines an implicit conversion from a string identifier to an <see cref="ExecutorPlaceholder"/>.
    /// </summary>
    /// <param name="id">The string identifier to convert to a placeholder.</param>
    public static implicit operator ExecutorBinding(string id) => new ExecutorPlaceholder(id);

    /// <summary>
    /// Defines an implicit conversion from a <see cref="RequestPort "/>to an <see cref="ExecutorBinding"/>.
    /// </summary>
    /// <param name="port">The RequestPort instance to convert.</param>
    public static implicit operator ExecutorBinding(RequestPort port) => port.BindAsExecutor();

    /// <summary>
    /// Defines an implicit conversion from an <see cref="AIAgent"/> to an <see cref="ExecutorBinding"/> instance.
    /// </summary>
    /// <param name="agent"></param>
    public static implicit operator ExecutorBinding(AIAgent agent) => agent.BindAsExecutor();
}
