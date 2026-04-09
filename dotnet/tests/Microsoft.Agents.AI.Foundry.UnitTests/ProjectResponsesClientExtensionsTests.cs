// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Reflection;
using Azure.AI.Extensions.OpenAI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Unit tests for the <see cref="ProjectResponsesClientExtensions"/> class.
/// </summary>
public sealed class ProjectResponsesClientExtensionsTests
{
    private static ProjectResponsesClient CreateTestClient()
    {
        return new ProjectResponsesClient(new FakeAuthenticationTokenProvider());
    }

    /// <summary>
    /// Verify that AsIChatClientWithStoredOutputDisabled throws ArgumentNullException when client is null.
    /// </summary>
    [Fact]
    public void AsIChatClientWithStoredOutputDisabled_WithNullClient_ThrowsArgumentNullException()
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            ((ProjectResponsesClient)null!).AsIChatClientWithStoredOutputDisabled());

        Assert.Equal("responseClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsIChatClientWithStoredOutputDisabled wraps the original ProjectResponsesClient,
    /// which remains accessible via the service chain.
    /// </summary>
    [Fact]
    public void AsIChatClientWithStoredOutputDisabled_InnerResponsesClientIsAccessible()
    {
        // Arrange
        var responseClient = CreateTestClient();

        // Act
        var chatClient = responseClient.AsIChatClientWithStoredOutputDisabled();

        // Assert - the inner ProjectResponsesClient should be accessible via GetService
        var innerClient = chatClient.GetService<ResponsesClient>();
        Assert.NotNull(innerClient);
        Assert.Same(responseClient, innerClient);
    }

    /// <summary>
    /// Verify that AsIChatClientWithStoredOutputDisabled with includeReasoningEncryptedContent false
    /// wraps the original ProjectResponsesClient, which remains accessible via the service chain.
    /// </summary>
    [Fact]
    public void AsIChatClientWithStoredOutputDisabled_WithIncludeReasoningFalse_InnerResponsesClientIsAccessible()
    {
        // Arrange
        var responseClient = CreateTestClient();

        // Act
        var chatClient = responseClient.AsIChatClientWithStoredOutputDisabled(includeReasoningEncryptedContent: false);

        // Assert - the inner ProjectResponsesClient should be accessible via GetService
        var innerClient = chatClient.GetService<ResponsesClient>();
        Assert.NotNull(innerClient);
        Assert.Same(responseClient, innerClient);
    }

    /// <summary>
    /// Verify that AsIChatClientWithStoredOutputDisabled with default parameter (includeReasoningEncryptedContent = true)
    /// configures StoredOutputEnabled to false and includes ReasoningEncryptedContent in IncludedProperties.
    /// </summary>
    [Fact]
    public void AsIChatClientWithStoredOutputDisabled_Default_ConfiguresStoredOutputDisabledWithReasoningEncryptedContent()
    {
        // Arrange
        var responseClient = CreateTestClient();

        // Act
        var chatClient = responseClient.AsIChatClientWithStoredOutputDisabled();

        // Assert
        var createResponseOptions = GetCreateResponseOptionsFromPipeline(chatClient);
        Assert.NotNull(createResponseOptions);
        Assert.False(createResponseOptions.StoredOutputEnabled);
        Assert.Contains(IncludedResponseProperty.ReasoningEncryptedContent, createResponseOptions.IncludedProperties);
    }

    /// <summary>
    /// Verify that AsIChatClientWithStoredOutputDisabled with includeReasoningEncryptedContent explicitly set to true
    /// configures StoredOutputEnabled to false and includes ReasoningEncryptedContent in IncludedProperties.
    /// </summary>
    [Fact]
    public void AsIChatClientWithStoredOutputDisabled_WithIncludeReasoningTrue_ConfiguresStoredOutputDisabledWithReasoningEncryptedContent()
    {
        // Arrange
        var responseClient = CreateTestClient();

        // Act
        var chatClient = responseClient.AsIChatClientWithStoredOutputDisabled(includeReasoningEncryptedContent: true);

        // Assert
        var createResponseOptions = GetCreateResponseOptionsFromPipeline(chatClient);
        Assert.NotNull(createResponseOptions);
        Assert.False(createResponseOptions.StoredOutputEnabled);
        Assert.Contains(IncludedResponseProperty.ReasoningEncryptedContent, createResponseOptions.IncludedProperties);
    }

    /// <summary>
    /// Verify that AsIChatClientWithStoredOutputDisabled with includeReasoningEncryptedContent set to false
    /// configures StoredOutputEnabled to false and does not include ReasoningEncryptedContent in IncludedProperties.
    /// </summary>
    [Fact]
    public void AsIChatClientWithStoredOutputDisabled_WithIncludeReasoningFalse_ConfiguresStoredOutputDisabledWithoutReasoningEncryptedContent()
    {
        // Arrange
        var responseClient = CreateTestClient();

        // Act
        var chatClient = responseClient.AsIChatClientWithStoredOutputDisabled(includeReasoningEncryptedContent: false);

        // Assert
        var createResponseOptions = GetCreateResponseOptionsFromPipeline(chatClient);
        Assert.NotNull(createResponseOptions);
        Assert.False(createResponseOptions.StoredOutputEnabled);
        Assert.DoesNotContain(IncludedResponseProperty.ReasoningEncryptedContent, createResponseOptions.IncludedProperties);
    }

    /// <summary>
    /// Verify that AsIChatClientWithStoredOutputDisabled works with an optional deployment name.
    /// </summary>
    [Fact]
    public void AsIChatClientWithStoredOutputDisabled_WithDeploymentName_ConfiguresStoredOutputDisabled()
    {
        // Arrange
        var responseClient = CreateTestClient();

        // Act
        var chatClient = responseClient.AsIChatClientWithStoredOutputDisabled(deploymentName: "my-deployment");

        // Assert
        var createResponseOptions = GetCreateResponseOptionsFromPipeline(chatClient);
        Assert.NotNull(createResponseOptions);
        Assert.False(createResponseOptions.StoredOutputEnabled);
        Assert.Contains(IncludedResponseProperty.ReasoningEncryptedContent, createResponseOptions.IncludedProperties);
    }

    /// <summary>
    /// Extracts the <see cref="CreateResponseOptions"/> produced by the ConfigureOptions pipeline
    /// by using reflection to access the configure action and invoking it on a test <see cref="ChatOptions"/>.
    /// </summary>
    private static CreateResponseOptions? GetCreateResponseOptionsFromPipeline(IChatClient chatClient)
    {
        var configureField = chatClient.GetType().GetField("_configureOptions", BindingFlags.NonPublic | BindingFlags.Instance);
        Assert.NotNull(configureField);

        var configureAction = configureField.GetValue(chatClient) as Action<ChatOptions>;
        Assert.NotNull(configureAction);

        var options = new ChatOptions();
        configureAction(options);

        Assert.NotNull(options.RawRepresentationFactory);
        return options.RawRepresentationFactory(chatClient) as CreateResponseOptions;
    }
}
