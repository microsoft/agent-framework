// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using Microsoft.Extensions.Configuration;

namespace Microsoft.Shared.Samples;

/// <summary>
/// Provides a centralized configuration management system for accessing application settings.
/// </summary>
public sealed class TestConfiguration
{
    private readonly IConfigurationRoot _configRoot;
    private static TestConfiguration? s_instance;

    private TestConfiguration(IConfigurationRoot configRoot)
    {
        this._configRoot = configRoot;
    }

    /// <summary>
    /// Initializes the configuration system with the specified configuration root.
    /// </summary>
    /// <param name="configRoot">The root of the configuration hierarchy used to initialize the system. Must not be <see langword="null"/>.</param>
    public static void Initialize(IConfigurationRoot configRoot)
    {
        s_instance = new TestConfiguration(configRoot);
    }

    /// <summary>
    /// Provides access to the configuration root for the application.
    /// </summary>
    public static IConfigurationRoot? ConfigurationRoot => s_instance?._configRoot;

    /// <summary>
    /// Gets the configuration settings for the OpenAI integration.
    /// </summary>
    public static OpenAIConfig OpenAI => LoadSection<OpenAIConfig>();

    /// <summary>
    /// Retrieves a configuration section based on the specified key.
    /// </summary>
    /// <param name="caller">The key identifying the configuration section to retrieve. Cannot be null or empty.</param>
    /// <returns>The <see cref="IConfigurationSection"/> corresponding to the specified key.</returns>
    /// <exception cref="InvalidOperationException">Thrown if the configuration root is not initialized or the specified key does not correspond to a valid section.</exception>
    public static IConfigurationSection GetSection(string caller)
    {
        return s_instance?._configRoot.GetSection(caller) ??
               throw new InvalidOperationException(caller);
    }

    private static T LoadSection<T>([CallerMemberName] string? caller = null)
    {
        if (s_instance is null)
        {
            throw new InvalidOperationException(
                "TestConfiguration must be initialized with a call to Initialize(IConfigurationRoot) before accessing configuration values.");
        }

        if (string.IsNullOrEmpty(caller))
        {
            throw new ArgumentNullException(nameof(caller));
        }

        return s_instance._configRoot.GetSection(caller).Get<T>() ??
               throw new InvalidOperationException(caller);
    }

    /// <summary>Represents the configuration settings required to interact with the OpenAI service.</summary>
    public class OpenAIConfig
    {
        /// <summary>Gets or sets the identifier for the chat completion model used in the application.</summary>
        public string? ChatModelId { get; set; }

        /// <summary>Gets or sets the identifier for the embedding model used in the application.</summary>
        public string? EmbeddingModelId { get; set; }

        /// <summary>Gets or sets the API key used for authentication with the OpenAI service.</summary>
        public string? ApiKey { get; set; }
    }
}
