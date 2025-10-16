using Azure.AI.AgentsHosting.Ingress.Common.Id;

namespace Azure.AI.AgentsHosting.Ingress.Invocation;

public class AgentInvocationContext(IIdGenerator idGenerator,
    string responseId,
    string conversationId)
{
    private static readonly AsyncLocal<AgentInvocationContext?> _current = new();

    public static AgentInvocationContext? Current => _current.Value;

    internal static IAsyncDisposable Setup(AgentInvocationContext context)
    {
        var previous = _current.Value;
        _current.Value = context;
        return new ScopedContext(previous);
    }

    public IIdGenerator IdGenerator { get; } = idGenerator;

    public string ResponseId { get; } = responseId;

    public string ConversationId { get; } = conversationId;

    private sealed class ScopedContext(AgentInvocationContext? previous) : IAsyncDisposable
    {
        public ValueTask DisposeAsync()
        {
            _current.Value = previous;
            return ValueTask.CompletedTask;
        }
    }
}
