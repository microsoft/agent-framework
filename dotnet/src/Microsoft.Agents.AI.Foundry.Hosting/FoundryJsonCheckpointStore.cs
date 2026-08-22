// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Core.Storage;
using Azure.Core;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Provides a <see cref="JsonCheckpointStore"/> that persists workflow checkpoints through
/// <see cref="FoundryStateStore"/>.
/// </summary>
/// <remarks>
/// <para>
/// The AgentServer SDK selects the backend. In Foundry hosting it writes to the platform's durable
/// state store. Outside Foundry hosting it uses the SDK's local state-store fallback under
/// <c>~/.agentserver/state_stores</c>.
/// </para>
/// <para>
/// Item keys are hashes of the session identifier and the checkpoint identifier, because the
/// platform limits an item key to 128 characters and neither identifier is bounded. Hashing rather
/// than truncating means two different checkpoints can never end up sharing a key and overwriting
/// each other.
/// </para>
/// <para>
/// Retention. Retrieving a checkpoint happens when a workflow is resuming from it. At that point,
/// superseded ancestors and earlier entries without a parent are deleted. Sibling branches, the
/// resumed checkpoint, and later checkpoints are retained so another persisted or concurrent run
/// cannot lose its live state. Note that this makes <see cref="RetrieveCheckpointAsync"/> a write
/// operation as well as a read.
/// </para>
/// <para>
/// Concurrency. Adding a checkpoint writes the checkpoint item and then updates the session's index
/// item using the platform's optimistic concurrency check, retrying a bounded number of times when
/// another writer got there first. Two instances committing checkpoints for the same session at the
/// same time therefore do not lose entries.
/// </para>
/// <para>
/// This store partitions only by workflow session identifier, which is the only partition the
/// <see cref="ICheckpointStore{TStoreObject}"/> contract carries. It does not partition by end
/// user. Callers that serve several end users from one workflow session must keep user separation
/// in the session identifier itself.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FoundryJsonCheckpointStore : JsonCheckpointStore
{
    /// <summary>
    /// The default state-store name used to hold every workflow checkpoint persisted by this store.
    /// </summary>
    public const string DefaultStoreName = "agent-framework/checkpoints";

    /// <summary>
    /// How many times a losing index update is retried before giving up. Each attempt re-reads the
    /// index, so a retry only happens when another writer committed a checkpoint in between.
    /// </summary>
    private const int MaxIndexUpdateAttempts = 8;

    /// <summary>The item-body field holding the serialized checkpoint JSON.</summary>
    private const string CheckpointField = "checkpoint";

    /// <summary>The item-body field holding the owning session identifier, for traceability.</summary>
    private const string SessionField = "session";

    /// <summary>The item-body field of an index item holding the ordered checkpoint entries.</summary>
    private const string EntriesField = "entries";

    private const string EntryIdProperty = "id";
    private const string EntryParentProperty = "parent";
    private const string EntryHasParentProperty = "hasParent";

    private readonly FoundryStateStoreBinding _binding;
    private readonly ILogger? _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryJsonCheckpointStore"/> class.
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
    /// <param name="storeName">The state-store name to hold the checkpoints. Defaults to <see cref="DefaultStoreName"/>.</param>
    /// <param name="itemTtlSeconds">
    /// How long a checkpoint survives without being written, in seconds. Defaults to the platform
    /// default of 30 days; <c>-1</c> means never expire. A write renews the window, a read does
    /// not. The value only takes effect when this store is created for the first time, because the
    /// platform fixes it at creation.
    /// </param>
    /// <param name="loggerFactory">
    /// Creates the logger this store reports through. Optional, but without one a failure to clean
    /// up old checkpoints leaves no trace, since it is deliberately not allowed to fail the call it
    /// happens in.
    /// </param>
    public FoundryJsonCheckpointStore(
        Uri? endpoint = null,
        TokenCredential? credential = null,
        string storeName = DefaultStoreName,
        int itemTtlSeconds = FoundryStateStore.DefaultItemTtlSeconds,
        ILoggerFactory? loggerFactory = null)
    {
        _ = Throw.IfNullOrWhitespace(storeName);

        this.StoreName = storeName;
        this._logger = loggerFactory?.CreateLogger<FoundryJsonCheckpointStore>();
        this._binding = new(cancellationToken => FoundryStateStore.GetOrCreateAsync(
            storeName,
            credential,
            endpoint,
            description: "Agent Framework hosted workflow checkpoints.",
            itemTtlSeconds: itemTtlSeconds,
            cancellationToken: cancellationToken));
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryJsonCheckpointStore"/> class over a
    /// caller-supplied state store. Used by tests to substitute the platform client.
    /// </summary>
    /// <param name="storeFactory">Resolves the bound state store on first use.</param>
    /// <param name="storeName">The state-store name, for diagnostics.</param>
    /// <param name="loggerFactory">Creates the logger this store reports through.</param>
    internal FoundryJsonCheckpointStore(
        Func<CancellationToken, Task<FoundryStateStore>> storeFactory,
        string storeName = DefaultStoreName,
        ILoggerFactory? loggerFactory = null)
    {
        _ = Throw.IfNull(storeFactory);

        this._binding = new(storeFactory);
        this.StoreName = storeName;
        this._logger = loggerFactory?.CreateLogger<FoundryJsonCheckpointStore>();
    }

    /// <summary>Gets the state-store name that holds the checkpoints.</summary>
    public string StoreName { get; }

    /// <inheritdoc/>
    public override async ValueTask<CheckpointInfo> CreateCheckpointAsync(string sessionId, JsonElement value, CheckpointInfo? parent = null)
    {
        _ = Throw.IfNullOrWhitespace(sessionId);

        BinaryData checkpointData = FoundryStateStoreJson.ToBinaryData(value);

        FoundryStateStore store = await this._binding.GetAsync(CancellationToken.None).ConfigureAwait(false);
        string sessionIndexKey = BuildIndexKey(sessionId);

        // The identifier is chosen once, so a retried index update does not leave behind an orphan
        // checkpoint item under a discarded identifier.
        CheckpointInfo checkpointInfo = new(sessionId, Guid.NewGuid().ToString("N"));

        // Store the checkpoint itself, once. Only the index update below is ever retried.
        await store.SetItemAsync(
            BuildCheckpointKey(sessionId, checkpointInfo.CheckpointId),
            new Dictionary<string, BinaryData>
            {
                [CheckpointField] = checkpointData,
                [SessionField] = FoundryStateStoreJson.ToJsonString(sessionId),
            },
            cancellationToken: CancellationToken.None).ConfigureAwait(false);

        // Announce the stored checkpoint by appending its identifier to the session's index, giving
        // way and reading again whenever another instance updated that same index first.
        for (int attempt = 0; attempt < MaxIndexUpdateAttempts; attempt++)
        {
            StateStoreItem? indexItem = await store.GetItemAsync(sessionIndexKey, CancellationToken.None).ConfigureAwait(false);
            List<IndexEntry> entries = ReadEntries(indexItem);

            if (Contains(entries, checkpointInfo.CheckpointId))
            {
                // Two random identifiers colliding is not realistic, but the file-system and
                // in-memory stores both guard against it and this store keeps the same guarantee.
                throw new InvalidOperationException(
                    $"The generated checkpoint identifier '{checkpointInfo.CheckpointId}' is already in use for session '{sessionId}'.");
            }

            entries.Add(new IndexEntry(checkpointInfo.CheckpointId, parent?.CheckpointId, HasParentMetadata: true));

            try
            {
                await WriteEntriesAsync(store, sessionIndexKey, sessionId, entries, indexItem?.Etag).ConfigureAwait(false);
                return checkpointInfo;
            }
            catch (FoundryStorageException ex) when (IsLostRace(ex))
            {
                // Another writer added a checkpoint to the same session between the read and the
                // write. The checkpoint item is already stored under its own key, so the next
                // attempt simply re-reads the index and appends to the newer list.
                if (this._logger?.IsEnabled(LogLevel.Debug) is true)
                {
                    this._logger.LogDebug(
                        ex,
                        "Attempt {Attempt} of {MaxAttempts} to index checkpoint '{CheckpointId}' for session '{SessionId}' lost to another writer. Retrying.",
                        attempt + 1,
                        MaxIndexUpdateAttempts,
                        checkpointInfo.CheckpointId,
                        sessionId);
                }

                continue;
            }
        }

        throw new InvalidOperationException(
            $"Could not add a checkpoint for session '{sessionId}' to the Foundry state store after {MaxIndexUpdateAttempts} attempts because other writers kept updating the same session index.");
    }

    /// <summary>
    /// Returns a stored checkpoint and deletes superseded checkpoints from its lineage.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The deletion keeps old checkpoints from piling up. Sibling branches and checkpoints committed
    /// after the retrieved checkpoint are retained because they may belong to another persisted or
    /// concurrent run.
    /// </para>
    /// <para>
    /// A workflow writes one checkpoint per superstep and only ever resumes from the most
    /// recent one, so a conversation that ran for a long time would otherwise leave behind every
    /// checkpoint it ever wrote, and the index listing them would grow past the size the platform
    /// accepts for a single item.
    /// </para>
    /// </remarks>
    /// <param name="sessionId">The workflow session that owns the checkpoint.</param>
    /// <param name="key">Identifies the checkpoint to return and resume.</param>
    /// <returns>The stored checkpoint.</returns>
    /// <exception cref="KeyNotFoundException">No such checkpoint is stored for that session.</exception>
    public override async ValueTask<JsonElement> RetrieveCheckpointAsync(string sessionId, CheckpointInfo key)
    {
        _ = Throw.IfNullOrWhitespace(sessionId);
        _ = Throw.IfNull(key);

        FoundryStateStore store = await this._binding.GetAsync(CancellationToken.None).ConfigureAwait(false);
        StateStoreItem? item = await store.GetItemAsync(BuildCheckpointKey(sessionId, key.CheckpointId), CancellationToken.None).ConfigureAwait(false);
        if (!FoundryStateStoreJson.TryGetField(item, CheckpointField, out BinaryData? checkpointData))
        {
            throw new KeyNotFoundException(
                $"Checkpoint '{key.CheckpointId}' was not found for session '{sessionId}' in the Foundry state store '{this.StoreName}'.");
        }

        JsonElement checkpoint = ParseCheckpoint(checkpointData);

        // Keeps a session's checkpoints from piling up.
        await this.PruneObsoleteCheckpointsAsync(store, sessionId, key.CheckpointId).ConfigureAwait(false);

        return checkpoint;
    }

    /// <summary>
    /// Reads the stored bytes into a standalone <see cref="JsonElement"/>.
    /// </summary>
    /// <remarks>
    /// <see cref="JsonElement.ParseValue(ref Utf8JsonReader)"/> returns an element that owns its own
    /// memory, so there is no document to dispose and no copy to take. The reader lives in this
    /// method rather than in the caller because it is a <c>ref struct</c>, which cannot be held
    /// across an <c>await</c>.
    /// </remarks>
    private static JsonElement ParseCheckpoint(BinaryData checkpointData)
    {
        Utf8JsonReader reader = new(checkpointData.ToMemory().Span);
        return JsonElement.ParseValue(ref reader);
    }

    /// <summary>
    /// Deletes superseded ancestors and legacy predecessors of the checkpoint being resumed.
    /// </summary>
    /// <remarks>
    /// <para>
    /// A session accumulates one checkpoint per superstep, and only the most recent one is ever
    /// resumed from. Without this, a long conversation leaves behind every checkpoint it ever wrote
    /// and the session's index item grows until it can no longer be saved.
    /// </para>
    /// </remarks>
    private async Task PruneObsoleteCheckpointsAsync(FoundryStateStore store, string sessionId, string resumedCheckpointId)
    {
        string sessionIndexKey = BuildIndexKey(sessionId);

        try
        {
            StateStoreItem? indexItem = await store.GetItemAsync(sessionIndexKey, CancellationToken.None).ConfigureAwait(false);

            List<IndexEntry> entries = ReadEntries(indexItem);
            int resumedIndex = entries.FindIndex(entry => entry.CheckpointId == resumedCheckpointId);
            if (resumedIndex <= 0)
            {
                return;
            }

            HashSet<string> ancestorIds = GetAncestorIds(entries, resumedCheckpointId);
            List<IndexEntry> obsolete = [];
            List<IndexEntry> retained = [];

            for (int index = 0; index < entries.Count; index++)
            {
                IndexEntry entry = entries[index];
                // Legacy entries and parentless roots cannot be classified as branches, so they keep
                // the original commit-order pruning behavior.
                if (index < resumedIndex &&
                    (!entry.HasParentMetadata ||
                     entry.ParentCheckpointId is null ||
                     ancestorIds.Contains(entry.CheckpointId)))
                {
                    obsolete.Add(entry);
                }
                else
                {
                    retained.Add(entry);
                }
            }

            if (obsolete.Count == 0)
            {
                return;
            }

            // The index is shortened first. A checkpoint item that is still listed but already gone
            // would be read as a missing checkpoint, whereas one that is listed nowhere is simply
            // never asked for.
            await WriteEntriesAsync(store, sessionIndexKey, sessionId, retained, indexItem?.Etag).ConfigureAwait(false);

            foreach (IndexEntry entry in obsolete)
            {
                try
                {
                    await store.DeleteItemAsync(BuildCheckpointKey(sessionId, entry.CheckpointId), cancellationToken: CancellationToken.None).ConfigureAwait(false);
                }
                catch (FoundryStorageNotFoundException ex)
                {
                    // Already deleted, by an earlier attempt or another instance.
                    if (this._logger?.IsEnabled(LogLevel.Debug) is true)
                    {
                        this._logger.LogDebug(
                            ex,
                            "Obsolete checkpoint '{CheckpointId}' of session '{SessionId}' was already gone.",
                            entry.CheckpointId,
                            sessionId);
                    }
                }
            }
        }
        catch (FoundryStorageException ex) when (IsLostRace(ex))
        {
            // Another instance updated the same session index first. Leaving the old items in place
            // is safer than deleting against a stale index; a later resume can prune them.
            if (this._logger?.IsEnabled(LogLevel.Debug) is true)
            {
                this._logger.LogDebug(
                    ex,
                    "Pruning obsolete checkpoints of session '{SessionId}' lost to another writer. The old checkpoints remain until a later resume or expiry.",
                    sessionId);
            }
        }
        catch (FoundryStorageException ex)
        {
            // Not a lost race: the store refused the call for a reason of its own, a credential or a
            // network problem for instance. The checkpoint has already been retrieved by this point,
            // so failing the resume over housekeeping would break a conversation that was about to
            // carry on. It is reported instead, because left unreported this is how a session's
            // checkpoints would silently pile up until the index no longer fits.
            this._logger?.LogWarning(
                ex,
                "Could not prune obsolete checkpoints of session '{SessionId}' in the Foundry state store '{StoreName}'. The resume itself succeeded; the leftovers stay until the store's own expiry removes them.",
                sessionId,
                this.StoreName);
        }
    }

    private static HashSet<string> GetAncestorIds(List<IndexEntry> entries, string checkpointId)
    {
        Dictionary<string, IndexEntry> entriesById = [];
        foreach (IndexEntry entry in entries)
        {
            entriesById[entry.CheckpointId] = entry;
        }

        HashSet<string> ancestors = new(StringComparer.Ordinal);
        if (!entriesById.TryGetValue(checkpointId, out IndexEntry? current) ||
            !current.HasParentMetadata)
        {
            return ancestors;
        }

        string? parentId = current.ParentCheckpointId;
        while (parentId is not null && ancestors.Add(parentId))
        {
            if (!entriesById.TryGetValue(parentId, out IndexEntry? parent) ||
                !parent.HasParentMetadata)
            {
                break;
            }

            parentId = parent.ParentCheckpointId;
        }

        return ancestors;
    }

    /// <inheritdoc/>
    public override async ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(string sessionId, CheckpointInfo? withParent = null)
    {
        _ = Throw.IfNullOrWhitespace(sessionId);

        FoundryStateStore store = await this._binding.GetAsync(CancellationToken.None).ConfigureAwait(false);
        StateStoreItem? indexItem = await store.GetItemAsync(BuildIndexKey(sessionId), CancellationToken.None).ConfigureAwait(false);

        List<CheckpointInfo> result = [];
        foreach (IndexEntry entry in ReadEntries(indexItem))
        {
            // Same filter the file-system store applies: an entry written before parents were
            // recorded is always included, because its parent is unknown rather than different.
            if (withParent is null || !entry.HasParentMetadata || entry.ParentCheckpointId == withParent.CheckpointId)
            {
                result.Add(new CheckpointInfo(sessionId, entry.CheckpointId));
            }
        }

        return result;
    }

    /// <summary>Reports whether the index already lists the given checkpoint identifier.</summary>
    private static bool Contains(List<IndexEntry> entries, string checkpointId)
    {
        foreach (IndexEntry entry in entries)
        {
            if (entry.CheckpointId == checkpointId)
            {
                return true;
            }
        }

        return false;
    }

    /// <summary>
    /// Reports whether a storage failure means "someone else wrote this item first", which is the
    /// only failure this store retries. A 412 says the optimistic concurrency check failed; a 409
    /// says an item this store expected to be absent had already been created.
    /// </summary>
    private static bool IsLostRace(FoundryStorageException exception)
        => exception is FoundryStoragePreconditionException or FoundryStorageConflictException;

    private static List<IndexEntry> ReadEntries(StateStoreItem? indexItem)
    {
        List<IndexEntry> entries = [];

        if (!FoundryStateStoreJson.TryGetField(indexItem, EntriesField, out BinaryData? entriesData))
        {
            return entries;
        }

        using JsonDocument document = JsonDocument.Parse(entriesData.ToMemory());
        if (document.RootElement.ValueKind != JsonValueKind.Array)
        {
            return entries;
        }

        foreach (JsonElement element in document.RootElement.EnumerateArray())
        {
            if (element.ValueKind != JsonValueKind.Object ||
                !element.TryGetProperty(EntryIdProperty, out JsonElement idElement) ||
                idElement.GetString() is not string checkpointId ||
                checkpointId.Length == 0)
            {
                continue;
            }

            string? parentId = element.TryGetProperty(EntryParentProperty, out JsonElement parentElement) && parentElement.ValueKind == JsonValueKind.String
                ? parentElement.GetString()
                : null;

            bool hasParentMetadata = element.TryGetProperty(EntryHasParentProperty, out JsonElement hasParentElement) &&
                hasParentElement.ValueKind == JsonValueKind.True;

            entries.Add(new IndexEntry(checkpointId, parentId, hasParentMetadata));
        }

        return entries;
    }

    private static async Task WriteEntriesAsync(FoundryStateStore store, string sessionIndexKey, string sessionId, List<IndexEntry> entries, string? ifMatch)
    {
        Dictionary<string, BinaryData> value = new()
        {
            [EntriesField] = WriteEntries(entries),
            [SessionField] = FoundryStateStoreJson.ToJsonString(sessionId),
        };

        if (ifMatch is null)
        {
            // The index did not exist a moment ago. CreateItemAsync fails with a conflict if another
            // writer created it in the meantime, which the caller retries.
            await store.CreateItemAsync(sessionIndexKey, value, cancellationToken: CancellationToken.None).ConfigureAwait(false);
            return;
        }

        await store.SetItemAsync(sessionIndexKey, value, ifMatch: ifMatch, cancellationToken: CancellationToken.None).ConfigureAwait(false);
    }

    private static BinaryData WriteEntries(List<IndexEntry> entries)
    {
        System.Buffers.ArrayBufferWriter<byte> buffer = new();
        using (Utf8JsonWriter writer = new(buffer))
        {
            writer.WriteStartArray();
            foreach (IndexEntry entry in entries)
            {
                writer.WriteStartObject();
                writer.WriteString(EntryIdProperty, entry.CheckpointId);
                if (entry.ParentCheckpointId is not null)
                {
                    writer.WriteString(EntryParentProperty, entry.ParentCheckpointId);
                }

                writer.WriteBoolean(EntryHasParentProperty, entry.HasParentMetadata);
                writer.WriteEndObject();
            }

            writer.WriteEndArray();
        }

        return BinaryData.FromBytes(buffer.WrittenMemory);
    }

    /// <summary>
    /// Builds the key of the item holding a session's ordered checkpoint index. The <c>wi-</c>
    /// prefix separates index items from checkpoint items, which share one state store.
    /// </summary>
    internal static string BuildIndexKey(string sessionId) => $"wi-{HashKeyParts(sessionId)}";

    /// <summary>
    /// Builds the key of the item holding one checkpoint's serialized state. The <c>wc-</c> prefix
    /// separates checkpoint items from index items, which share one state store.
    /// </summary>
    internal static string BuildCheckpointKey(string sessionId, string checkpointId) => $"wc-{HashKeyParts(sessionId, checkpointId)}";

    /// <summary>
    /// Folds the identifiers an item key is made of into a fixed-length string.
    /// </summary>
    /// <remarks>
    /// The platform caps an item key at 128 characters, and neither a workflow session identifier
    /// nor a checkpoint identifier has a bounded length, so they are hashed. Hashing rather than
    /// truncating matters: two sessions whose identifiers share a long prefix would otherwise be cut
    /// down to the same key and overwrite each other's checkpoints. The parts are joined with a NUL
    /// character, which cannot appear inside either identifier, so no two different combinations can
    /// produce the same input. The result is written in the URL-safe base64 alphabet because the
    /// key becomes a segment of the request path the platform client builds.
    /// </remarks>
    /// <param name="parts">The identifiers that make this key unique, in a fixed order.</param>
    /// <returns>The hashed key body, without the prefix that says what kind of item it is.</returns>
    private static string HashKeyParts(params string[] parts)
    {
        byte[] hash = SHA256.HashData(Encoding.UTF8.GetBytes(string.Join("\u0000", parts)));
        return Convert.ToBase64String(hash).TrimEnd('=').Replace('+', '-').Replace('/', '_');
    }

    private sealed record IndexEntry(string CheckpointId, string? ParentCheckpointId, bool HasParentMetadata);
}
