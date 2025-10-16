using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;

using Azure.AI.AgentsHosting.Ingress.Invocation.Stream;
// TODO: Add telemetry support
// using Azure.AI.AgentsHosting.Ingress.Telemetry;

using AzureAIAgents.Models;

namespace Azure.AI.AgentsHosting.Ingress.Invocation;

/// <summary>
/// Base class for agent invocation implementations.
/// </summary>
public abstract class AgentInvocationBase : IAgentInvocation
{
    /// <summary>
    /// When overridden in a derived class, performs the actual agent invocation.
    /// </summary>
    /// <param name="createResponse">The create response request.</param>
    /// <param name="context">The agent invocation context.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>A task representing the response.</returns>
    protected abstract Task<AzureAIAgents.Models.Response> DoInvokeAsync(CreateResponse createResponse,
        AgentInvocationContext context,
        CancellationToken cancellationToken);

    /// <summary>
    /// When overridden in a derived class, performs the actual streaming agent invocation.
    /// </summary>
    /// <param name="createResponse">The create response request.</param>
    /// <param name="context">The agent invocation context.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>A nested stream event generator.</returns>
    protected abstract INestedStreamEventGenerator<AzureAIAgents.Models.Response> DoInvokeStream(CreateResponse createResponse,
        AgentInvocationContext context,
        CancellationToken cancellationToken);

    /// <inheritdoc/>
    public async Task<AzureAIAgents.Models.Response> InvokeAsync(CreateResponse createResponse,
        AgentInvocationContext context,
        CancellationToken cancellationToken = default)
    {
        try
        {
            return await this.DoInvokeAsync(createResponse, context, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception e)
        {
            Activity.Current?.AddException(e);

            if (e is AgentInvocationException aie)
            {
                // TODO: Add telemetry support
                // Activity.Current?.SetResponsesTag("error.code", aie.Error.Code)
                //     .SetResponsesTag("error.message", aie.Error.Message);
                throw;
            }

            throw new AgentInvocationException(AzureAIAgentsModelFactory.ResponseError(message: e.Message));
        }
    }

    /// <inheritdoc/>
    public async IAsyncEnumerable<ResponseStreamEvent> InvokeStreamAsync(CreateResponse createResponse,
        AgentInvocationContext context,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var generator = this.DoInvokeStream(createResponse, context, cancellationToken);
        await foreach (var group in generator.GenerateAsync().WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            await foreach (var e in group.Events.WithCancellation(cancellationToken).ConfigureAwait(false))
            {
                yield return e;
            }
        }
    }
}
