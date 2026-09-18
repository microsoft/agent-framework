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
/// <see cref="FoundryToolboxService"/> can keep the container routable and surface the consent
/// requirement as a per-request <c>oauth_consent_request</c> instead of failing readiness.
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

        if (string.IsNullOrEmpty(exceptionMessage))
        {
            return false;
        }

        // Fast pre-check: avoid JSON work unless the marker code is present.
        if (exceptionMessage!.IndexOf(ConsentRequiredCode, StringComparison.Ordinal) < 0)
        {
            return false;
        }

        int jsonStart = exceptionMessage.IndexOf('{');
        if (jsonStart < 0)
        {
            return false;
        }

        var result = new List<McpConsentInfo>();
        try
        {
            using var document = JsonDocument.Parse(exceptionMessage.AsSpan(jsonStart).ToString());
            if (!document.RootElement.TryGetProperty("errors", out var errors)
                || errors.ValueKind != JsonValueKind.Array)
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
}
