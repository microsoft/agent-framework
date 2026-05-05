// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
#if NET
using System.Diagnostics.CodeAnalysis;
#endif
using System.Reflection;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Pipeline policy that stamps <c>x-client-*</c> headers from the current
/// <see cref="ClientHeadersScope"/> onto outbound OpenAI Responses requests.
/// </summary>
/// <remarks>
/// <para>
/// Registered once per <see cref="OpenAIRequestPolicies"/> instance via the new MEAI 10.5.1
/// extension hook. Headers are written using <see cref="PipelineRequestHeaders.Set(string, string)"/>
/// so per-call values overwrite anything stamped earlier in the pipeline (for example by static
/// pipeline policies registered on the underlying client). This also makes accidental double
/// registration value-stable.
/// </para>
/// </remarks>
internal sealed class ClientHeadersPolicy : PipelinePolicy
{
    public static ClientHeadersPolicy Instance { get; } = new ClientHeadersPolicy();

    private ClientHeadersPolicy()
    {
    }

    public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        Stamp(message);
        ProcessNext(message, pipeline, currentIndex);
    }

    public override ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        Stamp(message);
        return ProcessNextAsync(message, pipeline, currentIndex);
    }

    private static void Stamp(PipelineMessage message)
    {
        var headers = ClientHeadersScope.Current;
        if (headers is null || headers.Count == 0)
        {
            return;
        }

        foreach (var kvp in headers)
        {
            // Per-call wins: Set overwrites any same-name header previously stamped by other policies.
            message.Request.Headers.Set(kvp.Key, kvp.Value);
        }
    }
}

/// <summary>
/// Best-effort reflection helpers for <see cref="OpenAIRequestPolicies"/>. MEAI 10.5.1 does not
/// publicly expose its registered-policies list, so we reach into the private <c>_entries</c>
/// field to detect duplicate registrations of <see cref="ClientHeadersPolicy.Instance"/>.
/// </summary>
/// <remarks>
/// All access is guarded with try/catch and graceful fallback. If MEAI changes the field name
/// or shape in a future bump, dedup degrades to "always add" but stamping stays correct because
/// <see cref="ClientHeadersPolicy"/> uses <c>Headers.Set</c>. A CI test asserts the field shape
/// to fail loudly on future MEAI bumps.
/// </remarks>
internal static class OpenAIRequestPoliciesReflection
{
    private static readonly Lazy<FieldInfo?> s_entriesField = new(() =>
    {
        try
        {
            return typeof(OpenAIRequestPolicies).GetField(
                "_entries",
                BindingFlags.Instance | BindingFlags.NonPublic);
        }
        catch
        {
            return null;
        }
    });

    /// <summary>Returns <see langword="true"/> if <paramref name="policies"/> already contains <paramref name="policy"/>.</summary>
    /// <remarks>Returns <see langword="false"/> on any reflection failure (caller should treat the registration as not yet done).</remarks>
#if NET
    [UnconditionalSuppressMessage("Trimming", "IL2075:RequiresUnreferencedCode",
        Justification = "Reflecting on the private Entry struct shipped by Microsoft.Extensions.AI.OpenAI; falls back gracefully if shape changes. CI test asserts the field shape on every MEAI bump.")]
#endif
    public static bool ContainsPolicy(OpenAIRequestPolicies policies, PipelinePolicy policy)
    {
        try
        {
            if (s_entriesField.Value?.GetValue(policies) is not Array entries)
            {
                return false;
            }

            for (int i = 0; i < entries.Length; i++)
            {
                var entry = entries.GetValue(i);
                if (entry is null)
                {
                    continue;
                }

                // Entry is a private struct with a Policy property/field. Try property first, then field.
                var entryType = entry.GetType();
                var policyMember = entryType.GetProperty("Policy", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                object? value = policyMember is not null
                    ? policyMember.GetValue(entry)
                    : entryType.GetField("Policy", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)?.GetValue(entry);

                if (ReferenceEquals(value, policy))
                {
                    return true;
                }
            }

            return false;
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// Registers <paramref name="policy"/> on <paramref name="policies"/> if not already present.
    /// </summary>
    /// <returns>
    /// <see langword="true"/> if <c>AddPolicy</c> was called on this invocation; <see langword="false"/>
    /// when the policy was already detected as present and the call was skipped.
    /// </returns>
    public static bool AddPolicyIfMissing(OpenAIRequestPolicies policies, PipelinePolicy policy, PipelinePosition position = PipelinePosition.PerCall)
    {
        if (ContainsPolicy(policies, policy))
        {
            return false;
        }

        policies.AddPolicy(policy, position);
        return true;
    }
}
