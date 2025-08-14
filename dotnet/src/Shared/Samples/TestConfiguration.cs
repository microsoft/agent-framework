// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
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

    /// <summary>Represents the configuration settings required to interact with the OpenAI service.</summary>
    public class OpenAIConfig
    {
        /// <summary>Gets or sets the identifier for the chat completion model used in the application.</summary>
        [DisplayName("OpenAI Chat Model")]
        [Description("The OpenAI model identifier to use for chat completions (e.g., 'gpt-4o', 'gpt-5'). This determines which AI model will process your requests.")]
        [Required]
        public string ChatModelId { get; set; }

        /// <summary>Gets or sets the API key used for authentication with the OpenAI service.</summary>
        [DisplayName("OpenAI API Key")]
        [Description("Your OpenAI API key for authentication. You can find this in your OpenAI account dashboard under API keys. Keep this secure as it provides access to your OpenAI account.")]
        [Required, Sensitive]
        public string ApiKey { get; set; }
    }

    /// <summary>
    /// Represents the configuration settings required to interact with the Azure OpenAI service.
    /// </summary>
    public class AzureOpenAIConfig
    {
        /// <summary>Gets the URI endpoint used to connect to the service.</summary>
        [DisplayName("Azure OpenAI Endpoint")]
        [Description("The endpoint URL for your Azure OpenAI service instance. This can be found in the Azure portal under your OpenAI resource (e.g., 'https://your-resource.openai.azure.com/').")]
        [Required, Sensitive]
        public Uri Endpoint { get; set; }

        /// <summary>Gets or sets the name of the deployment.</summary>
        [DisplayName("Azure OpenAI Deployment Name")]
        [Description("The name of your model deployment in Azure OpenAI. This is the deployment you created for your specific model (e.g., 'gpt-4-deployment').")]
        [Required]
        public string DeploymentName { get; set; }

        /// <summary>Gets or sets the API key used for authentication with the OpenAI service.</summary>
        [DisplayName("Azure OpenAI API Key")]
        [Description("Your Azure OpenAI API key for authentication. This can be found in the Azure portal under your OpenAI resource's 'Keys and Endpoint' section. Leave empty to use Azure AD authentication.")]
        [Optional, Sensitive]
        public string? ApiKey { get; set; }
    }

    /// <summary>Represents the configuration settings required to interact with the Azure AI service.</summary>
    public sealed class AzureAIConfig
    {
        /// <summary>Gets or sets the endpoint of Azure AI Foundry project.</summary>
        [DisplayName("Azure AI Foundry Project Endpoint")]
        [Description("The endpoint URL for your Azure AI Foundry project. This can be found in the Azure AI Foundry portal under your project's overview page (e.g., 'https://your-project.cognitiveservices.azure.com/api/projects/your-project').")]
        [Required, Sensitive]
        public string Endpoint { get; set; }

        /// <summary>Gets or sets the name of the model deployment.</summary>
        [DisplayName("Azure AI Foundry Deployment Name")]
        [Description("The name of your model deployment in Azure AI Foundry. This is the deployment you created for your specific model within your AI Foundry project.")]
        [Required]
        public string DeploymentName { get; set; }
    }

    /// <summary>
    /// Initializes the configuration system with the specified configuration root.
    /// </summary>
    /// <param name="configRoot">The root of the configuration hierarchy used to initialize the system. Must not be <see langword="null"/>.</param>
    public static void Initialize(IConfigurationRoot configRoot)
    {
        s_instance = new TestConfiguration(configRoot);
    }

    #region Private Members

    private readonly IConfigurationRoot _configRoot;
    private static TestConfiguration? s_instance;

    private TestConfiguration(IConfigurationRoot configRoot)
    {
        this._configRoot = configRoot;
    }

    /// <summary>
    /// Gets the configuration settings for the AzureAI integration.
    /// </summary>
    public static AzureAIConfig AzureAI => LoadSection<AzureAIConfig>();

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

    /// <summary>
    /// Marks a configuration property as containing sensitive data that should be masked in the UI.
    /// </summary>
    [AttributeUsage(AttributeTargets.Property)]
    public sealed class SensitiveAttribute : Attribute;

    /// <summary>
    /// Marks a configuration property as optional (not required for the application to function).
    /// </summary>
    [AttributeUsage(AttributeTargets.Property)]
    public sealed class OptionalAttribute : Attribute;
}
