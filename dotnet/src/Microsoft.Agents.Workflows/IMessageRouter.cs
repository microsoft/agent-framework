﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows;

internal interface IMessageRouter
{
    HashSet<Type> IncomingTypes { get; }

    bool CanHandle(object message);
    bool CanHandle(Type candidateType);
    ValueTask<CallResult?> RouteMessageAsync(object message, IWorkflowContext context, bool requireRoute = false);
}
