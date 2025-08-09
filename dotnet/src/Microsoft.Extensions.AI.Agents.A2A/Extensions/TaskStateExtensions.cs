// Copyright (c) Microsoft. All rights reserved.

using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A.Extensions;

internal static class TaskStateExtensions
{
    public static bool IsFinalState(this TaskState state)
        => state is TaskState.Completed
                 or TaskState.Failed
                 or TaskState.Canceled
                 or TaskState.Rejected;

    public static bool IsActive(this TaskState state)
        => state is TaskState.Working
                 or TaskState.Submitted;
}
