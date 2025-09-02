// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Specialized;

internal interface IOutputSink<TResult> : IIdentified
{
    TResult? Result { get; }
}
