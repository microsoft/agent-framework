// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Declarative.Interpreter;

internal sealed class InputPortAction(InputPort port) : IModeledAction
{
    public string Id => port.Id;
    public InputPort InputPort => port;
}
