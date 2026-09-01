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
    public void AddAGUIServer_ConfiguresJsonOptions_OmitsOptionalFieldsWithNoValue()
    {
        JsonSerializerOptions options = BuildConfiguredSerializerOptions();

        string json = JsonSerializer.Serialize<BaseEvent>(new RunStartedEvent { ThreadId = "thread", RunId = "run" }, options);

        // AG-UI receivers declare the optional event fields as optional, not nullable, so writing them
        // as explicit nulls fails validation client-side. The configured options must omit them.
        json.Should().NotContain("null");
        json.Should().Be("""{"type":"RUN_STARTED","threadId":"thread","runId":"run"}""");
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
