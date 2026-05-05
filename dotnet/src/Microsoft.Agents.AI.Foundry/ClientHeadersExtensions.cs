// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Provides extension methods for attaching per-call <c>x-client-*</c> headers to an agent run
/// and for opting an existing <see cref="AIAgent"/> into the client-headers pipeline.
/// </summary>
/// <remarks>
/// <para>
/// The Foundry platform forwards headers prefixed with <c>x-client-</c> transparently from the
/// Agent Endpoint into the agent container (see the multi-tenant overlay design). Callers use
/// <see cref="WithClientHeader(ChatOptions, string, string)"/> or
/// <see cref="WithClientHeaders(ChatOptions, IEnumerable{KeyValuePair{string, string}})"/> to
/// stamp headers per <c>RunAsync</c> call (for example to attest the SaaS end-user identity
/// in <c>x-client-end-user-id</c>).
/// </para>
/// <para>
/// Headers are only delivered to the wire when:
/// <list type="number">
/// <item><description>the agent has been wrapped with <see cref="UseClientHeaders(AIAgentBuilder)"/> (or built via a Foundry factory that pre-wires it), and</description></item>
/// <item><description>the underlying <see cref="IChatClient"/> exposes the experimental MEAI 10.5.1 <see cref="OpenAIRequestPolicies"/> service (true for OpenAI-backed clients).</description></item>
/// </list>
/// When either condition is not met the call is a silent no-op.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public static class ClientHeadersExtensions
{
    /// <summary>The well-known <see cref="ChatOptions.AdditionalProperties"/> key used to carry the dictionary across packages.</summary>
    internal const string ClientHeadersKey = "Microsoft.Agents.AI.Foundry.ClientHeaders";

    /// <summary>The required prefix on every client header name (case-insensitive).</summary>
    private const string ClientHeaderPrefix = "x-client-";

    /// <summary>
    /// Adds a single <c>x-client-*</c> header to the per-call carrier on <paramref name="options"/>.
    /// </summary>
    /// <param name="options">The <see cref="ChatOptions"/> instance to mutate.</param>
    /// <param name="name">The header name. Must start with <c>x-client-</c> (case-insensitive).</param>
    /// <param name="value">The header value. Must be non-empty.</param>
    /// <returns><paramref name="options"/> for fluent chaining.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="options"/>, <paramref name="name"/>, or <paramref name="value"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="name"/> does not start with <c>x-client-</c>, or is empty/whitespace, or <paramref name="value"/> is empty.</exception>
    /// <exception cref="InvalidOperationException">The carrier slot on <see cref="ChatOptions.AdditionalProperties"/> is occupied by a value of a foreign type.</exception>
    public static ChatOptions WithClientHeader(this ChatOptions options, string name, string value)
    {
        _ = Throw.IfNull(options);
        ValidateHeader(name, value);

        var dict = GetOrCreateHeadersDictionary(options);
        dict[name] = value;
        return options;
    }

    /// <summary>
    /// Adds multiple <c>x-client-*</c> headers to the per-call carrier on <paramref name="options"/>.
    /// </summary>
    /// <remarks>Validation is all-or-nothing: if any entry is invalid no entries are written.</remarks>
    /// <param name="options">The <see cref="ChatOptions"/> instance to mutate.</param>
    /// <param name="headers">The headers to add. Each name must start with <c>x-client-</c>.</param>
    /// <returns><paramref name="options"/> for fluent chaining.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="options"/> or <paramref name="headers"/> is <see langword="null"/>, or any element of <paramref name="headers"/> has a <see langword="null"/> name or value.</exception>
    /// <exception cref="ArgumentException">Any header name does not start with <c>x-client-</c>, or any name is empty/whitespace, or any value is empty.</exception>
    /// <exception cref="InvalidOperationException">The carrier slot on <see cref="ChatOptions.AdditionalProperties"/> is occupied by a value of a foreign type.</exception>
    public static ChatOptions WithClientHeaders(this ChatOptions options, IEnumerable<KeyValuePair<string, string>> headers)
    {
        _ = Throw.IfNull(options);
        _ = Throw.IfNull(headers);

        // Validate first; mutate only when every entry passes.
        var staged = new List<KeyValuePair<string, string>>();
        foreach (var kvp in headers)
        {
            ValidateHeader(kvp.Key, kvp.Value);
            staged.Add(kvp);
        }

        if (staged.Count == 0)
        {
            return options;
        }

        var dict = GetOrCreateHeadersDictionary(options);
        foreach (var kvp in staged)
        {
            dict[kvp.Key] = kvp.Value;
        }

        return options;
    }

    /// <summary>
    /// Wraps the agent built by <paramref name="builder"/> so that headers stamped by
    /// <see cref="WithClientHeader(ChatOptions, string, string)"/> on the per-call
    /// <see cref="ChatOptions"/> are forwarded onto the outbound HTTP request.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Idempotent: if the inner agent is already wrapped with a <see cref="ClientHeadersAgent"/>
    /// anywhere in its delegating chain, the agent is returned unchanged. This makes
    /// <c>myFoundryAgent.AsBuilder().UseClientHeaders().Build()</c> safe even though Foundry
    /// agents are pre-wired automatically.
    /// </para>
    /// <para>
    /// Also registers <see cref="ClientHeadersPolicy"/> against the underlying chat client's
    /// <see cref="OpenAIRequestPolicies"/> service if available. When the underlying chat client
    /// is not OpenAI-backed (the service lookup returns <see langword="null"/>), the registration
    /// step is silently skipped; the agent decorator still runs but no headers are stamped on
    /// the wire. See the type-level remarks for the conditions under which delivery happens.
    /// </para>
    /// </remarks>
    /// <param name="builder">The <see cref="AIAgentBuilder"/> to extend.</param>
    /// <returns>The same builder, to allow fluent chaining.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="builder"/> is <see langword="null"/>.</exception>
    public static AIAgentBuilder UseClientHeaders(this AIAgentBuilder builder) =>
        Throw.IfNull(builder).Use((AIAgent innerAgent, IServiceProvider services) =>
        {
            // Agent-side dedup: if any decorator in the chain is already a ClientHeadersAgent, no-op.
            if (innerAgent.GetService<ClientHeadersAgent>() is not null)
            {
                return innerAgent;
            }

            // Best-effort policy registration on the underlying OpenAI-backed chat client.
            // Silent no-op when the service is unavailable (non-OpenAI providers).
            if (innerAgent.GetService<OpenAIRequestPolicies>() is { } policies)
            {
                OpenAIRequestPoliciesReflection.AddPolicyIfMissing(
                    policies,
                    ClientHeadersPolicy.Instance,
                    System.ClientModel.Primitives.PipelinePosition.PerCall);
            }

            return new ClientHeadersAgent(innerAgent);
        });

    /// <summary>Reads the headers dictionary stamped by callers, or <see langword="null"/> if none.</summary>
    [SuppressMessage("Design", "CA1002:Do not expose generic lists", Justification = "Internal helper.")]
    internal static IReadOnlyDictionary<string, string>? GetClientHeaders(this ChatOptions options)
    {
        if (options.AdditionalProperties is null)
        {
            return null;
        }

        if (!options.AdditionalProperties.TryGetValue(ClientHeadersKey, out var raw))
        {
            return null;
        }

        return raw as Dictionary<string, string>;
    }

    private static Dictionary<string, string> GetOrCreateHeadersDictionary(ChatOptions options)
    {
        options.AdditionalProperties ??= new AdditionalPropertiesDictionary();

        if (options.AdditionalProperties.TryGetValue(ClientHeadersKey, out var existing))
        {
            if (existing is Dictionary<string, string> dict)
            {
                return dict;
            }

            throw new InvalidOperationException(
                $"ChatOptions.AdditionalProperties[\"{ClientHeadersKey}\"] is occupied by a value of type '{existing?.GetType().FullName ?? "null"}', expected Dictionary<string, string>.");
        }

        var fresh = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        options.AdditionalProperties[ClientHeadersKey] = fresh;
        return fresh;
    }

    private static void ValidateHeader(string name, string value)
    {
        _ = Throw.IfNull(name);
        _ = Throw.IfNull(value);

        if (string.IsNullOrWhiteSpace(name))
        {
            throw new ArgumentException("Header name must not be empty or whitespace.", nameof(name));
        }

        if (value.Length == 0)
        {
            throw new ArgumentException("Header value must not be empty.", nameof(value));
        }

        if (!name.StartsWith(ClientHeaderPrefix, StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException(
                $"Header name '{name}' must start with '{ClientHeaderPrefix}' (case-insensitive). Only x-client-* headers are forwarded by the Foundry platform.",
                nameof(name));
        }
    }
}
