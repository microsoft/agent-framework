// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Declarative.Interpreter;

internal sealed class RequestPortAction(RequestPort port) : IModeledAction
{
    public string Id => port.Id;
    public RequestPort RequestPort => port;
}
