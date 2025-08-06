// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// .
/// </summary>
/// <param name="Id"></param>
/// <param name="Request"></param>
/// <param name="Response"></param>
public record InputPort(string Id, Type Request, Type Response)
{ };
