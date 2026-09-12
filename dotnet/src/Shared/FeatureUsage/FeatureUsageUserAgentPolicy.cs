// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005 // Required in projects with implicit usings disabled.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Threading.Tasks;

#pragma warning restore IDE0005

namespace Microsoft.Agents.AI.Internal;

internal sealed class FeatureUsageUserAgentPolicy : PipelinePolicy
{
    private const string UserAgentHeader = "User-Agent";
    private readonly Func<Uri?, bool> _isApprovedOrigin;
    private readonly Func<string, bool, string> _applyToUserAgent;

    internal FeatureUsageUserAgentPolicy(
        Func<Uri?, bool> isApprovedOrigin,
        Func<string, bool, string> applyToUserAgent)
    {
        this._isApprovedOrigin = isApprovedOrigin;
        this._applyToUserAgent = applyToUserAgent;
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
        bool hadHeader = message.Request.Headers.TryGetValue(UserAgentHeader, out string? current);
        current ??= string.Empty;

        string updated = this._applyToUserAgent(current, this._isApprovedOrigin(message.Request.Uri));
        if (string.Equals(current, updated, StringComparison.Ordinal))
        {
            return;
        }

        if (updated.Length > 0)
        {
            message.Request.Headers.Set(UserAgentHeader, updated);
        }
        else if (hadHeader)
        {
            message.Request.Headers.Remove(UserAgentHeader);
        }
    }
}
