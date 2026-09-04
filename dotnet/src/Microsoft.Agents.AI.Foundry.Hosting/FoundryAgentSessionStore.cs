// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Core.Storage;
using Azure.Core;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Provides an <see cref="AgentSessionStore"/> that persists the agent-framework's serialized
/// <see cref="AgentSession"/> state through <see cref="FoundryStateStore"/>.
/// </summary>
/// <remarks>
/// <para>
/// The AgentServer SDK selects the backend. In Foundry hosting it writes to the platform's durable
/// state store, so a session survives container replacement and is visible to every instance of the
/// agent. Outside Foundry hosting it uses the SDK's local state-store fallback under
/// <c>~/.agentserver/state_stores</c>.
/// </para>
/// <para>
/// Layout. All sessions live in one state store, named <see cref="DefaultStoreName"/> unless
/// overridden, and each agent and <see cref="AgentSessionStoreKey"/> pair is one item in it. The item
/// key is a hash of an unambiguous encoding of the hosted registration identity and session key.
/// Hashing is required because the platform limits an item key to 128
/// characters. The readable encoding is stored alongside the session so an item can still be traced
/// back to its partition.
/// </para>
/// <para>
/// Logical isolation is expressed through <see cref="AgentSessionStoreKey.Partitions"/> rather than
/// through the state store's own <c>userIsolation</c> option. That option is fixed when the store is
/// created, while session partitions may vary per request.
/// </para>
/// <para>
/// The bound state store is resolved once, on first use, and reused for the lifetime of this
/// instance. Resolving it costs one round trip (plus one more the very first time, to create the
/// store), so it deliberately does not happen per request.
/// </para>
/// <para>
/// Direct callers must provide an agent with a stable <see cref="AIAgent.Name"/>. The Foundry
/// response handler supplies keyed and default registration identities explicitly, including for
/// unnamed agents.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FoundryAgentSessionStore : AgentSessionStore
{
    /// <summary>
    /// The default state-store name used to hold every agent session persisted by this store.
    /// </summary>
    public const string DefaultStoreName = "agent-framework/sessions";

    /// <summary>The item-body field holding the serialized session JSON.</summary>
    private const string SessionField = "session";

    /// <summary>The item-body field holding the readable logical key, for traceability.</summary>
    private const string KeyField = "key";

    private readonly FoundryStateStoreBinding _binding;

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryAgentSessionStore"/> class.
    /// </summary>
    /// <param name="endpoint">
    /// The Foundry project endpoint. Used only in Foundry hosting. When <see langword="null"/>,
    /// it is read from the <c>FOUNDRY_PROJECT_ENDPOINT</c> environment variable. Outside Foundry
    /// hosting, the AgentServer SDK ignores it and uses its local state-store fallback.
    /// </param>
    /// <param name="credential">
    /// The credential used to authenticate to the Foundry storage API. May be <see langword="null"/>
    /// outside Foundry hosting, where the AgentServer SDK uses its local state-store fallback.
    /// </param>
    /// <param name="storeName">The state-store name to hold the sessions. Defaults to <see cref="DefaultStoreName"/>.</param>
    /// <param name="itemTtlSeconds">
    /// How long a session survives without being written, in seconds. Defaults to the platform
    /// default of 30 days; <c>-1</c> means never expire. A write renews the window, a read does
    /// not. The value only takes effect when this store is created for the first time, because the
    /// platform fixes it at creation.
    /// </param>
    public FoundryAgentSessionStore(
        Uri? endpoint = null,
        TokenCredential? credential = null,
        string storeName = DefaultStoreName,
        int itemTtlSeconds = FoundryStateStore.DefaultItemTtlSeconds)
    {
        _ = Throw.IfNullOrWhitespace(storeName);

        this.StoreName = storeName;
        this._binding = new(cancellationToken => FoundryStateStore.GetOrCreateAsync(
            storeName,
            credential,
            endpoint,
            description: "Agent Framework hosted agent sessions.",
            itemTtlSeconds: itemTtlSeconds,
            cancellationToken: cancellationToken));
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryAgentSessionStore"/> class over a
    /// caller-supplied state store. Used by tests to substitute the platform client.
    /// </summary>
    /// <param name="storeFactory">Resolves the bound state store on first use.</param>
    /// <param name="storeName">The state-store name, for diagnostics.</param>
    internal FoundryAgentSessionStore(Func<CancellationToken, Task<FoundryStateStore>> storeFactory, string storeName = DefaultStoreName)
    {
        _ = Throw.IfNull(storeFactory);

        this._binding = new(storeFactory);
        this.StoreName = storeName;
    }

    /// <summary>Gets the state-store name that holds the sessions.</summary>
    public string StoreName { get; }

    /// <inheritdoc/>
    public override async ValueTask SaveSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        AgentSession session,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(agent);
        _ = Throw.IfNull(key);
        _ = Throw.IfNull(session);

        string agentIdentity = FoundryHostingAgent.GetSessionStorageIdentity(agent);
        JsonElement serialized = await agent.SerializeSessionAsync(session, cancellationToken: cancellationToken).ConfigureAwait(false);
        BinaryData sessionData = ToBinaryData(serialized);

        string logicalKey = FoundryAgentSessionKeyEncoder.BuildLogicalKey(agentIdentity, key);
        FoundryStateStore store = await this.GetStoreAsync(cancellationToken).ConfigureAwait(false);

        await store.SetItemAsync(
            FoundryAgentSessionKeyEncoder.BuildStorageKey(logicalKey),
            new Dictionary<string, BinaryData>
            {
                [SessionField] = sessionData,
                [KeyField] = ToJsonString(logicalKey),
            },
            cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override async ValueTask<AgentSession?> GetSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(agent);
        _ = Throw.IfNull(key);

        string logicalKey = FoundryAgentSessionKeyEncoder.BuildLogicalKey(
            FoundryHostingAgent.GetSessionStorageIdentity(agent),
            key);
        FoundryStateStore store = await this.GetStoreAsync(cancellationToken).ConfigureAwait(false);

        // GetItemAsync already answers null for an item that is not there, which is exactly the
        // "nothing stored" result this method contracts to return.
        StateStoreItem? item = await store.GetItemAsync(
            FoundryAgentSessionKeyEncoder.BuildStorageKey(logicalKey),
            cancellationToken).ConfigureAwait(false);
        if (!FoundryStateStoreJson.TryGetField(item, SessionField, out BinaryData? sessionData))
        {
            return null;
        }

        ReadOnlyMemory<byte> bytes = sessionData.ToMemory();
        // Parse and clone so the document buffer can be released.
        using JsonDocument document = JsonDocument.Parse(bytes);
        JsonElement element = document.RootElement.Clone();
        return await agent.DeserializeSessionAsync(element, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Resolves the bound state store, creating it on the platform the first time. See
    /// <see cref="FoundryStateStoreBinding"/> for the caching and failure behaviour.
    /// </summary>
    private ValueTask<FoundryStateStore> GetStoreAsync(CancellationToken cancellationToken)
        => this._binding.GetAsync(cancellationToken);

    private static BinaryData ToBinaryData(JsonElement element) => FoundryStateStoreJson.ToBinaryData(element);

    private static BinaryData ToJsonString(string value) => FoundryStateStoreJson.ToJsonString(value);
}
