// Copyright (c) Microsoft. All rights reserved.

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal static class AGUIEventTypes
{
    public const string RunStarted = "RUN_STARTED";

    public const string RunFinished = "RUN_FINISHED";

    public const string RunError = "RUN_ERROR";

    public const string TextMessageStart = "TEXT_MESSAGE_START";

    public const string TextMessageContent = "TEXT_MESSAGE_CONTENT";

    public const string TextMessageEnd = "TEXT_MESSAGE_END";

    public const string ToolCallStart = "TOOL_CALL_START";

    public const string ToolCallArgs = "TOOL_CALL_ARGS";

    public const string ToolCallEnd = "TOOL_CALL_END";

    public const string ToolCallResult = "TOOL_CALL_RESULT";

    public const string StateSnapshot = "STATE_SNAPSHOT";

    public const string StateDelta = "STATE_DELTA";

    public const string ReasoningStart = "REASONING_START";

    public const string ReasoningMessageStart = "REASONING_MESSAGE_START";

    public const string ReasoningMessageContent = "REASONING_MESSAGE_CONTENT";

    public const string ReasoningMessageEnd = "REASONING_MESSAGE_END";

    public const string ReasoningEnd = "REASONING_END";

    public const string ReasoningMessageChunk = "REASONING_MESSAGE_CHUNK";

    public const string ReasoningEncryptedValue = "REASONING_ENCRYPTED_VALUE";
}
