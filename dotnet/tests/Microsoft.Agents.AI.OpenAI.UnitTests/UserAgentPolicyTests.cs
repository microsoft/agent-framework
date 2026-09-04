// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI.Chat;
using OpenAI.Responses;
using OpenAIClient = OpenAI.OpenAIClient;
using OpenAIClientOptions = OpenAI.OpenAIClientOptions;

namespace Microsoft.Agents.AI.OpenAI.UnitTests;

[Collection(nameof(FeatureUsageTestGroup))]
public sealed class UserAgentPolicyTests : IDisposable
{
    private const string FeatureMaskDisabledEnvironmentVariable = "AGENT_FRAMEWORK_FEATURE_MASK_DISABLED";

    [Theory]
    [InlineData("https://openai.azure.com/")]
    [InlineData("https://resource.openai.azure.com/")]
    [InlineData("https://cognitiveservices.azure.com/")]
    [InlineData("https://resource.cognitiveservices.azure.com/")]
    [InlineData("https://services.ai.azure.com/")]
    [InlineData("https://project.services.ai.azure.com/")]
    [InlineData("https://RESOURCE.OPENAI.AZURE.COM./")]
    public void AzureOpenAIOrigin_AcceptsApprovedHttpsOrigins(string value)
    {
        // Arrange / Act
        bool approved = OpenAIUserAgentPolicies.Registration.IsApprovedOrigin(new Uri(value));

        // Assert
        Assert.True(approved);
    }

    [Theory]
    [InlineData("http://resource.openai.azure.com/")]
    [InlineData("https://resource.openai.azure.com.example.test/")]
    [InlineData("https://inference.ai.azure.com/")]
    [InlineData("https://api.openai.com/")]
    [InlineData("https://example.com/")]
    public void AzureOpenAIOrigin_RejectsNonAzureOpenAIOrigins(string value)
    {
        // Arrange / Act
        bool approved = OpenAIUserAgentPolicies.Registration.IsApprovedOrigin(new Uri(value));

        // Assert
        Assert.False(approved);
    }

    [Fact]
    public async Task AzureOpenAIChatAgent_EmitsBaseAndFeatureUserAgentAsync()
    {
        // Arrange
        using var handler = new RecordingHandler();
        OpenAIClient client = CreateAzureOpenAIClient(handler);
        ChatClientAgent agent = client.GetChatClient("deployment").AsAIAgent();
        FeatureUsageAssert.Reset();

        // Act
        _ = await Record.ExceptionAsync(() => agent.RunAsync("hello"));

        // Assert
        AssertEligibleUserAgent(Assert.Single(handler.UserAgents));
    }

    [Fact]
    public async Task AzureOpenAIResponsesAgent_EmitsBaseAndFeatureUserAgentAsync()
    {
        // Arrange
        using var handler = new RecordingHandler();
        OpenAIClient client = CreateAzureOpenAIClient(handler);
        ChatClientAgent agent = client.GetResponsesClient().AsAIAgent(model: "deployment");
        FeatureUsageAssert.Reset();

        // Act
        _ = await Record.ExceptionAsync(() => agent.RunAsync("hello"));

        // Assert
        AssertEligibleUserAgent(Assert.Single(handler.UserAgents));
    }

    [Fact]
    public async Task AzureOpenAIChatAgent_DisabledMaskEmitsOnlyBaseUserAgentAsync()
    {
        // Arrange
        string? originalValue = Environment.GetEnvironmentVariable(FeatureMaskDisabledEnvironmentVariable);
        try
        {
            Environment.SetEnvironmentVariable(FeatureMaskDisabledEnvironmentVariable, "true");
            FeatureUsageAssert.Reset();
            using var handler = new RecordingHandler();
            OpenAIClient client = CreateAzureOpenAIClient(handler);
            ChatClientAgent agent = client.GetChatClient("deployment").AsAIAgent();

            // Act
            _ = await Record.ExceptionAsync(() => agent.RunAsync("hello"));

            // Assert
            string userAgent = Assert.IsType<string>(Assert.Single(handler.UserAgents));
            Assert.Contains("agent-framework-dotnet/", userAgent, StringComparison.Ordinal);
            Assert.DoesNotContain("(feat=", userAgent, StringComparison.Ordinal);
        }
        finally
        {
            Environment.SetEnvironmentVariable(FeatureMaskDisabledEnvironmentVariable, originalValue);
            FeatureUsageAssert.Reset();
        }
    }

    [Theory]
    [InlineData("https://api.openai.com/v1")]
    [InlineData("https://gateway.example.com/v1")]
    [InlineData("http://resource.openai.azure.com/v1")]
    [InlineData("https://resource.openai.azure.com.evil.test/v1")]
    [InlineData("https://resource.inference.ai.azure.com/v1")]
    public async Task IneligibleOpenAIChatAgent_DoesNotEmitAgentFrameworkUserAgentAsync(string endpoint)
    {
        // Arrange
        using var handler = new RecordingHandler();
#pragma warning disable CA5399
        var httpClient = new HttpClient(handler, disposeHandler: false);
#pragma warning restore CA5399
        var options = new OpenAIClientOptions
        {
            Endpoint = new Uri(endpoint),
            Transport = new HttpClientPipelineTransport(httpClient),
        };
        var client = new OpenAIClient(new ApiKeyCredential("test-key"), options);
        ChatClientAgent agent = client.GetChatClient("model").AsAIAgent();
        FeatureUsageAssert.Reset();

        // Act
        _ = await Record.ExceptionAsync(() => agent.RunAsync("hello"));

        // Assert
        string userAgent = Assert.IsType<string>(Assert.Single(handler.UserAgents));
        Assert.DoesNotContain("agent-framework-dotnet/", userAgent, StringComparison.Ordinal);
        Assert.DoesNotContain("(feat=", userAgent, StringComparison.Ordinal);
    }

    public void Dispose() => FeatureUsageAssert.Reset();

    private static OpenAIClient CreateAzureOpenAIClient(HttpMessageHandler handler)
    {
#pragma warning disable CA5399
        var httpClient = new HttpClient(handler, disposeHandler: false);
#pragma warning restore CA5399
        return new OpenAIClient(
            new ApiKeyCredential("test-key"),
            new OpenAIClientOptions
            {
                Endpoint = new Uri("https://resource.openai.azure.com/openai/v1/"),
                Transport = new HttpClientPipelineTransport(httpClient),
            });
    }

    private static void AssertEligibleUserAgent(string? userAgent)
    {
        Assert.NotNull(userAgent);
        Assert.Contains("agent-framework-dotnet/", userAgent, StringComparison.Ordinal);
#pragma warning disable MAAI001
        Assert.Contains(FeatureUsage.ApplyToUserAgent(string.Empty), userAgent, StringComparison.Ordinal);
#pragma warning restore MAAI001
    }

    private sealed class RecordingHandler : HttpMessageHandler
    {
        public List<string?> UserAgents { get; } = [];

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            this.UserAgents.Add(
                request.Headers.TryGetValues("User-Agent", out IEnumerable<string>? values)
                    ? string.Join(" ", values)
                    : null);

            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("{}", Encoding.UTF8, "application/json"),
                RequestMessage = request,
            });
        }
    }
}
