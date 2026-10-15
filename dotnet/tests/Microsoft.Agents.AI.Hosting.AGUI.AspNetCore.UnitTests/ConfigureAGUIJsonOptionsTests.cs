// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using AGUI.Abstractions;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Unit tests for the JSON options configured by <c>AddAGUIServer</c> (via <see cref="ConfigureAGUIJsonOptions"/>).
/// </summary>
public sealed class ConfigureAGUIJsonOptionsTests
{
    [Fact]
    public void AddAGUIServer_ConfiguresJsonOptions_ResolvesAGUIWireTypes()
    {
        JsonSerializerOptions options = BuildConfiguredSerializerOptions();

        // The AG-UI wire context must be in the resolver chain (needed on the net10
        // TypedResults.ServerSentEvents path, which serializes events through these options).
        Assert.Null(Record.Exception(() => options.GetTypeInfo(typeof(RunStartedEvent))));
    }

    [Fact]
    public void AddAGUIServer_ConfiguresJsonOptions_ResolvesAgentAbstractionsTypes()
    {
        JsonSerializerOptions options = BuildConfiguredSerializerOptions();

        // The Agent Framework abstractions resolver must also be present so M.E.AI types resolve.
        Assert.Null(Record.Exception(() => options.GetTypeInfo(typeof(ChatMessage))));
    }

    [Fact]
    public void AddAGUIServer_ConfiguresJsonOptions_RoundTripsInterruptRequest()
    {
        // Arrange
        JsonSerializerOptions options = BuildConfiguredSerializerOptions();
        ChatMessage message = new(ChatRole.Assistant, [new InterruptRequestContent("request-1")
        {
            Reason = "confirmation",
            Message = "Approve this action?",
        }]);

        // Act
        string json = JsonSerializer.Serialize(message, options);
        ChatMessage restored = JsonSerializer.Deserialize<ChatMessage>(json, options)!;

        // Assert
        InterruptRequestContent content = Assert.IsType<InterruptRequestContent>(Assert.Single(restored.Contents));
        Assert.Equal("request-1", content.RequestId);
        Assert.Equal("confirmation", content.Reason);
        Assert.Equal("Approve this action?", content.Message);
    }

    [Fact]
    public void AddAGUIServer_ConfiguresJsonOptions_RoundTripsInterruptResponse()
    {
        // Arrange
        JsonSerializerOptions options = BuildConfiguredSerializerOptions();
        ChatMessage message = new(ChatRole.User, [new InterruptResponseContent("request-1")
        {
            Payload = JsonSerializer.SerializeToElement(new { approved = true }),
        }]);

        // Act
        string json = JsonSerializer.Serialize(message, options);
        ChatMessage restored = JsonSerializer.Deserialize<ChatMessage>(json, options)!;

        // Assert
        InterruptResponseContent content = Assert.IsType<InterruptResponseContent>(Assert.Single(restored.Contents));
        Assert.Equal("request-1", content.RequestId);
        Assert.True(Assert.IsType<JsonElement>(content.Payload).GetProperty("approved").GetBoolean());
    }

    private static JsonSerializerOptions BuildConfiguredSerializerOptions()
    {
        ServiceCollection services = new();
        services.AddOptions();
        services.AddAGUIServer();

        using ServiceProvider provider = services.BuildServiceProvider();
        return provider
            .GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>()
            .Value.SerializerOptions;
    }
}
