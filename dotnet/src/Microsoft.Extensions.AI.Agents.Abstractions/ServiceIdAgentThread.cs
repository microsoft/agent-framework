// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// A base class for agent threads that always store conversation state in the service, and only keep an ID reference in the <see cref="AgentThread"/>.
/// </summary>
public abstract class ServiceIdAgentThread : AgentThread
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ServiceIdAgentThread"/> class.
    /// </summary>
    protected ServiceIdAgentThread()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ServiceIdAgentThread"/> class with the specified service thread ID.
    /// </summary>
    /// <param name="serviceThreadId">The ID that the conversation state is stored under in the service.</param>
    protected ServiceIdAgentThread(string serviceThreadId)
    {
        this.ServiceThreadId = Throw.IfNullOrEmpty(serviceThreadId);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ServiceIdAgentThread"/> class from serialized state.
    /// </summary>
    /// <param name="serializedThreadState">A <see cref="JsonElement"/> representing the serialized state of the thread.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <exception cref="ArgumentException">The <paramref name="serializedThreadState"/> is not a JSON object.</exception>
    /// <exception cref="JsonException">The <paramref name="serializedThreadState"/> is invalid or cannot be deserialized to the expected type.</exception>
    protected ServiceIdAgentThread(
        JsonElement serializedThreadState,
        JsonSerializerOptions? jsonSerializerOptions = null)
    {
        if (serializedThreadState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized thread state must be a JSON object.", nameof(serializedThreadState));
        }

        var state = JsonSerializer.Deserialize(
            serializedThreadState,
            AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ServiceIdAgentThreadState))) as ServiceIdAgentThreadState;

        if (state?.ServiceThreadId is string serviceThreadId)
        {
            this.ServiceThreadId = serviceThreadId;
        }
    }

    /// <summary>
    /// Gets the ID that the conversation state is stored under in the service.
    /// </summary>
    protected string? ServiceThreadId { get; set; }

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    public override async Task<JsonElement> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        var state = new ServiceIdAgentThreadState
        {
            ServiceThreadId = this.ServiceThreadId,
        };

        return JsonSerializer.SerializeToElement(state, AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ServiceIdAgentThreadState)));
    }

    internal sealed class ServiceIdAgentThreadState
    {
        public string? ServiceThreadId { get; set; }
    }
}
