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

public abstract class AgentInvocationBase : IAgentInvocation
{
    protected abstract Task<AzureAIAgents.Models.Response> DoInvokeAsync(CreateResponse createResponse,
        AgentInvocationContext context,
        CancellationToken cancellationToken);

    protected abstract INestedStreamEventGenerator<AzureAIAgents.Models.Response> DoInvokeStreamAsync(CreateResponse createResponse,
        AgentInvocationContext context,
        CancellationToken cancellationToken);

    public async Task<AzureAIAgents.Models.Response> InvokeAsync(CreateResponse createResponse,
        AgentInvocationContext context,
        CancellationToken cancellationToken = default)
    {
        try
        {
            return await DoInvokeAsync(createResponse, context, cancellationToken).ConfigureAwait(false);
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

    public async IAsyncEnumerable<ResponseStreamEvent> InvokeStreamAsync(CreateResponse createResponse,
        AgentInvocationContext context,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var generator = DoInvokeStreamAsync(createResponse, context, cancellationToken);
        await foreach (var group in generator.Generate().WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            await foreach (var e in group.Events.WithCancellation(cancellationToken).ConfigureAwait(false))
            {
                yield return e;
            }
        }
    }
}
