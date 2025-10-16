using Azure.AI.AgentsHosting.Ingress.Common;

namespace Azure.AI.AgentsHosting.Ingress.Invocation.Stream;

public abstract class NestedChunkedUpdatingGeneratorBase<TAggregate, TUpdate> : NestedStreamEventGeneratorBase<TAggregate>
    where TAggregate : class
{
    public required IAsyncEnumerable<TUpdate> Updates { get; init; }

    protected ISequenceNumber GroupSeq { get; } = SequenceNumberFactory.Default;

    private bool IsChanged(TUpdate? previous, TUpdate? current) => previous != null && current != null && Changed(previous, current);

    protected abstract bool Changed(TUpdate previous, TUpdate current);

    protected abstract NestedEventsGroup<TAggregate> CreateGroup(IAsyncEnumerable<TUpdate> updateGroup);

    public override async IAsyncEnumerable<NestedEventsGroup<TAggregate>> Generate()
    {
        var chunkedUpdates = Updates.ChunkOnChange(IsChanged, cancellationToken: CancellationToken);
        await foreach (var updateGroup in chunkedUpdates.WithCancellation(CancellationToken).ConfigureAwait(false))
        {
            yield return CreateGroup(updateGroup);
        }
    }
}
