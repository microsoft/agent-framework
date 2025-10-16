using System.Diagnostics.CodeAnalysis;

namespace Azure.AI.AgentsHosting.Ingress.Invocation.Stream;

public interface ISequenceNumber
{
    int Current();

    int Next();
}

public static class SequenceNumberFactory
{
    public static ISequenceNumber Atomic => new AtomicSequenceNumber();

    public static ISequenceNumber Default => new DefaultSequenceNumber();
}

public class DefaultSequenceNumber : ISequenceNumber
{
    private volatile int _sequenceNumber = 0;

    public int Current() => _sequenceNumber;

    [SuppressMessage("ReSharper", "NonAtomicCompoundOperator")]
    public int Next() => _sequenceNumber++;
}

public class AtomicSequenceNumber : ISequenceNumber
{
    private volatile int _sequenceNumber = 0;

    public int Current() => _sequenceNumber;

    public int Next() => Interlocked.Increment(ref _sequenceNumber) - 1;
}
