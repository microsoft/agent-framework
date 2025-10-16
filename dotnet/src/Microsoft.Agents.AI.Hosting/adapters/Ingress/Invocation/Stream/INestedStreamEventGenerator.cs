using AzureAIAgents.Models;

namespace Azure.AI.AgentsHosting.Ingress.Invocation.Stream;

public interface INestedStreamEventGenerator<TAggregate> where TAggregate : class
{
    IAsyncEnumerable<NestedEventsGroup<TAggregate>> Generate();
}

public class NestedEventsGroup<T> where T : class
{
    public required Func<T> CreateAggregate { get; init; }

    public required IAsyncEnumerable<ResponseStreamEvent> Events { get; init; }
}
