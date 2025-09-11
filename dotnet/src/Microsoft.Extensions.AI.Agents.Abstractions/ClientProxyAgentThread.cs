// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// A thread type that may be used by any agent that proxies a remote agent where the remote agent has its own thread management.
/// </summary>
public class ClientProxyAgentThread : AgentThread
{
    private string? _serviceThreadId;

    /// <summary>
    /// Initializes a new instance of the <see cref="ClientProxyAgentThread"/> class.
    /// </summary>
    public ClientProxyAgentThread()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ClientProxyAgentThread"/> class from serialized state.
    /// </summary>
    /// <param name="serializedThreadState">A <see cref="JsonElement"/> representing the serialized state of the thread.</param>
    public ClientProxyAgentThread(JsonElement serializedThreadState)
    {
        var state = JsonSerializer.Deserialize(
            serializedThreadState,
            AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ThreadState))) as ThreadState;

        if (state?.ServiceThreadid is string threadId && !string.IsNullOrWhiteSpace(threadId))
        {
            this.ServiceThreadid = threadId;
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
            ServiceThreadid = this.ServiceThreadid
        };

        return JsonSerializer.SerializeToElement(state, AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ThreadState)));
    }

    /// <summary>
    /// Gets or sets the id of the service thread to support cases where the thread is owned by an underlying agent service.
    /// </summary>
    public virtual string? ServiceThreadid
    {
        get => this._serviceThreadId;
        set
        {
            this._serviceThreadId = Throw.IfNullOrWhitespace(value);
        }
    }

    internal sealed class ThreadState
    {
        public string? ServiceThreadid { get; set; }
    }
}
