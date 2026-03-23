// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Base abstraction for all agent threads.
/// </summary>
/// <remarks>
/// <para>
/// An <see cref="AgentSession"/> contains the state of a specific conversation with an agent which may include:
/// <list type="bullet">
/// <item><description>Conversation history or a reference to externally stored conversation history.</description></item>
/// <item><description>Memories or a reference to externally stored memories.</description></item>
/// <item><description>Any other state that the agent needs to persist across runs for a conversation.</description></item>
/// </list>
/// </para>
/// <para>
/// An <see cref="AgentSession"/> may also have behaviors attached to it that may include:
/// <list type="bullet">
/// <item><description>Customized storage of state.</description></item>
/// <item><description>Data extraction from and injection into a conversation.</description></item>
/// <item><description>Chat history reduction, e.g. where messages needs to be summarized or truncated to reduce the size.</description></item>
/// </list>
/// An <see cref="AgentSession"/> is always constructed by an <see cref="AIAgent"/> so that the <see cref="AIAgent"/>
/// can attach any necessary behaviors to the <see cref="AgentSession"/>. See the <see cref="AIAgent.CreateSessionAsync(System.Threading.CancellationToken)"/>
/// and <see cref="AIAgent.DeserializeSessionAsync(JsonElement, JsonSerializerOptions?, System.Threading.CancellationToken)"/> methods for more information.
/// </para>
/// <para>
/// Because of these behaviors, an <see cref="AgentSession"/> may not be reusable across different agents, since each agent
/// may add different behaviors to the <see cref="AgentSession"/> it creates.
/// </para>
/// <para>
/// To support conversations that may need to survive application restarts or separate service requests, an <see cref="AgentSession"/> can be serialized
/// and deserialized, so that it can be saved in a persistent store.
/// The <see cref="AIAgent"/> provides the <see cref="AIAgent.SerializeSessionAsync(AgentSession, JsonSerializerOptions?, System.Threading.CancellationToken)"/> method to serialize the session to a
/// <see cref="JsonElement"/> and the <see cref="AIAgent.DeserializeSessionAsync(JsonElement, JsonSerializerOptions?, System.Threading.CancellationToken)"/> method
/// can be used to deserialize the session.
/// </para>
/// <para>
/// <strong>Security considerations:</strong> Serialized sessions may contain conversation content, session identifiers,
/// and other potentially sensitive data including PII. Developers should:
/// <list type="bullet">
/// <item><description>Treat serialized session data as sensitive and store it securely with appropriate access controls and encryption at rest.</description></item>
/// <item><description>Treat restoring a session from an untrusted source as equivalent to accepting untrusted input. A compromised storage backend
/// could alter message roles to escalate trust, or inject adversarial content that influences LLM behavior.</description></item>
/// </list>
/// </para>
/// </remarks>
/// <seealso cref="AIAgent"/>
/// <seealso cref="AIAgent.CreateSessionAsync(System.Threading.CancellationToken)"/>
/// <seealso cref="AIAgent.DeserializeSessionAsync(JsonElement, JsonSerializerOptions?, System.Threading.CancellationToken)"/>
[DebuggerDisplay("{DebuggerDisplay,nq}")]
public abstract class AgentSession
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSession"/> class.
    /// </summary>
    protected AgentSession()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSession"/> class.
    /// </summary>
    protected AgentSession(AgentSessionStateBag stateBag)
    {
        this.StateBag = Throw.IfNull(stateBag);
    }

    /// <summary>
    /// Gets any arbitrary state associated with this session.
    /// </summary>
    /// <remarks>
    /// Data stored in the <see cref="StateBag"/> will be included when the session is serialized.
    /// Avoid storing secrets, credentials, or highly sensitive data in the state bag without appropriate encryption,
    /// as this data may be persisted to external storage.
    /// </remarks>
    [JsonPropertyName("stateBag")]
    public AgentSessionStateBag StateBag { get; protected set; } = new();

    /// <summary>Asks the <see cref="AgentSession"/> for an object of the specified type <paramref name="serviceType"/>.</summary>
    /// <param name="serviceType">The type of object being requested.</param>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="serviceType"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly-typed services that might be provided by the <see cref="AgentSession"/>,
    /// including itself or any services it might be wrapping. For example, to access a <see cref="ChatHistoryProvider"/> if available for the instance,
    /// <see cref="GetService"/> may be used to request it.
    /// </remarks>
    public virtual object? GetService(Type serviceType, object? serviceKey = null)
    {
        _ = Throw.IfNull(serviceType);

        return serviceKey is null && serviceType.IsInstanceOfType(this)
            ? this
            : null;
    }

    /// <summary>Asks the <see cref="AgentSession"/> for an object of type <typeparamref name="TService"/>.</summary>
    /// <typeparam name="TService">The type of the object to be retrieved.</typeparam>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly typed services that may be provided by the <see cref="AgentSession"/>,
    /// including itself or any services it might be wrapping.
    /// </remarks>
    public TService? GetService<TService>(object? serviceKey = null)
        => this.GetService(typeof(TService), serviceKey) is TService service ? service : default;

    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    private string DebuggerDisplay => $"StateBag Count = {this.StateBag.Count}";
}
