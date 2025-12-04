// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Base abstraction for all agent threads.
/// </summary>
/// <remarks>
/// <para>
/// An <see cref="AgentThread"/> contains the state of a specific conversation with an agent which may include:
/// <list type="bullet">
/// <item><description>Conversation history or a reference to externally stored conversation history.</description></item>
/// <item><description>Memories or a reference to externally stored memories.</description></item>
/// <item><description>Any other state that the agent needs to persist across runs for a conversation.</description></item>
/// </list>
/// </para>
/// <para>
/// An <see cref="AgentThread"/> may also have behaviors attached to it that may include:
/// <list type="bullet">
/// <item><description>Customized storage of state.</description></item>
/// <item><description>Data extraction from and injection into a conversation.</description></item>
/// <item><description>Chat history reduction, e.g. where messages needs to be summarized or truncated to reduce the size.</description></item>
/// </list>
/// An <see cref="AgentThread"/> is always constructed by an <see cref="AIAgent"/> so that the <see cref="AIAgent"/>
/// can attach any necessary behaviors to the <see cref="AgentThread"/>. See the <see cref="AIAgent.GetNewThread()"/>
/// and <see cref="AIAgent.DeserializeThread(JsonElement, JsonSerializerOptions?)"/> methods for more information.
/// </para>
/// <para>
/// Because of these behaviors, an <see cref="AgentThread"/> may not be reusable across different agents, since each agent
/// may add different behaviors to the <see cref="AgentThread"/> it creates.
/// </para>
/// <para>
/// To support conversations that may need to survive application restarts or separate service requests, an <see cref="AgentThread"/> can be serialized
/// and deserialized, so that it can be saved in a persistent store.
/// The <see cref="AgentThread"/> provides the <see cref="Serialize(JsonSerializerOptions?)"/> method to serialize the thread to a
/// <see cref="JsonElement"/> and the <see cref="AIAgent.DeserializeThread(JsonElement, JsonSerializerOptions?)"/> method
/// can be used to deserialize the thread.
/// </para>
/// </remarks>
/// <seealso cref="AIAgent"/>
/// <seealso cref="AIAgent.GetNewThread()"/>
/// <seealso cref="AIAgent.DeserializeThread(JsonElement, JsonSerializerOptions?)"/>
public abstract class AgentThread
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentThread"/> class.
    /// </summary>
    protected AgentThread()
    {
    }

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    public virtual JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
        => default;

    /// <summary>Asks the <see cref="AgentThread"/> for an object of the specified type <paramref name="serviceType"/>.</summary>
    /// <param name="serviceType">The type of object being requested.</param>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="serviceType"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly-typed services that might be provided by the <see cref="AgentThread"/>,
    /// including itself or any services it might be wrapping. For example, to access the <see cref="AgentThreadMetadata"/> for the instance,
    /// <see cref="GetService"/> may be used to request it.
    /// </remarks>
    public virtual object? GetService(Type serviceType, object? serviceKey = null)
    {
        _ = Throw.IfNull(serviceType);

        return serviceKey is null && serviceType.IsInstanceOfType(this)
            ? this
            : null;
    }

    /// <summary>Asks the <see cref="AgentThread"/> for an object of type <typeparamref name="TService"/>.</summary>
    /// <typeparam name="TService">The type of the object to be retrieved.</typeparam>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly typed services that may be provided by the <see cref="AgentThread"/>,
    /// including itself or any services it might be wrapping.
    /// </remarks>
    public TService? GetService<TService>(object? serviceKey = null)
        => this.GetService(typeof(TService), serviceKey) is TService service ? service : default;
}
