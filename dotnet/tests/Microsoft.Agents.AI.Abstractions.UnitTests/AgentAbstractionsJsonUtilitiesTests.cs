// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

#pragma warning disable CA1812 // Avoid uninstantiated internal classes

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Tests for <see cref="AgentAbstractionsJsonUtilities"/>
/// </summary>
public class AgentAbstractionsJsonUtilitiesTests
{
    [Fact]
    public void DefaultOptions_HasExpectedConfiguration()
    {
        var options = AgentAbstractionsJsonUtilities.DefaultOptions;

        // Must be read-only singleton.
        Assert.NotNull(options);
        Assert.Same(options, AgentAbstractionsJsonUtilities.DefaultOptions);
        Assert.True(options.IsReadOnly);

        // Must conform to JsonSerializerDefaults.Web
        Assert.Equal(JsonNamingPolicy.CamelCase, options.PropertyNamingPolicy);
        Assert.True(options.PropertyNameCaseInsensitive);
        Assert.Equal(JsonNumberHandling.AllowReadingFromString, options.NumberHandling);

        // Additional settings
        Assert.Equal(JsonIgnoreCondition.WhenWritingNull, options.DefaultIgnoreCondition);
        Assert.Same(JavaScriptEncoder.UnsafeRelaxedJsonEscaping, options.Encoder);
    }

    [Theory]
    [InlineData("<script>alert('XSS')</script>", "<script>alert('XSS')</script>")]
    [InlineData("""{"forecast":"sunny", "temperature":"75"}""", """{\"forecast\":\"sunny\", \"temperature\":\"75\"}""")]
    [InlineData("""{"message":"Πάντα ῥεῖ."}""", """{\"message\":\"Πάντα ῥεῖ.\"}""")]
    [InlineData("""{"message":"七転び八起き"}""", """{\"message\":\"七転び八起き\"}""")]
    [InlineData("""☺️🤖🌍𝄞""", """☺️\uD83E\uDD16\uD83C\uDF0D\uD834\uDD1E""")]
    public void DefaultOptions_UsesExpectedEscaping(string input, string expectedJsonString)
    {
        var options = AgentAbstractionsJsonUtilities.DefaultOptions;
        string json = JsonSerializer.Serialize(input, options);
        Assert.Equal($@"""{expectedJsonString}""", json);
    }

    [Fact]
    public void DefaultOptions_UsesReflectionWhenDefault()
    {
        Type anonType = new { Name = 42 }.GetType();
        Assert.Equal(JsonSerializer.IsReflectionEnabledByDefault, AgentAbstractionsJsonUtilities.DefaultOptions.TryGetTypeInfo(anonType, out _));
    }

    // The following two tests validate behaviors of reflection-based serialization
    // which is only available in .NET Framework builds.
#if NETFRAMEWORK
    [Fact]
    public void DefaultOptions_AllowsReadingNumbersFromStrings_AndOmitsNulls()
    {
        var obj = JsonSerializer.Deserialize<NumberContainer>(
            "{\"value\":\"42\",\"optional\":null}", // value as string, optional null
            AgentAbstractionsJsonUtilities.DefaultOptions);
        Assert.NotNull(obj);
        Assert.Equal(42, obj!.Value);
        Assert.Null(obj.Optional);
        Assert.Equal("{\"value\":42}",
            JsonSerializer.Serialize(obj, AgentAbstractionsJsonUtilities.DefaultOptions)); // null omitted
    }

    [Fact]
    public void DefaultOptions_SerializesEnumsAsStrings()
    {
        Assert.Equal("\"Monday\"", JsonSerializer.Serialize(DayOfWeek.Monday, AgentAbstractionsJsonUtilities.DefaultOptions));
    }
#endif

    [Fact]
    public void DefaultOptions_UsesCamelCasePropertyNames_ForAgentRunResponse()
    {
        var response = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Hello"));
        string json = JsonSerializer.Serialize(response, AgentAbstractionsJsonUtilities.DefaultOptions);
        Assert.Contains("\"messages\"", json);
        Assert.DoesNotContain("\"Messages\"", json);
    }

    private sealed class NumberContainer
    {
        public int Value { get; set; }
        public string? Optional { get; set; }
    }
}
