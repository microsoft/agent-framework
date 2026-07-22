// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal interface IStatefulEdgeRunner
{
    ValueTask<PortableValue> ExportStateAsync();
    ValueTask ImportStateAsync(PortableValue state);
}

internal abstract class EdgeRunner
{
    protected internal abstract ValueTask<DeliveryMapping?> ChaseEdgeAsync(MessageEnvelope envelope, IStepTracer? stepTracer, CancellationToken cancellationToken = default);
}

internal abstract class EdgeRunner<TEdgeData>(
    IRunnerContext runContext, TEdgeData edgeData) : EdgeRunner()
{
    protected IRunnerContext RunContext { get; } = Throw.IfNull(runContext);
    protected TEdgeData EdgeData { get; } = Throw.IfNull(edgeData);

    protected async ValueTask<ExecutorProtocol> FindSourceProtocolAsync(string sourceId, IStepTracer? stepTracer, CancellationToken cancellationToken = default)
    {
        Executor sourceExecutor = await this.RunContext.EnsureExecutorAsync(Throw.IfNull(sourceId), stepTracer, cancellationToken)
                                                       .ConfigureAwait(false);

        return sourceExecutor.Protocol;
    }

    protected async ValueTask<Type?> GetMessageRuntimeTypeAsync(MessageEnvelope envelope, IStepTracer? stepTracer, CancellationToken cancellationToken = default)
    {
        // The only difficulty occurs when we have gone through a checkpoint cycle, because the messages turn into PortableValue objects.
        if (envelope.Message is PortableValue portableValue)
        {
            if (envelope.SourceId == null)
            {
                return null;
            }

            ExecutorProtocol protocol = await this.FindSourceProtocolAsync(envelope.SourceId, stepTracer, cancellationToken).ConfigureAwait(false);
            return protocol.SendTypeTranslator.MapTypeId(portableValue.TypeId);
        }

        return envelope.Message.GetType();
    }

    protected static bool CanHandle(Executor target, Type? runtimeType)
    {
        // If we have a runtimeType, this is either a non-serialized object, or we successfully mapped a PortableValue back to its original type.
        // In either case, we can check if the target can handle that type. Alternatively, even if we do not have a type, if the target has a catch-all,
        // we can still route to it, since it should be able to handle anything.
        return runtimeType != null ? target.CanHandle(runtimeType) : target.Router.HasCatchAll;
    }

    protected async ValueTask<bool> CanHandleAsync(string candidateTargetId, Type? runtimeType, IStepTracer? stepTracer, CancellationToken cancellationToken = default)
    {
        Executor candidateTarget = await this.RunContext.EnsureExecutorAsync(Throw.IfNull(candidateTargetId), stepTracer, cancellationToken)
                                                        .ConfigureAwait(false);

        return CanHandle(candidateTarget, runtimeType);
    }

    protected Activity? StartActivity() => this.RunContext.TelemetryContext.StartEdgeGroupProcessActivity();
}
