// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Reflection;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Pipeline policy that appends the hosted-agent <c>User-Agent</c> segment
/// (e.g. <c>"foundry-hosting/agent-framework-dotnet/{version}"</c>) to outgoing requests.
/// </summary>
/// <remarks>
/// <para>
/// The supplement value is computed once from the Microsoft.Agents.AI.Foundry.Hosting
/// assembly's informational version. The policy is idempotent on retries: if the segment
/// is already present in the <c>User-Agent</c> header, the policy does not append it again.
/// </para>
/// <para>
/// This policy is added at request time (per-call <see cref="PipelinePosition"/>)
/// by <see cref="UserAgentResponsesClient"/> when invoking the wrapped
/// <see cref="OpenAI.Responses.ResponsesClient"/>. It is only registered when an agent is
/// resolved by the Foundry hosting layer.
/// </para>
/// </remarks>
internal sealed class HostedAgentUserAgentPolicy : PipelinePolicy
{
    public static HostedAgentUserAgentPolicy Instance { get; } = new HostedAgentUserAgentPolicy();

    private static readonly string s_supplementValue = CreateSupplementValue();

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
            if (existing.Contains(s_supplementValue))
            {
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
