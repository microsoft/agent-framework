// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Text.Json;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides a base class for agent sessions that store conversation state remotely in a service and maintain only an identifier reference locally.
/// </summary>
/// <remarks>
/// This class is designed for scenarios where conversation state is managed by an external service (such as a cloud-based AI service)
/// rather than being stored locally. The session maintains only the service identifier needed to reference the remote conversation state.
/// </remarks>
[DebuggerDisplay("ServiceSessionId = {ServiceSessionId}")]
public abstract class ServiceIdAgentSession : AgentSession
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ServiceIdAgentSession"/> class without a service session identifier.
    /// </summary>
    /// <remarks>
    /// When using this constructor, the <see cref="ServiceSessionId"/> will be <see langword="null"/> initially
    /// and should be set by derived classes when the remote conversation is created.
    /// </remarks>
    protected ServiceIdAgentSession()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ServiceIdAgentSession"/> class with the specified service session identifier.
    /// </summary>
    /// <param name="serviceSessionId">The unique identifier that references the conversation state stored in the remote service.</param>
    /// <exception cref="ArgumentNullException"><paramref name="serviceSessionId"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="serviceSessionId"/> is empty or contains only whitespace.</exception>
    protected ServiceIdAgentSession(string serviceSessionId)
    {
        this.ServiceSessionId = Throw.IfNullOrEmpty(serviceSessionId);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ServiceIdAgentSession"/> class from previously serialized state.
    /// </summary>
    /// <param name="serializedState">A <see cref="JsonElement"/> representing the serialized state of the session.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <exception cref="ArgumentException">The <paramref name="serializedState"/> is not a JSON object.</exception>
    /// <exception cref="JsonException">The <paramref name="serializedState"/> is invalid or cannot be deserialized to the expected type.</exception>
    /// <remarks>
    /// This constructor enables restoration of a service-backed session from serialized state, typically used
    /// when deserializing session information that was previously saved or transmitted across application boundaries.
    /// </remarks>
    protected ServiceIdAgentSession(
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null)
    {
        if (serializedState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized session state must be a JSON object.", nameof(serializedState));
        }

        var state = serializedState.Deserialize(
            AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ServiceIdAgentSessionState))) as ServiceIdAgentSessionState;

        if (state?.ServiceSessionId is string serviceSessionId)
        {
            this.ServiceSessionId = serviceSessionId;
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
    protected string? ServiceSessionId { get; set; }

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    protected internal virtual JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var state = new ServiceIdAgentSessionState
        {
            ServiceSessionId = this.ServiceSessionId,
        };

        return JsonSerializer.SerializeToElement(state, AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ServiceIdAgentSessionState)));
    }

    internal sealed class ServiceIdAgentSessionState
    {
        public string? ServiceSessionId { get; set; }
    }
}
