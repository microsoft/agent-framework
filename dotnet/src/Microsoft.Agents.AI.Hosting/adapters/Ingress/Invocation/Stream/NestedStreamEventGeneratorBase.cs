using System.Collections.Generic;
using System.Threading;

namespace Azure.AI.AgentsHosting.Ingress.Invocation.Stream;

/// <summary>
/// Base class for nested stream event generators.
/// </summary>
/// <typeparam name="TAggregate">The type of aggregate to generate.</typeparam>
public abstract class NestedStreamEventGeneratorBase<TAggregate>
    : INestedStreamEventGenerator<TAggregate>
    where TAggregate : class
{
    /// <summary>
    /// Gets or sets the sequence number generator.
    /// </summary>
    public required ISequenceNumber Seq { get; init; }

    /// <summary>
    /// Gets or sets the cancellation token.
    /// </summary>
    public CancellationToken CancellationToken { get; init; } = CancellationToken.None;

    /// <inheritdoc/>
    public abstract IAsyncEnumerable<NestedEventsGroup<TAggregate>> GenerateAsync();
}
