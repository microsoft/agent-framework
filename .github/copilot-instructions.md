# Microsoft Agent Framework - GitHub Copilot Instructions

Always reference these instructions first and only fall back to search or bash commands when you encounter unexpected information that does not match the information provided here.

## Working Effectively with Microsoft Agent Framework

Microsoft Agent Framework is a comprehensive multi-language framework for building, orchestrating, and deploying AI agents with support for both .NET and Python implementations. This framework includes agents, multi-agent orchestration, graph-based workflows, and various AI provider integrations.

### Quick Repository Setup

**CRITICAL**: Always install required dependencies and perform setup steps before making changes.

#### Install uv package manager (Required for Python development)
```bash
pip3 install uv
export PATH="$HOME/.local/bin:$PATH"
```

#### Python Development Setup - NEVER CANCEL: Setup takes 1-2 minutes
```bash
cd python
# Create virtual environment - takes ~1 second
uv venv --clear --python 3.12
# Install dependencies - takes ~30 seconds, NEVER CANCEL 
uv sync --dev --no-group=docs
```

#### .NET Development Setup - REQUIRES .NET 9.0.300+
**CRITICAL**: This repository requires .NET 9.0.300 or later. Standard GitHub runners have .NET 8.0 which will NOT work.
- The repository uses .slnx solution format which requires .NET 9+
- All projects target net9.0 framework
- Use `dotnet --version` to check your version
- If .NET version is insufficient, document this limitation clearly

### Build and Test Operations - NEVER CANCEL LONG-RUNNING COMMANDS

#### Python Build and Test - NEVER CANCEL: Full cycle takes 3-4 minutes
```bash
cd python
export PATH="$HOME/.local/bin:$PATH"

# Build all packages - takes ~5 seconds, NEVER CANCEL
uv run poe build

# Run all tests - takes ~50 seconds, NEVER CANCEL, set timeout to 120+ seconds
uv run poe test

# Run formatting - takes ~1 second
uv run poe format

# Run linting - takes ~1 second  
uv run poe lint

# Run comprehensive checks (format, lint, pyright, mypy, test, markdown lint, samples check)
# NEVER CANCEL: Takes 3+ minutes, set timeout to 300+ seconds
uv run poe check
```

#### .NET Build and Test - REQUIRES .NET 9.0.300+
```bash
cd dotnet
# Build main solution - NEVER CANCEL: May take 5-10 minutes, set timeout to 600+ seconds
dotnet build agent-framework-dotnet.slnx -c Release --warnaserror

# Run unit tests - NEVER CANCEL: May take 5-15 minutes, set timeout to 900+ seconds  
find . -name "*.UnitTests.csproj" -exec dotnet test {} -c Release --no-build \;

# Format code
dotnet format
```

**CRITICAL .NET LIMITATION**: If .NET 9.0.300+ is not available, document this clearly:
- "Do not attempt to build .NET projects - requires .NET 9.0.300+ which may not be available in all environments"
- "All .NET samples and projects target net9.0 and use .slnx format requiring .NET 9+"

### Validation Scenarios - Always Test These After Changes

#### Python Validation
Always run these validation steps after making Python changes:
```bash
cd python
export PATH="$HOME/.local/bin:$PATH"

# 1. Format and lint check
uv run poe format && uv run poe lint

# 2. Type checking - NEVER CANCEL: Takes 1-2 minutes
uv run poe pyright

# 3. Run tests - NEVER CANCEL: Takes ~50 seconds, set timeout to 120+ seconds
uv run poe test

# 4. Build packages
uv run poe build

# 5. Comprehensive validation - NEVER CANCEL: Takes 3+ minutes, set timeout to 300+ seconds
uv run poe check
```

#### .NET Validation (if .NET 9.0.300+ available)
```bash
cd dotnet
# Format code
dotnet format

# Build solution - NEVER CANCEL: Set timeout to 600+ seconds
dotnet build agent-framework-dotnet.slnx -c Release --warnaserror

# Run unit tests - NEVER CANCEL: Set timeout to 900+ seconds
find . -name "*.UnitTests.csproj" -exec dotnet test {} -c Release --no-build \;
```

### Key Project Structure

#### Python Projects (`python/packages/`)
- `main/` - Core agent framework package 
- `azure/` - Azure AI integrations
- `copilotstudio/` - Copilot Studio integration
- `foundry/` - Azure AI Foundry integration  
- `mem0/` - Memory integration
- `runtime/` - Runtime components
- `lab/gaia/` - GAIA benchmark integration
- `lab/lightning/` - Lightning AI integration

#### .NET Projects (`dotnet/src/`)
- `Microsoft.Extensions.AI.Agents/` - Core agents
- `Microsoft.Extensions.AI.Agents.Abstractions/` - Abstractions
- `Microsoft.Extensions.AI.Agents.OpenAI/` - OpenAI integration
- `Microsoft.Extensions.AI.Agents.AzureAI/` - Azure AI integration
- `Microsoft.Extensions.AI.Agents.CopilotStudio/` - Copilot Studio integration
- `Microsoft.Agents.Workflows/` - Workflow engine
- `Microsoft.Agents.Orchestration/` - Multi-agent orchestration

### Sample Applications

#### Python Samples (`python/samples/getting_started/`)
- `minimal_sample.py` - Basic agent example
- `agents/` - Agent creation samples
- `chat_client/` - Direct chat client usage
- `workflow/` - Workflow orchestration samples
- `multimodal_input/` - Image and multimodal processing

#### .NET Samples (`dotnet/samples/GettingStarted/`)
- `Agents/` - Agent creation and usage samples
- `AgentProviders/` - Different AI provider integrations  
- `AgentOrchestration/` - Multi-agent patterns
- `Workflows/` - Workflow orchestration samples

### Environment Variables and Configuration

Most samples require API keys. Common environment variables:
```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL_ID=gpt-4o-mini

# Azure OpenAI  
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://...
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=...

# Azure AI Foundry
FOUNDRY_PROJECT_ENDPOINT=...
FOUNDRY_MODEL_DEPLOYMENT_NAME=...
```

### Common Issues and Workarounds

#### Python Issues
- **Pre-commit hook failures**: Network restrictions may cause pre-commit install to fail. This is expected in restricted environments.
- **Package installation timeouts**: Use `uv sync --dev --no-group=docs` to skip documentation dependencies
- **Build warnings**: License classifier deprecation warnings in lab packages are expected

#### .NET Issues  
- **"Element <Solution> is unrecognized"**: Indicates .NET version < 9.0.300. Document this limitation.
- **Build failures on older .NET**: All projects require .NET 9+. Do not attempt workarounds.
- **Missing global.json**: Project requires .NET SDK 9.0.300 as specified in `dotnet/global.json`

### Timing Expectations - NEVER CANCEL THESE OPERATIONS

| Operation | Python Time | .NET Time | Timeout Setting |
|-----------|-------------|-----------|-----------------|
| Dependency Install | 30 seconds | N/A | 120 seconds |
| Build | 5 seconds | 5-10 minutes | 600 seconds |
| Unit Tests | 50 seconds | 5-15 minutes | 900 seconds |
| Full Check | 3+ minutes | 10-20 minutes | 1200 seconds |
| Format/Lint | 1-2 seconds | 1-2 minutes | 120 seconds |

**CRITICAL**: Always set appropriate timeouts for long-running operations. GitHub Actions show these operations can take significant time in CI environments.

### When Making Changes

1. **Always run setup steps first** - Install uv, create venv, sync dependencies
2. **Test incrementally** - Run format/lint after each change
3. **Validate thoroughly** - Run full test suite before committing  
4. **Check both languages** - If change affects both Python and .NET
5. **Document limitations** - If .NET 9+ not available, document clearly
6. **Never cancel builds** - Let all operations complete, they may take time

### Environment Validation

To verify your development environment is properly set up, run these quick validation tests:

#### Python Environment Check
```bash
cd python
export PATH="$HOME/.local/bin:$PATH"
uv --version                    # Should show uv 0.8.18+
uv run python --version        # Should show Python 3.12+
uv run poe format && echo "✅ Environment validated"
```

#### Test Framework Functionality
```bash
cd python
# Run a simple workflow sample to verify framework works
uv run python samples/getting_started/workflow/_start-here/step1_executors_and_edges.py
# Should output: WorkflowCompletedEvent(origin=..., data=DLROW OLLEH)
```

### Additional Resources

- Main README: `/README.md`
- Python setup guide: `/python/DEV_SETUP.md`  
- .NET setup guide: `/dotnet/README.md`
- Contributing guidelines: `/CONTRIBUTING.md`
- Sample workflows: `/workflows/README.md`