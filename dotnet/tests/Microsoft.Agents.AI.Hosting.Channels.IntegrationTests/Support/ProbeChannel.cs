// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>
/// Minimal test-only channel used to exercise the channel/host contract directly, independent of any
/// concrete protocol. Contributes a couple of routes that call the host run/stream seam, an endpoint
/// filter that stamps a header, and lifecycle callbacks that flip flags.
/// </summary>
internal sealed class ProbeChannel : Channel
{
    private readonly string _path;

    public ProbeChannel(string path = "/probe")
    {
        this._path = path;
    }

    public override string Name => "probe";

    public override string Path => this._path;

    public bool StartupFired { get; private set; }

    public bool ShutdownFired { get; private set; }

    public override ChannelContribution Contribute(ChannelContext context) => new()
    {
        EndpointFilters = [new HeaderStampFilter()],
        OnStartup = _ => { this.StartupFired = true; return default; },
        OnShutdown = _ => { this.ShutdownFired = true; return default; },
        Routes =
        [
            endpoints =>
            {
                endpoints.MapGet("/ping", () => Results.Text("pong"));

                endpoints.MapPost("/run", async (HttpContext http) =>
                {
                    var input = await new System.IO.StreamReader(http.Request.Body).ReadToEndAsync(http.RequestAborted).ConfigureAwait(false);
                    var request = new ChannelRequest("probe", "message.create", input);
                    var result = await context.RunAsync(request, http.RequestAborted).ConfigureAwait(false);
                    var text = (result.ResultObject as AgentResponse)?.Text ?? result.ResultObject?.ToString();
                    return Results.Text(text ?? string.Empty);
                });

                endpoints.MapPost("/stream", async (HttpContext http) =>
                {
                    var input = await new System.IO.StreamReader(http.Request.Body).ReadToEndAsync(http.RequestAborted).ConfigureAwait(false);
                    var request = new ChannelRequest("probe", "message.create", input) { Stream = true };
                    var updates = 0;
                    var completed = 0;
                    await foreach (var item in context.StreamAsync(request, http.RequestAborted).ConfigureAwait(false))
                    {
                        if (item is HostedStreamUpdate) { updates++; }
                        else if (item is HostedStreamCompleted) { completed++; }
                    }
                    return Results.Text($"updates={updates};completed={completed}");
                });
            },
        ],
    };

    private sealed class HeaderStampFilter : IEndpointFilter
    {
        public async ValueTask<object?> InvokeAsync(EndpointFilterInvocationContext context, EndpointFilterDelegate next)
        {
            context.HttpContext.Response.Headers["x-probe-filter"] = "applied";
            return await next(context).ConfigureAwait(false);
        }
    }
}
