// Copyright (c) Microsoft. All rights reserved.
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents;

/// <summary>
/// Optional parameters for agent creation used when create an <see cref="Agent"/>
/// using an instance of <see cref="AgentFactory"/>.
/// <remarks>
/// Implementors of <see cref="AgentFactory"/> can extend this class to provide
/// agent specific creation options.
/// </remarks>
/// </summary>

public class AgentCreationOptions
{
}
