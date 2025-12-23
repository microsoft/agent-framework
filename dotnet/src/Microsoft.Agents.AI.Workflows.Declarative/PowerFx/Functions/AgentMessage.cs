// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.PowerFx.Functions;

internal sealed class AgentMessage : MessageFunction
{
    public const string FunctionName = nameof(AgentMessage);

    public AgentMessage() : base(FunctionName) { }

    public static FormulaValue Execute(StringValue input) => Create(ChatRole.Assistant, input);
}
