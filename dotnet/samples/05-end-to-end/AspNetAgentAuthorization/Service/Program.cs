// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to authorize AI agent tools using OAuth 2.0
// scopes. The /chat endpoint requires the "agent.chat" scope, and each tool
// checks its own scope (expenses.view, expenses.approve) at runtime.

using System.Security.Claims;
using System.Text.Json.Serialization;
using AspNetAgentAuthorization.Service;
using Microsoft.Agents.AI;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Authorization;
using Microsoft.Extensions.AI;
using OpenAI;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);

// ---------------------------------------------------------------------------
// Authentication: JWT Bearer tokens validated against the OIDC provider
// ---------------------------------------------------------------------------
builder.Services
    .AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.Authority = builder.Configuration["Auth:Authority"]
            ?? throw new InvalidOperationException("Auth:Authority is not configured.");
        options.Audience = builder.Configuration["Auth:Audience"]
            ?? throw new InvalidOperationException("Auth:Audience is not configured.");

        // For local development with HTTP-only Keycloak
        options.RequireHttpsMetadata = !builder.Environment.IsDevelopment();

        options.TokenValidationParameters.ValidateAudience = true;
        options.TokenValidationParameters.ValidateLifetime = true;

        // In Codespaces, tokens are issued with the public tunnel URL as
        // issuer (Keycloak sees X-Forwarded-Host from the tunnel) but the
        // agent-service discovers Keycloak via the internal Docker hostname.
        // Disable issuer validation in development to handle this mismatch.
        options.TokenValidationParameters.ValidateIssuer = !builder.Environment.IsDevelopment();
    });

// ---------------------------------------------------------------------------
// Authorization: policy requiring the "agent.chat" scope
// ---------------------------------------------------------------------------
builder.Services.AddAuthorizationBuilder()
    .AddPolicy("AgentChat", policy =>
        policy.RequireAuthenticatedUser()
              .RequireAssertion(context =>
              {
                  // Keycloak puts scopes in the "scope" claim (space-delimited)
                  var scopeClaim = context.User.FindFirstValue("scope");
                  if (scopeClaim is not null)
                  {
                      var scopes = scopeClaim.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                      if (scopes.Contains("agent.chat", StringComparer.OrdinalIgnoreCase))
                      {
                          return true;
                      }
                  }

                  return false;
              }));

// ---------------------------------------------------------------------------
// Configure JSON serialization
// ---------------------------------------------------------------------------
builder.Services.ConfigureHttpJsonOptions(options =>
    options.SerializerOptions.TypeInfoResolverChain.Add(SampleServiceSerializerContext.Default));

// ---------------------------------------------------------------------------
// Create the AI agent with expense approval tools, registered in DI
// ---------------------------------------------------------------------------
string apiKey = builder.Configuration["OPENAI_API_KEY"]
    ?? throw new InvalidOperationException("Set the OPENAI_API_KEY environment variable.");
string model = builder.Configuration["OPENAI_MODEL"] ?? "gpt-4.1-mini";

builder.Services.AddHttpContextAccessor();
builder.Services.AddScoped<IUserContext, KeycloakUserContext>();
builder.Services.AddScoped<ExpenseService>();
builder.Services.AddScoped<AIAgent>(sp =>
{
    var expenseService = sp.GetRequiredService<ExpenseService>();

    return new OpenAIClient(apiKey)
        .GetChatClient(model)
        .AsIChatClient()
        .AsAIAgent(
            name: "ExpenseApprovalAgent",
            instructions: "You are an expense approval assistant. You can list pending expenses "
                        + "and approve them if the user has the required permissions and approval limit. "
                        + "Keep responses concise.",
            tools:
            [
                AIFunctionFactory.Create(expenseService.ListPendingExpenses),
                AIFunctionFactory.Create(expenseService.ApproveExpense),
            ]);
});

WebApplication app = builder.Build();

app.UseAuthentication();
app.UseAuthorization();

// ---------------------------------------------------------------------------
// POST /chat — requires the "agent.chat" scope
// ---------------------------------------------------------------------------
app.MapPost("/chat", [Authorize(Policy = "AgentChat")] async (ChatRequest request, IUserContext userContext, AIAgent agent) =>
{
    var response = await agent.RunAsync(request.Message);

    return Results.Ok(new ChatResponse(response.Text, userContext.DisplayName));
});

await app.RunAsync();

// ---------------------------------------------------------------------------
// Request / Response models
// ---------------------------------------------------------------------------
internal sealed record ChatRequest(string Message);
internal sealed record ChatResponse(string Reply, string User);

[JsonSerializable(typeof(ChatRequest))]
[JsonSerializable(typeof(ChatResponse))]
internal sealed partial class SampleServiceSerializerContext : JsonSerializerContext;
