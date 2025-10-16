using System;
using System.Threading;
using System.Threading.Tasks;

using Azure.AI.AgentsHosting.Ingress.Common.Id;

namespace Azure.AI.AgentsHosting.Ingress.Invocation;

/// <summary>
/// Represents the context for an agent invocation.
/// </summary>
/// <param name="idGenerator">The ID generator.</param>
/// <param name="responseId">The response ID.</param>
/// <param name="conversationId">The conversation ID.</param>
public class AgentInvocationContext(IIdGenerator idGenerator,
    string responseId,
    string conversationId)
{
    private static readonly AsyncLocal<AgentInvocationContext?> _current = new();

    /// <summary>
    /// Gets the current agent invocation context.
    /// </summary>
    public static AgentInvocationContext? Current => _current.Value;

    internal static IAsyncDisposable Setup(AgentInvocationContext context)
    {
        var previous = _current.Value;
        _current.Value = context;
        return new ScopedContext(previous);
    }

    /// <summary>
    /// Gets the ID generator for this context.
    /// </summary>
    public IIdGenerator IdGenerator { get; } = idGenerator;

    /// <summary>
    /// Gets the response ID.
    /// </summary>
    public string ResponseId { get; } = responseId;

    /// <summary>
    /// Gets the conversation ID.
    /// </summary>
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
