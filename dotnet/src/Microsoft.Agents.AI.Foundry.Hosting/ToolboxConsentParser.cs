// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Parses the aggregate <c>tools/list</c> failure that the Foundry Toolboxes proxy returns
/// when one or more tool sources require OAuth consent before they can be enumerated.
/// </summary>
/// <remarks>
/// <para>
/// Unlike the per-tool-call path (JSON-RPC error <c>-32006</c>, handled by
/// <see cref="ConsentAwareMcpClientAIFunction"/>), a consent-gated tool fails at
/// <em>enumeration</em> time. The proxy returns a top-level aggregate error whose message
/// embeds a JSON payload describing each failing source, for example:
/// </para>
/// <code>
/// Request failed (remote): tools/list failed for 1 tool source(s), succeeded for 0 tool source(s)
/// {"errors":[{"name":"send_email","type":"mcp","error":{"code":"CONSENT_REQUIRED","message":"https://.../login?data=..."}}]}
/// </code>
/// <para>
/// The consent URL lives in <c>errors[].error.message</c>. This parser extracts those URLs so
/// <see cref="FoundryToolboxService"/> can surface the caller's consent requirement as an
/// <c>oauth_consent_request</c> for the response that opened the toolbox.
/// </para>
/// <para>
/// The payload is deserialized into <see cref="ToolsListFailure"/>. A payload that does not have that shape is
/// treated as unreadable rather than partially interpreted.
/// </para>
/// </remarks>
internal static partial class ToolboxConsentParser
{
    private const string ConsentRequiredCode = "CONSENT_REQUIRED";

    /// <summary>
    /// Attempts to interpret a <c>tools/list</c> failure message as a pure OAuth-consent
    /// requirement.
    /// </summary>
    /// <param name="toolboxName">The toolbox whose enumeration failed.</param>
    /// <param name="exceptionMessage">The <see cref="Exception.Message"/> of the MCP protocol exception.</param>
    /// <param name="consents">
    /// On success, one <see cref="McpConsentInfo"/> per consent-gated tool source. Empty otherwise.
    /// </param>
    /// <returns>
    /// <see langword="true"/> only when the message embeds a parseable <c>errors</c> array and
    /// <em>every</em> entry is a <c>CONSENT_REQUIRED</c> error. Returns <see langword="false"/>
    /// when no JSON payload is present, when parsing fails, or when any non-consent error is
    /// present (in that case consent alone cannot make enumeration succeed, so the caller should
    /// treat the failure as a hard error).
    /// </returns>
    public static bool TryParseConsentRequired(
        string toolboxName,
        string? exceptionMessage,
        out IReadOnlyList<McpConsentInfo> consents)
    {
        consents = [];

        // Fast pre-check: avoid JSON work unless the marker code is present.
        if (!ContainsConsentRequiredCode(exceptionMessage)
            || ParseToolSourceFailures(exceptionMessage!) is not { Count: > 0 } failures)
        {
            return false;
        }

        var result = new List<McpConsentInfo>(failures.Count);
        foreach (var failure in failures)
        {
            if (failure?.Error is not { } error
                || !string.Equals(error.Code, ConsentRequiredCode, StringComparison.Ordinal)
                || string.IsNullOrEmpty(error.Message))
            {
                // A non-consent error means enumeration stays broken even after consent.
                return false;
            }

            result.Add(new McpConsentInfo(toolboxName, failure.Name ?? toolboxName, error.Message));
        }

        consents = result;
        return true;
    }

    /// <summary>
    /// Describes, for a log entry, a toolbox failure that reports a <c>CONSENT_REQUIRED</c> tool source or
    /// cannot be fully inspected, without any consent links the failure may carry.
    /// </summary>
    /// <remarks>
    /// A consent link is issued for one caller, and the package never logs one. When enumeration fails both for
    /// consent and for another reason, <see cref="TryParseConsentRequired"/> rejects the error and the toolbox is
    /// skipped, so logging the exception would write that link to the logs. The description names each failing
    /// tool source and its error code only; a value that is not a plain identifier is replaced.
    /// </remarks>
    /// <param name="exception">The failure, including its inner exceptions.</param>
    /// <param name="description">On success, the failing tool sources and their error codes.</param>
    /// <returns>
    /// <see langword="true"/> when any exception in the chain mentions <c>CONSENT_REQUIRED</c> or the entire
    /// chain cannot be inspected, so the exception must not be logged; otherwise <see langword="false"/>.
    /// </returns>
    public static bool TryDescribeConsentFailure(Exception exception, out string description)
    {
        description = string.Empty;
        List<string> sources = [];
        bool consentRequired = false;
        bool inspectedAllExceptions;
        foreach (var message in GetExceptionMessages(exception, out inspectedAllExceptions))
        {
            if (!ContainsConsentRequiredCode(message))
            {
                continue;
            }

            consentRequired = true;

            // A payload that cannot be read adds nothing; the failure is still described without it.
            foreach (var failure in ParseToolSourceFailures(message) ?? [])
            {
                sources.Add($"{ToLoggableIdentifier(failure?.Name)} ({ToLoggableIdentifier(failure?.Error?.Code)})");
            }
        }

        if (!consentRequired && inspectedAllExceptions)
        {
            return false;
        }

        description = sources.Count > 0 ? string.Join(", ", sources) : "unreadable";
        return true;
    }

    private static bool ContainsConsentRequiredCode(string? message) =>
        message?.IndexOf(ConsentRequiredCode, StringComparison.Ordinal) >= 0;

    /// <summary>
    /// Reads the failing tool sources from the JSON payload that follows the text of a <c>tools/list</c> failure
    /// message.
    /// </summary>
    /// <returns>
    /// The <c>errors</c> entries, or <see langword="null"/> when the message has no payload, the payload is not
    /// valid JSON, or it does not have the shape of <see cref="ToolsListFailure"/>.
    /// </returns>
    private static List<ToolSourceFailure?>? ParseToolSourceFailures(string message)
    {
        int jsonStart = message.IndexOf('{');
        if (jsonStart < 0)
        {
            return null;
        }

        try
        {
            return JsonSerializer.Deserialize(message.AsSpan(jsonStart), ToolboxConsentJsonContext.Default.ToolsListFailure)?.Errors;
        }
        catch (JsonException)
        {
            return null;
        }
    }

    /// <summary>Reads the messages of an exception and the exceptions it wraps, up to a limit.</summary>
    private static List<string> GetExceptionMessages(Exception exception, out bool inspectedAllExceptions)
    {
        // Bounded so a pathological chain cannot keep a failure path busy.
        const int MaxExceptions = 32;
        var pending = new Stack<Exception>();
        List<string> messages = [];
        pending.Push(exception);
        for (int visited = 0; visited < MaxExceptions && pending.Count > 0; visited++)
        {
            var current = pending.Pop();
            messages.Add(current.Message);

            if (current is AggregateException aggregate)
            {
                foreach (var inner in aggregate.InnerExceptions)
                {
                    pending.Push(inner);
                }
            }
            else if (current.InnerException is { } inner)
            {
                pending.Push(inner);
            }
        }

        inspectedAllExceptions = pending.Count == 0;
        return messages;
    }

    /// <summary>Returns a value from the failure payload only when it is a plain identifier.</summary>
    private static string ToLoggableIdentifier(string? value)
    {
        const int MaxLength = 128;
        if (string.IsNullOrEmpty(value) || value!.Length > MaxLength)
        {
            return "unknown";
        }

        foreach (char c in value)
        {
            if (!(char.IsAsciiLetterOrDigit(c) || c is '_' or '-' or '.'))
            {
                return "unknown";
            }
        }

        return value;
    }

    /// <summary>The JSON payload of an aggregate <c>tools/list</c> failure.</summary>
    /// <param name="Errors">One entry per failing tool source.</param>
    private sealed record ToolsListFailure(List<ToolSourceFailure?>? Errors);

    /// <summary>One failing tool source of an aggregate <c>tools/list</c> failure.</summary>
    /// <param name="Name">The name of the tool source.</param>
    /// <param name="Error">Why the tool source failed.</param>
    private sealed record ToolSourceFailure(string? Name, ToolSourceError? Error);

    /// <summary>The error a tool source reported.</summary>
    /// <param name="Code">The error code, for example <c>CONSENT_REQUIRED</c>.</param>
    /// <param name="Message">The error message; for <c>CONSENT_REQUIRED</c>, the caller's consent link.</param>
    private sealed record ToolSourceError(string? Code, string? Message);

    [JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
    [JsonSerializable(typeof(ToolsListFailure))]
    private sealed partial class ToolboxConsentJsonContext : JsonSerializerContext;
}
