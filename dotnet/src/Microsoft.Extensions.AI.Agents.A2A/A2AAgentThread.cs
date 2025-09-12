// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Thread for A2A based agents.
/// </summary>
public sealed class A2AAgentThread : AgentThread
{
    /// <summary>
    /// Initializes a new instance of the <see cref="A2AAgentThread"/> class.
    /// </summary>
    internal A2AAgentThread()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="A2AAgentThread"/> class from serialized state.
    /// </summary>
    /// <param name="serializedThreadState">A <see cref="JsonElement"/> representing the serialized state of the thread.</param>
    internal A2AAgentThread(JsonElement serializedThreadState)
    {
        if (serializedThreadState.ValueKind == JsonValueKind.Undefined || serializedThreadState.ValueKind == JsonValueKind.Null)
        {
            return;
        }

        var state = JsonSerializer.Deserialize(
            serializedThreadState,
            A2AAgentJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ThreadState))) as ThreadState;

        if (state?.ContextId is string contextId)
        {
            this.ContextId = contextId;
        }
    }

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    public override async Task<JsonElement> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        var state = new ThreadState
        {
            ContextId = this.ContextId
        };

        return JsonSerializer.SerializeToElement(state, A2AAgentJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ThreadState)));
    }

    /// <summary>
    /// Gets the A2A context id that is being used to communicate with the A2A service.
    /// </summary>
    public string? ContextId { get; internal set; }

    internal sealed class ThreadState
    {
        [JsonPropertyName("contextId")]
        public string? ContextId { get; set; }
    }
}
