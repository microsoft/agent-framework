// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal interface IModelBuilder<TCondition> where TCondition : class
{
    void Connect(IModeledAction source, IModeledAction target, TCondition? condition = null);
}
