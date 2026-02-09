// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

using System;
using System.Collections.Generic;
using Aspire.Hosting.AgentFramework;

namespace Aspire.Hosting.ApplicationModel;

/// <summary>
/// An annotation that tracks an agent service backend referenced by a DevUI resource.
/// </summary>
/// <remarks>
/// This annotation is used to configure DevUI to aggregate entities from multiple
/// agent service backends. Each annotation represents one backend that DevUI should
/// connect to for entity discovery and request routing.
/// </remarks>
public class AgentServiceAnnotation : IResourceAnnotation
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentServiceAnnotation"/> class.
    /// </summary>
    /// <param name="agentService">The agent service resource.</param>
    /// <param name="entityIdPrefix">
    /// An optional prefix to add to entity IDs from this backend to avoid conflicts.
    /// If not specified, the resource name will be used as the prefix.
    /// </param>
    /// <param name="agents">
    /// Optional list of agents declared by this backend. When provided, the aggregator builds the entity
    /// listing directly from these declarations instead of querying the backend's <c>/v1/entities</c> endpoint.
    /// </param>
    public AgentServiceAnnotation(IResource agentService, string? entityIdPrefix = null, IReadOnlyList<AgentEntityInfo>? agents = null)
    {
        ArgumentNullException.ThrowIfNull(agentService);

        AgentService = agentService;
        EntityIdPrefix = entityIdPrefix;
        Agents = agents ?? [];
    }

    /// <summary>
    /// Gets the agent service resource that exposes AI agents.
    /// </summary>
    public IResource AgentService { get; }

    /// <summary>
    /// Gets the prefix to use for entity IDs from this backend.
    /// </summary>
    /// <remarks>
    /// When <c>null</c>, the resource name will be used as the prefix.
    /// Entity IDs will be formatted as "{prefix}/{entityId}" to ensure uniqueness
    /// across multiple agent backends.
    /// </remarks>
    public string? EntityIdPrefix { get; }

    /// <summary>
    /// Gets the list of agents declared by this backend.
    /// </summary>
    /// <remarks>
    /// When non-empty, the DevUI aggregator uses these declarations to build the entity listing
    /// without querying the backend. When empty, the aggregator falls back to calling
    /// <c>GET /v1/entities</c> on the backend for discovery.
    /// </remarks>
    public IReadOnlyList<AgentEntityInfo> Agents { get; }
}
