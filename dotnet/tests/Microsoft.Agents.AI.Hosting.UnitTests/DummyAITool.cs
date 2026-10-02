// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Inert <see cref="AITool"/> used where a test only needs a tool identity to register and assert on.
/// </summary>
internal sealed class DummyAITool : AITool;
