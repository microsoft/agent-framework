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
}
