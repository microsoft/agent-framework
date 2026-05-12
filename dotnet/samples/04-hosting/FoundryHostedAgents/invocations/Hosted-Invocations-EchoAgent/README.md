# Hosted-Invocations-EchoAgent

A minimal echo agent hosted as a Foundry Hosted Agent using the **Invocations protocol**. The agent reads the request body as plain text, passes it through a custom `EchoAIAgent`, and writes the echoed text back in the response. No LLM or Azure credentials are required.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)

## Configuration

Copy the template:

```bash
cp .env.example .env
```

> **Note:** `.env` is gitignored. The `.env.example` template is checked in as a reference.

## Running directly (contributors)

This project uses `ProjectReference` to build against the local Agent Framework source.

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/invocations/Hosted-Invocations-EchoAgent
dotnet run
```

The agent will start on `http://localhost:8088`.

### Test it

```bash
curl -X POST http://localhost:8088/invocations \
  -H "Content-Type: text/plain" \
  -d "Hello, world!"
```

Expected response:

```
Echo: Hello, world!
```

## Running with Docker

Since this project uses `ProjectReference`, the standard `Dockerfile` cannot resolve dependencies outside this folder. Use `Dockerfile.contributor` which takes a pre-published output.

### 1. Publish for the container runtime (Linux Alpine)

```bash
dotnet publish -c Debug -f net10.0 -r linux-musl-x64 --self-contained false -o out
```

### 2. Build the Docker image

```bash
docker build -f Dockerfile.contributor -t hosted-invocations-echo-agent .
```

### 3. Run the container

```bash
docker run --rm -p 8088:8088 hosted-invocations-echo-agent
```

### 4. Test it

```bash
curl -X POST http://localhost:8088/invocations \
  -H "Content-Type: text/plain" \
  -d "Hello from Docker!"
```

## NuGet package users

If you are consuming the Agent Framework as a NuGet package (not building from source), use the standard `Dockerfile` instead of `Dockerfile.contributor`. See the commented section in `Hosted-Invocations-EchoAgent.csproj` for the `PackageReference` alternative.
