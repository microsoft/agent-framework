// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Microsoft.Extensions.AI;

#pragma warning disable OPENAI001, MEAI001, MAAI001, SCME0001

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Shared helpers and fake clients used by the served-model test suite
/// (<see cref="ServedModelScopeTests"/>, <see cref="ServedModelPolicyTests"/>).
/// </summary>
internal static class ServedModelTestHelpers
{
    public static string MinimalResponseJson() => """
        {
          "id":"resp_1","object":"response","created_at":1700000000,"status":"completed",
          "model":"fake","output":[],"usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}
        }
        """;

    /// <summary>
    /// Creates a <see cref="FoundryChatClient"/> backed by a real OpenAI Responses pipeline
    /// routed through the supplied <paramref name="handler"/>. The <see cref="ServedModelPolicy"/>
    /// is registered automatically by the <see cref="FoundryChatClient"/> constructor.
    /// </summary>
    public static IChatClient CreateChatClientWithPolicy(HttpMessageHandler handler)
    {
#pragma warning disable CA5399
        var http = new HttpClient(handler);
#pragma warning restore CA5399

        var projectClient = new AIProjectClient(
            new Uri("https://test.openai.azure.com/"),
            new FakeAuthenticationTokenProvider(),
            new AIProjectClientOptions { Transport = new HttpClientPipelineTransport(http) });

        return new FoundryChatClient(projectClient, "fake");
    }

    /// <summary>
    /// An <see cref="HttpClientHandler"/> that returns a fixed response body and optionally
    /// includes the <c>x-ms-served-model</c> response header.
    /// </summary>
    public sealed class ServedModelHandler : HttpClientHandler
    {
        private readonly string _body;
        private readonly string? _servedModel;

        public ServedModelHandler(string body, string? servedModel)
        {
            this._body = body;
            this._servedModel = servedModel;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var resp = new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(this._body, Encoding.UTF8, "application/json"),
                RequestMessage = request,
            };

            if (this._servedModel is not null)
            {
                resp.Headers.Add("x-ms-served-model", this._servedModel);
            }

            return Task.FromResult(resp);
        }
    }
}
