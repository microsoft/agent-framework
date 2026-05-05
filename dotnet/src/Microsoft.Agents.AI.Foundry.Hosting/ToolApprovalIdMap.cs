// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Helper for translating between agent-framework tool-approval request ids and the
/// strict-format wire ids required by the Responses Server SDK <c>mcp_approval_request</c>
/// item type, and for preserving the original <see cref="FunctionCallContent"/> across
/// the request/response round trip. The mapping is persisted in
/// <see cref="AgentSessionStateBag"/> so an approval request emitted on one HTTP turn can
/// be matched to the response posted back on the next turn — and the original tool-call
/// details (name, arguments, call id) can be faithfully reconstructed on the inbound
/// side, since the wire <c>mcp_approval_response</c> only echoes the approval id.
/// </summary>
internal static class ToolApprovalIdMap
{
    /// <summary>
    /// State-bag key used to store the wire-id ↔ approval-entry mapping.
    /// </summary>
    public const string StateBagKey = "Microsoft.Agents.AI.Foundry.Hosting.ToolApprovalIdMap";

    /// <summary>
    /// Captures everything needed to faithfully reconstruct the original
    /// <see cref="FunctionCallContent"/> on the inbound (response) side.
    /// </summary>
    /// <remarks>
    /// FICC composes <c>RequestId</c> as <c>"ficc_{CallId}"</c>; we therefore store
    /// <c>CallId</c> independently so the reconstructed function-call id matches what
    /// the model originally emitted (and what the backend Conversations API persisted),
    /// enabling the resulting <c>function_call_output</c> to pair correctly.
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
    /// Records the wire-id → approval-entry mapping in the supplied state bag,
    /// preserving the original <see cref="FunctionCallContent"/> details so the inbound
    /// <c>mcp_approval_response</c> handler can reconstruct it losslessly.
    /// </summary>
    [RequiresUnreferencedCode("FunctionCallContent.Arguments serialization may require types that cannot be statically analyzed.")]
    [RequiresDynamicCode("FunctionCallContent.Arguments serialization may require runtime code generation.")]
    public static void Record(AgentSessionStateBag? stateBag, string wireId, string afRequestId, FunctionCallContent functionCall)
    {
        if (stateBag is null)
        {
            return;
        }

        ArgumentNullException.ThrowIfNull(functionCall);

        var map = LoadMap(stateBag);
        map[wireId] = new ApprovalEntry
        {
            AfRequestId = afRequestId,
            CallId = functionCall.CallId,
            Name = functionCall.Name,
            Arguments = functionCall.Arguments is not null
                ? JsonSerializer.Serialize(functionCall.Arguments)
                : null,
        };
        stateBag.SetValue(StateBagKey, map);
    }

    /// <summary>
    /// Looks up the AF request id for a given wire id. Returns the wire id verbatim
    /// when no mapping is present (best-effort fallback that keeps converters total).
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

        try
        {
            map = stateBag.GetValue<Dictionary<string, ApprovalEntry>>(StateBagKey)
                ?? new Dictionary<string, ApprovalEntry>(StringComparer.Ordinal);
            return true;
        }
        catch (JsonException)
        {
            // Defensive: if a state bag carries an older-format value we cannot deserialize,
            // start fresh rather than failing the whole request. This only loses the ability
            // to round-trip an in-flight approval, which the caller already gracefully handles
            // via the wire-id fallback path.
            map = new Dictionary<string, ApprovalEntry>(StringComparer.Ordinal);
            return true;
        }
    }
}
