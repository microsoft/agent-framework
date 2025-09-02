// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Checkpointing;

internal class ExportedState(object state)
{
    public Type RuntimeType => Throw.IfNull(state).GetType();
    public object Value => Throw.IfNull(state);
}
