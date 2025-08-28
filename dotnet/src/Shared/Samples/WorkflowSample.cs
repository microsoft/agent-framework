// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Samples;

namespace Microsoft.Shared.SampleUtilities;

/// <summary>
/// Provides a base class for workflow samples that demonstrates workflow usage patterns.
/// Inherits from <see cref="BaseSample"/> and provides utility methods for chat clients,
/// and writing responses to the console or test output.
/// </summary>
public abstract class WorkflowSample(ITestOutputHelper output) : BaseSample(output)
{
    /// <summary>
    /// Creates an instance of the Azure OpenAI chat client.
    /// </summary>
    /// <returns>An instance of <see cref="IChatClient"/>.</returns>
    protected IChatClient GetAzureOpenAIChatClient()
        => ((TestConfiguration.AzureOpenAI.ApiKey is null)
            ? new AzureOpenAIClient(TestConfiguration.AzureOpenAI.Endpoint, new AzureCliCredential())
            : new AzureOpenAIClient(TestConfiguration.AzureOpenAI.Endpoint, new ApiKeyCredential(TestConfiguration.AzureOpenAI.ApiKey)))
                .GetChatClient(TestConfiguration.AzureOpenAI.DeploymentName)
                .AsIChatClient();
}