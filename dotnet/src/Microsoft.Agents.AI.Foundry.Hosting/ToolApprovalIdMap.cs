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
/// <remarks>
/// Because this mapping lives in the session state bag, it is serialized as part of the
/// <see cref="AgentSession"/> by the active <c>AgentSessionStore</c> — there is no separate
/// approval store. Consequently, partitioning the persisted session per agent and per user
/// (see <c>FileSystemAgentSessionStore</c>) automatically isolates pending tool approvals
/// per tenant as well: one user can never resolve another user's saved approval request.
/// </remarks>
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
        public string? McpServerLabel { get; set; }
        public string? McpToolName { get; set; }
        public bool IsMcpToolCall { get; set; }
        public bool? Approved { get; set; }
        public bool Consumed { get; set; }
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
    public static void Record(
        AgentSessionStateBag? stateBag,
        string wireId,
        string afRequestId,
        string? callId,
        string? name,
        string? argumentsJson,
        string? mcpServerLabel = null,
        string? mcpToolName = null,
        bool isMcpToolCall = false)
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
            McpServerLabel = mcpServerLabel,
            McpToolName = mcpToolName,
            IsMcpToolCall = isMcpToolCall,
        };
        stateBag.SetValue(StateBagKey, map);
    }

    /// <summary>
    /// Records the caller's decision for an approval request so a later function result can
    /// distinguish an executed MCP call from a synthetic rejection result. A decision is a
    /// one-time capability: duplicate or conflicting responses are rejected.
    /// </summary>
    /// <returns>The decided approval entry.</returns>
    /// <exception cref="InvalidOperationException">
    /// The state bag or approval mapping is unavailable, or the request was already decided.
    /// </exception>
    public static ApprovalEntry RecordDecision(AgentSessionStateBag? stateBag, string wireId, bool approved)
    {
        if (stateBag is null)
        {
            throw new InvalidOperationException(
                $"No approval mapping recorded for wire id '{wireId}' because no agent session state bag is available.");
        }

        var map = LoadMap(stateBag);
        if (!map.TryGetValue(wireId, out var entry))
        {
            throw new InvalidOperationException($"No approval mapping recorded for wire id '{wireId}'.");
        }

        if (entry.Approved is not null)
        {
            throw new InvalidOperationException($"Approval request '{wireId}' has already been decided.");
        }

        entry.Approved = approved;
        stateBag.SetValue(StateBagKey, map);
        return entry;
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

    /// <summary>
    /// Consumes the decided MCP approval entry for an original tool call id.
    /// </summary>
    /// <returns>
    /// The consumed entry, or <see langword="null"/> when the call has no decided MCP approval.
    /// </returns>
    /// <exception cref="InvalidOperationException">The approval result was already consumed.</exception>
    public static ApprovalEntry? ConsumeMcpEntryByCallId(
        AgentSessionStateBag? stateBag,
        string callId,
        bool isMcpToolCall)
    {
        if (!TryLoadMap(stateBag, out var map))
        {
            return null;
        }

        foreach (var entry in map.Values)
        {
            if (entry.McpServerLabel is not null
                && entry.IsMcpToolCall == isMcpToolCall
                && string.Equals(entry.CallId, callId, StringComparison.Ordinal))
            {
                if (entry.Approved is null)
                {
                    return null;
                }

                if (entry.Consumed)
                {
                    throw new InvalidOperationException(
                        $"Approval result for function call '{callId}' has already been consumed.");
                }

                entry.Consumed = true;
                stateBag!.SetValue(StateBagKey, map);
                return entry;
            }
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

/// <summary>
/// Persists the caller-facing MCP item id for a locally executed function-shaped MCP call so
/// AgentServer history can be restored to the original function call/result transcript.
/// </summary>
internal static class LocalMcpCallIdMap
{
    public const string StateBagKey = "Microsoft.Agents.AI.Foundry.Hosting.LocalMcpCallIdMap";

    internal sealed class CallEntry
    {
        public string CallId { get; set; } = string.Empty;
        public string FunctionName { get; set; } = string.Empty;
        public string ToolName { get; set; } = string.Empty;
        public string ServerLabel { get; set; } = string.Empty;
    }

    public static void Record(
        AgentSessionStateBag? stateBag,
        string wireId,
        string callId,
        string functionName,
        string toolName,
        string serverLabel)
    {
        if (stateBag is null)
        {
            return;
        }

        var map = LoadMap(stateBag);
        map[wireId] = new CallEntry
        {
            CallId = callId,
            FunctionName = functionName,
            ToolName = toolName,
            ServerLabel = serverLabel,
        };
        stateBag.SetValue(StateBagKey, map);
    }

    public static CallEntry? ResolveEntry(AgentSessionStateBag? stateBag, string wireId)
    {
        if (stateBag?.GetValue<Dictionary<string, CallEntry>>(StateBagKey)?.TryGetValue(wireId, out var entry) is true)
        {
            return entry;
        }

        return null;
    }

    private static Dictionary<string, CallEntry> LoadMap(AgentSessionStateBag stateBag) =>
        stateBag.GetValue<Dictionary<string, CallEntry>>(StateBagKey)
            ?? new Dictionary<string, CallEntry>(StringComparer.Ordinal);
}

/// <summary>
/// Persists the caller-facing MCP item id for an MCP call that was already represented as native
/// MCP content inside the agent, preserving its original correlation id across hosted history replay.
/// </summary>
internal static class NativeMcpCallIdMap
{
    public const string StateBagKey = "Microsoft.Agents.AI.Foundry.Hosting.NativeMcpCallIdMap";

    internal sealed class CallEntry
    {
        public string CallId { get; set; } = string.Empty;
        public string ToolName { get; set; } = string.Empty;
        public string ServerLabel { get; set; } = string.Empty;
    }

    public static void Record(
        AgentSessionStateBag? stateBag,
        string wireId,
        string callId,
        string toolName,
        string serverLabel)
    {
        if (stateBag is null)
        {
            return;
        }

        var map = stateBag.GetValue<Dictionary<string, CallEntry>>(StateBagKey)
            ?? new Dictionary<string, CallEntry>(StringComparer.Ordinal);
        map[wireId] = new CallEntry
        {
            CallId = callId,
            ToolName = toolName,
            ServerLabel = serverLabel,
        };
        stateBag.SetValue(StateBagKey, map);
    }

    public static CallEntry? ResolveEntry(AgentSessionStateBag? stateBag, string wireId)
    {
        if (stateBag?.GetValue<Dictionary<string, CallEntry>>(StateBagKey)?.TryGetValue(wireId, out var entry) is true)
        {
            return entry;
        }

        return null;
    }
}
