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
        Assert.Equal("user", output[0].Role);
        var text = Assert.IsType<WireTextContent>(Assert.Single(output[0].Content));
        Assert.Equal("Hello world", text.Text);
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
        Assert.IsType<WireImageContent>(Assert.Single(output[0].Content));
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
        var toolCall = Assert.IsType<WireToolCallContent>(Assert.Single(output[0].Content));
        Assert.Equal("c1", toolCall.ToolCallId);
        Assert.Equal("get_weather", toolCall.Name);
    }

    [Fact]
    public void ConvertMessage_FunctionCallWithoutArguments_OmitsArguments()
    {
        var msg = new ChatMessage(ChatRole.Assistant,
        [
            new FunctionCallContent("c1", "list_items"),
        ]);
        var output = FoundryEvalConverter.ConvertMessage(msg);

        var toolCall = Assert.IsType<WireToolCallContent>(Assert.Single(output[0].Content));
        Assert.Null(toolCall.Arguments);
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
        Assert.All(output, m => Assert.Equal("tool", m.Role));
        Assert.Equal("c1", output[0].ToolCallId);
        Assert.Equal("c2", output[1].ToolCallId);
    }

    [Fact]
    public void ConvertMessage_EmptyContent_ProducesEmptyTextFallback()
    {
        var msg = new ChatMessage(ChatRole.Assistant, Array.Empty<AIContent>());
        var output = FoundryEvalConverter.ConvertMessage(msg);

        Assert.Single(output);
        var text = Assert.IsType<WireTextContent>(Assert.Single(output[0].Content));
        Assert.Equal(string.Empty, text.Text);
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
        Assert.Equal(2, output[0].Content.Count);
        Assert.IsType<WireTextContent>(output[0].Content[0]);
        Assert.IsType<WireImageContent>(output[0].Content[1]);
    }

    // ---------------------------------------------------------------
    // FoundryEvalConverter.ConvertEvalItem tests
    // ---------------------------------------------------------------

    [Fact]
    public void ConvertEvalItem_BasicItem_HasQueryAndResponse()
    {
        var item = new EvalItem(query: "What is AI?", response: "Artificial Intelligence.");
        var payload = FoundryEvalConverter.ConvertEvalItem(item);

        Assert.Equal("What is AI?", payload.Query);
        Assert.Equal("Artificial Intelligence.", payload.Response);
        Assert.NotNull(payload.QueryMessages);
        Assert.NotNull(payload.ResponseMessages);
    }

    [Fact]
    public void ConvertEvalItem_WithContext_IncludesContextField()
    {
        var item = new EvalItem(query: "q", response: "r")
        {
            Context = "Some grounding context",
        };
        var payload = FoundryEvalConverter.ConvertEvalItem(item);

        Assert.Equal("Some grounding context", payload.Context);
    }

    [Fact]
    public void ConvertEvalItem_WithoutContext_OmitsContextField()
    {
        var item = new EvalItem(query: "q", response: "r");
        var payload = FoundryEvalConverter.ConvertEvalItem(item);

        Assert.Null(payload.Context);
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
        Assert.Equal("azure_ai_evaluator", entry.Type);
        Assert.Equal("builtin.relevance", entry.EvaluatorName);

        Assert.NotNull(entry.DataMapping);
        var mapping = entry.DataMapping;
        Assert.Equal("{{item.query}}", mapping["query"]);
        Assert.Equal("{{item.response}}", mapping["response"]);
    }

    [Fact]
    public void BuildTestingCriteria_AgentEvaluator_UsesConversationArrayMapping()
    {
        var criteria = FoundryEvalConverter.BuildTestingCriteria(
            ["intent_resolution"], "gpt-4o-mini", includeDataMapping: true);

        Assert.Single(criteria);
        var mapping = criteria[0].DataMapping;
        Assert.NotNull(mapping);
        Assert.Equal("{{item.query_messages}}", mapping["query"]);
        Assert.Equal("{{item.response_messages}}", mapping["response"]);
    }

    [Fact]
    public void BuildTestingCriteria_ToolEvaluator_IncludesToolDefinitions()
    {
        var criteria = FoundryEvalConverter.BuildTestingCriteria(
            ["tool_call_accuracy"], "gpt-4o-mini", includeDataMapping: true);

        Assert.Single(criteria);
        var mapping = criteria[0].DataMapping;
        Assert.NotNull(mapping);
        Assert.True(mapping.ContainsKey("tool_definitions"));
        Assert.Equal("{{item.tool_definitions}}", mapping["tool_definitions"]);
    }

    [Fact]
    public void BuildTestingCriteria_GroundednessEvaluator_IncludesContext()
    {
        var criteria = FoundryEvalConverter.BuildTestingCriteria(
            ["groundedness"], "gpt-4o-mini", includeDataMapping: true);

        Assert.Single(criteria);
        var mapping = criteria[0].DataMapping;
        Assert.NotNull(mapping);
        Assert.True(mapping.ContainsKey("context"));
        Assert.Equal("{{item.context}}", mapping["context"]);
    }

    [Fact]
    public void BuildTestingCriteria_WithoutDataMapping_OmitsMappingField()
    {
        var criteria = FoundryEvalConverter.BuildTestingCriteria(
            ["relevance"], "gpt-4o-mini", includeDataMapping: false);

        Assert.Single(criteria);
        Assert.Null(criteria[0].DataMapping);
    }

    // ---------------------------------------------------------------
    // FoundryEvalConverter.BuildItemSchema tests
    // ---------------------------------------------------------------

    [Fact]
    public void BuildItemSchema_Default_HasQueryResponseAndConversationFields()
    {
        var schema = FoundryEvalConverter.BuildItemSchema();

        Assert.True(schema.Properties.ContainsKey("query"));
        Assert.True(schema.Properties.ContainsKey("response"));
        Assert.True(schema.Properties.ContainsKey("query_messages"));
        Assert.True(schema.Properties.ContainsKey("response_messages"));
        Assert.False(schema.Properties.ContainsKey("context"));
        Assert.False(schema.Properties.ContainsKey("tool_definitions"));
    }

    [Fact]
    public void BuildItemSchema_WithContext_IncludesContextProperty()
    {
        var schema = FoundryEvalConverter.BuildItemSchema(hasContext: true);

        Assert.True(schema.Properties.ContainsKey("context"));
    }

    [Fact]
    public void BuildItemSchema_WithTools_IncludesToolDefinitionsProperty()
    {
        var schema = FoundryEvalConverter.BuildItemSchema(hasTools: true);

        Assert.True(schema.Properties.ContainsKey("tool_definitions"));
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
        Assert.Equal(2, output[0].Content.Count);
        var text = Assert.IsType<WireTextContent>(output[0].Content[0]);
        Assert.Equal("Describe this image", text.Text);
        var image = Assert.IsType<WireImageContent>(output[0].Content[1]);
        Assert.Contains("data:image/png;base64,", image.ImageUrl);
    }
}
