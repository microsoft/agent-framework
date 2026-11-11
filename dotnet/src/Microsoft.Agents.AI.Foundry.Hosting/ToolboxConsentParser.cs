// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;

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
/// </remarks>
internal static class ToolboxConsentParser
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
        if (!ContainsConsentRequiredCode(exceptionMessage))
        {
            return false;
        }

        var result = new List<McpConsentInfo>();
        try
        {
            using var document = ParseErrorsPayload(exceptionMessage!, out var errors);
            if (document is null)
            {
                return false;
            }

            foreach (var error in errors.EnumerateArray())
            {
                if (!error.TryGetProperty("error", out var errorBody)
                    || !errorBody.TryGetProperty("code", out var code)
                    || code.ValueKind != JsonValueKind.String
                    || !string.Equals(code.GetString(), ConsentRequiredCode, StringComparison.Ordinal))
                {
                    // A non-consent error means enumeration stays broken even after consent.
                    return false;
                }

                string? consentUrl = errorBody.TryGetProperty("message", out var message)
                    && message.ValueKind == JsonValueKind.String
                        ? message.GetString()
                        : null;

                if (string.IsNullOrEmpty(consentUrl))
                {
                    return false;
                }

                string toolName = error.TryGetProperty("name", out var name)
                    && name.ValueKind == JsonValueKind.String
                        ? name.GetString() ?? toolboxName
                        : toolboxName;

                result.Add(new McpConsentInfo(toolboxName, toolName, consentUrl!));
            }
        }
        catch (JsonException)
        {
            return false;
        }

        if (result.Count == 0)
        {
            return false;
        }

        consents = result;
        return true;
    }

    /// <summary>
    /// Describes, for a log entry, a toolbox failure that reports a <c>CONSENT_REQUIRED</c> tool source anywhere
    /// in its exception chain, without the consent links the failure carries.
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
    /// <see langword="true"/> when any exception in the chain mentions <c>CONSENT_REQUIRED</c>, so the exception
    /// must not be logged; otherwise <see langword="false"/>.
    /// </returns>
    public static bool TryDescribeConsentFailure(Exception exception, out string description)
    {
        description = string.Empty;
        List<string> sources = [];
        bool consentRequired = false;
        foreach (var message in EnumerateMessages(exception))
        {
            if (!ContainsConsentRequiredCode(message))
            {
                continue;
            }

            consentRequired = true;
            try
            {
                using var document = ParseErrorsPayload(message, out var errors);
                if (document is null)
                {
                    continue;
                }

                foreach (var error in errors.EnumerateArray())
                {
                    string? name = error.ValueKind == JsonValueKind.Object
                        && error.TryGetProperty("name", out var nameElement)
                        && nameElement.ValueKind == JsonValueKind.String
                            ? nameElement.GetString()
                            : null;
                    string? code = error.ValueKind == JsonValueKind.Object
                        && error.TryGetProperty("error", out var errorBody)
                        && errorBody.ValueKind == JsonValueKind.Object
                        && errorBody.TryGetProperty("code", out var codeElement)
                        && codeElement.ValueKind == JsonValueKind.String
                            ? codeElement.GetString()
                            : null;
                    sources.Add($"{ToLoggableIdentifier(name)} ({ToLoggableIdentifier(code)})");
                }
            }
            catch (JsonException)
            {
                // The payload cannot be read; the failure is still described without it.
            }
        }

        if (!consentRequired)
        {
            return false;
        }

        description = sources.Count > 0 ? string.Join(", ", sources) : "unreadable";
        return true;
    }

    private static bool ContainsConsentRequiredCode(string? message) =>
        message?.IndexOf(ConsentRequiredCode, StringComparison.Ordinal) >= 0;

    /// <summary>
    /// Parses the JSON payload that follows the text of a <c>tools/list</c> failure message, and returns its
    /// <c>errors</c> array.
    /// </summary>
    /// <returns>The parsed document, which owns <paramref name="errors"/>, or <see langword="null"/> when the
    /// message has no payload with an <c>errors</c> array.</returns>
    /// <exception cref="JsonException">The payload is not valid JSON.</exception>
    private static JsonDocument? ParseErrorsPayload(string message, out JsonElement errors)
    {
        errors = default;
        int jsonStart = message.IndexOf('{');
        if (jsonStart < 0)
        {
            return null;
        }

        var document = JsonDocument.Parse(message.AsSpan(jsonStart).ToString());
        if (document.RootElement.ValueKind != JsonValueKind.Object
            || !document.RootElement.TryGetProperty("errors", out errors)
            || errors.ValueKind != JsonValueKind.Array)
        {
            document.Dispose();
            errors = default;
            return null;
        }

        return document;
    }

    /// <summary>Yields the message of an exception and of every exception it wraps.</summary>
    private static IEnumerable<string> EnumerateMessages(Exception exception)
    {
        // Bounded so a pathological chain cannot keep a failure path busy.
        const int MaxExceptions = 32;
        var pending = new Stack<Exception>();
        pending.Push(exception);
        for (int visited = 0; visited < MaxExceptions && pending.Count > 0; visited++)
        {
            var current = pending.Pop();
            yield return current.Message;

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
}
