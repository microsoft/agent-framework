using System.Diagnostics.CodeAnalysis;
using System.Threading;

namespace Azure.AI.AgentsHosting.Ingress.Invocation.Stream;

/// <summary>
/// Defines a sequence number generator.
/// </summary>
public interface ISequenceNumber
{
    /// <summary>
    /// Gets the current sequence number without incrementing.
    /// </summary>
    /// <returns>The current sequence number.</returns>
    int Current();

    /// <summary>
    /// Gets the next sequence number.
    /// </summary>
    /// <returns>The next sequence number.</returns>
    int GetNext();
}

/// <summary>
/// Factory for creating sequence number generators.
/// </summary>
public static class SequenceNumberFactory
{
    /// <summary>
    /// Gets an atomic (thread-safe) sequence number generator.
    /// </summary>
    public static ISequenceNumber Atomic => new AtomicSequenceNumber();

    /// <summary>
    /// Gets a default sequence number generator.
    /// </summary>
    public static ISequenceNumber Default => new DefaultSequenceNumber();
}

/// <summary>
/// Implements a non-atomic sequence number generator.
/// </summary>
public class DefaultSequenceNumber : ISequenceNumber
{
    private volatile int _sequenceNumber;

    /// <inheritdoc/>
    public int Current() => this._sequenceNumber;

    /// <inheritdoc/>
    [SuppressMessage("ReSharper", "NonAtomicCompoundOperator")]
    public int GetNext() => this._sequenceNumber++;
}

/// <summary>
/// Implements a thread-safe atomic sequence number generator.
/// </summary>
public class AtomicSequenceNumber : ISequenceNumber
{
    private volatile int _sequenceNumber;

    /// <inheritdoc/>
    public int Current() => this._sequenceNumber;

    /// <inheritdoc/>
    public int GetNext() => Interlocked.Increment(ref this._sequenceNumber) - 1;
}
