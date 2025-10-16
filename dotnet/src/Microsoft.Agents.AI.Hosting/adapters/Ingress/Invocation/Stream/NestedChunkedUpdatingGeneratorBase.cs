using System.Collections.Generic;
using System.Runtime.CompilerServices;

using Azure.AI.AgentsHosting.Ingress.Common;

namespace Azure.AI.AgentsHosting.Ingress.Invocation.Stream;

/// <summary>
/// Base class for generators that create nested events from chunked updates.
/// </summary>
/// <typeparam name="TAggregate">The type of aggregate to generate.</typeparam>
/// <typeparam name="TUpdate">The type of update to process.</typeparam>
public abstract class NestedChunkedUpdatingGeneratorBase<TAggregate, TUpdate> : NestedStreamEventGeneratorBase<TAggregate>
    where TAggregate : class
{
    /// <summary>
    /// Gets or sets the updates to process.
    /// </summary>
    public required IAsyncEnumerable<TUpdate> Updates { get; init; }

    /// <summary>
    /// Gets the sequence number generator for groups.
    /// </summary>
    protected ISequenceNumber GroupSeq { get; } = SequenceNumberFactory.Default;

    private bool IsChanged(TUpdate? previous, TUpdate? current) => previous != null && current != null && this.Changed(previous, current);

    /// <summary>
    /// Determines if two updates are different.
    /// </summary>
    /// <param name="previous">The previous update.</param>
    /// <param name="current">The current update.</param>
    /// <returns>True if the updates are different; otherwise, false.</returns>
    protected abstract bool Changed(TUpdate previous, TUpdate current);

    /// <summary>
    /// Creates a group from an update sequence.
    /// </summary>
    /// <param name="updateGroup">The group of updates.</param>
    /// <returns>A nested events group.</returns>
    protected abstract NestedEventsGroup<TAggregate> CreateGroup(IAsyncEnumerable<TUpdate> updateGroup);

    /// <inheritdoc/>
    public override async IAsyncEnumerable<NestedEventsGroup<TAggregate>> GenerateAsync()
    {
#pragma warning disable CA2007 // Consider calling ConfigureAwait on the awaited task
        await foreach (var updateGroup in this.Updates.ChunkOnChangeAsync(IsChanged, cancellationToken: this.CancellationToken))
        {
            this.CancellationToken.ThrowIfCancellationRequested();
            yield return CreateGroup(updateGroup);
        }
#pragma warning restore CA2007
    }
}
