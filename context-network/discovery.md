# Context Network Discovery Guide

## Welcome

This context network contains all planning, architectural, and coordination information for the Microsoft Agent Framework project. This guide will help you navigate to the information you need.

## Quick Start Paths

### I'm New to the Project
1. **Start Here**: [Project Definition](foundation/project_definition.md) - Understand the mission and scope
2. **Then**: [Architecture Overview](foundation/architecture.md) - Learn the system architecture
3. **Next**: [Development Setup](processes/development.md) - Set up your environment
4. **Finally**: [Contributing Guide](processes/contributing.md) - Start contributing

### I'm Implementing a Feature
1. **Check Decisions**: [Decision Records](decisions/index.md) - Review relevant ADRs
2. **Review Architecture**: [Architecture Overview](foundation/architecture.md) - Understand system design
3. **Check Domain**: [Python](domains/python/index.md) or [.NET](domains/dotnet/index.md) - Language-specific patterns
4. **Follow Principles**: [Development Principles](foundation/principles.md) - Coding standards
5. **Document Design**: Create design document in [design/](design/) if complex

### I'm Fixing a Bug
1. **Write Failing Test**: Demonstrate the bug
2. **Review Principles**: [Development Principles](foundation/principles.md) - Ensure correct approach
3. **Implement Fix**: Follow code quality standards
4. **Run Checks**:
   - Python: `uv run poe check`
   - .NET: `dotnet build && dotnet test && dotnet format`

### I'm Making an Architectural Decision
1. **Review Existing**: [Decision Records](decisions/index.md) - Check for related decisions
2. **Understand Context**: [Architecture Overview](foundation/architecture.md) - System context
3. **Create ADR**: Use [ADR template](decisions/adr-template.md)
4. **Document Process**: Follow [ADR creation process](decisions/index.md#creating-new-adrs)

### I'm Working with Workflows
1. **Understand Architecture**: [Workflows Domain](domains/workflows/index.md)
2. **Review Samples**: `workflow-samples/`, `dotnet/samples/GettingStarted/Workflows/`, `python/samples/getting_started/workflows/`
3. **Check Patterns**: Common workflow patterns in samples

## Context Network Structure

### Foundation
Core project information that rarely changes:
- **[Project Definition](foundation/project_definition.md)**: Mission, scope, objectives
- **[Architecture Overview](foundation/architecture.md)**: System architecture
- **[Development Principles](foundation/principles.md)**: Coding standards and principles

### Domains
Language and feature-specific documentation:
- **[Python Domain](domains/python/index.md)**: Python implementation details
- **[.NET Domain](domains/dotnet/index.md)**: .NET implementation details
- **[Workflows Domain](domains/workflows/index.md)**: Multi-agent orchestration

### Processes
How we work:
- **[Development Processes](processes/development.md)**: Setup, commands, workflows
- **[Contributing](processes/contributing.md)**: Contribution guidelines

### Decisions
Architectural decisions and rationale:
- **[Decision Records Index](decisions/index.md)**: All ADRs
- **[Templates](decisions/)**: ADR templates for new decisions

### Design
Technical design documentation:
- **[Design Documents Index](design/index.md)**: Implementation designs
- **[Python Package Setup](design/python-package-setup.md)**: Package structure

### Specs
Feature and integration specifications:
- **[Specifications Index](specs/index.md)**: All specifications
- **[Foundry SDK Alignment](specs/001-foundry-sdk-alignment.md)**: Azure AI Foundry integration

### Planning
Project planning and roadmap (to be populated):
- **[Planning Index](planning/index.md)**: Roadmap and work in progress

### Meta
Information about the context network itself:
- **[Updates](meta/updates/index.md)**: Changes to the context network
- **[Maintenance](meta/maintenance.md)**: How to maintain this network

## Common Navigation Patterns

### By Activity

| Activity | Path |
|----------|------|
| Onboarding | [Project Definition](foundation/project_definition.md) → [Architecture](foundation/architecture.md) → [Development Setup](processes/development.md) |
| Feature Development | [Decisions](decisions/index.md) → [Domain Docs](domains/) → [Principles](foundation/principles.md) |
| Bug Fixing | [Principles](foundation/principles.md) → [Development Processes](processes/development.md) |
| Architecture Review | [Architecture](foundation/architecture.md) → [Decisions](decisions/index.md) → [Design Docs](design/index.md) |
| Documentation | [Domain Indexes](domains/) → [Processes](processes/) |

### By Role

| Role | Key Documents |
|------|--------------|
| New Contributor | [Project Definition](foundation/project_definition.md), [Development Setup](processes/development.md), [Contributing](processes/contributing.md) |
| Developer | [Domain Docs](domains/), [Principles](foundation/principles.md), [Processes](processes/) |
| Architect | [Architecture](foundation/architecture.md), [Decisions](decisions/index.md), [Design Docs](design/index.md) |
| Maintainer | [All Sections](#context-network-structure), [Meta Documentation](meta/) |

### By Technology

| Technology | Entry Point |
|-----------|-------------|
| Python | [Python Domain](domains/python/index.md) |
| .NET | [.NET Domain](domains/dotnet/index.md) |
| Workflows | [Workflows Domain](domains/workflows/index.md) |
| OpenAI | [Architecture: Provider Integrations](foundation/architecture.md#layer-2-provider-integrations) |
| Azure | [Architecture: Provider Integrations](foundation/architecture.md#layer-2-provider-integrations) |

## For AI Agents

When working with this repository:

### Always Do
1. **Consult context network** before implementing features or making architectural decisions
2. **Check existing ADRs** before proposing changes to established patterns
3. **Document decisions** in appropriate sections (decisions/, design/, specs/)
4. **Update relationship maps** when creating dependencies between components

### Remember
- **Context Network = Blueprints**: Planning, design, and documentation
- **Project Files = Building**: The actual code that runs

### File Placement Rules
**Context Network (put here):**
- Architecture diagrams
- System design descriptions
- Implementation plans
- Project roadmaps
- Technical decision records
- Research findings
- Task delegation documents
- Meeting notes

**Project Structure (NOT in context network):**
- Source code files
- Build configuration
- Resource files
- Public user documentation (README, etc.)
- Deployment scripts
- Tests
- Samples

## Search Tips

### Finding Information

1. **By Topic**: Use domain indexes ([Python](domains/python/index.md), [.NET](domains/dotnet/index.md), [Workflows](domains/workflows/index.md))
2. **By Decision**: Check [Decision Records Index](decisions/index.md)
3. **By Process**: See [Processes](processes/)
4. **By Design**: Review [Design Documents Index](design/index.md)

### Creating New Documentation

1. **Architectural Decision**: Use [ADR template](decisions/adr-template.md), place in `decisions/`
2. **Design Document**: Create in `design/`, add to [index](design/index.md)
3. **Specification**: Use [spec template](specs/spec-template.md), place in `specs/`
4. **Domain Documentation**: Add to appropriate domain in `domains/`

## Maintenance

This context network should be kept current. See [Maintenance Guide](meta/maintenance.md) for:
- Update procedures
- Review schedules
- Quality standards
- Evolution processes

## Feedback

If you find gaps, outdated information, or have suggestions for improving this context network, please:
1. File an issue describing the problem
2. Or create a PR with improvements
3. Tag with `documentation` label

## Version Information

- **Created**: 2025-10-11
- **Last Major Update**: 2025-10-11
- **Context Network Version**: 1.0

## Related Resources

- **Repository Root**: [.context-network.md](../.context-network.md) - Discovery file
- **Project README**: `../README.md` - Public project documentation
- **Contributing**: `../CONTRIBUTING.md` - Public contribution guide
- **CLAUDE.md**: `../CLAUDE.md` - AI agent instructions
