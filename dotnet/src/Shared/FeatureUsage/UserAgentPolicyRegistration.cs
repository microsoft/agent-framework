// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005 // Required in projects with implicit usings disabled.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using ApprovedOriginPredicate = System.Func<System.Uri?, bool>;
using PipelinePolicyList = System.Collections.Generic.IReadOnlyList<System.ClientModel.Primitives.PipelinePolicy>;
using UserAgentTransformer = System.Func<string, bool, string>;

#pragma warning restore IDE0005

namespace Microsoft.Agents.AI.Internal;

#pragma warning disable MEAI001

internal enum BaseUserAgentScope
{
    AllRequests,
    ApprovedOrigins,
}

internal sealed class AgentFrameworkUserAgentPolicy : PipelinePolicy
{
    private const string UserAgentHeader = "User-Agent";
    private readonly ApprovedOriginPredicate _isApprovedOrigin;
    private readonly BaseUserAgentScope _scope;
    private readonly string _segmentValue;

    internal AgentFrameworkUserAgentPolicy(ApprovedOriginPredicate isApprovedOrigin, BaseUserAgentScope scope)
    {
        this._isApprovedOrigin = isApprovedOrigin;
        this._scope = scope;
        this._segmentValue = CreateSegmentValue();
    }

    public override void Process(
        PipelineMessage message,
        PipelinePolicyList pipeline,
        int currentIndex)
    {
        this.UpdateHeader(message);
        ProcessNext(message, pipeline, currentIndex);
    }

    public override ValueTask ProcessAsync(
        PipelineMessage message,
        PipelinePolicyList pipeline,
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

internal sealed class FeatureUsageUserAgentPolicy : PipelinePolicy
{
    private const string UserAgentHeader = "User-Agent";
    private readonly ApprovedOriginPredicate _isApprovedOrigin;
    private readonly UserAgentTransformer _applyToUserAgent;

    internal FeatureUsageUserAgentPolicy(
        ApprovedOriginPredicate isApprovedOrigin,
        UserAgentTransformer applyToUserAgent)
    {
        this._isApprovedOrigin = isApprovedOrigin;
        this._applyToUserAgent = applyToUserAgent;
    }

    public override void Process(
        PipelineMessage message,
        PipelinePolicyList pipeline,
        int currentIndex)
    {
        this.UpdateHeader(message);
        ProcessNext(message, pipeline, currentIndex);
    }

    public override ValueTask ProcessAsync(
        PipelineMessage message,
        PipelinePolicyList pipeline,
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

internal sealed class AgentFrameworkUserAgentPolicyRegistration
{
    // Linked-source consumers intentionally maintain independent registration state for their own wrapper pipelines.
    private readonly string[] _approvedHostSuffixes;
    private readonly ConditionalWeakTable<OpenAIRequestPolicies, RegistrationMarker> _registrations = new();
    private readonly object _registrationLock = new();

    internal AgentFrameworkUserAgentPolicyRegistration(
        string[] approvedHostSuffixes,
        BaseUserAgentScope baseUserAgentScope)
    {
        this._approvedHostSuffixes = approvedHostSuffixes is null
            ? throw new ArgumentNullException(nameof(approvedHostSuffixes))
            : (string[])approvedHostSuffixes.Clone();
        this.BaseUserAgentPolicy = new(this.IsApprovedOrigin, baseUserAgentScope);
#pragma warning disable MAAI001
        this.FeatureUsagePolicy = new(this.IsApprovedOrigin, FeatureUsage.ApplyToUserAgent);
#pragma warning restore MAAI001
    }

    internal AgentFrameworkUserAgentPolicy BaseUserAgentPolicy { get; }

    internal FeatureUsageUserAgentPolicy FeatureUsagePolicy { get; }

    internal bool IsApprovedOrigin(Uri? uri)
    {
        if (uri?.IsAbsoluteUri != true ||
            !string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        string host = uri.IdnHost.TrimEnd('.');
        foreach (string suffix in this._approvedHostSuffixes)
        {
            if (string.Equals(host, suffix, StringComparison.OrdinalIgnoreCase) ||
                host.EndsWith($".{suffix}", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        return false;
    }

    internal bool TryRegister(IChatClient? chatClient)
    {
        return chatClient?.GetService<OpenAIRequestPolicies>() is { } policies &&
            this.TryRegister(policies);
    }

    internal bool TryRegister(OpenAIRequestPolicies policies)
    {
        lock (this._registrationLock)
        {
            if (this._registrations.TryGetValue(policies, out _))
            {
                return false;
            }

            policies.AddPolicy(this.BaseUserAgentPolicy, PipelinePosition.PerCall);
            policies.AddPolicy(this.FeatureUsagePolicy, PipelinePosition.BeforeTransport);
            this._registrations.Add(policies, new RegistrationMarker());
            return true;
        }
    }

    private sealed class RegistrationMarker;
}

#pragma warning restore MEAI001
