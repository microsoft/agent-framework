# Microsoft Agent Framework - Copilot Instructions

## Repository Overview

This is the **Microsoft Agent Framework** repository, a comprehensive multi-language framework for building, orchestrating, and deploying AI agents. The framework supports both **Python** and **.NET (C#)** implementations with consistent APIs and feature parity across both languages.

## Repository Structure

```
agent-framework/
├── dotnet/              # C#/.NET implementation
├── python/              # Python implementation
├── docs/                # Shared documentation
├── workflow-samples/    # Workflow examples
├── .github/             # GitHub workflows and configuration
├── README.md            # Main repository documentation
├── CONTRIBUTING.md      # Contribution guidelines
└── SECURITY.md          # Security policy
```

## Language-Specific Directories

- **`dotnet/`**: Contains all C#/.NET code, including source, samples, tests, and .NET-specific documentation
- **`python/`**: Contains all Python code, including packages, samples, tests, and Python-specific documentation

## Key Features

1. **Graph-based Workflows**: Connect agents and deterministic functions using data flows with streaming, checkpointing, human-in-the-loop, and time-travel capabilities
2. **Multi-Agent Orchestration**: Coordinate multiple agents to collaborate on complex tasks
3. **Multiple LLM Provider Support**: Azure OpenAI, OpenAI, Azure AI, Copilot Studio, and more
4. **Built-in Observability**: OpenTelemetry integration for distributed tracing and monitoring
5. **Middleware System**: Flexible middleware for request/response processing and custom pipelines
6. **Developer UI (DevUI)**: Interactive developer UI for agent development, testing, and debugging (Python)

## General Development Conventions

### Documentation

- **Main README**: Repository-wide overview and quick start guides for both languages
- **Language-specific READMEs**: Found in `python/README.md` and `dotnet/README.md`
- **Design Docs**: Located in `docs/design/` for technical design specifications
- **ADRs (Architectural Decision Records)**: Found in `docs/decisions/` documenting important architectural decisions
- **Specs**: Technical specifications in `docs/specs/`

### Contribution Guidelines

- Follow the guidelines in `CONTRIBUTING.md`
- Adhere to language-specific coding standards (see language-specific instruction files)
- All public APIs should be well-documented
- Include tests for new features and bug fixes
- Ensure cross-platform compatibility (Windows, macOS, Linux)

### Cross-Language Consistency

When working on features that exist in both Python and .NET:
- Maintain API consistency between languages where possible
- Use similar naming conventions (accounting for language idioms)
- Document any intentional differences between implementations
- Consider feature parity when adding new capabilities

### Multi-Language Development

- **Python**: Targets Python 3.10+ with async/await patterns
- **.NET**: Targets .NET 8.0+ (with multi-targeting support) using modern C# features
- Both implementations share the same conceptual architecture but use language-appropriate idioms

## Common Patterns

### Agent Creation

Both languages follow similar patterns for creating agents:
- Initialize a chat client (OpenAI, Azure OpenAI, etc.)
- Create an agent with instructions and optional tools
- Run the agent with user input
- Handle responses and streaming

### Tools and Functions

- Functions are decorated/attributed for use as agent tools
- Parameters use type annotations for automatic schema generation
- Tools can be added to agents for extended capabilities

### Workflows

- Graph-based orchestration for complex multi-agent scenarios
- Support for conditional branching, loops, and parallel execution
- State management and checkpointing for reliability

## Testing Strategy

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test integration with external services (LLM providers)
- **Sample Tests**: Ensure samples remain functional
- Use environment variables or `.env` files for configuration (never commit secrets)

## Path-Specific Instructions

For detailed language-specific instructions:
- **Python**: See `.github/copilot-instructions/python/python.instructions.md`
- **.NET/C#**: See `.github/copilot-instructions/dotnet/dotnet.instructions.md`

## Getting Help

- **Issues**: File GitHub issues for bugs or feature requests
- **Discussions**: Use GitHub Discussions for questions
- **Discord**: Join the Microsoft Azure AI Foundry Discord community
- **Documentation**: Refer to [Microsoft Learn documentation](https://learn.microsoft.com/agent-framework/)
