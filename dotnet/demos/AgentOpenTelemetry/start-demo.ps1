# OpenTelemetry Console Demo with Aspire Dashboard (Docker)
# This script starts the Aspire Dashboard via Docker and the Console Application

param(
    [switch]$SkipBuild,
    [switch]$Help
)

if ($Help) {
    Write-Host "OpenTelemetry Console Demo with Aspire Dashboard" -ForegroundColor Green
    Write-Host ""
    Write-Host "Usage: .\start-demo.ps1 [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -SkipBuild    Skip building the console application"
    Write-Host "  -Help         Show this help message"
    Write-Host ""
    Write-Host "Prerequisites:"
    Write-Host "  - Docker installed and running"
    Write-Host "  - Set OPENAI_API_KEY or AZURE_OPENAI_ENDPOINT environment variable"
    Write-Host "  - .NET 9.0 SDK installed"
    Write-Host ""
    exit 0
}

Write-Host "🚀 Starting OpenTelemetry Console Demo..." -ForegroundColor Green
Write-Host ""

# Check if we're in the right directory
if (!(Test-Path "AgentOpenTelemetry.csproj")) {
    Write-Host "❌ Error: Please run this script from the AgentOpenTelemetry directory" -ForegroundColor Red
    Write-Host "Expected to find AgentOpenTelemetry.csproj file" -ForegroundColor Red
    exit 1
}

# Check if Docker is running
try {
    docker version | Out-Null
    Write-Host "✅ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker is not running or not installed" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again" -ForegroundColor Red
    exit 1
}

# Check for API keys
$hasOpenAI = $env:OPENAI_API_KEY -ne $null -and $env:OPENAI_API_KEY -ne ""
$hasAzureOpenAI = $env:AZURE_OPENAI_ENDPOINT -ne $null -and $env:AZURE_OPENAI_ENDPOINT -ne ""

if (!$hasOpenAI -and !$hasAzureOpenAI) {
    Write-Host "⚠️  Warning: No API keys found!" -ForegroundColor Yellow
    Write-Host "Please set one of the following environment variables:" -ForegroundColor Yellow
    Write-Host "  - OPENAI_API_KEY (for OpenAI)" -ForegroundColor Yellow
    Write-Host "  - AZURE_OPENAI_ENDPOINT (for Azure OpenAI)" -ForegroundColor Yellow
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/N)"
    if ($continue -ne "y" -and $continue -ne "Y") {
        exit 1
    }
}

if ($hasOpenAI) {
    Write-Host "✅ Found OpenAI API key" -ForegroundColor Green
}
if ($hasAzureOpenAI) {
    Write-Host "✅ Found Azure OpenAI endpoint" -ForegroundColor Green
    if ($env:AZURE_OPENAI_DEPLOYMENT_NAME) {
        Write-Host "✅ Using deployment: $($env:AZURE_OPENAI_DEPLOYMENT_NAME)" -ForegroundColor Green
    } else {
        Write-Host "ℹ️  Using default deployment: gpt-4o-mini" -ForegroundColor Cyan
    }
}

# Build console app if not skipped
if (!$SkipBuild) {
    Write-Host ""
    Write-Host "🔨 Building console application..." -ForegroundColor Cyan

    $buildResult = dotnet build --verbosity quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to build Console App" -ForegroundColor Red
        exit 1
    }

    Write-Host "✅ Build completed successfully" -ForegroundColor Green
}

Write-Host ""
Write-Host "🐳 Starting Aspire Dashboard via Docker..." -ForegroundColor Cyan

# Stop any existing Aspire Dashboard container
Write-Host "🧹 Stopping any existing Aspire Dashboard container..." -ForegroundColor Gray
docker stop aspire-dashboard 2>$null | Out-Null
docker rm aspire-dashboard 2>$null | Out-Null

# Start Aspire Dashboard in Docker daemon mode with fixed token
Write-Host "🚀 Starting Aspire Dashboard container..." -ForegroundColor Green
$fixedToken = "demo-token-12345"
$dockerResult = docker run -d `
    --name aspire-dashboard `
    -p 4318:18888 `
    -p 4317:18889 `
    -e DOTNET_DASHBOARD_UNSECURED_ALLOW_ANONYMOUS=true `
    --restart unless-stopped `
    mcr.microsoft.com/dotnet/aspire-dashboard:9.0

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to start Aspire Dashboard container" -ForegroundColor Red
    Write-Host "Make sure Docker is running and try again" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Aspire Dashboard started successfully!" -ForegroundColor Green
Write-Host "📊 OTLP Endpoint: http://localhost:4318" -ForegroundColor Cyan

# Wait for dashboard to be ready by polling the port
Write-Host "⏳ Waiting for dashboard to be ready..." -ForegroundColor Gray
$maxWaitSeconds = 10
$waitCount = 0
$dashboardReady = $false

while ($waitCount -lt $maxWaitSeconds -and !$dashboardReady) {
    try {
        $tcpConnection = Test-NetConnection -ComputerName "localhost" -Port 4317 -InformationLevel Quiet -WarningAction SilentlyContinue -ErrorAction SilentlyContinue
        if ($tcpConnection) {
            $dashboardReady = $true
            Write-Host "✅ Dashboard is ready! (took $waitCount seconds)" -ForegroundColor Green
        } else {
            Write-Host "." -NoNewline -ForegroundColor Gray
            Start-Sleep -Seconds 1
            $waitCount++
        }
    } catch {
        Write-Host "." -NoNewline -ForegroundColor Gray
        Start-Sleep -Seconds 1
        $waitCount++
    }
}

if (!$dashboardReady) {
    Write-Host ""
    Write-Host "⚠️  Dashboard port 4317 not responding after $maxWaitSeconds seconds" -ForegroundColor Yellow
    Write-Host "   Continuing anyway - dashboard might still be starting..." -ForegroundColor Yellow
} else {
    Write-Host ""
}

# Open the dashboard in browser (anonymous access enabled)
Write-Host "🚀 Opening dashboard in browser..." -ForegroundColor Green
Write-Host "🌐 Dashboard URL: http://localhost:4318" -ForegroundColor Cyan
Start-Process "http://localhost:4318"

Write-Host ""
Write-Host "💬 Starting Console Application..." -ForegroundColor Cyan
Write-Host "You can now interact with the AI agent!" -ForegroundColor Green
Write-Host ""

# Set the OTLP endpoint for the console application (Docker Aspire Dashboard)
$otlpEndpoint = "http://localhost:4317"
Write-Host "📊 Using OTLP endpoint: $otlpEndpoint" -ForegroundColor Cyan

$env:OTEL_EXPORTER_OTLP_ENDPOINT = $otlpEndpoint

# Start the console application in the current window
Write-Host ""
Write-Host "🎯 Starting the console application..." -ForegroundColor Green
Write-Host "💡 Tip: The dashboard should now be open in your browser!" -ForegroundColor Cyan
Write-Host ""

dotnet run

Write-Host ""
Write-Host "👋 Demo completed!" -ForegroundColor Green
Write-Host "🐳 The Aspire Dashboard is still running in Docker." -ForegroundColor Gray
Write-Host "💻 You can view telemetry data in the browser tab that opened." -ForegroundColor Gray
Write-Host "🛑 To stop the dashboard: docker stop aspire-dashboard" -ForegroundColor Gray
