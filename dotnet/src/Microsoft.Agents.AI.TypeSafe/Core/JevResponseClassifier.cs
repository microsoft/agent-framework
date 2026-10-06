// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Classifies System One responses like the official TypeSafe SDK: any 2xx status is a success, and 408, 429, and
/// every 5xx status are retriable.
/// </summary>
/// <remarks>
/// <see cref="PipelineMessageClassifier.Default"/> only retries 500, 502, 503, and 504 among the 5xx statuses, which
/// leaves out 529, the status TypeSafe answers when it is overloaded. Network failures are left to the default
/// classifier, which retries them, as the SDK does.
/// </remarks>
internal sealed class JevResponseClassifier : PipelineMessageClassifier
{
    public static JevResponseClassifier Instance { get; } = new();

    public override bool TryClassify(PipelineMessage message, out bool isError)
    {
        if (message.Response is not { } response)
        {
            isError = false;
            return false;
        }

        isError = response.Status is < 200 or >= 300;
        return true;
    }

    public override bool TryClassify(PipelineMessage message, Exception? exception, out bool isRetriable)
    {
        if (exception is not null || message.Response is not { } response)
        {
            isRetriable = false;
            return false;
        }

        isRetriable = response.Status is 408 or 429 or (>= 500 and <= 599);
        return true;
    }
}
