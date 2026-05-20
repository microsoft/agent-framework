// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Extensions.AI;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

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
        // Spec-compliant payload: a JSON string literal.
        var funcOutput = new OutputItemFunctionToolCallOutput(
            callId: "call_def",
            output: BinaryData.FromString("\"result data\""));

        var messages = InputConverter.ConvertOutputItemsToMessages([funcOutput]);

        Assert.Single(messages);
        Assert.Equal(ChatRole.Tool, messages[0].Role);
        var result = messages[0].Contents.OfType<FunctionResultContent>().FirstOrDefault();
        Assert.NotNull(result);
        Assert.Equal("call_def", result.CallId);
        // Round-trip: the JSON-string wire payload is unwrapped to the original tool result text.
        Assert.Equal("result data", result.Result as string);
    }

    [Fact]
    public void ConvertOutputItemsToMessages_FunctionToolCallOutput_LegacyRawJsonArray_PassesThrough()
    {
        // Legacy/non-conforming producers that emitted a raw JSON value (array/object) in
        // `output` are tolerated: the raw text is forwarded as the FunctionResultContent.Result
        // so the model still sees the original tool-output shape on replay.
        var funcOutput = new OutputItemFunctionToolCallOutput(
            callId: "call_legacy",
            output: BinaryData.FromString("[{\"id\":1}]"));

        var messages = InputConverter.ConvertOutputItemsToMessages([funcOutput]);

        var result = messages[0].Contents.OfType<FunctionResultContent>().FirstOrDefault();
        Assert.NotNull(result);
        Assert.Equal("[{\"id\":1}]", result.Result as string);
    }

    [Fact]
    public void ConvertInputToMessages_FunctionCallOutput_JsonStringPayload_Unwraps()
    {
        // Spec-compliant inbound payload — a JSON string literal — must be unwrapped so
        // FunctionResultContent.Result is the original tool result text, not the JSON-encoded form.
        var input = new[]
        {
            new
            {
                type = "function_call_output",
                id = "fc_out_002",
                call_id = "call_456",
                output = "sunny"
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.Single(messages);
        var funcResult = messages[0].Contents.OfType<FunctionResultContent>().FirstOrDefault();
        Assert.NotNull(funcResult);
        Assert.Equal("sunny", funcResult.Result as string);
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

    // === Tool-approval (HITL) wire-format coverage ===

    [Fact]
    public void ConvertItemsToMessages_McpApprovalRequest_ProducesToolApprovalRequest()
    {
        var item = new ItemMcpApprovalRequest(
            id: "mcpr_" + new string('a', 50),
            serverLabel: "agent_framework",
            name: "get_weather",
            arguments: "{\"city\":\"Seattle\"}");

        var messages = InputConverter.ConvertItemsToMessages([item]);

        var content = Assert.IsType<ToolApprovalRequestContent>(Assert.Single(messages[0].Contents));
        Assert.Equal(item.Id, content.RequestId);
        var fc = Assert.IsType<FunctionCallContent>(content.ToolCall);
        Assert.Equal("get_weather", fc.Name);
        Assert.NotNull(fc.Arguments);
        Assert.Equal("Seattle", fc.Arguments!["city"]?.ToString());
    }

    [Fact]
    public void ConvertItemsToMessages_McpApprovalResponse_ThrowsWhenNoMapping()
    {
        // Without a recorded ApprovalEntry the converter cannot reconstruct the original
        // function call faithfully — any placeholder it produced would still fail downstream
        // (FICC has no tool to invoke; Azure's stored function_call can't pair with the
        // synthetic id). Fail fast with a clear error instead of continuing into a confusing
        // HTTP 400 deep inside the agent loop.
        var wireId = "mcpr_" + new string('a', 50);
        var item = new MCPApprovalResponse(approvalRequestId: wireId, approve: true);

        var ex = Assert.Throws<InvalidOperationException>(() => InputConverter.ConvertItemsToMessages([item]));
        Assert.Contains(wireId, ex.Message);
    }

    [Fact]
    public void ConvertItemsToMessages_McpApprovalResponse_ResolvesAfRequestIdFromStateBag()
    {
        const string AfRequestId = "ficc_call_xyz";
        var wireId = ToolApprovalIdMap.ComputeWireId(AfRequestId);
        var stateBag = new AgentSessionStateBag();
        ToolApprovalIdMap.Record(
            stateBag,
            wireId,
            AfRequestId,
            "call_xyz",
            "issue_refund",
            "{\"order_id\":123}");

        var item = new MCPApprovalResponse(approvalRequestId: wireId, approve: false);

        var messages = InputConverter.ConvertItemsToMessages([item], stateBag);

        var content = Assert.IsType<ToolApprovalResponseContent>(Assert.Single(messages[0].Contents));
        Assert.Equal(AfRequestId, content.RequestId);
        Assert.False(content.Approved);

        // Verify the original FunctionCallContent is reconstructed losslessly:
        // - CallId matches the model-issued id (without FICC's "ficc_" prefix), so the
        //   resulting function_call_output pairs with Azure's stored function_call.
        // - Name matches the original tool, so FICC can invoke the right function on resume.
        // - Arguments are preserved.
        var fcc = Assert.IsType<FunctionCallContent>(content.ToolCall);
        Assert.Equal("call_xyz", fcc.CallId);
        Assert.Equal("issue_refund", fcc.Name);
        Assert.NotNull(fcc.Arguments);
        Assert.Equal(123, ((System.Text.Json.JsonElement)fcc.Arguments!["order_id"]!).GetInt32());
    }

    [Fact]
    public void ConvertOutputItemsToMessages_McpApprovalRequest_ProducesToolApprovalRequest()
    {
        var item = new OutputItemMcpApprovalRequest(
            id: "mcpr_" + new string('b', 50),
            serverLabel: "agent_framework",
            name: "delete_file",
            arguments: "{}");

        var messages = InputConverter.ConvertOutputItemsToMessages([item]);

        var content = Assert.IsType<ToolApprovalRequestContent>(Assert.Single(messages[0].Contents));
        Assert.Equal(item.Id, content.RequestId);
        Assert.Equal("delete_file", Assert.IsType<FunctionCallContent>(content.ToolCall).Name);
    }

    [Fact]
    public void ConvertOutputItemsToMessages_McpApprovalResponse_ProducesToolApprovalResponse()
    {
        const string AfRequestId = "ficc_call_history";
        var wireId = ToolApprovalIdMap.ComputeWireId(AfRequestId);
        var stateBag = new AgentSessionStateBag();
        ToolApprovalIdMap.Record(
            stateBag,
            wireId,
            AfRequestId,
            "call_history",
            "delete_file",
            "{\"path\":\"/tmp/x\"}");

        var item = new OutputItemMcpApprovalResponseResource(
            id: "ar_history_id",
            approvalRequestId: wireId,
            approve: true);

        var messages = InputConverter.ConvertOutputItemsToMessages([item], stateBag);

        var content = Assert.IsType<ToolApprovalResponseContent>(Assert.Single(messages[0].Contents));
        Assert.Equal(AfRequestId, content.RequestId);
        Assert.True(content.Approved);

        var fcc = Assert.IsType<FunctionCallContent>(content.ToolCall);
        Assert.Equal("call_history", fcc.CallId);
        Assert.Equal("delete_file", fcc.Name);
    }

    [Fact]
    public void ConvertItemsToMessages_McpApprovalRequest_MalformedArguments_PreservesRaw()
    {
        var item = new ItemMcpApprovalRequest(
            id: "mcpr_" + new string('c', 50),
            serverLabel: "agent_framework",
            name: "noisy",
            arguments: "not valid json");

        var messages = InputConverter.ConvertItemsToMessages([item]);

        var content = Assert.IsType<ToolApprovalRequestContent>(Assert.Single(messages[0].Contents));
        var fc = Assert.IsType<FunctionCallContent>(content.ToolCall);
        Assert.NotNull(fc.Arguments);
        Assert.Equal("not valid json", fc.Arguments!["_raw"]?.ToString());
    }

    [Fact]
    public void ToolApprovalIdMap_Record_EmptyCallId_IsNoOp()
    {
        var stateBag = new AgentSessionStateBag();
        var wireId = "mcpr_" + new string('d', 50);

        ToolApprovalIdMap.Record(stateBag, wireId, "ficc_x", callId: string.Empty, name: "tool", argumentsJson: "{}");

        Assert.Null(ToolApprovalIdMap.ResolveEntry(stateBag, wireId));
    }

    [Fact]
    public void ToolApprovalIdMap_Record_EmptyName_IsNoOp()
    {
        var stateBag = new AgentSessionStateBag();
        var wireId = "mcpr_" + new string('e', 50);

        ToolApprovalIdMap.Record(stateBag, wireId, "ficc_x", callId: "call_xyz", name: string.Empty, argumentsJson: "{}");

        Assert.Null(ToolApprovalIdMap.ResolveEntry(stateBag, wireId));
    }

    // ── input_file data-URI decoding (TryDecodeTextDataUri) ──

    [Fact]
    public void ConvertInputToMessages_FileContentWithTextDataUri_DecodesToTextContent()
    {
        var encoded = Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes("hello world"));
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_text_uri",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_file", file_data = $"data:text/plain;base64,{encoded}" } }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        var text = Assert.IsType<MeaiTextContent>(Assert.Single(messages[0].Contents));
        Assert.Equal("hello world", text.Text);
    }

    [Fact]
    public void ConvertInputToMessages_FileContentWithTextDataUriAndFilename_PrefixesFilenameInDecodedText()
    {
        var encoded = Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes("body"));
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_text_uri_name",
                status = "completed",
                role = "user",
                content = new[]
                {
                    new
                    {
                        type = "input_file",
                        filename = "notes.txt",
                        file_data = $"data:text/plain;base64,{encoded}"
                    }
                }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        var text = Assert.IsType<MeaiTextContent>(Assert.Single(messages[0].Contents));
        Assert.StartsWith("[File: notes.txt]", text.Text, StringComparison.Ordinal);
        Assert.Contains("body", text.Text, StringComparison.Ordinal);
    }

    [Fact]
    public void ConvertInputToMessages_FileContentWithNonTextDataUri_RemainsDataContent()
    {
        // image/png data URIs must NOT be decoded as text — only text/* is decoded inline.
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_image_uri",
                status = "completed",
                role = "user",
                content = new[]
                {
                    new { type = "input_file", file_data = "data:image/png;base64,iVBORw0KGgo=" }
                }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.IsType<DataContent>(Assert.Single(messages[0].Contents));
    }

    [Fact]
    public void ConvertInputToMessages_FileContentWithMalformedDataUri_FallsBackToDataContent()
    {
        // Missing ;base64, marker — TryDecodeTextDataUri should return false and the
        // original payload survives as DataContent.
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_bad_uri",
                status = "completed",
                role = "user",
                content = new[]
                {
                    new { type = "input_file", file_data = "data:text/plain,not-base64-payload" }
                }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        Assert.IsType<DataContent>(Assert.Single(messages[0].Contents));
    }

    [Fact]
    public void ConvertInputToMessages_FileContentWithFileUrlAndFilename_PropagatesFilename()
    {
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_url_name",
                status = "completed",
                role = "user",
                content = new[]
                {
                    new
                    {
                        type = "input_file",
                        file_url = "https://example.com/doc.pdf",
                        filename = "doc.pdf"
                    }
                }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        var uri = Assert.IsType<UriContent>(Assert.Single(messages[0].Contents));
        Assert.NotNull(uri.AdditionalProperties);
        Assert.Equal("doc.pdf", uri.AdditionalProperties!["filename"]);
    }

    [Fact]
    public void ConvertInputToMessages_FileContentWithFileIdAndFilename_PropagatesFilename()
    {
        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_id_name",
                status = "completed",
                role = "user",
                content = new[]
                {
                    new
                    {
                        type = "input_file",
                        file_id = "file_abc123",
                        filename = "doc.pdf"
                    }
                }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        var hosted = Assert.IsType<HostedFileContent>(Assert.Single(messages[0].Contents));
        Assert.NotNull(hosted.AdditionalProperties);
        Assert.Equal("doc.pdf", hosted.AdditionalProperties!["filename"]);
    }

    // ── C2: SDK content types passing through ItemMessage / OutputItemMessage ──

    [Fact]
    public void ConvertItemsToMessages_SdkTextContent_ProducesTextContent()
    {
        var msg = new ItemMessage(
            MessageRole.User,
            new MessageContent[] { new Azure.AI.AgentServer.Responses.Models.TextContent("plain text") });

        var messages = InputConverter.ConvertItemsToMessages([msg]);

        var text = Assert.IsType<MeaiTextContent>(Assert.Single(messages[0].Contents));
        Assert.Equal("plain text", text.Text);
    }

    [Fact]
    public void ConvertItemsToMessages_SummaryTextContent_ProducesTextContent()
    {
        var msg = new ItemMessage(
            MessageRole.Assistant,
            new MessageContent[] { new SummaryTextContent("a summary") });

        var messages = InputConverter.ConvertItemsToMessages([msg]);

        var text = Assert.IsType<MeaiTextContent>(Assert.Single(messages[0].Contents));
        Assert.Equal("a summary", text.Text);
    }

    [Fact]
    public void ConvertItemsToMessages_ReasoningTextContent_ProducesTextReasoningContent()
    {
        var msg = new ItemMessage(
            MessageRole.Assistant,
            new MessageContent[] { new MessageContentReasoningTextContent("internal reasoning") });

        var messages = InputConverter.ConvertItemsToMessages([msg]);

        var reasoning = Assert.IsType<TextReasoningContent>(Assert.Single(messages[0].Contents));
        Assert.Equal("internal reasoning", reasoning.Text);
    }

    [Fact]
    public void ConvertItemsToMessages_ComputerScreenshotContent_HttpUrl_ProducesUriContent()
    {
        var screenshot = new ComputerScreenshotContent(
            imageUrl: new Uri("https://example.com/screen.png"),
            fileId: null!,
            detail: default);
        var msg = new ItemMessage(MessageRole.User, new MessageContent[] { screenshot });

        var messages = InputConverter.ConvertItemsToMessages([msg]);

        var uri = Assert.IsType<UriContent>(Assert.Single(messages[0].Contents));
        Assert.Equal("https://example.com/screen.png", uri.Uri.ToString());
    }

    [Fact]
    public void ConvertItemsToMessages_ComputerScreenshotContent_DataUri_ProducesDataContent()
    {
        var screenshot = new ComputerScreenshotContent(
            imageUrl: new Uri("data:image/png;base64,iVBORw0KGgo="),
            fileId: null!,
            detail: default);
        var msg = new ItemMessage(MessageRole.User, new MessageContent[] { screenshot });

        var messages = InputConverter.ConvertItemsToMessages([msg]);

        var data = Assert.IsType<DataContent>(Assert.Single(messages[0].Contents));
        Assert.StartsWith("data:image", data.Uri);
    }

    [Fact]
    public void ConvertOutputItemsToMessages_SummaryTextContent_ProducesTextContent()
    {
        var outputMsg = new OutputItemMessage(
            id: "out_summary",
            role: MessageRole.Assistant,
            content: new MessageContent[] { new SummaryTextContent("output summary") },
            status: MessageStatus.Completed);

        var messages = InputConverter.ConvertOutputItemsToMessages([outputMsg]);

        var text = Assert.IsType<MeaiTextContent>(Assert.Single(messages[0].Contents));
        Assert.Equal("output summary", text.Text);
    }

    [Fact]
    public void ConvertOutputItemsToMessages_ReasoningTextContent_ProducesTextReasoningContent()
    {
        var outputMsg = new OutputItemMessage(
            id: "out_reasoning",
            role: MessageRole.Assistant,
            content: new MessageContent[] { new MessageContentReasoningTextContent("output reasoning") },
            status: MessageStatus.Completed);

        var messages = InputConverter.ConvertOutputItemsToMessages([outputMsg]);

        var reasoning = Assert.IsType<TextReasoningContent>(Assert.Single(messages[0].Contents));
        Assert.Equal("output reasoning", reasoning.Text);
    }

    [Fact]
    public void ConvertOutputItemsToMessages_ComputerScreenshotContent_ProducesUriContent()
    {
        var screenshot = new ComputerScreenshotContent(
            imageUrl: new Uri("https://example.com/output-screen.png"),
            fileId: null!,
            detail: default);
        var outputMsg = new OutputItemMessage(
            id: "out_screenshot",
            role: MessageRole.Assistant,
            content: new MessageContent[] { screenshot },
            status: MessageStatus.Completed);

        var messages = InputConverter.ConvertOutputItemsToMessages([outputMsg]);

        var uri = Assert.IsType<UriContent>(Assert.Single(messages[0].Contents));
        Assert.Equal("https://example.com/output-screen.png", uri.Uri.ToString());
    }

    [Fact]
    public void ConvertOutputItemsToMessages_SdkTextContent_ProducesTextContent()
    {
        var outputMsg = new OutputItemMessage(
            id: "out_text",
            role: MessageRole.Assistant,
            content: new MessageContent[] { new Azure.AI.AgentServer.Responses.Models.TextContent("sdk text") },
            status: MessageStatus.Completed);

        var messages = InputConverter.ConvertOutputItemsToMessages([outputMsg]);

        var text = Assert.IsType<MeaiTextContent>(Assert.Single(messages[0].Contents));
        Assert.Equal("sdk text", text.Text);
    }

    [Fact]
    public void ConvertInputToMessages_OversizedTextDataUri_FallsBackToDataContent()
    {
        // The decoder must reject oversized base64 payloads so a malicious or
        // misconfigured client cannot trigger a multi-megabyte allocation.
        // We construct a base64 payload whose encoded length exceeds the 16 MiB cap
        // (using a tiny but valid base64 unit repeated to keep the test fast).
        const int OverLimit = (16 * 1024 * 1024) + 4;
        var encoded = new string('A', OverLimit);
        var dataUri = "data:text/plain;base64," + encoded;

        var input = new[]
        {
            new
            {
                type = "message",
                id = "msg_oversize",
                status = "completed",
                role = "user",
                content = new[]
                {
                    new
                    {
                        type = "input_file",
                        file_data = dataUri,
                        filename = "huge.txt",
                    }
                }
            }
        };

        var request = new CreateResponse();
        request.Input = BinaryData.FromObjectAsJson(input);

        var messages = InputConverter.ConvertInputToMessages(request);

        // Should NOT have decoded into a TextContent (which would have allocated).
        Assert.DoesNotContain(messages[0].Contents, c => c is MeaiTextContent t && t.Text.Length > 1024);
        // Should have fallen back to DataContent (carrying the original opaque blob).
        Assert.Contains(messages[0].Contents, c => c is DataContent);
    }
}
