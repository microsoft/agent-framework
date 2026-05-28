// Copyright (c) Microsoft. All rights reserved.
using Aspire.Hosting;

var builder = DistributedApplication.CreateBuilder(args);

// ── DTS emulator ─────────────────────────────────────────────────────────────
// Provides a local Durable Task Scheduler compatible with Azure DTS.
// UI available at http://localhost:8082 once started.
var dtsEmulator = builder
    .AddContainer("dts-emulator", "mcr.microsoft.com/dts/dts-emulator", "latest")
    .WithHttpEndpoint(targetPort: 8080, port: 8080, name: "grpc")
    .WithHttpEndpoint(targetPort: 8082, port: 8082, name: "ui");

var schedulerEndpoint = dtsEmulator.GetEndpoint("grpc");

// ── Foundry Local (optional LLM provider) ────────────────────────────────────
// Downloads phi-3.5-mini (~5 GB) on first run.
// Set SQUAD_AF_PROVIDER=azure-openai to skip Foundry Local.
var foundry = builder
    .AddFoundry("foundry")
    .RunAsFoundryLocal();

// ── Demo project ─────────────────────────────────────────────────────────────
var demo = builder
    .AddProject<Projects.Squad_SquadWithDTS>("chat")
    .WithReference(foundry)
    .WithReference(dtsEmulator)
    .WithEnvironment("DTS_ENDPOINT", schedulerEndpoint)
    // OTel: gRPC endpoint for .NET exporters (Aspire dashboard port 21021)
    .WithEnvironment("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:21021")
    // OTel: HTTP/protobuf endpoint for Copilot CLI / Node.js SDK (port 21022)
    .WithEnvironment("OTEL_EXPORTER_OTLP_ENDPOINT_HTTP", "http://localhost:21022")
    // Accept self-signed dev cert in Node.js components
    .WithEnvironment("NODE_TLS_REJECT_UNAUTHORIZED", "0")
    .WithEnvironment("SQUAD_AF_EXAMPLE", "incident");

builder.Build().Run();
