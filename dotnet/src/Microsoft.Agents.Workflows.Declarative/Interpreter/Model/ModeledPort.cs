// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class ModeledPort(InputPort port) : IModeledAction
{
    public string Id => port.Id;
    public InputPort InputPort => port;
}
