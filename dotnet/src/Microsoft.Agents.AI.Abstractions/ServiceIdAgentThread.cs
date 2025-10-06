// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Text.Json;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides a base class for agent threads that store conversation state remotely in a service and maintain only an identifier reference locally.
/// </summary>
/// <remarks>
/// This class is designed for scenarios where conversation state is managed by an external service (such as a cloud-based AI service)
/// rather than being stored locally. The thread maintains only the service identifier needed to reference the remote conversation state.
/// </remarks>
[DebuggerDisplay("ServiceThreadId = {ServiceThreadId}")]
public abstract class ServiceIdAgentThread : AgentThread
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ServiceIdAgentThread"/> class without a service thread identifier.
    /// </summary>
    /// <remarks>
    /// When using this constructor, the <see cref="ServiceThreadId"/> will be <see langword="null"/> initially
    /// and should be set by derived classes when the remote conversation is created.
    /// </remarks>
    protected ServiceIdAgentThread()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ServiceIdAgentThread"/> class with the specified service thread identifier.
    /// </summary>
    /// <param name="serviceThreadId">The unique identifier that references the conversation state stored in the remote service.</param>
    /// <exception cref="ArgumentNullException"><paramref name="serviceThreadId"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="serviceThreadId"/> is empty or contains only whitespace.</exception>
    protected ServiceIdAgentThread(string serviceThreadId)
    {
        this.ServiceThreadId = Throw.IfNullOrEmpty(serviceThreadId);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ServiceIdAgentThread"/> class from previously serialized state.
    /// </summary>
    /// <param name="serializedThreadState">A <see cref="JsonElement"/> representing the serialized state of the thread.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <exception cref="ArgumentException">The <paramref name="serializedThreadState"/> is not a JSON object.</exception>
    /// <exception cref="JsonException">The <paramref name="serializedThreadState"/> is invalid or cannot be deserialized to the expected type.</exception>
    /// <remarks>
    /// This constructor enables restoration of a service-backed thread from serialized state, typically used
    /// when deserializing thread information that was previously saved or transmitted across application boundaries.
    /// </remarks>
    protected ServiceIdAgentThread(
        JsonElement serializedThreadState,
        JsonSerializerOptions? jsonSerializerOptions = null)
    {
        if (serializedThreadState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized thread state must be a JSON object.", nameof(serializedThreadState));
        }

        var state = serializedThreadState.Deserialize(
            AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ServiceIdAgentThreadState))) as ServiceIdAgentThreadState;

        if (state?.ServiceThreadId is string serviceThreadId)
        {
            this.ServiceThreadId = serviceThreadId;
        }
    }

    /// <summary>
    /// Gets or sets the unique identifier that references the conversation state stored in the remote service.
    /// </summary>
    /// <value>
    /// A string identifier that uniquely identifies the conversation within the remote service,
    /// or <see langword="null"/> if no remote conversation has been established yet.
    /// </value>
    /// <remarks>
    /// This identifier is used by derived classes to reference the remote conversation state when making
    /// API calls to the backing service. The exact format and meaning of this identifier depends on the
    /// specific service implementation.
    /// </remarks>
    protected string? ServiceThreadId { get; set; }

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use for the serialization process.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state, containing the service thread identifier.</returns>
    /// <remarks>
    /// The serialized state contains only the service thread identifier, as all other conversation state
    /// is maintained remotely by the backing service. This makes the serialized representation very lightweight.
    /// </remarks>
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
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
