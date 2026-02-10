// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using Aspire.Hosting.AgentFramework;
using Aspire.Hosting.ApplicationModel;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace Aspire.Hosting;

/// <summary>
/// Provides extension methods for adding Agent Framework DevUI resources to the application model.
/// </summary>
public static class AgentFrameworkBuilderExtensions
{
    /// <summary>
    /// Adds a DevUI resource for testing AI agents in a distributed application.
    /// </summary>
    /// <remarks>
    /// <para>
    /// DevUI is a web-based interface for testing and debugging AI agents using the OpenAI Responses protocol.
    /// When configured with <see cref="WithAgentService{TSource}"/>, it aggregates agents from multiple backend services
    /// and provides a unified testing interface.
    /// </para>
    /// <para>
    /// The aggregator runs as an in-process reverse proxy within the AppHost, requiring no external container image.
    /// It proxies the DevUI frontend from the first configured backend and aggregates entity listings from all backends.
    /// </para>
    /// <para>
    /// This resource is excluded from the deployment manifest as it is intended for development use only.
    /// </para>
    /// </remarks>
    /// <param name="builder">The <see cref="IDistributedApplicationBuilder"/>.</param>
    /// <param name="name">The name to give the resource.</param>
    /// <param name="port">The host port for the DevUI web interface. If not specified, a random port will be assigned.</param>
    /// <returns>A reference to the <see cref="IResourceBuilder{T}"/> for chaining.</returns>
    /// <example>
    /// <code>
    /// var devui = builder.AddDevUI("devui")
    ///     .WithAgentService(dotnetAgent)
    ///     .WithAgentService(pythonAgent);
    /// </code>
    /// </example>
    public static IResourceBuilder<DevUIResource> AddDevUI(
        this IDistributedApplicationBuilder builder,
        string name,
        int? port = null)
    {
        ArgumentNullException.ThrowIfNull(builder);
        ArgumentNullException.ThrowIfNull(name);

        var resource = new DevUIResource(name, port);

        var resourceBuilder = builder.AddResource(resource)
            .ExcludeFromManifest(); // DevUI is a dev-only tool

        // Initialize the in-process aggregator when the resource is initialized by the orchestrator
        builder.Eventing.Subscribe<InitializeResourceEvent>(resource, async (e, ct) =>
        {
            var logger = e.Logger;
            var aggregator = new DevUIAggregatorHostedService(resource, e.Services.GetRequiredService<ILoggerFactory>().CreateLogger<DevUIAggregatorHostedService>());

            try
            {
                // Wait for dependencies (e.g. agent service backends) before starting.
                // Custom resources must manually publish BeforeResourceStartedEvent to trigger
                // the orchestrator's WaitFor mechanism.
                await e.Eventing.PublishAsync(new BeforeResourceStartedEvent(resource, e.Services), ct).ConfigureAwait(false);

                await e.Notifications.PublishUpdateAsync(resource, snapshot => snapshot with
                {
                    State = KnownResourceStates.Starting
                }).ConfigureAwait(false);

                await aggregator.StartAsync(ct).ConfigureAwait(false);

                // Allocate the endpoint so the URL appears in the Aspire dashboard
                var endpointAnnotation = resource.Annotations
                    .OfType<EndpointAnnotation>()
                    .First(ea => ea.Name == DevUIResource.PrimaryEndpointName);

                endpointAnnotation.AllocatedEndpoint = new AllocatedEndpoint(
                    endpointAnnotation, "localhost", aggregator.AllocatedPort);

                var devuiUrl = $"http://localhost:{aggregator.AllocatedPort}/devui/";

                await e.Notifications.PublishUpdateAsync(resource, snapshot => snapshot with
                {
                    State = KnownResourceStates.Running,
                    Urls = [new UrlSnapshot("DevUI", devuiUrl, IsInternal: false)]
                }).ConfigureAwait(false);

                // Shut down the aggregator when the app stops
                var lifetime = e.Services.GetRequiredService<IHostApplicationLifetime>();
                lifetime.ApplicationStopping.Register(() =>
                {
                    e.Notifications.PublishUpdateAsync(resource, snapshot => snapshot with
                    {
                        State = KnownResourceStates.Finished
                    }).GetAwaiter().GetResult();

                    aggregator.StopAsync(CancellationToken.None).GetAwaiter().GetResult();
                    aggregator.DisposeAsync().AsTask().GetAwaiter().GetResult();
                });
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "Failed to start DevUI aggregator");

                await e.Notifications.PublishUpdateAsync(resource, snapshot => snapshot with
                {
                    State = KnownResourceStates.FailedToStart
                }).ConfigureAwait(false);
            }
        });

        return resourceBuilder;
    }

    /// <summary>
    /// Configures DevUI to connect to an agent service backend.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Each agent service should expose the OpenAI Responses and Conversations API endpoints
    /// (via <c>MapOpenAIResponses</c> and <c>MapOpenAIConversations</c>).
    /// </para>
    /// <para>
    /// When <paramref name="agents"/> is provided, the aggregator builds the entity listing from
    /// these declarations without querying the backend. When not provided, a single agent named
    /// after the service resource is assumed. Agent services don't need a <c>/v1/entities</c> endpoint.
    /// </para>
    /// </remarks>
    /// <typeparam name="TSource">The type of the agent service resource.</typeparam>
    /// <param name="builder">The DevUI resource builder.</param>
    /// <param name="agentService">The agent service resource to connect to.</param>
    /// <param name="agents">
    /// Optional list of agents declared by this backend. When provided, the aggregator uses these
    /// declarations directly. When not provided, defaults to a single agent named after the
    /// <paramref name="agentService"/> resource. The backend doesn't need to expose a
    /// <c>/v1/entities</c> endpoint in either case.
    /// </param>
    /// <param name="entityIdPrefix">
    /// An optional prefix to add to entity IDs from this backend.
    /// If not specified, the resource name will be used as the prefix.
    /// </param>
    /// <returns>A reference to the <see cref="IResourceBuilder{T}"/> for chaining.</returns>
    /// <example>
    /// <code>
    /// var writerAgent = builder.AddProject&lt;Projects.WriterAgent&gt;("writer-agent");
    /// var editorAgent = builder.AddProject&lt;Projects.EditorAgent&gt;("editor-agent");
    ///
    /// builder.AddDevUI("devui")
    ///     .WithAgentService(writerAgent, agents: [new("writer", "Writes short stories")])
    ///     .WithAgentService(editorAgent, agents: [new("editor", "Edits and formats stories")])
    ///     .WaitFor(writerAgent)
    ///     .WaitFor(editorAgent);
    /// </code>
    /// </example>
    public static IResourceBuilder<DevUIResource> WithAgentService<TSource>(
        this IResourceBuilder<DevUIResource> builder,
        IResourceBuilder<TSource> agentService,
        IReadOnlyList<AgentEntityInfo>? agents = null,
        string? entityIdPrefix = null)
        where TSource : IResourceWithEndpoints
    {
        ArgumentNullException.ThrowIfNull(builder);
        ArgumentNullException.ThrowIfNull(agentService);

        // Default to a single agent named after the service resource
        agents ??= [new AgentEntityInfo(agentService.Resource.Name)];

        builder.WithAnnotation(new AgentServiceAnnotation(agentService.Resource, entityIdPrefix, agents));
        builder.WithRelationship(agentService.Resource, "agent-backend");

        return builder;
    }
}
