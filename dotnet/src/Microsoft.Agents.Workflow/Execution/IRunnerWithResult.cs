// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal interface IRunnerWithResult<TResult>
{
    ISuperStepRunner StepRunner { get; }

    ValueTask<TResult> GetResultAsync(CancellationToken cancellation = default);
}
