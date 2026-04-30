// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.Foundry.UnitTests.Hosting;

public class InputConverterTests
{
    [Fact]
    public void ConvertInputToMessages_EmptyRequest_ReturnsEmptyList()
    {
        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(Array.Empty<object>());

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Empty(messages);
    }

    [Fact]
    public void ConvertInputToMessages_UserTextMessage_ReturnsUserMessage()
    {
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_001",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_text", text = "Hello, agent!" } }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        Assert.Equal(ChatRole.User, messages[0].Role);
        Assert.Contains(messages[0].Contents, c => c is MeaiTextContent tc && tc.Text == "Hello, agent!");
    }

    [Fact]
    public void ConvertInputToMessages_FunctionCallOutput_ReturnsToolMessage()
    {
        var input = new[]
        {
            new
            {
                type = "function_call_output",
                id = "fc_out_001",
                call_id = "call_123",
                output = "42"
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        Assert.Equal(ChatRole.Tool, messages[0].Role);
        var funcResult = messages[0].Contents.OfType<FunctionResultContent>().FirstOrDefault();
        Assert.NotNull(funcResult);
        Assert.Equal("call_123", funcResult.CallId);
    }

    [Fact]
    public void ConvertInputToMessages_FunctionToolCall_ReturnsAssistantMessage()
    {
        var input = new[]
        {
            new
            {
                type = "function_call",
                id = "fc_001",
                call_id = "call_456",
                name = "get_weather",
                arguments = "{\"location\": \"Seattle\"}"
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        Assert.Equal(ChatRole.Assistant, messages[0].Role);
        var funcCall = messages[0].Contents.OfType<FunctionCallContent>().FirstOrDefault();
        Assert.NotNull(funcCall);
        Assert.Equal("call_456", funcCall.CallId);
        Assert.Equal("get_weather", funcCall.Name);
    }

    [Fact]
    public void ConvertInputToMessages_MultipleItems_ReturnsAllMessages()
    {
        var input = new object[]
        {
            new
            {
                type = "message",
                id = "msg_001",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_text", text = "What's the weather?" } }
            },
            new
            {
                type = "function_call",
                id = "fc_001",
                call_id = "call_789",
                name = "get_weather",
                arguments = "{}"
            },
            new
            {
                type = "function_call_output",
                id = "fc_out_001",
                call_id = "call_789",
                output = "Sunny, 72°F"
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Equal(3, messages.Count);
        Assert.Equal(ChatRole.User, messages[0].Role);
        Assert.Equal(ChatRole.Assistant, messages[1].Role);
        Assert.Equal(ChatRole.Tool, messages[2].Role);
    }

    [Fact]
    public void ConvertToChatOptions_SetsTemperatureAndTopP()
    {
        var request = new CreateResponse { Temperature = 0.7, TopP = 0.9, MaxOutputTokens = 1000, Model = "gpt-4o" };

        var options = InputConverter.ConvertToChatOptions(request);

        Assert.Equal(0.7f, options.Temperature);
        Assert.Equal(0.9f, options.TopP);
        Assert.Equal(1000, options.MaxOutputTokens);
        Assert.Null(options.ModelId);
    }

    [Fact]
    public void ConvertToChatOptions_NullValues_SetsNulls()
    {
        var request = new CreateResponse();

        var options = InputConverter.ConvertToChatOptions(request);

        Assert.Null(options.Temperature);
        Assert.Null(options.TopP);
        Assert.Null(options.MaxOutputTokens);
    }

    [Fact]
    public void ConvertOutputItemsToMessages_OutputMessage_ReturnsAssistantMessage()
    {
        var textContent = new MessageContentOutputTextContent(
            "Hello from assistant",
            Array.Empty<Annotation>(),
            Array.Empty<LogProb>());
        var outputMsg = new OutputItemMessage(
            id: "out_001",
            role: MessageRole.Assistant,
            content: [textContent],
            status: MessageStatus.Completed);

        var messages = InputConverter.ConvertOutputItemsToMessages([outputMsg]);

        Assert.Single(messages);
        Assert.Equal(ChatRole.Assistant, messages[0].Role);
        Assert.Contains(messages[0].Contents, c => c is MeaiTextContent tc && tc.Text == "Hello from assistant");
    }

    [Fact]
    public void ConvertOutputItemsToMessages_FunctionToolCall_ReturnsAssistantMessage()
    {
        var funcCall = new OutputItemFunctionToolCall(
            callId: "call_abc",
            name: "search",
            arguments: "{\"query\": \"test\"}");

        var messages = InputConverter.ConvertOutputItemsToMessages([funcCall]);

        Assert.Single(messages);
        Assert.Equal(ChatRole.Assistant, messages[0].Role);
        var content = messages[0].Contents.OfType<FunctionCallContent>().FirstOrDefault();
        Assert.NotNull(content);
        Assert.Equal("call_abc", content.CallId);
        Assert.Equal("search", content.Name);
    }

    [Fact]
    public void ConvertOutputItemsToMessages_FunctionToolCallOutput_ReturnsToolMessage()
    {
        var funcOutput = new OutputItemFunctionToolCallOutput(
            callId: "call_def",
            output: BinaryData.FromString("result data"));

        var messages = InputConverter.ConvertOutputItemsToMessages([funcOutput]);

        Assert.Single(messages);
        Assert.Equal(ChatRole.Tool, messages[0].Role);
        var result = messages[0].Contents.OfType<FunctionResultContent>().FirstOrDefault();
        Assert.NotNull(result);
        Assert.Equal("call_def", result.CallId);
    }

    [Fact]
    public void ConvertOutputItemsToMessages_ReasoningItem_ReturnsNull()
    {
        var reasoning = new OutputItemReasoningItem("reason_001", []);

        var messages = InputConverter.ConvertOutputItemsToMessages([reasoning]);

        Assert.Empty(messages);
    }

    // ── Image Content Tests (B-03 through B-06) ──

    [Fact]
    public void ConvertInputToMessages_ImageContentWithHttpUrl_ReturnsUriContent()
    {
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_image", image_url = "https://example.com/img.png" } }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        Assert.Contains(messages[0].Contents, c => c is UriContent);
    }

    [Fact]
    public void ConvertInputToMessages_ImageContentWithDataUri_ReturnsDataContent()
    {
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_image", image_url = "data:image/png;base64,iVBORw0KGgo=" } }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        Assert.Contains(messages[0].Contents, c => c is DataContent);
    }

    [Fact]
    public void ConvertInputToMessages_ImageContentWithFileId_ReturnsHostedFileContent()
    {
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_image", file_id = "file_abc123" } }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        Assert.Contains(messages[0].Contents, c => c is HostedFileContent);
    }

    [Fact]
    public void ConvertInputToMessages_ImageContentNoUrlOrFileId_ProducesNoContent()
    {
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_image" } }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        Assert.Single(messages[0].Contents);
    }

    // ── File Content Tests (B-07 through B-11) ──

    [Fact]
    public void ConvertInputToMessages_FileContentWithUrl_ReturnsUriContent()
    {
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_file", file_url = "https://example.com/doc.pdf" } }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        Assert.Contains(messages[0].Contents, c => c is UriContent);
    }

    [Fact]
    public void ConvertInputToMessages_FileContentWithInlineData_ReturnsDataContent()
    {
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_file", file_data = "data:application/pdf;base64,iVBORw0KGgo=" } }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        Assert.Contains(messages[0].Contents, c => c is DataContent);
    }

    [Fact]
    public void ConvertInputToMessages_FileContentWithFileId_ReturnsHostedFileContent()
    {
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_file", file_id = "file_xyz789" } }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        Assert.Contains(messages[0].Contents, c => c is HostedFileContent);
    }

    [Fact]
    public void ConvertInputToMessages_FileContentWithFilenameOnly_ReturnsFallbackText()
    {
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_file", filename = "report.pdf" } }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        Assert.Contains(messages[0].Contents, c => c is MeaiTextContent tc && tc.Text!.Contains("report.pdf"));
    }

    [Fact]
    public void ConvertInputToMessages_FileContentWithNothing_ProducesNoContent()
    {
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_file" } }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        Assert.Single(messages[0].Contents);
    }

    // ── Mixed Content / Edge Cases (B-15 through B-18) ──

    [Fact]
    public void ConvertInputToMessages_MixedContentInSingleMessage_ReturnsAllContentTypes()
    {
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = new object[]
                {
                    new { type = "input_text", text = "Look at this:" },
                    new { type = "input_image", image_url = "https://example.com/img.png" }
                }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        Assert.Equal(2, messages[0].Contents.Count);
    }

    [Fact]
    public void ConvertInputToMessages_EmptyMessageContent_ReturnsFallbackTextContent()
    {
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = Array.Empty<object>()
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        var textContent = Assert.IsType<MeaiTextContent>(Assert.Single(messages[0].Contents));
        Assert.Equal(string.Empty, textContent.Text);
    }

    [Fact]
    public void ConvertOutputItemsToMessages_OutputMessageRefusal_ReturnsRefusalText()
    {
        var refusal = new MessageContentRefusalContent("I cannot help with that");
        var outputMsg = new OutputItemMessage(
            id: "out_1",
            role: MessageRole.Assistant,
            content: [refusal],
            status: MessageStatus.Completed);

        var messages = InputConverter.ConvertOutputItemsToMessages([outputMsg]);

        Assert.Single(messages);
        Assert.Contains(messages[0].Contents, c => c is MeaiTextContent tc && tc.Text!.Contains("[Refusal:"));
        Assert.Contains(messages[0].Contents, c => c is MeaiTextContent tc && tc.Text!.Contains("I cannot help with that"));
    }

    [Fact]
    public void ConvertInputToMessages_ItemReferenceParam_IsSkipped()
    {
        var input = new object[]
        {
            new { type = "item_reference", id = "ref_001" },
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_text", text = "Hello" } }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
    }

    // ── Role Mapping Tests (C-01 through C-05) ──

    [Fact]
    public void ConvertInputToMessages_UserRole_ReturnsChatRoleUser()
    {
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_text", text = "Hi" } }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        Assert.Equal(ChatRole.User, messages[0].Role);
    }

    [Fact]
    public void ConvertOutputItemsToMessages_AssistantRole_ReturnsChatRoleAssistant()
    {
        // OutputItemMessage always maps to assistant role
        var textContent = new MessageContentOutputTextContent(
            "Hi", Array.Empty<Annotation>(), Array.Empty<LogProb>());
        var outputMsg = new OutputItemMessage(
            id: "msg_1",
            role: MessageRole.Assistant,
            content: [textContent],
            status: MessageStatus.Completed);

        var messages = InputConverter.ConvertOutputItemsToMessages([outputMsg]);

        Assert.Single(messages);
        Assert.Equal(ChatRole.Assistant, messages[0].Role);
    }

    // ── History Conversion Edge Cases (D-02 through D-12) ──

    [Fact]
    public void ConvertOutputItemsToMessages_OutputMessageWithRefusal_ReturnsRefusalText()
    {
        var refusal = new MessageContentRefusalContent("Not allowed");
        var outputMsg = new OutputItemMessage(
            id: "out_1",
            role: MessageRole.Assistant,
            content: [refusal],
            status: MessageStatus.Completed);

        var messages = InputConverter.ConvertOutputItemsToMessages([outputMsg]);

        Assert.Single(messages);
        Assert.Equal(ChatRole.Assistant, messages[0].Role);
        Assert.Contains(messages[0].Contents, c => c is MeaiTextContent tc && tc.Text!.Contains("[Refusal:"));
        Assert.Contains(messages[0].Contents, c => c is MeaiTextContent tc && tc.Text!.Contains("Not allowed"));
    }

    [Fact]
    public void ConvertOutputItemsToMessages_OutputMessageWithEmptyContent_ReturnsFallbackText()
    {
        var outputMsg = new OutputItemMessage(
            id: "out_1",
            role: MessageRole.Assistant,
            content: [],
            status: MessageStatus.Completed);

        var messages = InputConverter.ConvertOutputItemsToMessages([outputMsg]);

        Assert.Single(messages);
        var textContent = Assert.IsType<MeaiTextContent>(Assert.Single(messages[0].Contents));
        Assert.Equal(string.Empty, textContent.Text);
    }

    [Fact]
    public void ConvertOutputItemsToMessages_FunctionToolCallWithMalformedArgs_UsesRawFallback()
    {
        var funcCall = new OutputItemFunctionToolCall(
            callId: "call_1",
            name: "test",
            arguments: "not-json{{{");

        var messages = InputConverter.ConvertOutputItemsToMessages([funcCall]);

        Assert.Single(messages);
        var content = messages[0].Contents.OfType<FunctionCallContent>().FirstOrDefault();
        Assert.NotNull(content);
        Assert.NotNull(content.Arguments);
        Assert.True(content.Arguments.ContainsKey("_raw"));
    }

    [Fact]
    public void ConvertOutputItemsToMessages_UnknownOutputItemType_IsSkipped()
    {
        var messages = InputConverter.ConvertOutputItemsToMessages([]);

        Assert.Empty(messages);
    }

    [Fact]
    public void ConvertToChatOptions_ModelId_NotSetFromRequest()
    {
        var request = new CreateResponse { Model = "my-model" };

        var options = InputConverter.ConvertToChatOptions(request);

        // Model from the request is intentionally NOT propagated — the hosted agent uses its own model.
        Assert.Null(options.ModelId);
    }

    // ── ReadMcpToolboxMarkers tests ──────────────────────────────────────────────

    [Fact]
    public void ReadMcpToolboxMarkers_NullTools_ReturnsEmpty()
    {
        var request = new CreateResponse();
        // Tools defaults to null when not set via JSON deserialization.

        var markers = InputConverter.ReadMcpToolboxMarkers(request);

        Assert.Empty(markers);
    }

    [Fact]
    public void ReadMcpToolboxMarkers_McpToolWithToolboxAddress_ReturnsMarker()
    {
        var request = new CreateResponse();
        request.Tools.Add(new MCPTool("test-toolbox")
        {
            ServerUrl = new Uri("foundry-toolbox://my-toolbox")
        });

        var markers = InputConverter.ReadMcpToolboxMarkers(request);

        Assert.Single(markers);
        Assert.Equal("my-toolbox", markers[0].Name);
        Assert.Null(markers[0].Version);
    }

    [Fact]
    public void ReadMcpToolboxMarkers_McpToolWithVersionedAddress_ReturnsNameAndVersion()
    {
        var request = new CreateResponse();
        request.Tools.Add(new MCPTool("test-toolbox")
        {
            ServerUrl = new Uri("foundry-toolbox://my-toolbox?version=v3")
        });

        var markers = InputConverter.ReadMcpToolboxMarkers(request);

        Assert.Single(markers);
        Assert.Equal("my-toolbox", markers[0].Name);
        Assert.Equal("v3", markers[0].Version);
    }

    [Fact]
    public void ReadMcpToolboxMarkers_McpToolWithNonToolboxUrl_SkipsIt()
    {
        var request = new CreateResponse();
        request.Tools.Add(new MCPTool("external-mcp")
        {
            ServerUrl = new Uri("https://example.com/mcp")
        });

        var markers = InputConverter.ReadMcpToolboxMarkers(request);

        Assert.Empty(markers);
    }

    [Fact]
    public void ReadMcpToolboxMarkers_McpToolWithNullServerUrl_SkipsIt()
    {
        var request = new CreateResponse();
        request.Tools.Add(new MCPTool("test") { ServerUrl = null });

        var markers = InputConverter.ReadMcpToolboxMarkers(request);

        Assert.Empty(markers);
    }

    [Fact]
    public void ReadMcpToolboxMarkers_MixedTools_ReturnsOnlyToolboxMarkers()
    {
        var request = new CreateResponse();
        request.Tools.Add(new MCPTool("external")
        {
            ServerUrl = new Uri("https://example.com/mcp")
        });
        request.Tools.Add(new MCPTool("toolbox-1")
        {
            ServerUrl = new Uri("foundry-toolbox://box-a")
        });
        request.Tools.Add(new MCPTool("toolbox-2")
        {
            ServerUrl = new Uri("foundry-toolbox://box-b?version=2025-01")
        });

        var markers = InputConverter.ReadMcpToolboxMarkers(request);

        Assert.Equal(2, markers.Count);
        Assert.Equal("box-a", markers[0].Name);
        Assert.Null(markers[0].Version);
        Assert.Equal("box-b", markers[1].Name);
        Assert.Equal("2025-01", markers[1].Version);
    }
}
