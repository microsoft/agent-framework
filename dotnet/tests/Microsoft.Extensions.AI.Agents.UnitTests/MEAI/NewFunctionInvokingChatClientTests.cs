// Copyright (c) Microsoft. All rights reserved.

// AF repo suppressions for code copied from MEAI.
#pragma warning disable CA5394 // Do not use insecure randomness
#pragma warning disable IDE0009 // Member access should be qualified.
#pragma warning disable IDE0039 // Use local function

using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI;

public class NewFunctionInvokingChatClientTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task AllFunctionCallsReplacedWithApprovalsWhenAllRequireApprovalAsync(bool useAdditionalTools)
    {
        AITool[] tools =
        [
            new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "Result 1", "Func1")),
            new ApprovalRequiredAIFunction(AIFunctionFactory.Create((int i) => $"Result 2: {i}", "Func2")) { RequiresApprovalCallback = async (context) => context.FunctionCall.Name == "Func2" },
        ];

        var options = new ChatOptions
        {
            Tools = useAdditionalTools ? null : tools
        };

        List<ChatMessage> input =
        [
            new ChatMessage(ChatRole.User, "hello"),
        ];

        List<ChatMessage> downstreamClientOutput =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
        ];

        List<ChatMessage> expectedOutput =
        [
            new ChatMessage(ChatRole.Assistant,
            [
                new FunctionApprovalRequestContent("callId1", new FunctionCallContent("callId1", "Func1")),
                new FunctionApprovalRequestContent("callId2", new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ])
        ];

        await InvokeAndAssertAsync(options, input, downstreamClientOutput, expectedOutput, additionalTools: useAdditionalTools ? tools : null);

        await InvokeAndAssertStreamingAsync(options, input, downstreamClientOutput, expectedOutput, additionalTools: useAdditionalTools ? tools : null);
    }

    [Fact]
    public async Task AllFunctionCallsReplacedWithApprovalsWhenAnyRequireApprovalAsync()
    {
        var options = new ChatOptions
        {
            Tools =
            [
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "Result 1", "Func1")),
                AIFunctionFactory.Create((int i) => $"Result 2: {i}", "Func2"),
            ]
        };

        List<ChatMessage> input =
        [
            new ChatMessage(ChatRole.User, "hello"),
        ];

        List<ChatMessage> downstreamClientOutput =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
        ];

        List<ChatMessage> expectedOutput =
        [
            new ChatMessage(ChatRole.Assistant,
            [
                new FunctionApprovalRequestContent("callId1", new FunctionCallContent("callId1", "Func1")),
                new FunctionApprovalRequestContent("callId2", new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ])
        ];

        await InvokeAndAssertAsync(options, input, downstreamClientOutput, expectedOutput);

        await InvokeAndAssertStreamingAsync(options, input, downstreamClientOutput, expectedOutput);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task AllFunctionCallsReplacedWithApprovalsWhenAnyRequestOrAdditionalRequireApprovalAsync(bool additionalToolsRequireApproval)
    {
        AIFunction func1 = AIFunctionFactory.Create(() => "Result 1", "Func1");
        AIFunction func2 = AIFunctionFactory.Create((int i) => $"Result 2: {i}", "Func2");
        AITool[] additionalTools =
        [
            additionalToolsRequireApproval ? new ApprovalRequiredAIFunction(func1) : func1,
        ];

        var options = new ChatOptions
        {
            Tools =
            [
                additionalToolsRequireApproval ? func2 : new ApprovalRequiredAIFunction(func2),
            ]
        };

        List<ChatMessage> input =
        [
            new ChatMessage(ChatRole.User, "hello"),
        ];

        List<ChatMessage> downstreamClientOutput =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
        ];

        List<ChatMessage> expectedOutput =
        [
            new ChatMessage(ChatRole.Assistant,
            [
                new FunctionApprovalRequestContent("callId1", new FunctionCallContent("callId1", "Func1")),
                new FunctionApprovalRequestContent("callId2", new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ])
        ];

        await InvokeAndAssertAsync(options, input, downstreamClientOutput, expectedOutput, additionalTools: additionalTools);

        await InvokeAndAssertStreamingAsync(options, input, downstreamClientOutput, expectedOutput, additionalTools: additionalTools);
    }

    [Fact]
    public async Task ApprovedApprovalResponsesAreExecutedAsync()
    {
        var options = new ChatOptions
        {
            Tools =
            [
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "Result 1", "Func1")),
                AIFunctionFactory.Create((int i) => $"Result 2: {i}", "Func2"),
            ]
        };

        List<ChatMessage> input =
        [
            new ChatMessage(ChatRole.User, "hello"),
            new ChatMessage(ChatRole.Assistant,
            [
                new FunctionApprovalRequestContent("callId1", new FunctionCallContent("callId1", "Func1")),
                new FunctionApprovalRequestContent("callId2", new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ]) { MessageId = "resp1" },
            new ChatMessage(ChatRole.User,
            [
                new FunctionApprovalResponseContent("callId1", true, new FunctionCallContent("callId1", "Func1")),
                new FunctionApprovalResponseContent("callId2", true, new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ]),
        ];

        List<ChatMessage> expectedDownstreamClientInput =
        [
            new ChatMessage(ChatRole.User, "hello"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Result 1"), new FunctionResultContent("callId2", result: "Result 2: 42")]),
        ];

        List<ChatMessage> downstreamClientOutput =
        [
            new ChatMessage(ChatRole.Assistant, "world"),
        ];

        List<ChatMessage> output =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Result 1"), new FunctionResultContent("callId2", result: "Result 2: 42")]),
            new ChatMessage(ChatRole.Assistant, "world"),
        ];

        await InvokeAndAssertAsync(options, input, downstreamClientOutput, output, expectedDownstreamClientInput);

        await InvokeAndAssertStreamingAsync(options, input, downstreamClientOutput, output, expectedDownstreamClientInput);
    }

    [Fact]
    public async Task ApprovedApprovalResponsesFromSeparateFCCMessagesAreExecutedAsync()
    {
        var options = new ChatOptions
        {
            Tools =
            [
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "Result 1", "Func1")),
                AIFunctionFactory.Create((int i) => $"Result 2: {i}", "Func2"),
            ]
        };

        List<ChatMessage> input =
        [
            new ChatMessage(ChatRole.User, "hello"),
            new ChatMessage(ChatRole.Assistant,
            [
                new FunctionApprovalRequestContent("callId1", new FunctionCallContent("callId1", "Func1")),
            ]) { MessageId = "resp1" },
            new ChatMessage(ChatRole.Assistant,
            [
                new FunctionApprovalRequestContent("callId2", new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ]) { MessageId = "resp2" },
            new ChatMessage(ChatRole.User,
            [
                new FunctionApprovalResponseContent("callId1", true, new FunctionCallContent("callId1", "Func1")),
            ]),
            new ChatMessage(ChatRole.User,
            [
                new FunctionApprovalResponseContent("callId2", true, new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ]),
        ];

        List<ChatMessage> expectedDownstreamClientInput =
        [
            new ChatMessage(ChatRole.User, "hello"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1")]) { MessageId = "resp1" },
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]) { MessageId = "resp2" },
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Result 1"), new FunctionResultContent("callId2", result: "Result 2: 42")]),
        ];

        List<ChatMessage> downstreamClientOutput =
        [
            new ChatMessage(ChatRole.Assistant, "world"),
        ];

        List<ChatMessage> output =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1")]) { MessageId = "resp1" },
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]) { MessageId = "resp2" },
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Result 1"), new FunctionResultContent("callId2", result: "Result 2: 42")]),
            new ChatMessage(ChatRole.Assistant, "world"),
        ];

        await InvokeAndAssertAsync(options, input, downstreamClientOutput, output, expectedDownstreamClientInput);

        await InvokeAndAssertStreamingAsync(options, input, downstreamClientOutput, output, expectedDownstreamClientInput);
    }

    [Fact]
    public async Task RejectedApprovalResponsesAreFailedAsync()
    {
        var options = new ChatOptions
        {
            Tools =
            [
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "Result 1", "Func1")),
                AIFunctionFactory.Create((int i) => $"Result 2: {i}", "Func2"),
            ]
        };

        List<ChatMessage> input =
        [
            new ChatMessage(ChatRole.User, "hello"),
            new ChatMessage(ChatRole.Assistant,
            [
                new FunctionApprovalRequestContent("callId1", new FunctionCallContent("callId1", "Func1")),
                new FunctionApprovalRequestContent("callId2", new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ]) { MessageId = "resp1" },
            new ChatMessage(ChatRole.User,
            [
                new FunctionApprovalResponseContent("callId1", false, new FunctionCallContent("callId1", "Func1")),
                new FunctionApprovalResponseContent("callId2", false, new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ]),
        ];

        List<ChatMessage> expectedDownstreamClientInput =
        [
            new ChatMessage(ChatRole.User, "hello"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Error: Function invocation approval was not granted."), new FunctionResultContent("callId2", result: "Error: Function invocation approval was not granted.")]),
        ];

        List<ChatMessage> downstreamClientOutput =
        [
            new ChatMessage(ChatRole.Assistant, "world"),
        ];

        List<ChatMessage> output =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Error: Function invocation approval was not granted."), new FunctionResultContent("callId2", result: "Error: Function invocation approval was not granted.")]),
            new ChatMessage(ChatRole.Assistant, "world"),
        ];

        await InvokeAndAssertAsync(options, input, downstreamClientOutput, output, expectedDownstreamClientInput);

        await InvokeAndAssertStreamingAsync(options, input, downstreamClientOutput, output, expectedDownstreamClientInput);
    }

    [Fact]
    public async Task MixedApprovedAndRejectedApprovalResponsesAreExecutedAndFailedAsync()
    {
        var options = new ChatOptions
        {
            Tools =
            [
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "Result 1", "Func1")),
                AIFunctionFactory.Create((int i) => $"Result 2: {i}", "Func2"),
            ]
        };

        List<ChatMessage> input =
        [
            new ChatMessage(ChatRole.User, "hello"),
            new ChatMessage(ChatRole.Assistant,
            [
                new FunctionApprovalRequestContent("callId1", new FunctionCallContent("callId1", "Func1")),
                new FunctionApprovalRequestContent("callId2", new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ]) { MessageId = "resp1" },
            new ChatMessage(ChatRole.User,
            [
                new FunctionApprovalResponseContent("callId1", false, new FunctionCallContent("callId1", "Func1")),
                new FunctionApprovalResponseContent("callId2", true, new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ]),
        ];

        List<ChatMessage> expectedDownstreamClientInput =
        [
            new ChatMessage(ChatRole.User, "hello"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Error: Function invocation approval was not granted.")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId2", result: "Result 2: 42")]),
        ];

        List<ChatMessage> downstreamClientOutput =
        [
            new ChatMessage(ChatRole.Assistant, "world"),
        ];

        List<ChatMessage> nonStreamingOutput =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Error: Function invocation approval was not granted.")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId2", result: "Result 2: 42")]),
            new ChatMessage(ChatRole.Assistant, "world"),
        ];

        List<ChatMessage> streamingOutput =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Error: Function invocation approval was not granted."), new FunctionResultContent("callId2", result: "Result 2: 42")]),
            new ChatMessage(ChatRole.Assistant, "world"),
        ];

        await InvokeAndAssertAsync(options, input, downstreamClientOutput, nonStreamingOutput, expectedDownstreamClientInput);

        await InvokeAndAssertStreamingAsync(options, input, downstreamClientOutput, streamingOutput, expectedDownstreamClientInput);
    }

    [Fact]
    public async Task ApprovedInputsAreExecutedAndFunctionResultsAreConvertedAsync()
    {
        var options = new ChatOptions
        {
            Tools =
            [
                AIFunctionFactory.Create(() => "Result 1", "Func1"),
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create((int i) => $"Result 2: {i}", "Func2")),
            ]
        };

        List<ChatMessage> input =
        [
            new ChatMessage(ChatRole.User, "hello"),
            new ChatMessage(ChatRole.Assistant,
            [
                new FunctionApprovalRequestContent("callId1", new FunctionCallContent("callId1", "Func1")),
                new FunctionApprovalRequestContent("callId2", new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ]) { MessageId = "resp1" },
            new ChatMessage(ChatRole.User,
            [
                new FunctionApprovalResponseContent("callId1", true, new FunctionCallContent("callId1", "Func1")),
                new FunctionApprovalResponseContent("callId2", true, new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ]),
        ];

        List<ChatMessage> expectedDownstreamClientInput =
        [
            new ChatMessage(ChatRole.User, "hello"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Result 1"), new FunctionResultContent("callId2", result: "Result 2: 42")]),
        ];

        List<ChatMessage> downstreamClientOutput =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 3 } })]),
        ];

        List<ChatMessage> output =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Result 1"), new FunctionResultContent("callId2", result: "Result 2: 42")]),
            new ChatMessage(ChatRole.Assistant, [new FunctionApprovalRequestContent("callId2", new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 3 } }))]),
        ];

        await InvokeAndAssertAsync(options, input, downstreamClientOutput, output, expectedDownstreamClientInput);

        await InvokeAndAssertStreamingAsync(options, input, downstreamClientOutput, output, expectedDownstreamClientInput);
    }

    [Fact]
    public async Task AlreadyExecutedApprovalsAreIgnoredAsync()
    {
        var options = new ChatOptions
        {
            Tools =
            [
                AIFunctionFactory.Create(() => "Result 1", "Func1"),
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create((int i) => $"Result 2: {i}", "Func2")),
            ]
        };

        List<ChatMessage> input =
        [
            new ChatMessage(ChatRole.User, "hello"),
            new ChatMessage(ChatRole.Assistant,
            [
                new FunctionApprovalRequestContent("callId1", new FunctionCallContent("callId1", "Func1")),
                new FunctionApprovalRequestContent("callId2", new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ]) { MessageId = "resp1" },
            new ChatMessage(ChatRole.User,
            [
                new FunctionApprovalResponseContent("callId1", true, new FunctionCallContent("callId1", "Func1")),
                new FunctionApprovalResponseContent("callId2", true, new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ]),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Result 1"), new FunctionResultContent("callId2", result: "Result 2: 42")]),
            new ChatMessage(ChatRole.Assistant,
            [
                new FunctionApprovalRequestContent("callId3", new FunctionCallContent("callId3", "Func1")),
            ]) { MessageId = "resp2" },
            new ChatMessage(ChatRole.User,
            [
                new FunctionApprovalResponseContent("callId3", true, new FunctionCallContent("callId3", "Func1")),
            ]),
        ];

        List<ChatMessage> expectedDownstreamClientInput =
        [
            new ChatMessage(ChatRole.User, "hello"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Result 1"), new FunctionResultContent("callId2", result: "Result 2: 42")]),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId3", "Func1")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId3", result: "Result 1")]),
        ];

        List<ChatMessage> downstreamClientOutput =
        [
            new ChatMessage(ChatRole.Assistant, "World"),
        ];

        List<ChatMessage> output =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId3", "Func1")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId3", result: "Result 1")]),
            new ChatMessage(ChatRole.Assistant, "World"),
        ];

        await InvokeAndAssertAsync(options, input, downstreamClientOutput, output, expectedDownstreamClientInput);

        await InvokeAndAssertStreamingAsync(options, input, downstreamClientOutput, output, expectedDownstreamClientInput);
    }

    [Fact]
    public async Task ApprovalRequestWithoutApprovalResponseThrowsAsync()
    {
        var options = new ChatOptions
        {
            Tools =
            [
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "Result 1", "Func1")),
                AIFunctionFactory.Create((int i) => $"Result 2: {i}", "Func2"),
            ]
        };

        List<ChatMessage> input =
        [
            new ChatMessage(ChatRole.User, "hello"),
            new ChatMessage(ChatRole.Assistant,
            [
                new FunctionApprovalRequestContent("callId1", new FunctionCallContent("callId1", "Func1")),
            ]) { MessageId = "resp1" },
        ];

        var invokeException = await Assert.ThrowsAsync<InvalidOperationException>(
            async () => await InvokeAndAssertAsync(options, input, [], [], []));
        Assert.Equal("FunctionApprovalRequestContent found with FunctionCall.CallId(s) 'callId1' that have no matching FunctionApprovalResponseContent.", invokeException.Message);

        var invokeStreamingException = await Assert.ThrowsAsync<InvalidOperationException>(
            async () => await InvokeAndAssertStreamingAsync(options, input, [], [], []));
        Assert.Equal("FunctionApprovalRequestContent found with FunctionCall.CallId(s) 'callId1' that have no matching FunctionApprovalResponseContent.", invokeStreamingException.Message);
    }

    [Fact]
    public async Task ApprovedApprovalResponsesWithoutApprovalRequestAreExecutedAsync()
    {
        var options = new ChatOptions
        {
            Tools =
            [
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "Result 1", "Func1")),
                AIFunctionFactory.Create((int i) => $"Result 2: {i}", "Func2"),
            ]
        };

        List<ChatMessage> input =
        [
            new ChatMessage(ChatRole.User, "hello"),
            new ChatMessage(ChatRole.User,
            [
                new FunctionApprovalResponseContent("callId1", true, new FunctionCallContent("callId1", "Func1")),
                new FunctionApprovalResponseContent("callId2", true, new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ]),
        ];

        List<ChatMessage> expectedDownstreamClientInput =
        [
            new ChatMessage(ChatRole.User, "hello"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Result 1"), new FunctionResultContent("callId2", result: "Result 2: 42")]),
        ];

        List<ChatMessage> downstreamClientOutput =
        [
            new ChatMessage(ChatRole.Assistant, "world"),
        ];

        List<ChatMessage> output =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Result 1"), new FunctionResultContent("callId2", result: "Result 2: 42")]),
            new ChatMessage(ChatRole.Assistant, "world"),
        ];

        await InvokeAndAssertAsync(options, input, downstreamClientOutput, output, expectedDownstreamClientInput);

        await InvokeAndAssertStreamingAsync(options, input, downstreamClientOutput, output, expectedDownstreamClientInput);
    }

    [Fact]
    public async Task FunctionCallContentIsNotPassedToDownstreamServiceWithServiceThreadsAsync()
    {
        var options = new ChatOptions
        {
            Tools =
            [
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "Result 1", "Func1")),
                AIFunctionFactory.Create((int i) => $"Result 2: {i}", "Func2"),
            ],
            ConversationId = "test-conversation",
        };

        List<ChatMessage> input =
        [
            new ChatMessage(ChatRole.User,
            [
                new FunctionApprovalResponseContent("callId1", true, new FunctionCallContent("callId1", "Func1")),
                new FunctionApprovalResponseContent("callId2", true, new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } }))
            ]),
        ];

        List<ChatMessage> expectedDownstreamClientInput =
        [
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Result 1"), new FunctionResultContent("callId2", result: "Result 2: 42")]),
        ];

        List<ChatMessage> downstreamClientOutput =
        [
            new ChatMessage(ChatRole.Assistant, "world"),
        ];

        List<ChatMessage> output =
        [
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1"), new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("callId1", result: "Result 1"), new FunctionResultContent("callId2", result: "Result 2: 42")]),
            new ChatMessage(ChatRole.Assistant, "world"),
        ];

        await InvokeAndAssertAsync(options, input, downstreamClientOutput, output, expectedDownstreamClientInput);

        await InvokeAndAssertStreamingAsync(options, input, downstreamClientOutput, output, expectedDownstreamClientInput);
    }

    /// <summary>
    /// Since we do not have a way of supporting both functions that require approval and those that do not
    /// in one invocation, we always require all function calls to be approved if any require approval.
    /// If we are therefore unsure as to whether we will encounter a function call that requires approval,
    /// we have to wait until we find one before yielding any function call content.
    /// If we don't have any function calls that require approval at all though, we can just yield all content normally
    /// since this issue won't apply.
    /// </summary>
    [Fact]
    public async Task FunctionCallContentIsYieldedImmediatelyIfNoApprovalRequiredWhenStreamingAsync()
    {
        var options = new ChatOptions
        {
            Tools =
            [
                AIFunctionFactory.Create(() => "Result 1", "Func1"),
                AIFunctionFactory.Create((int i) => $"Result 2: {i}", "Func2"),
            ]
        };

        List<ChatMessage> input = [new ChatMessage(ChatRole.User, "hello")];

        Func<ChatClientBuilder, ChatClientBuilder> configurePipeline = b => b.Use(s => new NewFunctionInvokingChatClient(s));
        using CancellationTokenSource cts = new();

        var updateYieldCount = 0;

        async IAsyncEnumerable<ChatResponseUpdate> YieldInnerClientUpdates(IEnumerable<ChatMessage> contents, ChatOptions? actualOptions, [EnumeratorCancellation] CancellationToken actualCancellationToken)
        {
            Assert.Equal(cts.Token, actualCancellationToken);
            await Task.Yield();
            var messageId = Guid.NewGuid().ToString("N");

            updateYieldCount++;
            yield return new ChatResponseUpdate(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1")]) { MessageId = messageId };
            updateYieldCount++;
            yield return new ChatResponseUpdate(ChatRole.Assistant, [new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]) { MessageId = messageId };
        }

        using var innerClient = new TestChatClient { GetStreamingResponseAsyncCallback = YieldInnerClientUpdates };
        IChatClient service = configurePipeline(innerClient.AsBuilder()).Build();

        var updates = service.GetStreamingResponseAsync(new EnumeratedOnceEnumerable<ChatMessage>(input), options, cts.Token);

        var updateCount = 0;
        await foreach (var update in updates)
        {
            if (updateCount < 2)
            {
                var functionCall = update.Contents.OfType<FunctionCallContent>().First();
                if (functionCall.CallId == "callId1")
                {
                    Assert.Equal("Func1", functionCall.Name);
                    Assert.Equal(1, updateYieldCount);
                }
                else if (functionCall.CallId == "callId2")
                {
                    Assert.Equal("Func2", functionCall.Name);
                    Assert.Equal(2, updateYieldCount);
                }
            }

            updateCount++;
        }
    }

    /// <summary>
    /// Since we do not have a way of supporting both functions that require approval and those that do not
    /// in one invocation, we always require all function calls to be approved if any require approval.
    /// If we are therefore unsure as to whether we will encounter a function call that requires approval,
    /// we have to wait until we find one before yielding any function call content.
    /// We can however, yield any other content until we encounter the first function call.
    /// </summary>
    [Fact]
    public async Task FunctionCalsAreBufferedUntilApprovalRequirementEncounteredWhenStreamingAsync()
    {
        var options = new ChatOptions
        {
            Tools =
            [
                AIFunctionFactory.Create(() => "Result 1", "Func1"),
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create((int i) => $"Result 2: {i}", "Func2")),
                AIFunctionFactory.Create(() => "Result 3", "Func3"),
            ]
        };

        List<ChatMessage> input = [new ChatMessage(ChatRole.User, "hello")];

        Func<ChatClientBuilder, ChatClientBuilder> configurePipeline = b => b.Use(s => new NewFunctionInvokingChatClient(s));
        using CancellationTokenSource cts = new();

        var updateYieldCount = 0;

        async IAsyncEnumerable<ChatResponseUpdate> YieldInnerClientUpdates(IEnumerable<ChatMessage> contents, ChatOptions? actualOptions, [EnumeratorCancellation] CancellationToken actualCancellationToken)
        {
            Assert.Equal(cts.Token, actualCancellationToken);
            await Task.Yield();
            var messageId = Guid.NewGuid().ToString("N");

            updateYieldCount++;
            yield return new ChatResponseUpdate(ChatRole.Assistant, [new TextContent("Text 1")]) { MessageId = messageId };
            updateYieldCount++;
            yield return new ChatResponseUpdate(ChatRole.Assistant, [new TextContent("Text 2")]) { MessageId = messageId };
            updateYieldCount++;
            yield return new ChatResponseUpdate(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func1")]) { MessageId = messageId };
            updateYieldCount++;
            yield return new ChatResponseUpdate(ChatRole.Assistant, [new FunctionCallContent("callId2", "Func2", arguments: new Dictionary<string, object?> { { "i", 42 } })]) { MessageId = messageId };
            updateYieldCount++;
            yield return new ChatResponseUpdate(ChatRole.Assistant, [new FunctionCallContent("callId1", "Func3")]) { MessageId = messageId };
        }

        using var innerClient = new TestChatClient { GetStreamingResponseAsyncCallback = YieldInnerClientUpdates };
        IChatClient service = configurePipeline(innerClient.AsBuilder()).Build();

        var updates = service.GetStreamingResponseAsync(new EnumeratedOnceEnumerable<ChatMessage>(input), options, cts.Token);

        var updateCount = 0;
        await foreach (var update in updates)
        {
            switch (updateCount)
            {
                case 0:
                    Assert.Equal("Text 1", update.Contents.OfType<TextContent>().First().Text);
                    // First content should be yielded immedately, since we don't have any function calls yet.
                    Assert.Equal(1, updateYieldCount);
                    break;
                case 1:
                    Assert.Equal("Text 2", update.Contents.OfType<TextContent>().First().Text);
                    // Second content should be yielded immedately, since we don't have any function calls yet.
                    Assert.Equal(2, updateYieldCount);
                    break;
                case 2:
                    var approvalRequest1 = update.Contents.OfType<FunctionApprovalRequestContent>().First();
                    Assert.Equal("callId1", approvalRequest1.FunctionCall.CallId);
                    Assert.Equal("Func1", approvalRequest1.FunctionCall.Name);
                    // Third content should have been buffered, since we have not yet encountered a function call that requires approval.
                    Assert.Equal(4, updateYieldCount);
                    break;
                case 3:
                    var approvalRequest2 = update.Contents.OfType<FunctionApprovalRequestContent>().First();
                    Assert.Equal("callId2", approvalRequest2.FunctionCall.CallId);
                    Assert.Equal("Func2", approvalRequest2.FunctionCall.Name);
                    // Fourth content can be yielded immediately, since it is the first function call that requires approval.
                    Assert.Equal(4, updateYieldCount);
                    break;
                case 4:
                    var approvalRequest3 = update.Contents.OfType<FunctionApprovalRequestContent>().First();
                    Assert.Equal("callId1", approvalRequest3.FunctionCall.CallId);
                    Assert.Equal("Func3", approvalRequest3.FunctionCall.Name);
                    // Fifth content can be yielded immediately, since we previously encountered a function call that requires approval.
                    Assert.Equal(5, updateYieldCount);
                    break;
            }

            updateCount++;
        }
    }

    private static async Task<List<ChatMessage>> InvokeAndAssertAsync(
        ChatOptions? options,
        List<ChatMessage> input,
        List<ChatMessage> downstreamClientOutput,
        List<ChatMessage> expectedOutput,
        List<ChatMessage>? expectedDownstreamClientInput = null,
        Func<ChatClientBuilder, ChatClientBuilder>? configurePipeline = null,
        AITool[]? additionalTools = null,
        IServiceProvider? services = null)
    {
        Assert.NotEmpty(input);

        configurePipeline ??= b => b.Use(s => new NewFunctionInvokingChatClient(s) { AdditionalTools = additionalTools });

        using CancellationTokenSource cts = new();
        long expectedTotalTokenCounts = 0;

        using var innerClient = new TestChatClient
        {
            GetResponseAsyncCallback = async (contents, actualOptions, actualCancellationToken) =>
            {
                Assert.Equal(cts.Token, actualCancellationToken);
                if (expectedDownstreamClientInput is not null)
                {
                    CompareMessageLists(expectedDownstreamClientInput, contents.ToList());
                }

                await Task.Yield();

                var usage = CreateRandomUsage();
                expectedTotalTokenCounts += usage.InputTokenCount!.Value;

                downstreamClientOutput.ForEach(m => m.MessageId = Guid.NewGuid().ToString("N"));
                return new ChatResponse(downstreamClientOutput) { Usage = usage };
            }
        };

        IChatClient service = configurePipeline(innerClient.AsBuilder()).Build(services);

        var result = await service.GetResponseAsync(new EnumeratedOnceEnumerable<ChatMessage>(input), options, cts.Token);
        Assert.NotNull(result);

        var actualOutput = result.Messages as List<ChatMessage> ?? result.Messages.ToList();
        CompareMessageLists(expectedOutput, actualOutput);

        // Usage should be aggregated over all responses, including AdditionalUsage
        var actualUsage = result.Usage!;
        Assert.Equal(expectedTotalTokenCounts, actualUsage.InputTokenCount);
        Assert.Equal(expectedTotalTokenCounts, actualUsage.OutputTokenCount);
        Assert.Equal(expectedTotalTokenCounts, actualUsage.TotalTokenCount);
        Assert.Equal(2, actualUsage.AdditionalCounts!.Count);
        Assert.Equal(expectedTotalTokenCounts, actualUsage.AdditionalCounts["firstValue"]);
        Assert.Equal(expectedTotalTokenCounts, actualUsage.AdditionalCounts["secondValue"]);

        return actualOutput;
    }

    private static UsageDetails CreateRandomUsage()
    {
        // We'll set the same random number on all the properties so that, when determining the
        // correct sum in tests, we only have to total the values once
        var value = new Random().Next(100);
        return new UsageDetails
        {
            InputTokenCount = value,
            OutputTokenCount = value,
            TotalTokenCount = value,
            AdditionalCounts = new() { ["firstValue"] = value, ["secondValue"] = value },
        };
    }

    private static async Task<List<ChatMessage>> InvokeAndAssertStreamingAsync(
        ChatOptions? options,
        List<ChatMessage> input,
        List<ChatMessage> downstreamClientOutput,
        List<ChatMessage> expectedOutput,
        List<ChatMessage>? expectedDownstreamClientInput = null,
        Func<ChatClientBuilder, ChatClientBuilder>? configurePipeline = null,
        AITool[]? additionalTools = null,
        IServiceProvider? services = null)
    {
        Assert.NotEmpty(input);

        configurePipeline ??= b => b.Use(s => new NewFunctionInvokingChatClient(s) { AdditionalTools = additionalTools });

        using CancellationTokenSource cts = new();

        using var innerClient = new TestChatClient
        {
            GetStreamingResponseAsyncCallback = (contents, actualOptions, actualCancellationToken) =>
            {
                Assert.Equal(cts.Token, actualCancellationToken);
                if (expectedDownstreamClientInput is not null)
                {
                    CompareMessageLists(expectedDownstreamClientInput, contents.ToList());
                }

                downstreamClientOutput.ForEach(m => m.MessageId = Guid.NewGuid().ToString("N"));
                return YieldAsync(new ChatResponse(downstreamClientOutput).ToChatResponseUpdates());
            }
        };

        IChatClient service = configurePipeline(innerClient.AsBuilder()).Build(services);

        var result = await service.GetStreamingResponseAsync(new EnumeratedOnceEnumerable<ChatMessage>(input), options, cts.Token).ToChatResponseAsync();
        Assert.NotNull(result);

        var actualOutput = result.Messages as List<ChatMessage> ?? result.Messages.ToList();

        expectedOutput ??= input;
        CompareMessageLists(expectedOutput, actualOutput);

        return actualOutput;
    }

    private static async IAsyncEnumerable<T> YieldAsync<T>(params T[] items)
    {
        await Task.Yield();
        foreach (var item in items)
        {
            yield return item;
        }
    }

    private static void CompareMessageLists(List<ChatMessage> expectedMessages, List<ChatMessage> actualMessages)
    {
        Assert.Equal(expectedMessages.Count, actualMessages.Count);
        for (int i = 0; i < expectedMessages.Count; i++)
        {
            var expectedMessage = expectedMessages[i];
            var chatMessage = actualMessages[i];

            Assert.Equal(expectedMessage.Role, chatMessage.Role);
            Assert.Equal(expectedMessage.Text, chatMessage.Text);
            Assert.Equal(expectedMessage.GetType(), chatMessage.GetType());

            Assert.Equal(expectedMessage.Contents.Count, chatMessage.Contents.Count);
            for (int j = 0; j < expectedMessage.Contents.Count; j++)
            {
                var expectedItem = expectedMessage.Contents[j];
                var chatItem = chatMessage.Contents[j];

                Assert.Equal(expectedItem.GetType(), chatItem.GetType());
                Assert.Equal(expectedItem.ToString(), chatItem.ToString());
                if (expectedItem is FunctionCallContent expectedFunctionCall)
                {
                    var chatFunctionCall = (FunctionCallContent)chatItem;
                    Assert.Equal(expectedFunctionCall.Name, chatFunctionCall.Name);
                    AssertExtensions.EqualFunctionCallParameters(expectedFunctionCall.Arguments, chatFunctionCall.Arguments);
                }
                else if (expectedItem is FunctionResultContent expectedFunctionResult)
                {
                    var chatFunctionResult = (FunctionResultContent)chatItem;
                    AssertExtensions.EqualFunctionCallResults(expectedFunctionResult.Result, chatFunctionResult.Result);
                }
            }
        }
    }

    private sealed class EnumeratedOnceEnumerable<T>(IEnumerable<T> items) : IEnumerable<T>
    {
        private int _iterated;

        public IEnumerator<T> GetEnumerator()
        {
            if (Interlocked.Exchange(ref _iterated, 1) != 0)
            {
                throw new InvalidOperationException("This enumerable can only be enumerated once.");
            }

            foreach (var item in items)
            {
                yield return item;
            }
        }

        IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
    }
}
