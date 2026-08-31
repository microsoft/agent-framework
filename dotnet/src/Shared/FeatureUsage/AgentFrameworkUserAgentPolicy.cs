// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005 // Required in projects with implicit usings disabled.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Reflection;
using System.Threading.Tasks;

#pragma warning restore IDE0005

namespace Microsoft.Agents.AI.Internal;

internal sealed class AgentFrameworkUserAgentPolicy : PipelinePolicy
{
    private const string UserAgentHeader = "User-Agent";
    private readonly Func<Uri?, bool> _isApprovedOrigin;
    private readonly BaseUserAgentScope _scope;
    private readonly string _segmentValue;

    internal AgentFrameworkUserAgentPolicy(Func<Uri?, bool> isApprovedOrigin, BaseUserAgentScope scope)
    {
        this._isApprovedOrigin = isApprovedOrigin;
        this._scope = scope;
        this._segmentValue = CreateSegmentValue();
    }

    public override void Process(
        PipelineMessage message,
        IReadOnlyList<PipelinePolicy> pipeline,
        int currentIndex)
    {
        this.UpdateHeader(message);
        ProcessNext(message, pipeline, currentIndex);
    }

    public override ValueTask ProcessAsync(
        PipelineMessage message,
        IReadOnlyList<PipelinePolicy> pipeline,
        int currentIndex)
    {
        this.UpdateHeader(message);
        return ProcessNextAsync(message, pipeline, currentIndex);
    }

    private void UpdateHeader(PipelineMessage message)
    {
        if (this._scope == BaseUserAgentScope.ApprovedOrigins &&
            !this._isApprovedOrigin(message.Request.Uri))
        {
            return;
        }

        if (message.Request.Headers.TryGetValue(UserAgentHeader, out string? existing) &&
            !string.IsNullOrEmpty(existing))
        {
            if (existing!.IndexOf(this._segmentValue, StringComparison.Ordinal) < 0)
            {
                message.Request.Headers.Set(UserAgentHeader, $"{existing} {this._segmentValue}");
            }

            return;
        }

        message.Request.Headers.Set(UserAgentHeader, this._segmentValue);
    }

    private static string CreateSegmentValue()
    {
        const string Name = "agent-framework-dotnet";

        if (typeof(AgentFrameworkUserAgentPolicy).Assembly
            .GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion is string version)
        {
            int metadataStart = version.IndexOf('+');
            if (metadataStart >= 0)
            {
                version = version.Substring(0, metadataStart);
            }

            if (version.Length > 0)
            {
                return $"{Name}/{version}";
            }
        }

        return Name;
    }
}
