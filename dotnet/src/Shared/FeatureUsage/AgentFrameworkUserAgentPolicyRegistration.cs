// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005 // Required in projects with implicit usings disabled.

using System;
using System.ClientModel.Primitives;
using System.Runtime.CompilerServices;
using Microsoft.Extensions.AI;

#pragma warning restore IDE0005

namespace Microsoft.Agents.AI.Internal;

#pragma warning disable MEAI001

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
