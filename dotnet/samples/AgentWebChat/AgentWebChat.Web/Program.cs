// Copyright (c) Microsoft. All rights reserved.

using AgentWebChat.Web;
using AgentWebChat.Web.Components;
using Microsoft.Extensions.AI.Agents.Runtime;

var builder = WebApplication.CreateBuilder(args);

// Add service defaults & Aspire client integrations.
builder.AddServiceDefaults();

// Add services to the container.
builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents();

builder.Services.AddOutputCache();

// This URL uses "https+http://" to indicate HTTPS is preferred over HTTP.
// Learn more about service discovery scheme resolution at https://aka.ms/dotnet/sdschemes.
Uri baseAddress = new("https+http://agenthost");

// for some reason does not resolve with `apiservice` url
Uri a2aAddress = new("http://localhost:5390/a2a");

builder.Services.AddHttpClient<AgentDiscoveryClient>(client => client.BaseAddress = baseAddress);
builder.Services.AddHttpClient<IActorClient, HttpActorClient>(client => client.BaseAddress = baseAddress);
builder.Services.AddSingleton(sp => new A2AActorClient(sp.GetRequiredService<ILogger<A2AActorClient>>(), a2aAddress));

var app = builder.Build();

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
    // The default HSTS value is 30 days. You may want to change this for production scenarios, see https://aka.ms/aspnetcore-hsts.
    app.UseHsts();
}

app.UseHttpsRedirection();

app.UseAntiforgery();

app.UseOutputCache();

app.MapStaticAssets();

app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

app.MapDefaultEndpoints();

app.Run();
