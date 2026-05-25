// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Reflection;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Pipeline policy that emits the hosted-agent <c>User-Agent</c> segment
/// (<c>"foundry-hosting/agent-framework-dotnet/{version}"</c>), matching Python's hosted
/// contract (<c>foundry-hosting/agent-framework-python/{version}</c>, see
/// <c>python/packages/core/agent_framework/_telemetry.py</c>: the hosted prefix is joined
/// with the base agent-framework segment into a single combined User-Agent value).
/// </summary>
/// <remarks>
/// <para>
/// The supplement value is computed once from the Microsoft.Agents.AI.Foundry.Hosting
/// assembly's informational version. The policy is idempotent on retries: if the segment
/// is already present in the <c>User-Agent</c> header, the policy does not append it again.
/// </para>
/// <para>
/// When a bare <c>agent-framework-dotnet/{version}</c> segment is already present (stamped by
/// the framework-wide <c>AgentFrameworkUserAgentPolicy</c> registered by
/// <c>FoundryChatClient</c>), this policy <em>replaces</em> that segment with the combined
/// hosted form so the wire never carries both forms simultaneously, preserving Python parity.
/// </para>
/// <para>
/// This policy is added at hosted-agent resolution time via the MEAI 10.5.1
/// <see cref="OpenAIRequestPolicies"/> hook on the agent's underlying chat client. It is only
/// registered when an agent is resolved by the Foundry hosting layer.
/// </para>
/// </remarks>
internal sealed class HostedAgentUserAgentPolicy : PipelinePolicy
{
    public static HostedAgentUserAgentPolicy Instance { get; } = new HostedAgentUserAgentPolicy();

    private static readonly string s_supplementValue = CreateSupplementValue();

    /// <summary>Bare segment stamped by <c>AgentFrameworkUserAgentPolicy</c> in the non-hosted scenario; this policy upgrades it in-place when both run.</summary>
    private const string BareAgentFrameworkPrefix = "agent-framework-dotnet/";

    /// <summary>Combined hosted segment that this policy emits. Recognized in-place so callers whose pipelines already carry a (possibly different-version) combined segment get it replaced rather than double-prefixed (Q-D fix).</summary>
    private const string CombinedHostedPrefix = "foundry-hosting/agent-framework-dotnet/";

    public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        AppendHeader(message);
        ProcessNext(message, pipeline, currentIndex);
    }

    public override async ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        AppendHeader(message);
        await ProcessNextAsync(message, pipeline, currentIndex).ConfigureAwait(false);
    }

    private static void AppendHeader(PipelineMessage message)
    {
        if (message.Request.Headers.TryGetValue("User-Agent", out var existing) && !string.IsNullOrEmpty(existing))
        {
            // Guard against double-append on retries or when the policy is registered on
            // multiple pipeline positions.
            if (existing!.Contains(s_supplementValue))
            {
                return;
            }

            // Combined-form check first: if the caller's pipeline already has
            // `foundry-hosting/agent-framework-dotnet/{version}` (with a version that differs
            // from ours — otherwise the .Contains above would have returned early), replace the
            // entire combined span in place. Without this, the bare-prefix search below would
            // match `agent-framework-dotnet/` *inside* the combined segment and produce a
            // malformed `foundry-hosting/foundry-hosting/agent-framework-dotnet/...` value.
            var combinedIdx = existing.IndexOf(CombinedHostedPrefix, StringComparison.Ordinal);
            if (combinedIdx >= 0)
            {
                var combinedEnd = existing.IndexOf(' ', combinedIdx);
                if (combinedEnd < 0)
                {
                    combinedEnd = existing.Length;
                }

                var replacedCombined = string.Concat(existing.AsSpan(0, combinedIdx), s_supplementValue.AsSpan(), existing.AsSpan(combinedEnd));
                message.Request.Headers.Set("User-Agent", replacedCombined);
                return;
            }

            // If the bare agent-framework segment is present (stamped by
            // AgentFrameworkUserAgentPolicy when not hosted), upgrade it in place to the
            // combined hosted form so the wire never carries both segments simultaneously.
            // Mirrors Python where get_user_agent() returns a single combined string when the
            // hosted prefix is registered.
            var idx = existing.IndexOf(BareAgentFrameworkPrefix, StringComparison.Ordinal);
            if (idx >= 0)
            {
                var end = existing.IndexOf(' ', idx);
                if (end < 0)
                {
                    end = existing.Length;
                }

                var replaced = string.Concat(existing.AsSpan(0, idx), s_supplementValue.AsSpan(), existing.AsSpan(end));
                message.Request.Headers.Set("User-Agent", replaced);
                return;
            }

            message.Request.Headers.Set("User-Agent", $"{existing} {s_supplementValue}");
        }
        else
        {
            message.Request.Headers.Set("User-Agent", s_supplementValue);
        }
    }

    private static string CreateSupplementValue()
    {
        const string Name = "foundry-hosting/agent-framework-dotnet";

        if (typeof(HostedAgentUserAgentPolicy).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion is string version)
        {
            int pos = version.IndexOf('+');
            if (pos >= 0)
            {
                version = version.Substring(0, pos);
            }

            if (version.Length > 0)
            {
                return $"{Name}/{version}";
            }
        }

        return Name;
    }
}
