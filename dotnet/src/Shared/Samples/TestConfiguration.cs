// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using Microsoft.Extensions.Configuration;

namespace Microsoft.Shared.Samples;

#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.

/// <summary>
/// Provides access to application configuration settings.
/// </summary>
public sealed class TestConfiguration
{
    /// <summary>Gets the configuration settings for the OpenAI integration.</summary>
    public static OpenAIConfig OpenAI => LoadSection<OpenAIConfig>();

    /// <summary>Gets the configuration settings for the Azure OpenAI integration.</summary>
    public static AzureOpenAIConfig AzureOpenAI => LoadSection<AzureOpenAIConfig>();

    /// <summary>Gets the configuration settings for the AzureAI integration.</summary>
    public static AzureAIConfig AzureAI => LoadSection<AzureAIConfig>();

    /// <summary>Represents the configuration settings required to interact with the OpenAI service.</summary>
    public class OpenAIConfig
    {
        /// <summary>Gets or sets the identifier for the chat completion model used in the application.</summary>
        public string ChatModelId { get; set; }

        /// <summary>Gets or sets the API key used for authentication with the OpenAI service.</summary>
        public string ApiKey { get; set; }
    }

    /// <summary>
    /// Represents the configuration settings required to interact with the Azure OpenAI service.
    /// </summary>
    public class AzureOpenAIConfig
    {
        /// <summary>Gets the URI endpoint used to connect to the service.</summary>
        public Uri Endpoint { get; set; }

        /// <summary>Gets or sets the name of the deployment.</summary>
        public string DeploymentName { get; set; }

        /// <summary>Gets or sets the API key used for authentication with the OpenAI service.</summary>
        public string? ApiKey { get; set; }
    }

    /// <summary>Represents the configuration settings required to interact with the Azure AI service.</summary>
    public sealed class AzureAIConfig
    {
        /// <summary>Gets or sets the endpoint of Azure AI Foundry project.</summary>
        public string? Endpoint { get; set; }

        /// <summary>Gets or sets the name of the model deployment.</summary>
        public string? DeploymentName { get; set; }
    }

    /// <summary>
    /// Initializes the configuration system with the specified configuration root.
    /// </summary>
    /// <param name="configRoot">The root of the configuration hierarchy used to initialize the system. Must not be <see langword="null"/>.</param>
    public static void Initialize(IConfigurationRoot configRoot) =>
        s_instance = new TestConfiguration(configRoot);

    #region Private Members

    private readonly IConfigurationRoot _configRoot;
    private static TestConfiguration? s_instance;

    private TestConfiguration(IConfigurationRoot configRoot)
    {
        this._configRoot = configRoot;
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

    #endregion
}
