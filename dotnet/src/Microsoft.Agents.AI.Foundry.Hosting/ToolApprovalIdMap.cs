// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Helper for translating between agent-framework tool-approval request ids and the
/// strict-format wire ids required by the Responses Server SDK <c>mcp_approval_request</c>
/// item type. The mapping is persisted in <see cref="AgentSessionStateBag"/> so an
/// approval request emitted on one HTTP turn can be matched to the response posted
/// back on the next turn.
/// </summary>
internal static class ToolApprovalIdMap
{
    /// <summary>
    /// State-bag key used to store the wire-id ↔ AF-request-id mapping.
    /// </summary>
    public const string StateBagKey = "Microsoft.Agents.AI.Foundry.Hosting.ToolApprovalIdMap";

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
    /// Records the wire-id → AF-request-id mapping in the supplied state bag.
    /// </summary>
    public static void Record(AgentSessionStateBag? stateBag, string wireId, string afRequestId)
    {
        if (stateBag is null)
        {
            return;
        }

        var map = stateBag.GetValue<Dictionary<string, string>>(StateBagKey)
            ?? new Dictionary<string, string>(StringComparer.Ordinal);
        map[wireId] = afRequestId;
        stateBag.SetValue(StateBagKey, map);
    }

    /// <summary>
    /// Looks up the AF request id for a given wire id. Returns the wire id verbatim
    /// when no mapping is present (best-effort fallback that keeps converters total).
    /// </summary>
    public static string Resolve(AgentSessionStateBag? stateBag, string wireId)
    {
        if (stateBag?.GetValue<Dictionary<string, string>>(StateBagKey) is { } map
            && map.TryGetValue(wireId, out var afRequestId))
        {
            return afRequestId;
        }

        return wireId;
    }
}
