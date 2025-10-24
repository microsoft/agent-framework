// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents the registration information for an executor, including its identifier, factory method, type, and
/// optional raw value.
/// </summary>
/// <param name="Id">The unique identifier for the executor registration.</param>
/// <param name="FactoryAsync">A factory function that creates an instance of the executor. The function accepts two string parameters and returns
/// a ValueTask containing the created Executor instance.</param>
/// <param name="ExecutorType">The type of the executor being registered. Must be a type derived from Executor.</param>
/// <param name="RawValue">An optional raw value associated with the registration. Can be used to store additional metadata or configuration.</param>
public abstract record class ExecutorRegistration(string Id, Func<string, ValueTask<Executor>>? FactoryAsync, Type ExecutorType, object? RawValue = null)
    : IIdentified,
      IEquatable<IIdentified>,
      IEquatable<string>
{
    /// <summary>
    /// Gets a value indicating whether the executor registration is unbound (i.e., does not have a factory method defined).
    /// </summary>
    [MemberNotNullWhen(false, nameof(FactoryAsync))]
    public bool IsUnbound => this.FactoryAsync == null;

    /// <summary>
    /// Gets a value whether instances of the executor created from this registration can be used in concurrent runs
    /// from the same <see cref="Workflow"/> instance.
    /// </summary>
    public abstract bool SupportsConcurrentSharedExecution { get; }

    /// <summary>
    /// Gets a value whether instances of the executor created from this registration can be reset between subsequent
    /// runs from the same <see cref="Workflow"/> instance. This value is not relevant for executors that <see
    /// cref="SupportsConcurrentSharedExecution"/>.
    /// </summary>
    public abstract bool SupportsResetting { get; }

    /// <inheritdoc/>
    public override string ToString() => $"{this.Id}:{(this.IsUnbound ? ":<unbound>" : this.ExecutorType.Name)}";

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
        => !this.IsUnbound
         ? this.CheckId(await this.FactoryAsync(runId).ConfigureAwait(false))
         : throw new InvalidOperationException(
                $"Cannot create executor with ID '{this.Id}': Registration ({this.GetType().Name}) is unbound.");

    /// <inheritdoc/>
    public virtual bool Equals(ExecutorRegistration? other) =>
        other is not null && other.Id == this.Id;

    /// <inheritdoc/>
    public bool Equals(IIdentified? other) =>
        other is not null && other.Id == this.Id;

    /// <inheritdoc/>
    public bool Equals(string? other) =>
        other is not null && other == this.Id;

    internal ValueTask<bool> TryResetAsync()
    {
        // If the executor supports concurrent use, then resetting is a no-op.
        if (this.SupportsConcurrentSharedExecution)
        {
            return new(true);
        }

        if (!this.SupportsResetting)
        {
            return new(false);
        }

        return this.ResetCoreAsync();
    }

    /// <summary>
    /// Resets the executor's shared resources to their initial state. Must be overridden by registrations that support
    /// resetting.
    /// </summary>
    /// <exception cref="InvalidOperationException"></exception>
    protected virtual ValueTask<bool> ResetCoreAsync() => throw new InvalidOperationException("Executor Registrations that support resetting must override ResetCoreAsync()");

    /// <inheritdoc/>
    public override int GetHashCode() => this.Id.GetHashCode();

    /// <summary>
    /// Defines an implicit conversion from an Executor to a ExecutorRegistrationEx instance.
    /// </summary>
    /// <remarks>This operator enables seamless conversion between Executor and NodeRegistrationEx types,
    /// allowing an Executor to be used wherever a NodeRegistrationEx is expected without explicit casting.</remarks>
    /// <param name="executor">The Executor instance to convert.</param>
    public static implicit operator ExecutorRegistration(Executor executor) => executor.RegisterExecutor();

    /// <summary>
    /// Defines an implicit conversion from a string identifier to an instance of ExecutorRegistrationEx.
    /// </summary>
    /// <remarks>This operator allows a string to be used wherever an ExecutorRegistrationEx is expected,
    /// enabling more concise and readable code when working with identifiers.</remarks>
    /// <param name="id">The string identifier to convert to an ExecutorRegistrationEx instance.</param>
    public static implicit operator ExecutorRegistration(string id) => new PlaceholderRegistration(id);

    /// <summary>
    /// Defines an implicit conversion from a RequestPort to an ExecutorRegistrationIsh instance.
    /// </summary>
    /// <remarks>This operator enables seamless assignment of a RequestPort to an ExecutorRegistrationIsh
    /// without requiring an explicit cast. The resulting ExecutorRegistrationIsh will encapsulate the provided
    /// RequestPort.</remarks>
    /// <param name="port">The RequestPort instance to convert.</param>
    public static implicit operator ExecutorRegistration(RequestPort port) => port.AsExecutor();

    /// <summary>
    /// Defines an implicit conversion from an AIAgent to an ExecutorRegistrationIsh instance.
    /// </summary>
    /// <param name="agent"></param>
    public static implicit operator ExecutorRegistration(AIAgent agent) => agent.AsExecutor();
}
