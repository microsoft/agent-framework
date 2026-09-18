// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Core.Storage;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Resolves a <see cref="FoundryStateStore"/> once and hands the same instance to every later
/// caller. Resolving costs a network round trip, plus one more the very first time to create the
/// store on the platform, so it deliberately does not happen per request.
/// </summary>
/// <remarks>
/// A failed attempt is not kept: the next call starts a fresh one, so a transient network or
/// permission failure at startup does not leave the store unusable for the life of the process.
/// </remarks>
internal sealed class FoundryStateStoreBinding
{
    private readonly Func<CancellationToken, Task<FoundryStateStore>> _factory;
    private readonly object _gate = new();
    private Task<FoundryStateStore>? _pending;

    public FoundryStateStoreBinding(Func<CancellationToken, Task<FoundryStateStore>> factory)
    {
        this._factory = Throw.IfNull(factory);
    }

    public async ValueTask<FoundryStateStore> GetAsync(CancellationToken cancellationToken)
    {
        Task<FoundryStateStore> binding;
        lock (this._gate)
        {
            // The shared work is started without the caller's cancellation token so one cancelled
            // request cannot cancel the binding for every other request.
            binding = this._pending ??= this._factory(CancellationToken.None);
        }

        try
        {
            // WaitAsync applies the caller's token to this caller's wait only.
            return await binding.WaitAsync(cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested && !binding.IsCompleted)
        {
            // This caller stopped waiting, but the shared binding is still usable by everyone else.
            throw;
        }
        catch
        {
            lock (this._gate)
            {
                if (ReferenceEquals(this._pending, binding))
                {
                    this._pending = null;
                }
            }

            throw;
        }
    }
}

/// <summary>
/// Small JSON helpers shared by the Foundry-backed stores. They are written with
/// <see cref="Utf8JsonWriter"/> rather than a serializer so the callers stay trimming and
/// ahead-of-time compilation safe.
/// </summary>
internal static class FoundryStateStoreJson
{
    /// <summary>Writes a <see cref="JsonElement"/> out as UTF-8 bytes.</summary>
    public static BinaryData ToBinaryData(JsonElement element)
    {
        ArrayBufferWriter<byte> buffer = new();
        using (Utf8JsonWriter writer = new(buffer))
        {
            element.WriteTo(writer);
        }

        return BinaryData.FromBytes(buffer.WrittenMemory);
    }

    /// <summary>Encodes a plain string as a JSON string value.</summary>
    public static BinaryData ToJsonString(string value)
    {
        ArrayBufferWriter<byte> buffer = new();
        using (Utf8JsonWriter writer = new(buffer))
        {
            writer.WriteStringValue(value);
        }

        return BinaryData.FromBytes(buffer.WrittenMemory);
    }

    /// <summary>
    /// Reads one field out of a state-store item body, treating a missing item, a missing field and
    /// an empty value all as "nothing stored".
    /// </summary>
    public static bool TryGetField(StateStoreItem? item, string field, [NotNullWhen(true)] out BinaryData? data)
    {
        data = null;

        if (item is null)
        {
            return false;
        }

        if (!item.Value.TryGetValue(field, out BinaryData? value) || value is null)
        {
            return false;
        }

        if (value.ToMemory().IsEmpty)
        {
            return false;
        }

        data = value;
        return true;
    }
}
