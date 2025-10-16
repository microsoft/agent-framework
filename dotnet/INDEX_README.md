# .NET Codebase Documentation Index

Welcome to the Microsoft Agent Framework .NET codebase documentation. This index provides comprehensive guides to help you navigate and understand the codebase.

## 📚 Documentation Structure

We've created four complementary documents to help you work with this codebase:

### 1. [CODEBASE_INDEX.md](./CODEBASE_INDEX.md) 📖
**Your comprehensive reference guide to the entire .NET codebase**

- **What it contains:**
  - Complete inventory of all projects (12 core libraries, 16 tests, ~90 samples)
  - Detailed breakdown of each library's purpose and components
  - File listings and directory structures
  - Dependency information
  - Sample project catalog with descriptions

- **Best for:**
  - Finding specific projects or files
  - Understanding what each library does
  - Locating samples for specific scenarios
  - Getting an overview of the codebase structure

- **Navigate to:** When you need to find something specific or understand the project organization.

---

### 2. [ARCHITECTURE.md](./ARCHITECTURE.md) 🏗️
**Deep dive into the architectural design and patterns**

- **What it contains:**
  - Visual architecture diagrams (layered architecture)
  - Dependency graphs showing project relationships
  - Data flow diagrams for key scenarios
  - Design patterns used throughout the codebase
  - Cross-cutting concerns (observability, DI, error handling)
  - Extension points for customization
  - Performance and security considerations

- **Best for:**
  - Understanding how components interact
  - Learning the design philosophy
  - Extending the framework
  - Making architectural decisions

- **Navigate to:** When you need to understand the "why" and "how" of the architecture.

---

### 3. [QUICK_START.md](./QUICK_START.md) 🚀
**Practical guide to get coding immediately**

- **What it contains:**
  - 5-minute quick start code
  - Common scenario implementations with code examples
  - Workflow examples (basic, conditional, parallel)
  - Environment setup instructions
  - Project structure templates
  - Testing guidance
  - Best practices
  - Troubleshooting tips

- **Best for:**
  - Getting started quickly
  - Copy-paste code examples
  - Learning by example
  - Solving specific problems

- **Navigate to:** When you want to start coding or need a working example.

---

### 4. [README.md](./README.md) 📝
**Official project introduction and getting started guide**

- **What it contains:**
  - Project overview
  - Installation instructions
  - Basic examples
  - Links to samples
  - Links to documentation

- **Best for:**
  - First-time visitors
  - Quick overview
  - Installation guidance

- **Navigate to:** Your starting point for the project.

---

## 🎯 Decision Tree: Which Document to Read?

```
Start Here
    ├─ "I'm new to the project"
    │   └─> Read: README.md → QUICK_START.md → Browse Samples
    │
    ├─ "I want to build something specific"
    │   └─> Read: QUICK_START.md → Find scenario → Check sample
    │
    ├─ "I need to understand how it all works"
    │   └─> Read: ARCHITECTURE.md → CODEBASE_INDEX.md
    │
    ├─ "I'm looking for a specific file/project"
    │   └─> Read: CODEBASE_INDEX.md → Navigate to location
    │
    ├─ "I want to extend or customize the framework"
    │   └─> Read: ARCHITECTURE.md (Extension Points) → CODEBASE_INDEX.md
    │
    └─ "I'm troubleshooting an issue"
        └─> Read: QUICK_START.md (Troubleshooting) → Check samples
```

---

## 📋 Quick Navigation by Task

### Learning Tasks

| What I Want to Do | Where to Go |
|-------------------|-------------|
| Get a project overview | [README.md](./README.md) |
| Understand the architecture | [ARCHITECTURE.md](./ARCHITECTURE.md) |
| Learn design patterns | [ARCHITECTURE.md](./ARCHITECTURE.md) § Design Patterns |
| See how components interact | [ARCHITECTURE.md](./ARCHITECTURE.md) § Data Flow Diagrams |
| Find code examples | [QUICK_START.md](./QUICK_START.md) § Common Scenarios |
| Browse all samples | [CODEBASE_INDEX.md](./CODEBASE_INDEX.md) § Samples |

### Development Tasks

| What I Want to Do | Where to Go |
|-------------------|-------------|
| Create my first agent | [QUICK_START.md](./QUICK_START.md) § 5-Minute Quick Start |
| Add function tools | [QUICK_START.md](./QUICK_START.md) § Scenario 2 |
| Build a workflow | [QUICK_START.md](./QUICK_START.md) § Workflows |
| Set up dependency injection | [QUICK_START.md](./QUICK_START.md) § Scenario 6 |
| Add observability | [QUICK_START.md](./QUICK_START.md) § Scenario 7 |
| Create a custom agent | [ARCHITECTURE.md](./ARCHITECTURE.md) § Extension Points |
| Write tests | [QUICK_START.md](./QUICK_START.md) § Testing |

### Reference Tasks

| What I Want to Do | Where to Go |
|-------------------|-------------|
| Find a specific project | [CODEBASE_INDEX.md](./CODEBASE_INDEX.md) § Quick Reference |
| Look up dependencies | [CODEBASE_INDEX.md](./CODEBASE_INDEX.md) § Dependencies |
| See all test projects | [CODEBASE_INDEX.md](./CODEBASE_INDEX.md) § Tests |
| Check build configuration | [CODEBASE_INDEX.md](./CODEBASE_INDEX.md) § Build Configuration |
| Find provider implementations | [CODEBASE_INDEX.md](./CODEBASE_INDEX.md) § Provider Libraries |

### Troubleshooting

| What's Wrong | Where to Go |
|--------------|-------------|
| Authentication issues | [QUICK_START.md](./QUICK_START.md) § Troubleshooting |
| Package not found | [QUICK_START.md](./QUICK_START.md) § Troubleshooting |
| Workflow not executing | [QUICK_START.md](./QUICK_START.md) § Troubleshooting |
| Understanding error messages | [ARCHITECTURE.md](./ARCHITECTURE.md) § Error Handling |

---

## 🗺️ Codebase Map

### Core Stack (Foundation)
```
Microsoft.Agents.AI.Abstractions  (interfaces & contracts)
            ↓
Microsoft.Agents.AI               (core implementation)
```
**Read:** [CODEBASE_INDEX.md § Core Libraries](./CODEBASE_INDEX.md#core-libraries)

### Provider Stack (AI Services)
```
Microsoft.Agents.AI
    ├─> Microsoft.Agents.AI.OpenAI
    ├─> Microsoft.Agents.AI.AzureAI  
    ├─> Microsoft.Agents.AI.CopilotStudio
    └─> Microsoft.Agents.AI.A2A
```
**Read:** [CODEBASE_INDEX.md § Provider Libraries](./CODEBASE_INDEX.md#provider-libraries)

### Hosting Stack (Applications)
```
Microsoft.Agents.AI.Hosting
    ├─> Microsoft.Agents.AI.Hosting.A2A
    │       └─> Microsoft.Agents.AI.Hosting.A2A.AspNetCore
    └─> Microsoft.Agents.AI.Hosting.OpenAI
```
**Read:** [CODEBASE_INDEX.md § Hosting Libraries](./CODEBASE_INDEX.md#hosting-libraries)

### Workflow Stack (Orchestration)
```
Microsoft.Agents.AI.Workflows
            ↓
Microsoft.Agents.AI.Workflows.Declarative
```
**Read:** [CODEBASE_INDEX.md § Workflow Libraries](./CODEBASE_INDEX.md#workflow-libraries)

---

## 🎓 Learning Paths

### Path 1: For .NET Developers New to AI Agents

1. **Start:** [README.md](./README.md) - Project overview
2. **Practice:** [QUICK_START.md](./QUICK_START.md) § 5-Minute Quick Start
3. **Explore:** `samples/GettingStarted/Agents/Agent_Step01_Running/`
4. **Progress:** Follow steps 02-16 in `samples/GettingStarted/Agents/`
5. **Deep Dive:** [ARCHITECTURE.md](./ARCHITECTURE.md) - Understand the design
6. **Reference:** [CODEBASE_INDEX.md](./CODEBASE_INDEX.md) - As needed

### Path 2: For AI Developers New to .NET

1. **Start:** [README.md](./README.md) - Project overview
2. **Quick Code:** [QUICK_START.md](./QUICK_START.md) - See C# patterns
3. **Compare:** `samples/SemanticKernelMigration/` - If coming from SK
4. **Learn .NET:** `samples/GettingStarted/Agents/Agent_Step09_DependencyInjection/`
5. **Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) - .NET patterns
6. **Build:** Use [QUICK_START.md](./QUICK_START.md) templates

### Path 3: For Workflow/Orchestration Focus

1. **Concepts:** [ARCHITECTURE.md](./ARCHITECTURE.md) § Workflow Flow Diagrams
2. **Code:** [QUICK_START.md](./QUICK_START.md) § Workflows
3. **Foundational:** `samples/GettingStarted/Workflows/_Foundational/`
4. **Advanced:** Browse workflow samples in [CODEBASE_INDEX.md](./CODEBASE_INDEX.md)
5. **YAML:** `workflow-samples/` + Declarative samples
6. **Reference:** [CODEBASE_INDEX.md](./CODEBASE_INDEX.md) § Microsoft.Agents.AI.Workflows

### Path 4: For Enterprise/Production

1. **Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) - Full understanding
2. **Security:** [ARCHITECTURE.md](./ARCHITECTURE.md) § Security Considerations
3. **Observability:** [QUICK_START.md](./QUICK_START.md) § Scenario 7
4. **DI/Hosting:** [QUICK_START.md](./QUICK_START.md) § Scenario 6
5. **Testing:** [QUICK_START.md](./QUICK_START.md) § Testing
6. **A2A:** `samples/A2AClientServer/` + [ARCHITECTURE.md](./ARCHITECTURE.md)
7. **Full Sample:** `samples/AgentWebChat/` (Aspire + Blazor)

---

## 📊 Statistics

### Codebase Size

| Category | Count |
|----------|-------|
| Core Library Projects | 12 |
| Test Projects | 16 |
| Sample Projects | ~90 |
| Total .cs Files | ~1000+ |
| YAML Examples | 10+ |

### Lines of Documentation

| Document | Sections | Approximate Lines |
|----------|----------|-------------------|
| CODEBASE_INDEX.md | 17 | 800+ |
| ARCHITECTURE.md | 13 | 900+ |
| QUICK_START.md | 15 | 850+ |
| **Total** | **45** | **2550+** |

---

## 🔗 External Resources

### Official Documentation
- [Microsoft Learn - Agent Framework](https://learn.microsoft.com/agent-framework/)
- [GitHub Repository](https://github.com/microsoft/agent-framework)
- [Design Documents](../docs/design/)
- [Architectural Decision Records](../docs/decisions/)

### Community
- [GitHub Discussions](https://github.com/microsoft/agent-framework/discussions)
- [GitHub Issues](https://github.com/microsoft/agent-framework/issues)

### Related Technologies
- [Microsoft.Extensions.AI](https://learn.microsoft.com/dotnet/ai/)
- [Azure OpenAI](https://learn.microsoft.com/azure/ai-services/openai/)
- [OpenTelemetry for .NET](https://opentelemetry.io/docs/languages/net/)
- [A2A Protocol](https://github.com/microsoft/agent-to-agent)
- [Model Context Protocol](https://modelcontextprotocol.io/)

---

## 🤝 Contributing

Before contributing, read:
1. [ARCHITECTURE.md](./ARCHITECTURE.md) - Understand design principles
2. [CODEBASE_INDEX.md](./CODEBASE_INDEX.md) - Know the structure
3. [../CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guidelines
4. [../CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) - Community standards

---

## 📝 Document Maintenance

### Keeping These Docs Updated

When making significant changes to the codebase:

| Change Type | Update Document |
|-------------|-----------------|
| New project added | CODEBASE_INDEX.md |
| New sample added | CODEBASE_INDEX.md, QUICK_START.md |
| Architecture change | ARCHITECTURE.md |
| New pattern/feature | ARCHITECTURE.md, QUICK_START.md |
| Dependency updated | CODEBASE_INDEX.md § Dependencies |
| New scenario | QUICK_START.md § Common Scenarios |

### Document Versioning

All documentation includes:
- **Last Updated:** Date stamp
- **Version:** Semantic version
- Located at bottom of each document

---

## 🎁 Bonus: Most Useful Files to Bookmark

### For Daily Development
1. `QUICK_START.md` - Code examples at your fingertips
2. `samples/GettingStarted/Agents/` - Reference implementations
3. `src/Microsoft.Agents.AI.Abstractions/` - Core interfaces

### For Architecture/Design
1. `ARCHITECTURE.md` - Design philosophy
2. `docs/decisions/` - Why decisions were made
3. `src/Microsoft.Agents.AI.Workflows/` - Complex patterns

### For Reference
1. `CODEBASE_INDEX.md` - Find anything quickly
2. `Directory.Packages.props` - Package versions
3. `tests/` - See how we test

---

## 💡 Pro Tips

### Searching the Codebase
```bash
# Find all agent implementations
grep -r "class.*Agent.*:" src/

# Find workflow executors
grep -r "Executor" src/Microsoft.Agents.AI.Workflows/

# Find samples using OpenAI
find samples/ -name "*OpenAI*"
```

### Building Efficiently
```bash
# Build only what you need
dotnet build src/Microsoft.Agents.AI/

# Skip tests during development
dotnet build --no-restore

# Watch mode for rapid iteration
dotnet watch run
```

### Documentation in Code
All public APIs have XML documentation. Use IDE IntelliSense or:
```bash
# Generate API docs
dotnet build -p:GenerateDocumentationFile=true
```

---

## 🎯 Your Next Step

Based on your goal, we recommend:

| Your Goal | Start Here | Then Go To |
|-----------|------------|------------|
| **I want to build my first agent** | [QUICK_START.md](./QUICK_START.md) § 5-Minute Quick Start | `samples/GettingStarted/Agents/Agent_Step01_Running/` |
| **I want to understand the framework** | [ARCHITECTURE.md](./ARCHITECTURE.md) | [CODEBASE_INDEX.md](./CODEBASE_INDEX.md) |
| **I want to build workflows** | [QUICK_START.md](./QUICK_START.md) § Workflows | `samples/GettingStarted/Workflows/` |
| **I want to contribute** | [ARCHITECTURE.md](./ARCHITECTURE.md) | [../CONTRIBUTING.md](../CONTRIBUTING.md) |
| **I need a reference** | [CODEBASE_INDEX.md](./CODEBASE_INDEX.md) | Specific sections as needed |

---

**Happy Coding! 🚀**

---

**Documentation Index Created:** October 14, 2025  
**Index Version:** 1.0  
**Covers Codebase Version:** Current (October 2025)

**Questions?** Open an issue on GitHub or start a discussion.

**Found an error in these docs?** PRs welcome!


