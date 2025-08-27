// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Execution;

internal interface IStepTracer
{
    void TraceActivated(string executorId);
    void TraceCheckpointCreated(CheckpointInfo checkpoint);
    void TraceIntantiated(string executorId);
    void TraceStatePublished();
}
