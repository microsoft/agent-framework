// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Reflection;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Framework-wide pipeline policy that appends the <c>agent-framework-dotnet/{version}</c>
/// segment to outgoing <c>User-Agent</c> headers, mirroring the
/// <c>agent-framework-python/{version}</c> contract used by every Python provider package.
/// </summary>
/// <remarks>
/// <para>
/// The segment value is computed once from the <c>Microsoft.Agents.AI.Foundry</c> assembly's
/// <see cref="AssemblyInformationalVersionAttribute"/>. The policy is idempotent on retries: if
/// the segment is already present in the <c>User-Agent</c> header, the policy does not append
/// it again.
/// </para>
/// <para>
/// The policy is registered by <c>FoundryChatClient</c> on the underlying chat client's
/// <c>OpenAIRequestPolicies</c> hook so every outbound Foundry call carries the segment. The
/// policy is currently colocated with the Foundry package; it is expected to migrate to a
/// framework-wide location (such as <c>Microsoft.Agents.AI</c>) once another provider package
/// adopts the same User-Agent contract.
/// </para>
/// </remarks>
internal sealed class AgentFrameworkUserAgentPolicy : PipelinePolicy
{
    /// <summary>Gets the singleton policy instance.</summary>
    public static AgentFrameworkUserAgentPolicy Instance { get; } = new AgentFrameworkUserAgentPolicy();

    private static readonly string s_segmentValue = CreateSegmentValue();

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
            // Guard against double-append on retries or when the policy
            // is registered on multiple pipeline positions.
            if (existing!.Contains(s_segmentValue))
            {
                return;
            }

            message.Request.Headers.Set("User-Agent", $"{existing} {s_segmentValue}");
        }
        else
        {
            message.Request.Headers.Set("User-Agent", s_segmentValue);
        }
    }

    private static string CreateSegmentValue()
    {
        const string Name = "agent-framework-dotnet";

        if (typeof(AgentFrameworkUserAgentPolicy).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion is string version)
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
