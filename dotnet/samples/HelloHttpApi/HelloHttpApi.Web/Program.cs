// Copyright (c) Microsoft. All rights reserved.

using A2A;
using HelloHttpApi.Web;
using HelloHttpApi.Web.Components;

var builder = WebApplication.CreateBuilder(args);

// Add service defaults & Aspire client integrations.
builder.AddServiceDefaults();

// Add services to the container.
builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents();

builder.Services.AddOutputCache();

// This URL uses "https+http://" to indicate HTTPS is preferred over HTTP.
// Learn more about service discovery scheme resolution at https://aka.ms/dotnet/sdschemes.
Uri baseAddress = new("https+http://apiservice");
Uri a2aPirateUrl = new("http://localhost:5390/a2a");

builder.Services.AddHttpClient<AgentClient>(client =>
{
    client.BaseAddress = baseAddress;
});

builder.Services.AddSingleton<A2ACardResolver>(sp =>
{
    return new A2ACardResolver(a2aPirateUrl);
});
builder.Services.AddSingleton<A2AClient>(sp =>
{
    return new A2AClient(a2aPirateUrl);
});

var app = builder.Build();

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
    // The default HSTS value is 30 days. You may want to change this for production scenarios, see https://aka.ms/aspnetcore-hsts.
    app.UseHsts();
}

app.UseHttpsRedirection();

app.UseStaticFiles();
app.UseAntiforgery();

app.UseOutputCache();

app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

app.MapDefaultEndpoints();

app.Run();
