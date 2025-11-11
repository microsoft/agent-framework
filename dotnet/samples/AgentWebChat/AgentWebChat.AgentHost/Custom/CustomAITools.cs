// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace AgentWebChat.AgentHost.Custom;

public class CustomAITool : AITool
{
}

public class CustomFunctionTool : AIFunction
{
    protected override ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken cancellationToken)
    {
        return new ValueTask<object?>(arguments.Context?.Count ?? 0);
    }
}
