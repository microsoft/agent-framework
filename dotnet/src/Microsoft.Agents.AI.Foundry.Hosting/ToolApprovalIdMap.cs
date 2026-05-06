// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Helper for translating between agent-framework tool-approval request ids and the
/// strict-format wire ids required by the Responses Server SDK <c>mcp_approval_request</c>
/// item type, and for preserving the original <see cref="FunctionCallContent"/> across
/// the request/response round trip. The mapping is persisted in
/// <see cref="AgentSessionStateBag"/>.
/// </summary>
internal static class ToolApprovalIdMap
{
    /// <summary>
    /// State-bag key used to store the wire-id ↔ approval-entry mapping.
    /// </summary>
    public const string StateBagKey = "Microsoft.Agents.AI.Foundry.Hosting.ToolApprovalIdMap";

    /// <summary>
    /// Captures the data needed to reconstruct the original
    /// <see cref="FunctionCallContent"/> on the inbound (response) side.
    /// </summary>
    /// <remarks>
    /// FICC composes <c>RequestId</c> as <c>"ficc_{CallId}"</c>; <c>CallId</c> is stored
    /// independently so the reconstructed function-call id matches the one the model
    /// emitted and the backend Conversations API persisted.
    /// </remarks>
    internal sealed class ApprovalEntry
    {
        public string AfRequestId { get; set; } = string.Empty;
        public string CallId { get; set; } = string.Empty;
        public string Name { get; set; } = string.Empty;
        public string? Arguments { get; set; }
    }

    /// <summary>
    /// SDK item-id format constraints: <c>{prefix}_{50_or_48_chars}</c>. We use the
    /// canonical <c>mcpr_</c> prefix and a SHA-256 truncated to 50 hex chars (25 bytes)
    /// for deterministic, format-safe wire ids.
    /// </summary>
    public static string ComputeWireId(string afRequestId)
    {
        ArgumentNullException.ThrowIfNull(afRequestId);

#if NET10_0_OR_GREATER
        Span<byte> hash = stackalloc byte[32];
        SHA256.HashData(Encoding.UTF8.GetBytes(afRequestId), hash);
#else
        byte[] hash = SHA256.HashData(Encoding.UTF8.GetBytes(afRequestId));
#endif
        // 25 bytes = 50 hex chars (matches SDK body length 50).
        return "mcpr_" + Convert.ToHexString(hash).AsSpan(0, 50).ToString();
    }

    /// <summary>
    /// Records the wire-id → approval-entry mapping in the supplied state bag.
    /// Arguments are passed as already-serialized JSON to keep this method
    /// trim/AOT-friendly (no polymorphic <c>object</c> serialization here).
    /// No-op when <paramref name="callId"/> or <paramref name="name"/> is empty —
    /// without those fields the entry cannot be used to faithfully reconstruct
    /// the original <see cref="FunctionCallContent"/> on the inbound side.
    /// </summary>
    public static void Record(AgentSessionStateBag? stateBag, string wireId, string afRequestId, string? callId, string? name, string? argumentsJson)
    {
        if (stateBag is null)
        {
            return;
        }

        if (string.IsNullOrEmpty(callId) || string.IsNullOrEmpty(name))
        {
            return;
        }

        var map = LoadMap(stateBag);
        map[wireId] = new ApprovalEntry
        {
            AfRequestId = afRequestId,
            CallId = callId!,
            Name = name!,
            Arguments = argumentsJson,
        };
        stateBag.SetValue(StateBagKey, map);
    }

    /// <summary>
    /// Looks up the AF request id for a given wire id. Returns the wire id verbatim
    /// when no mapping is present.
    /// </summary>
    public static string Resolve(AgentSessionStateBag? stateBag, string wireId)
    {
        if (TryLoadMap(stateBag, out var map)
            && map.TryGetValue(wireId, out var entry))
        {
            return entry.AfRequestId;
        }

        return wireId;
    }

    /// <summary>
    /// Looks up the full approval entry for a given wire id, or <see langword="null"/>
    /// when no mapping is present.
    /// </summary>
    public static ApprovalEntry? ResolveEntry(AgentSessionStateBag? stateBag, string wireId)
    {
        if (TryLoadMap(stateBag, out var map)
            && map.TryGetValue(wireId, out var entry))
        {
            return entry;
        }

        return null;
    }

    private static Dictionary<string, ApprovalEntry> LoadMap(AgentSessionStateBag stateBag)
        => TryLoadMap(stateBag, out var map) ? map : new Dictionary<string, ApprovalEntry>(StringComparer.Ordinal);

    private static bool TryLoadMap(AgentSessionStateBag? stateBag, out Dictionary<string, ApprovalEntry> map)
    {
        if (stateBag is null)
        {
            map = null!;
            return false;
        }

        // Don't swallow JsonException: ConvertMcpApprovalResponse fails fast on a missing entry,
        // so an empty map here would just turn a clear deserialization error into a confusing one.
        map = stateBag.GetValue<Dictionary<string, ApprovalEntry>>(StateBagKey)
            ?? new Dictionary<string, ApprovalEntry>(StringComparer.Ordinal);
        return true;
    }
}
