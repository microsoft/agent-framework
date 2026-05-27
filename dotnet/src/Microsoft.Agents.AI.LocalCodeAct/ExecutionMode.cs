// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

namespace Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// Defines how generated Python code is executed.
/// </summary>
public enum ExecutionMode
{
    /// <summary>
    /// Execute Python code in a subprocess. This is the default and only mode in .NET.
    /// Provides process-level isolation but is NOT a security sandbox on its own.
    /// Real sandboxing must come from external container/VM isolation.
    /// </summary>
    Subprocess,
}
