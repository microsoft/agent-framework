// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class ModeledPort(InputPort port) : IModeledAction
{
    public Type ActionType => typeof(InputPort);
    public string Id => port.Id;
    public InputPort InputPort => port;
}
