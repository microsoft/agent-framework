// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.PowerFx.Functions;

internal sealed class UserMessage : MessageFunction
{
    public const string FunctionName = nameof(UserMessage);

    public UserMessage() : base(FunctionName) { }

    public static FormulaValue Execute(StringValue input) => Create(ChatRole.User, input);
}
