// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Encodes agent session identities for Foundry-backed and filesystem storage implementations.
/// </summary>
internal static class FoundryAgentSessionKeyEncoder
{
    private static readonly UTF8Encoding s_strictUtf8 =
        new(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true);

    internal static string BuildLogicalKey(string agentIdentity, AgentSessionStoreKey key)
    {
        _ = Throw.IfNull(key);

        StringBuilder builder = new();
        AppendComponent(builder, 'a', Throw.IfNullOrWhitespace(agentIdentity));
        AppendComponent(builder, 's', key.SessionId);
        foreach (KeyValuePair<string, string> partition in key.Partitions)
        {
            AppendComponent(builder, 'n', partition.Key);
            AppendComponent(builder, 'v', partition.Value);
        }
        builder.Length--;
        return builder.ToString();
    }

    internal static string BuildStorageKey(string logicalKey)
    {
        byte[] hash;
        try
        {
            hash = SHA256.HashData(s_strictUtf8.GetBytes(logicalKey));
        }
        catch (EncoderFallbackException exception)
        {
            throw new ArgumentException(
                "Session keys and agent identities must contain valid UTF-16 text.",
                nameof(logicalKey),
                exception);
        }

        return $"s-{Convert.ToBase64String(hash).TrimEnd('=').Replace('+', '-').Replace('/', '_')}";
    }

    internal static string BuildAgentStorageKey(string agentIdentity)
    {
        _ = Throw.IfNullOrWhitespace(agentIdentity);
        return BuildStorageKey($"a{agentIdentity.Length}:{agentIdentity}");
    }

    private static void AppendComponent(StringBuilder builder, char prefix, string value)
        => builder.Append(prefix).Append(value.Length).Append(':').Append(value).Append('|');
}
