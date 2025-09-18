// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.Configuration;

namespace AgentConformance.IntegrationTests.Support;

/// <summary>
/// Helper for loading test configuration settings.
/// </summary>
public sealed class TestConfiguration
{
    private static readonly IConfiguration s_configuration = new ConfigurationBuilder()
        .AddJsonFile(path: "testsettings.json", optional: true)
        .AddJsonFile(path: "testsettings.development.json", optional: true)
        .AddEnvironmentVariables()
        .AddUserSecrets<TestConfiguration>()
        .Build();

    /// <summary>
    /// Loads the type of configuration using a section name based on the type name.
    /// </summary>
    /// <typeparam name="T">The type of config to load.</typeparam>
    /// <returns>The loaded configuration section of the specified type.</returns>
    /// <exception cref="InvalidOperationException">Thrown if the configuration section cannot be loaded.</exception>
    public static T LoadSection<T>()
    {
        var configType = typeof(T);
        var configTypeName = configType.Name;

        const string TrimText = "Configuration";
        if (configTypeName.EndsWith(TrimText, StringComparison.OrdinalIgnoreCase))
        {
            configTypeName = configTypeName.Substring(0, configTypeName.Length - TrimText.Length);
        }

        return s_configuration.GetRequiredSection(configTypeName).Get<T>() ??
            throw new InvalidOperationException($"Could not load config for {configTypeName}.");
    }
}
