// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Execution;

internal interface IRunnerWithOutput<TResult>
{
    ISuperStepRunner StepRunner { get; }

    TResult? RunningOutput { get; }
}
