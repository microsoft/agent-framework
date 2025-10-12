# Architectural Decision Records (ADRs)

## Purpose
This index provides navigation to all architectural decision records for the Microsoft Agent Framework project.

## Classification
- **Domain:** Decisions
- **Stability:** Dynamic (new decisions added regularly)
- **Abstraction:** Structural
- **Confidence:** Established

## About ADRs

An Architectural Decision (AD) is a justified software design choice that addresses a functional or non-functional requirement that is architecturally significant. An Architectural Decision Record (ADR) captures a single AD and its rationale.

For more information, see [adr.github.io](https://adr.github.io/).

## Decision Records

### Active Decisions

1. **[0001: Agent Run Response](0001-agent-run-response.md)**
   - Status: Accepted
   - Topic: Agent execution response structure

2. **[0002: Agent Tools](0002-agent-tools.md)**
   - Status: Accepted
   - Topic: Tool integration and function calling architecture

3. **[0003: Agent OpenTelemetry Instrumentation](0003-agent-opentelemetry-instrumentation.md)**
   - Status: Accepted
   - Topic: Observability and telemetry integration

4. **[0004: Foundry SDK Extensions](0004-foundry-sdk-extensions.md)**
   - Status: Accepted
   - Topic: Azure AI Foundry SDK integration

5. **[0005: Python Naming Conventions](0005-python-naming-conventions.md)**
   - Status: Accepted
   - Topic: Python package and module naming standards

6. **[0006: User Approval](0006-userapproval.md)**
   - Status: Accepted
   - Topic: Human-in-the-loop approval mechanisms

7. **[0007: Agent Filtering Middleware](0007-agent-filtering-middleware.md)**
   - Status: Accepted
   - Topic: Content filtering and guardrails architecture

8. **[0007: Python Subpackages](0007-python-subpackages.md)**
   - Status: Accepted
   - Topic: Python package structure and organization

## Creating New ADRs

### Process

1. **Copy Template**
   - Full template: [adr-template.md](adr-template.md)
   - Short template: [adr-short-template.md](adr-short-template.md)
   - Name: `NNNN-title-with-dashes.md` (check existing PRs for next number)

2. **Document Structure**
   - **Status**: Must initially be `proposed`
   - **Deciders**: List GitHub IDs of sign-off authorities (keep list short)
   - **Consulted**: List partners consulted
   - **Informed**: List stakeholders informed
   - **Date**: Decision date (update when accepted)

3. **Content Requirements**
   - For each option, list good/neutral/bad aspects
   - Include detailed investigations in "More Information" section
   - Can link to external documents

4. **Review & Approval**
   - Share PR with deciders (must be required reviewers)
   - Update status to `accepted` once decision is agreed
   - Update date when accepted
   - PR approval captures decision approval

5. **Superseding Decisions**
   - Decisions can be changed by new ADRs
   - Record negative outcomes in original ADR when superseded

## Decision Categories

### Architecture & Design
- Agent run response (0001)
- Agent tools (0002)
- Filtering middleware (0007)

### Integration & Extensions
- OpenTelemetry instrumentation (0003)
- Foundry SDK extensions (0004)

### Language-Specific
- Python naming conventions (0005)
- Python subpackages (0007)

### User Experience
- User approval mechanisms (0006)

## Relationship Network
- **Prerequisite Information**:
  - [Architecture Overview](../foundation/architecture.md)
- **Related Information**:
  - [Design Documents](../design/index.md)
  - [Specifications](../specs/index.md)
- **Dependent Information**:
  - All implementation work follows these decisions

## Navigation Guidance
- **Access Context**: Before making architectural changes or when understanding design rationale
- **Common Next Steps**:
  - Creating new ADR → Use templates provided
  - Understanding architecture → [Architecture Overview](../foundation/architecture.md)
  - Implementation details → [Design Documents](../design/index.md)
- **Related Tasks**: Architecture reviews, design proposals, technical planning

## Templates
- [Full ADR Template](adr-template.md)
- [Short ADR Template](adr-short-template.md)

## Metadata
- **Created:** 2025-10-11
- **Last Updated:** 2025-10-11
- **Updated By:** Context Network Setup

## Change History
- 2025-10-11: Initial index created during context network migration from docs/decisions/
