// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

public sealed class JevAIToolBuilderTests
{
    [Fact]
    public void Build_Defaults_DescribeTheJevContract()
    {
        // Act
        AIFunction tool = new JevAIToolBuilder(new ApiKeyCredential("test-key")).Build();

        // Assert
        Assert.Equal("ask_system_one", tool.Name);
        Assert.Contains("'choice'", tool.Description, StringComparison.Ordinal);
        Assert.Contains("'score'", tool.Description, StringComparison.Ordinal);
        Assert.Contains("'noul'", tool.Description, StringComparison.Ordinal);

        JsonElement schema = tool.JsonSchema;
        Assert.Equal(["state", "questions"], schema.GetProperty("required").EnumerateArray().Select(static r => r.GetString()));
        Assert.Equal(["string", "object", "array"], schema.GetProperty("properties").GetProperty("state").GetProperty("type").EnumerateArray().Select(static t => t.GetString()));
        JsonElement question = schema.GetProperty("properties").GetProperty("questions").GetProperty("additionalProperties");
        Assert.Equal(
            ["choice", "score", "noul"],
            question.GetProperty("anyOf").EnumerateArray().Select(static b => b.GetProperty("properties").GetProperty("type").GetProperty("const").GetString()));

        JsonElement[] branches = [.. question.GetProperty("anyOf").EnumerateArray()];
        JsonElement choiceCriteria = branches[0].GetProperty("properties").GetProperty("criteria");
        Assert.Equal(["string", "object", "array", "null"], choiceCriteria.GetProperty("additionalProperties").GetProperty("type").EnumerateArray().Select(static t => t.GetString()));
        Assert.Equal(1, choiceCriteria.GetProperty("minProperties").GetInt32());
        Assert.Equal(255, choiceCriteria.GetProperty("maxProperties").GetInt32());
        JsonElement scoreCriteria = branches[1].GetProperty("properties").GetProperty("criteria");
        Assert.Equal(["string", "object", "array"], scoreCriteria.GetProperty("items").GetProperty("type").EnumerateArray().Select(static t => t.GetString()));
        Assert.Equal(2, scoreCriteria.GetProperty("minItems").GetInt32());
        Assert.Equal(10, scoreCriteria.GetProperty("maxItems").GetInt32());
        Assert.Equal(4, branches[2].GetProperty("properties").GetProperty("instructions").GetProperty("type").GetArrayLength());

        JsonElement returnSchema = tool.ReturnJsonSchema!.Value;
        Assert.Equal(["model", "answers", "usage"], returnSchema.GetProperty("required").EnumerateArray().Select(static r => r.GetString()));
        Assert.True(returnSchema.GetProperty("properties").GetProperty("usage").GetProperty("properties").TryGetProperty("input_tokens", out _));
    }

    [Fact]
    public void Options_Defaults_MatchTheTypeSafeApi()
    {
        // Act
        var options = new JevAIToolOptions();

        // Assert
        Assert.Null(options.Endpoint);
        Assert.Equal("jev-latest", options.ModelId);
        Assert.Equal("ask_system_one", options.Name);
        Assert.Null(options.RetryPolicy);
    }

    [Fact]
    public void Build_WithTheTypeSafeApi_AssignsTheSdkDefaultsOnlyWhenUnset()
    {
        // Arrange
        var defaults = new JevAIToolOptions();
        var custom = new JevAIToolOptions
        {
            RetryPolicy = new System.ClientModel.Primitives.ClientRetryPolicy(maxRetries: 1),
            NetworkTimeout = TimeSpan.FromSeconds(30),
        };

        // Act
        _ = new JevAIToolBuilder(new ApiKeyCredential("test-key"), defaults).Build();
        _ = new JevAIToolBuilder(new ApiKeyCredential("test-key"), custom).Build();

        // Assert
        Assert.IsType<JevRetryPolicy>(defaults.RetryPolicy);
        Assert.Equal(TimeSpan.FromSeconds(10), defaults.NetworkTimeout);
        Assert.IsType<System.ClientModel.Primitives.ClientRetryPolicy>(custom.RetryPolicy);
        Assert.Equal(TimeSpan.FromSeconds(30), custom.NetworkTimeout);
    }

    [Fact]
    public void Build_WithACustomMapping_IgnoresTheApiOnlyOptions()
    {
        // Arrange
        var options = new JevAIToolOptions { ModelId = " ", Endpoint = new Uri("/relative", UriKind.Relative) };

        // Act
        AIFunction tool = new JevAIToolBuilder(options).UseMapping(static (_, _, _) => Task.FromResult(JevTestData.CreateResult())).Build();

        // Assert
        Assert.Equal("ask_system_one", tool.Name);
    }

    [Fact]
    public void Build_WithNameAndDescription_UsesTheOptions()
    {
        // Arrange
        var options = new JevAIToolOptions { Name = "triage_ticket", Description = "Classifies support tickets." };

        // Act
        AIFunction tool = new JevAIToolBuilder(options).UseMapping(static (_, _, _) => Task.FromResult(JevTestData.CreateResult())).Build();

        // Assert
        Assert.Equal("triage_ticket", tool.Name);
        Assert.Equal("Classifies support tickets.", tool.Description);
    }

    [Fact]
    public void Build_WithTheTypeSafeApi_MakesTheOptionsReadOnly()
    {
        // Arrange
        var options = new JevAIToolOptions();

        // Act
        _ = new JevAIToolBuilder(new ApiKeyCredential("test-key"), options).Build();

        // Assert
        Assert.Throws<InvalidOperationException>(() => options.Endpoint = new Uri("https://proxy.contoso.com/jev"));
        Assert.Throws<InvalidOperationException>(() => options.ModelId = "jev-1.13");
    }

    [Fact]
    public void Build_WithACustomMapping_LeavesTheOptionsWritable()
    {
        // Arrange
        var options = new JevAIToolOptions();

        // Act
        _ = new JevAIToolBuilder(new ApiKeyCredential("test-key"), options).UseMapping(static (_, _, _) => Task.FromResult(JevTestData.CreateResult())).Build();

        // Assert
        options.ModelId = "jev-1.13";
        Assert.Equal("jev-1.13", options.ModelId);
    }

    [Fact]
    public void Build_WithoutCredentialOrMapping_Throws()
    {
        // Act
        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() => new JevAIToolBuilder().Build());

        // Assert
        Assert.Contains("ApiKeyCredential", exception.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("name")]
    [InlineData("description")]
    [InlineData("model")]
    [InlineData("endpoint")]
    public void Build_InvalidOptions_Throw(string invalid)
    {
        // Arrange
        var options = new JevAIToolOptions();
        switch (invalid)
        {
            case "name": options.Name = " "; break;
            case "description": options.Description = ""; break;
            case "model": options.ModelId = " "; break;
            case "endpoint": options.Endpoint = new Uri("/v1/systemone", UriKind.Relative); break;
        }

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => new JevAIToolBuilder(new ApiKeyCredential("test-key"), options).Build());
    }

    [Fact]
    public void Methods_NullArguments_Throw()
    {
        // Arrange
        var builder = new JevAIToolBuilder();
        Task<string> systemOneAsync(string request, CancellationToken _) => Task.FromResult(request);
        string input(JevRequest _) => "request";
        JevResult output(string _) => JevTestData.CreateResult();
        Task<string> systemOneWithClientAsync(object _1, string request, CancellationToken _2) => Task.FromResult(request);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new JevAIToolBuilder((ApiKeyCredential)null!));
        Assert.Throws<ArgumentNullException>(() => builder.UseMapping(null!));
        Assert.Throws<ArgumentNullException>(() => builder.UseClient(null!, input, (Func<string, JevResult>)output));
        Assert.Throws<ArgumentNullException>(() => builder.UseClient((Func<string, CancellationToken, Task<string>>)systemOneAsync, null!, output));
        Assert.Throws<ArgumentNullException>(() => builder.UseClient(systemOneAsync, input, null!));
        Assert.Throws<ArgumentNullException>(() => builder.UseClient((Func<object, string, CancellationToken, Task<string>>)systemOneWithClientAsync, null!, output));
    }
}
