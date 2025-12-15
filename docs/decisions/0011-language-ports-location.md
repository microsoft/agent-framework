---
status: proposed
contact: qmuntal
date: 2025-12-15
deciders: qmuntal
consulted: 
informed: 
---

# Language Ports Location

## Context and Problem Statement

The Agent Framework currently supports .NET and Python languages, both developed within the same monorepo at `microsoft/agent-framework`. As the framework expands to support additional programming languages (such as Go, Java, TypeScript/JavaScript), we must decide on the optimal repository structure for hosting these language ports.

The fundamental question is: Should we maintain all language implementations in a single monorepo, or should each language port have its own dedicated repository?

This decision impacts developer experience, release management, contribution workflows, and long-term maintainability of the framework across multiple language ecosystems.

## Decision Drivers

- **Language Ecosystem Requirements**: Each language has unique conventions, tooling, and package management requirements (e.g., Go modules require specific repository structures, Java uses Maven Central conventions).
- **Release Cadence Independence**: Different language ports may need independent release cycles based on their ecosystem maturity and community needs.
- **Contributor Experience**: External contributors should have a clear, focused contribution path without being overwhelmed by unrelated language implementations.
- **Maintainability**: Repository structure should minimize maintenance burden while supporting effective cross-language coordination.
- **Issue Management**: Issue tracking should be organized to help contributors and maintainers focus on relevant language-specific problems.
- **Cross-Language Coordination**: Need to maintain consistency in APIs, features, and specifications across all language implementations.  
 
## Considered Options

- **Option 1**: Single monorepo for all language ports
- **Option 2**: Individual repositories per language port
  - **Option 2.1**: Separate repositories with centralized issue tracking
  - **Option 2.2**: Separate repositories with decentralized issue tracking (per-repository issues) 

## Pros and Cons of the Options

### Option 1: Single Monorepo for All Language Ports

All language ports would be maintained within a single repository (e.g., `microsoft/agent-framework`), with each language in its own subdirectory following the pattern `{language}/` (e.g., `dotnet/`, `python/`, `java/`, `go/`).

### Option 2: Individual Repositories per Language Port

Each language port would have its own dedicated repository following the naming pattern `agent-framework-{language}` (e.g., `agent-framework-go`, `agent-framework-java`, `agent-framework-typescript`).

#### Option 2.1: Separate Repositories with Centralized Issue Tracking

Each language has its own repository, but issues are tracked centrally in a single location (e.g., the main `agent-framework` repository or a dedicated tracking repository).

#### Option 2.2: Separate Repositories with Decentralized Issue Tracking

Each language port has both its own repository and its own issue tracking system.

## Decision Outcome

Chosen option: **Option 2.2 (Separate repositories with decentralized issue tracking)**, because it best aligns with the unique requirements and conventions of different language ecosystems while simplifying the contribution experience.

### Rationale

1. **Language Ecosystem Requirements**: Each language has specific repository structure requirements that cannot be easily accommodated in a monorepo:
   - Go modules require the repository to be the source of truth with specific constraints on branch and tag management
   - Java has conventions around Maven/Gradle project structures and artifact publishing
   - TypeScript/JavaScript projects have npm/pnpm workspace patterns that differ significantly from .NET and Python

2. **Independent Release Cycles**: New language ports will be at different maturity levels and need the flexibility to release at their own pace without being coupled to other implementations.

3. **Contributor Experience**: Decentralized issue tracking allows contributors to focus on language-specific problems without being overwhelmed by issues from other languages, lowering the barrier to entry for external contributions.

4. **Team Autonomy**: Language-specific teams can optimize their workflows, CI/CD pipelines, and issue management processes for their ecosystem without impacting other implementations.

### Coordination Mechanisms

To maintain consistency and enable effective collaboration across language implementations:

- **Shared GitHub Project Board**: A centralized project board will track high-level features, specifications, and cross-language initiatives.
- **Architecture Decision Records (ADRs)**: Cross-language decisions will continue to be documented in a central location (likely the original `agent-framework` repository).
- **Regular Sync Meetings**: Maintainers across language implementations will coordinate through scheduled sync meetings.
- **Specification Repository**: API specifications and schemas will be maintained in a central location to ensure consistency.
- **Communication Channels**: Dedicated Discord/Teams channels or GitHub Discussions for cross-language coordination.

### Consequences

- Good, because each language port can adopt the repository structure and conventions that best fit its ecosystem.
- Good, because language teams can release updates independently based on their community's needs and maturity level.
- Good, because the contribution experience is simplified for developers focusing on a specific language implementation.
- Good, because issue tracking remains focused and relevant for contributors interested in a particular language.
- Good, because CI/CD pipelines can be optimized for each language's tooling and testing requirements.
- Good, because repository size and complexity remain manageable for each individual language port.

- Bad, because coordinating cross-language features and specifications requires additional process and tooling.
- Bad, because sharing common resources like test fixtures, sample data, and documentation becomes more complex.
- Bad, because maintaining multiple repositories increases administrative overhead (permissions, CI/CD setup, security scanning).
- Bad, because there's a risk of API divergence if coordination mechanisms are not actively maintained.
- Bad, because new contributors need to understand the multi-repository structure to work across languages.

- Neutral, because this decision applies primarily to future language ports (Go, Java, TypeScript, etc.) and does not require changes to the existing .NET and Python implementations in the current `agent-framework` repository. The .NET and Python implementations may remain in the monorepo structure, serving as a reference point while new languages adopt the separate repository model.

## Validation

This decision will be validated through:

1. **Repository Setup**: Successful creation and configuration of the first new language repository (likely Go or Java) following this structure.
2. **Contributor Feedback**: Gathering feedback from both internal and external contributors on the repository structure and contribution experience.
3. **Coordination Effectiveness**: Regular review of how well coordination mechanisms (project board, ADRs, sync meetings) are working across repositories.
4. **Release Management**: Monitoring the effectiveness of independent release cycles in meeting community needs.

This ADR should be revisited after 6-12 months of operation with the new repository structure to assess whether the coordination mechanisms are adequate and whether any adjustments are needed.

## More Information

- Related specifications and schemas will be maintained in the `schemas/` directory of the original `agent-framework` repository
- Repository naming convention: `agent-framework-{language}` (e.g., `agent-framework-go`, `agent-framework-java`)
- Each new repository should include a README.md that links back to the main agent framework documentation and explains the relationship to other language implementations
- Cross-language issues should be tracked in the centralized GitHub project board with appropriate labels and cross-references to language-specific repositories
