// Copyright (c) Microsoft. All rights reserved.

using System.Reflection;
using Microsoft.Azure.Cosmos;

namespace Microsoft.Agents.AI.CosmosNoSql;

/// <summary>
/// Provides shared Cosmos DB client configuration for Agent Framework Cosmos NoSQL integrations.
/// Ensures all internally-created <see cref="CosmosClient"/> instances carry a consistent
/// <see cref="CosmosClientOptions.ApplicationName"/> for telemetry and diagnostics.
/// </summary>
internal static class CosmosOptionsHelper
{
    /// <summary>
    /// Maximum length allowed by the Cosmos DB .NET SDK for <see cref="CosmosClientOptions.ApplicationName"/>.
    /// </summary>
    private const int MaxApplicationNameLength = 64;

    private static readonly string s_version = GetVersion();

    /// <summary>
    /// Creates a <see cref="CosmosClientOptions"/> instance pre-configured with the
    /// Agent Framework application name for User-Agent identification.
    /// </summary>
    /// <param name="component">The fully-qualified component class name (e.g. "CosmosChatHistoryProvider").</param>
    /// <returns>A new <see cref="CosmosClientOptions"/> with <see cref="CosmosClientOptions.ApplicationName"/> set.</returns>
    public static CosmosClientOptions CreateOptions(string component)
    {
        return new CosmosClientOptions
        {
            ApplicationName = BuildApplicationName(component)
        };
    }

    /// <summary>
    /// Ensures the given <see cref="CosmosClient"/> has an <see cref="CosmosClientOptions.ApplicationName"/> set.
    /// If the client already has a non-empty ApplicationName, it is not overridden.
    /// </summary>
    /// <param name="cosmosClient">The client to apply the application name to.</param>
    /// <param name="component">The fully-qualified component class name (e.g. "CosmosChatHistoryProvider").</param>
    public static void EnsureApplicationName(CosmosClient cosmosClient, string component)
    {
        if (string.IsNullOrWhiteSpace(cosmosClient.ClientOptions.ApplicationName))
        {
            cosmosClient.ClientOptions.ApplicationName = BuildApplicationName(component);
        }
    }

    private static string BuildApplicationName(string component)
    {
        var applicationName = $"Microsoft.Agents.AI.CosmosNoSql.{component}/{s_version}";

        if (applicationName.Length > MaxApplicationNameLength)
        {
            applicationName = applicationName.Substring(0, MaxApplicationNameLength);
        }

        return applicationName;
    }

    private static string GetVersion()
    {
        if (typeof(CosmosOptionsHelper).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion is string version)
        {
            int pos = version.IndexOf('+', System.StringComparison.Ordinal);
            if (pos >= 0)
            {
                version = version.Substring(0, pos);
            }

            if (version.Length > 0)
            {
                return version;
            }
        }

        return "unknown";
    }
}
