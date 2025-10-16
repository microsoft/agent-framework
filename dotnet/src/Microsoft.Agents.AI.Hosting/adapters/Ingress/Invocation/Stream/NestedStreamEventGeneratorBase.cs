namespace Azure.AI.AgentsHosting.Ingress.Invocation.Stream;

public abstract class NestedStreamEventGeneratorBase<TAggregate>
    : INestedStreamEventGenerator<TAggregate>
    where TAggregate : class
{
    public required ISequenceNumber Seq { get; init; }

    public CancellationToken CancellationToken { get; init; } = CancellationToken.None;

    public abstract IAsyncEnumerable<NestedEventsGroup<TAggregate>> Generate();
}
