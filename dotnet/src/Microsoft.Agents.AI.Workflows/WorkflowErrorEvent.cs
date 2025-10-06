// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when a workflow encounters an error.
/// </summary>
/// <param name="e">
/// Optionally, the <see cref="Exception"/> representing the error.
/// </param>
public class WorkflowErrorEvent(Exception? e) : WorkflowEvent(e);
