// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Threading.Tasks;
using OpenAI;
using OpenAI.Responses;

#pragma warning disable OPENAI001, SCME0001

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// A <see cref="ResponsesClient"/> subclass that delegates every protocol-level request to a
/// wrapped <see cref="ResponsesClient"/>. Before each call, a
/// <see cref="HostedAgentUserAgentPolicy"/> is added to the per-call
/// <see cref="RequestOptions"/> so the wrapped client's pipeline appends the hosted-agent
/// <c>User-Agent</c> segment on the wire.
/// </summary>
/// <remarks>
/// <para>
/// The streaming overloads MEAI binds via reflection (<c>internal CreateResponseStreamingAsync(CreateResponseOptions, RequestOptions)</c>
/// and <c>internal GetResponseStreamingAsync(GetResponseOptions, RequestOptions)</c>) bottom out
/// in calls to the public-virtual non-streaming protocol overloads on <see langword="this"/>. Overriding those
/// non-streaming overloads is therefore sufficient to intercept both streaming and non-streaming traffic.
/// </para>
/// <para>
/// The base pipeline supplied to <see cref="ResponsesClient(ClientPipeline, OpenAIClientOptions)"/>
/// is a dummy pipeline whose terminal transport throws if invoked. Every override on this class
/// delegates to the inner client BEFORE any code path reaches <see cref="ResponsesClient.Pipeline"/>, so the dummy is
/// never expected to run; the throwing transport surfaces any unexpected escape route loudly.
/// </para>
/// </remarks>
internal sealed class DelegatingResponsesClient : ResponsesClient
{
    private readonly ResponsesClient _inner;

    public DelegatingResponsesClient(ResponsesClient inner)
        : base(BuildDummyPipeline(), new OpenAIClientOptions { Endpoint = inner?.Endpoint })
    {
        this._inner = inner ?? throw new ArgumentNullException(nameof(inner));
    }

    public override async Task<ClientResult> CreateResponseAsync(BinaryContent content, RequestOptions? options = null)
        => await this._inner.CreateResponseAsync(content, AddUserAgentPolicy(options)).ConfigureAwait(false);

    public override ClientResult CreateResponse(BinaryContent content, RequestOptions? options = null)
        => this._inner.CreateResponse(content, AddUserAgentPolicy(options));

    public override async Task<ClientResult> GetResponseAsync(string responseId, IEnumerable<IncludedResponseProperty>? include, bool? stream, int? startingAfter, bool? includeObfuscation, RequestOptions options)
        => await this._inner.GetResponseAsync(responseId, include, stream, startingAfter, includeObfuscation, AddUserAgentPolicy(options)).ConfigureAwait(false);

    public override ClientResult GetResponse(string responseId, IEnumerable<IncludedResponseProperty>? include, bool? stream, int? startingAfter, bool? includeObfuscation, RequestOptions options)
        => this._inner.GetResponse(responseId, include, stream, startingAfter, includeObfuscation, AddUserAgentPolicy(options));

    public override async Task<ClientResult> DeleteResponseAsync(string responseId, RequestOptions options)
        => await this._inner.DeleteResponseAsync(responseId, AddUserAgentPolicy(options)).ConfigureAwait(false);

    public override ClientResult DeleteResponse(string responseId, RequestOptions options)
        => this._inner.DeleteResponse(responseId, AddUserAgentPolicy(options));

    public override async Task<ClientResult> CancelResponseAsync(string responseId, RequestOptions options)
        => await this._inner.CancelResponseAsync(responseId, AddUserAgentPolicy(options)).ConfigureAwait(false);

    public override ClientResult CancelResponse(string responseId, RequestOptions options)
        => this._inner.CancelResponse(responseId, AddUserAgentPolicy(options));

    public override async Task<ClientResult> GetInputTokenCountAsync(string contentType, BinaryContent content, RequestOptions? options = null)
        => await this._inner.GetInputTokenCountAsync(contentType, content, AddUserAgentPolicy(options)).ConfigureAwait(false);

    public override ClientResult GetInputTokenCount(string contentType, BinaryContent content, RequestOptions? options = null)
        => this._inner.GetInputTokenCount(contentType, content, AddUserAgentPolicy(options));

    public override async Task<ClientResult> CompactResponseAsync(string contentType, BinaryContent content, RequestOptions? options = null)
        => await this._inner.CompactResponseAsync(contentType, content, AddUserAgentPolicy(options)).ConfigureAwait(false);

    public override ClientResult CompactResponse(string contentType, BinaryContent content, RequestOptions? options = null)
        => this._inner.CompactResponse(contentType, content, AddUserAgentPolicy(options));

    public override async Task<ClientResult> GetResponseInputItemCollectionPageAsync(string responseId, int? limit, string order, string after, string before, RequestOptions options)
        => await this._inner.GetResponseInputItemCollectionPageAsync(responseId, limit, order, after, before, AddUserAgentPolicy(options)).ConfigureAwait(false);

    public override ClientResult GetResponseInputItemCollectionPage(string responseId, int? limit, string order, string after, string before, RequestOptions options)
        => this._inner.GetResponseInputItemCollectionPage(responseId, limit, order, after, before, AddUserAgentPolicy(options));

    private static RequestOptions AddUserAgentPolicy(RequestOptions? options)
    {
        options ??= new RequestOptions();
        options.AddPolicy(HostedAgentUserAgentPolicy.Instance, PipelinePosition.PerCall);
        return options;
    }

    private static ClientPipeline BuildDummyPipeline()
    {
        var options = new ClientPipelineOptions
        {
            Transport = new ThrowingTransport(),
        };
        return ClientPipeline.Create(options, default, default, default);
    }

    private sealed class ThrowingTransport : PipelineTransport
    {
        private const string Message =
            "DelegatingResponsesClient transport invoked bypassed the override-and-delegate design. This exception should be unreachable and should never be thrown following the correct usage of DelegatingResponsesClient.";

        protected override PipelineMessage CreateMessageCore() => throw new InvalidOperationException(Message);
        protected override void ProcessCore(PipelineMessage message) => throw new InvalidOperationException(Message);
        protected override ValueTask ProcessCoreAsync(PipelineMessage message) => throw new InvalidOperationException(Message);
    }
}
