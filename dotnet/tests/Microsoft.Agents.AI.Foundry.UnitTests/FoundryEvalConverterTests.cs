// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Tests for <see cref="FoundryEvalConverter"/>.
/// </summary>
public sealed class FoundryEvalConverterTests
{
    // ---------------------------------------------------------------
    // ResolveEvaluator tests
    // ---------------------------------------------------------------

    [Fact]
    public void ResolveEvaluator_QualityShortNames_ResolvesToBuiltin()
    {
        Assert.Equal("builtin.relevance", FoundryEvalConverter.ResolveEvaluator("relevance"));
        Assert.Equal("builtin.coherence", FoundryEvalConverter.ResolveEvaluator("coherence"));
    }

    [Fact]
    public void ResolveEvaluator_FullyQualifiedName_ReturnsSame()
    {
        Assert.Equal("builtin.relevance", FoundryEvalConverter.ResolveEvaluator("builtin.relevance"));
    }

    [Fact]
    public void ResolveEvaluator_UnknownName_ThrowsArgumentException()
    {
        var ex = Assert.Throws<ArgumentException>(
            () => FoundryEvalConverter.ResolveEvaluator("gobblygook"));
        Assert.Contains("gobblygook", ex.Message);
    }

    [Fact]
    public void ResolveEvaluator_AgentEvaluators_ResolveCorrectly()
    {
        Assert.Equal("builtin.intent_resolution", FoundryEvalConverter.ResolveEvaluator("intent_resolution"));
        Assert.Equal("builtin.tool_call_accuracy", FoundryEvalConverter.ResolveEvaluator("tool_call_accuracy"));
    }
    // ---------------------------------------------------------------
    // FoundryEvalConverter.ConvertMessage tests
    // ---------------------------------------------------------------

    [Fact]
    public void ConvertMessage_PlainText_ProducesTextContent()
    {
        var msg = new ChatMessage(ChatRole.User, "Hello world");
        var output = FoundryEvalConverter.ConvertMessage(msg);

        Assert.Single(output);
        Assert.Equal("user", output[0]["role"]);
        var content = (List<Dictionary<string, object>>)output[0]["content"];
        Assert.Single(content);
        Assert.Equal("text", content[0]["type"]);
        Assert.Equal("Hello world", content[0]["text"]);
    }

    [Fact]
    public void ConvertMessage_ImageUri_ProducesInputImage()
    {
        var msg = new ChatMessage(ChatRole.User,
        [
            new UriContent(new Uri("https://example.com/img.png"), "image/png"),
        ]);
        var output = FoundryEvalConverter.ConvertMessage(msg);

        Assert.Single(output);
        var content = (List<Dictionary<string, object>>)output[0]["content"];
        Assert.Single(content);
        Assert.Equal("input_image", content[0]["type"]);
    }

    [Fact]
    public void ConvertMessage_FunctionCall_ProducesToolCallContent()
    {
        var msg = new ChatMessage(ChatRole.Assistant,
        [
            new FunctionCallContent("c1", "get_weather", new Dictionary<string, object?> { ["city"] = "Seattle" }),
        ]);
        var output = FoundryEvalConverter.ConvertMessage(msg);

        Assert.Single(output);
        var content = (List<Dictionary<string, object>>)output[0]["content"];
        Assert.Single(content);
        Assert.Equal("tool_call", content[0]["type"]);
        Assert.Equal("c1", content[0]["tool_call_id"]);
        Assert.Equal("get_weather", content[0]["name"]);
    }

    [Fact]
    public void ConvertMessage_FunctionCallWithoutArguments_OmitsArguments()
    {
        var msg = new ChatMessage(ChatRole.Assistant,
        [
            new FunctionCallContent("c1", "list_items"),
        ]);
        var output = FoundryEvalConverter.ConvertMessage(msg);

        var content = (List<Dictionary<string, object>>)output[0]["content"];
        Assert.DoesNotContain("arguments", content[0].Keys);
    }

    [Fact]
    public void ConvertMessage_FunctionResults_FanOutToSeparateMessages()
    {
        var msg = new ChatMessage(ChatRole.Tool,
        [
            new FunctionResultContent("c1", "72F sunny"),
            new FunctionResultContent("c2", "Paris 68F"),
        ]);
        var output = FoundryEvalConverter.ConvertMessage(msg);

        Assert.Equal(2, output.Count);
        Assert.All(output, m => Assert.Equal("tool", m["role"]));
        Assert.Equal("c1", output[0]["tool_call_id"]);
        Assert.Equal("c2", output[1]["tool_call_id"]);
    }

    [Fact]
    public void ConvertMessage_EmptyContent_ProducesEmptyTextFallback()
    {
        var msg = new ChatMessage(ChatRole.Assistant, Array.Empty<AIContent>());
        var output = FoundryEvalConverter.ConvertMessage(msg);

        Assert.Single(output);
        var content = (List<Dictionary<string, object>>)output[0]["content"];
        Assert.Single(content);
        Assert.Equal("text", content[0]["type"]);
        Assert.Equal(string.Empty, content[0]["text"]);
    }

    [Fact]
    public void ConvertMessage_MixedContent_ProducesAllContentTypes()
    {
        var msg = new ChatMessage(ChatRole.User,
        [
            new TextContent("Describe this"),
            new UriContent(new Uri("https://example.com/img.png"), "image/png"),
        ]);
        var output = FoundryEvalConverter.ConvertMessage(msg);

        Assert.Single(output);
        var content = (List<Dictionary<string, object>>)output[0]["content"];
        Assert.Equal(2, content.Count);
        Assert.Equal("text", content[0]["type"]);
        Assert.Equal("input_image", content[1]["type"]);
    }

    // ---------------------------------------------------------------
    // FoundryEvalConverter.ConvertEvalItem tests
    // ---------------------------------------------------------------

    [Fact]
    public void ConvertEvalItem_BasicItem_HasQueryAndResponse()
    {
        var item = new EvalItem(query: "What is AI?", response: "Artificial Intelligence.");
        var dict = FoundryEvalConverter.ConvertEvalItem(item);

        Assert.Equal("What is AI?", dict["query"]);
        Assert.Equal("Artificial Intelligence.", dict["response"]);
        Assert.True(dict.ContainsKey("query_messages"));
        Assert.True(dict.ContainsKey("response_messages"));
    }

    [Fact]
    public void ConvertEvalItem_WithContext_IncludesContextField()
    {
        var item = new EvalItem(query: "q", response: "r")
        {
            Context = "Some grounding context",
        };
        var dict = FoundryEvalConverter.ConvertEvalItem(item);

        Assert.Equal("Some grounding context", dict["context"]);
    }

    [Fact]
    public void ConvertEvalItem_WithoutContext_OmitsContextField()
    {
        var item = new EvalItem(query: "q", response: "r");
        var dict = FoundryEvalConverter.ConvertEvalItem(item);

        Assert.False(dict.ContainsKey("context"));
    }

    // ---------------------------------------------------------------
    // FoundryEvalConverter.BuildTestingCriteria tests
    // ---------------------------------------------------------------

    [Fact]
    public void BuildTestingCriteria_QualityEvaluator_UsesStringDataMapping()
    {
        var criteria = FoundryEvalConverter.BuildTestingCriteria(
            ["relevance"], "gpt-4o-mini", includeDataMapping: true);

        Assert.Single(criteria);
        var entry = criteria[0];
        Assert.Equal("azure_ai_evaluator", entry["type"]);
        Assert.Equal("builtin.relevance", entry["evaluator_name"]);

        var mapping = (Dictionary<string, string>)entry["data_mapping"];
        Assert.Equal("{{item.query}}", mapping["query"]);
        Assert.Equal("{{item.response}}", mapping["response"]);
    }

    [Fact]
    public void BuildTestingCriteria_AgentEvaluator_UsesConversationArrayMapping()
    {
        var criteria = FoundryEvalConverter.BuildTestingCriteria(
            ["intent_resolution"], "gpt-4o-mini", includeDataMapping: true);

        Assert.Single(criteria);
        var mapping = (Dictionary<string, string>)criteria[0]["data_mapping"];
        Assert.Equal("{{item.query_messages}}", mapping["query"]);
        Assert.Equal("{{item.response_messages}}", mapping["response"]);
    }

    [Fact]
    public void BuildTestingCriteria_ToolEvaluator_IncludesToolDefinitions()
    {
        var criteria = FoundryEvalConverter.BuildTestingCriteria(
            ["tool_call_accuracy"], "gpt-4o-mini", includeDataMapping: true);

        Assert.Single(criteria);
        var mapping = (Dictionary<string, string>)criteria[0]["data_mapping"];
        Assert.True(mapping.ContainsKey("tool_definitions"));
        Assert.Equal("{{item.tool_definitions}}", mapping["tool_definitions"]);
    }

    [Fact]
    public void BuildTestingCriteria_GroundednessEvaluator_IncludesContext()
    {
        var criteria = FoundryEvalConverter.BuildTestingCriteria(
            ["groundedness"], "gpt-4o-mini", includeDataMapping: true);

        Assert.Single(criteria);
        var mapping = (Dictionary<string, string>)criteria[0]["data_mapping"];
        Assert.True(mapping.ContainsKey("context"));
        Assert.Equal("{{item.context}}", mapping["context"]);
    }

    [Fact]
    public void BuildTestingCriteria_WithoutDataMapping_OmitsMappingField()
    {
        var criteria = FoundryEvalConverter.BuildTestingCriteria(
            ["relevance"], "gpt-4o-mini", includeDataMapping: false);

        Assert.Single(criteria);
        Assert.False(criteria[0].ContainsKey("data_mapping"));
    }

    // ---------------------------------------------------------------
    // FoundryEvalConverter.BuildItemSchema tests
    // ---------------------------------------------------------------

    [Fact]
    public void BuildItemSchema_Default_HasQueryResponseAndConversationFields()
    {
        var schema = FoundryEvalConverter.BuildItemSchema();
        var properties = (Dictionary<string, object>)schema["properties"];

        Assert.True(properties.ContainsKey("query"));
        Assert.True(properties.ContainsKey("response"));
        Assert.True(properties.ContainsKey("query_messages"));
        Assert.True(properties.ContainsKey("response_messages"));
        Assert.False(properties.ContainsKey("context"));
        Assert.False(properties.ContainsKey("tool_definitions"));
    }

    [Fact]
    public void BuildItemSchema_WithContext_IncludesContextProperty()
    {
        var schema = FoundryEvalConverter.BuildItemSchema(hasContext: true);
        var properties = (Dictionary<string, object>)schema["properties"];

        Assert.True(properties.ContainsKey("context"));
    }

    [Fact]
    public void BuildItemSchema_WithTools_IncludesToolDefinitionsProperty()
    {
        var schema = FoundryEvalConverter.BuildItemSchema(hasTools: true);
        var properties = (Dictionary<string, object>)schema["properties"];

        Assert.True(properties.ContainsKey("tool_definitions"));
    }

    // ---------------------------------------------------------------
    // FoundryEvalConverter.ConvertMessage DataContent test
    // ---------------------------------------------------------------

    [Fact]
    public void ConvertMessage_DataContent_ProducesInputImage()
    {
        var imageBytes = new byte[] { 0x89, 0x50, 0x4E, 0x47 }; // PNG magic bytes
        var msg = new ChatMessage(ChatRole.User,
        [
            new TextContent("Describe this image"),
            new DataContent(imageBytes, "image/png"),
        ]);

        var output = FoundryEvalConverter.ConvertMessage(msg);

        Assert.Single(output);
        var content = (List<Dictionary<string, object>>)output[0]["content"];
        Assert.Equal(2, content.Count);
        Assert.Equal("text", content[0]["type"]);
        Assert.Equal("Describe this image", content[0]["text"]);
        Assert.Equal("input_image", content[1]["type"]);
        Assert.Contains("data:image/png;base64,", (string)content[1]["image_url"]);
    }
}
