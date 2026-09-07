// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;
using OpenAI.Responses;

#pragma warning disable OPENAI001 // Experimental Responses API surfaces

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Verifies that citations produced by the Foundry Azure AI Search hosted tool survive the nested
/// model call and are returned by the hosted Responses API.
/// </summary>
[Trait("Category", "FoundryHostedAgents")]
public sealed class AzureSearchToolAnnotationsHostedAgentTests(
    AzureSearchToolAnnotationsHostedAgentFixture fixture)
    : IClassFixture<AzureSearchToolAnnotationsHostedAgentFixture>
{
    private static readonly TimeSpan s_timeout = TimeSpan.FromMinutes(3);
    private readonly AzureSearchToolAnnotationsHostedAgentFixture _fixture = fixture;

    [Fact]
    public async Task ResponsesApi_Streaming_EmitsUrlCitationAnnotationsAsync()
    {
        // Arrange
        ResponsesClient responses = this._fixture.AgentOpenAIClient.GetProjectResponsesClient();
        CreateResponseOptions options = CreateRequest();
        using CancellationTokenSource timeout = new(s_timeout);
        List<UriCitationMessageAnnotation> annotations = [];
        StreamingResponseCompletedUpdate? completed = null;

        // Act
        await foreach (StreamingResponseUpdate update in responses
            .CreateResponseStreamingAsync(options, timeout.Token)
            .WithCancellation(timeout.Token))
        {
            switch (update)
            {
                case StreamingResponseOutputTextAnnotationAddedUpdate
                {
                    Annotation: UriCitationMessageAnnotation annotation
                }:
                    annotations.Add(annotation);
                    break;

                case StreamingResponseCompletedUpdate completedUpdate:
                    completed = completedUpdate;
                    break;

                case StreamingResponseFailedUpdate failed:
                    throw new InvalidOperationException(
                        $"Hosted Azure AI Search response failed: {failed.Response.Error?.Message}");
            }
        }

        // Assert
        Assert.NotNull(completed);
        Assert.Contains(annotations, IsValidUrlCitation);
        Assert.Contains(GetFinalAnnotations(completed.Response), IsValidUrlCitation);
        Assert.Contains("TR-CANARY-7821", completed.Response.GetOutputText(), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ResponsesApi_NonStreaming_ReturnsUrlCitationAnnotationsAsync()
    {
        // Arrange
        ResponsesClient responses = this._fixture.AgentOpenAIClient.GetProjectResponsesClient();
        CreateResponseOptions options = CreateRequest();
        using CancellationTokenSource timeout = new(s_timeout);

        // Act
        ResponseResult response = (await responses.CreateResponseAsync(options, timeout.Token)).Value;

        // Assert
        Assert.True(
            response.Status == ResponseStatus.Completed,
            $"Hosted Azure AI Search response failed: {response.Error?.Message}");
        Assert.Contains("TR-CANARY-7821", response.GetOutputText(), StringComparison.OrdinalIgnoreCase);
        Assert.Contains(GetFinalAnnotations(response), IsValidUrlCitation);
    }

    private static CreateResponseOptions CreateRequest()
    {
        CreateResponseOptions options = new()
        {
            StoredOutputEnabled = false,
        };
        options.InputItems.Add(ResponseItem.CreateUserMessageItem(
            "What item code do I get with my return? Use Azure AI Search and cite the source."));
        return options;
    }

    private static IEnumerable<UriCitationMessageAnnotation> GetFinalAnnotations(ResponseResult response) =>
        response.OutputItems
            .OfType<MessageResponseItem>()
            .SelectMany(message => message.Content)
            .SelectMany(part => part.OutputTextAnnotations)
            .OfType<UriCitationMessageAnnotation>();

    private static bool IsValidUrlCitation(UriCitationMessageAnnotation annotation) =>
        annotation.Uri.IsAbsoluteUri &&
        !string.IsNullOrWhiteSpace(annotation.Title) &&
        annotation.StartIndex >= 0 &&
        annotation.EndIndex >= annotation.StartIndex;
}
