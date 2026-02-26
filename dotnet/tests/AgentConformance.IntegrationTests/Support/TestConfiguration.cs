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
        .AddJsonFile(path: "testsettings.development.json", optional: true)
        .AddEnvironmentVariables()
        .AddUserSecrets<TestConfiguration>()
        .Build();

    /// <summary>
    /// Gets a configuration value by its flat key name.
    /// </summary>
    /// <param name="key">The configuration key.</param>
    /// <returns>The configuration value, or <see langword="null"/> if not found.</returns>
    public static string? GetValue(string key) => s_configuration[key];

    /// <summary>
    /// Gets a required configuration value by its flat key name.
    /// </summary>
    /// <param name="key">The configuration key.</param>
    /// <returns>The configuration value.</returns>
    /// <exception cref="InvalidOperationException">Thrown if the configuration value is not found.</exception>
    public static string GetRequiredValue(string key) =>
        s_configuration[key] ?? throw new InvalidOperationException($"Configuration key '{key}' is required but was not found.");
}
