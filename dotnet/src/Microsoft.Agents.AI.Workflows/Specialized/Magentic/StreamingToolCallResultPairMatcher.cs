// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized.Magentic;

internal sealed class StreamingToolCallResultPairMatcher
{
    private enum CallType
    {
        Function,
        McpServerTool
    }

    private record CallSummaryKey(CallType Type, string CallId);

    private struct ToolCallSummary(CallType callType, string callId, string name)
    {
        public CallType CallType => callType;

        public string? CallId => callId;

        public string Name => name;
    }

    private readonly Dictionary<CallSummaryKey, ToolCallSummary> _callSummaries = new();

    private void Collect(CallType callType, string callId, string name, string callContentTypeName, string resultContentTypeName)
    {
        CallSummaryKey key = new(callType, callId);
        if (this._callSummaries.ContainsKey(key))
        {
            throw new InvalidOperationException($"Duplicate {callContentTypeName} with CallId '{callId}' without corresponding {resultContentTypeName}.");
        }

        this._callSummaries[key] = new ToolCallSummary(callType, callId, name);
    }

    public void CollectFunctionCall(FunctionCallContent callContent)
    {
        const string FunctionCallContentTypeName = nameof(FunctionCallContent);
        const string FunctionResultContentTypeName = nameof(FunctionResultContent);

        this.Collect(CallType.Function, callContent.CallId, callContent.Name, FunctionCallContentTypeName, FunctionResultContentTypeName);
    }

    public void CollectMcpServerToolCall(McpServerToolCallContent callContent)
    {
        const string McpServerToolCallContentTypeName = nameof(McpServerToolCallContent);
        const string McpServerToolResultContentTypeName = nameof(McpServerToolResultContent);

        this.Collect(CallType.McpServerTool, callContent.CallId, callContent.Name, McpServerToolCallContentTypeName, McpServerToolResultContentTypeName);
    }

    private bool TryResolve(CallType callType, string callId, [NotNullWhen(true)] out string? name)
    {
        CallSummaryKey key = new(callType, callId);

        bool hasMatchingCall = this._callSummaries.TryGetValue(key, out ToolCallSummary callSummary);
        if (hasMatchingCall)
        {
            this._callSummaries.Remove(key);
        }

        name = hasMatchingCall ? callSummary.Name : null;
        return hasMatchingCall;
    }

    public bool TryResolveFunctionCall(FunctionResultContent resultContent, [NotNullWhen(true)] out string? name)
        => this.TryResolve(CallType.Function, resultContent.CallId, out name);

    public bool TryResolveMcpServerToolCall(McpServerToolResultContent resultContent, [NotNullWhen(true)] out string? name)
        => this.TryResolve(CallType.McpServerTool, resultContent.CallId, out name);
}
