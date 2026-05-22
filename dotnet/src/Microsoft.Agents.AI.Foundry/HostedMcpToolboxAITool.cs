// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// A marker <see cref="HostedMcpServerTool"/> that identifies a Foundry Toolbox by name
/// (and optional version) on the OpenAI Responses <c>mcp</c> wire format.
/// </summary>
/// <remarks>
/// <para>
/// The hosted server recognizes this marker by its <see cref="HostedMcpServerTool.ServerAddress"/>
/// scheme (<see cref="UriScheme"/>) and resolves it to the set of MCP tools exposed by the
/// matching toolbox registered in the Foundry project.
/// </para>
/// <para>
/// Callers should not construct this type directly. Use one of the
/// <c>FoundryAITool.CreateHostedMcpToolbox(...)</c> factory overloads.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public sealed class HostedMcpToolboxAITool : HostedMcpServerTool
{
    /// <summary>
    /// The URI scheme used to identify Foundry Toolbox markers on the wire.
    /// </summary>
    public const string UriScheme = "foundry-toolbox";

    /// <summary>
    /// Initializes a new instance of the <see cref="HostedMcpToolboxAITool"/> class.
    /// </summary>
    /// <param name="toolboxName">The Foundry toolbox name.</param>
    /// <param name="version">
    /// Optional pinned toolbox version. When <see langword="null"/>, the project's default version is used.
    /// Currently reserved for forward compatibility — version-specific routing is handled server-side by
    /// the Foundry proxy.
    /// </param>
    public HostedMcpToolboxAITool(string toolboxName, string? version = null)
        : base(
            serverName: NotNullOrWhitespace(toolboxName, nameof(toolboxName)),
            serverAddress: BuildAddress(toolboxName, version))
    {
        this.ToolboxName = toolboxName;
        this.Version = version;
    }

    /// <summary>
    /// Gets the Foundry toolbox name.
    /// </summary>
    public string ToolboxName { get; }

    /// <summary>
    /// Gets the pinned toolbox version, or <see langword="null"/> to use the project's default.
    /// </summary>
    public string? Version { get; }

    /// <summary>
    /// Builds the toolbox marker address: <c>foundry-toolbox://{name}[?version={v}]</c>.
    /// </summary>
    public static string BuildAddress(string toolboxName, string? version)
    {
        _ = NotNullOrWhitespace(toolboxName, nameof(toolboxName));

        return string.IsNullOrEmpty(version)
            ? $"{UriScheme}://{toolboxName}"
            : $"{UriScheme}://{toolboxName}?version={Uri.EscapeDataString(version)}";
    }

    /// <summary>
    /// Attempts to parse a toolbox marker address into its name and optional version components.
    /// </summary>
    /// <param name="address">The <see cref="HostedMcpServerTool.ServerAddress"/> to inspect.</param>
    /// <param name="toolboxName">When this method returns <see langword="true"/>, the parsed toolbox name.</param>
    /// <param name="version">When this method returns <see langword="true"/>, the optional version, or <see langword="null"/>.</param>
    /// <returns><see langword="true"/> if <paramref name="address"/> is a Foundry toolbox marker; otherwise <see langword="false"/>.</returns>
    public static bool TryParseToolboxAddress(
        string? address,
        [NotNullWhen(true)] out string? toolboxName,
        out string? version)
    {
        toolboxName = null;
        version = null;

        if (string.IsNullOrEmpty(address))
        {
            return false;
        }

        if (!Uri.TryCreate(address, UriKind.Absolute, out var uri))
        {
            return false;
        }

        if (!string.Equals(uri.Scheme, UriScheme, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        // For foundry-toolbox://name, the name appears as Authority (host) with an empty path.
        // For foundry-toolbox:name (rare), it falls through to PathAndQuery.
        var name = uri.Host;
        if (string.IsNullOrEmpty(name) && !string.IsNullOrEmpty(uri.AbsolutePath))
        {
            name = uri.AbsolutePath.TrimStart('/');
        }

        if (string.IsNullOrEmpty(name))
        {
            return false;
        }

        toolboxName = name;

        var query = uri.Query;
        if (!string.IsNullOrEmpty(query))
        {
            // Minimal parser to avoid a HttpUtility dependency on netstandard.
            foreach (var part in query.TrimStart('?').Split('&'))
            {
                var eq = part.IndexOf('=');
                if (eq <= 0)
                {
                    continue;
                }

                var key = part.Substring(0, eq);
                if (string.Equals(key, "version", StringComparison.OrdinalIgnoreCase))
                {
                    version = Uri.UnescapeDataString(part.Substring(eq + 1));
                    break;
                }
            }
        }

        return true;
    }

    private static string NotNullOrWhitespace(string value, string paramName)
    {
        if (value is null)
        {
            throw new ArgumentNullException(paramName);
        }

        if (string.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException("Value cannot be empty or whitespace.", paramName);
        }

        return value;
    }
}
