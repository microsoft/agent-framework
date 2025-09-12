// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// A thread type that may be used by any agent that proxies a remote agent where the remote agent has its own thread management.
/// </summary>
public class ProxyAgentThread : AgentThread
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ProxyAgentThread"/> class.
    /// </summary>
    public ProxyAgentThread()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ProxyAgentThread"/> class from serialized state.
    /// </summary>
    /// <param name="serializedThreadState">A <see cref="JsonElement"/> representing the serialized state of the thread.</param>
    public ProxyAgentThread(JsonElement serializedThreadState)
    {
        var state = JsonSerializer.Deserialize(
            serializedThreadState,
            AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ThreadState))) as ThreadState;

        if (state?.ServiceThreadId is string threadId)
        {
            this.ServiceThreadId = threadId;
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
            ServiceThreadId = this.ServiceThreadId
        };

        return JsonSerializer.SerializeToElement(state, AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ThreadState)));
    }

    /// <summary>
    /// Gets or sets the id of the service thread to support cases where the thread is owned by an underlying agent service.
    /// </summary>
    public virtual string? ServiceThreadId { get; set; }

    internal sealed class ThreadState
    {
        [JsonPropertyName("serviceThreadId")]
        public string? ServiceThreadId { get; set; }
    }
}
