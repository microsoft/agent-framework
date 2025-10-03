---
# These are optional elements. Feel free to remove any of them.
status: {proposed | rejected | accepted | deprecated | … | superseded by [ADR-0001](0001-madr-architecture-decisions.md)}
contact: {person proposing the ADR}
date: {YYYY-MM-DD when the decision was last updated}
deciders: {list everyone involved in the decision}
consulted: {list everyone whose opinions are sought (typically subject-matter experts); and with whom there is a two-way communication}
informed: {list everyone who is kept up-to-date on progress; and with whom there is a one-way communication}
---

# Approach for Agent Framework 2.0

## Context and Problem Statement


Our team is responsible for an AI agent framework and currently maintains two related projects: Semantic Kernel (SK) and AutoGen (AG). This dual approach has led to overlap and potential fragmentation: both address similar needs (enabling developers to build and run AI agents) but with different implementations and audiences. Maintaining two frameworks is not sustainable long-term, and it confuses our story to customers and internal partners.

The core question is: Should we create a brand-new agent framework (starting from scratch) or evolve the existing Semantic Kernel into a version 2.0 that incorporates learnings from AutoGen and new capabilities? The decision will determine whether we carry forward SK’s foundation or replace it, directly impacting our development effort, user migration, and community alignment.


<!-- This is an optional element. Feel free to remove. -->

## Decision Drivers


- User and Customer Impact: We have an established user base on SK (who were encouraged to build production solutions on it) and a separate following around Autogen. We want to avoid splitting or losing either community. The solution should present a clear, persuasive story to users that communicates the added value as well as an upgrade path rather than a forced rewrite.
- Community and Perception: There is a messaging advantage if we evolve SK. We can frame the change as a natural evolution (“Semantic Kernel 2.0”) rather than introducing an entirely new framework that stakeholders might question the need for. Conversely, some Autogen users have biases against SK, so the plan must include a strategy to rebrand or reposition the evolved SK to appeal to them (for example, by dropping the word “Kernel” in the name and removing the concept and re-platforming AG AgentChat on SK2).
- Development Effort and Timeline: Building a new framework from scratch would mean re-implementing existing functionality (connectors, memory storage, plugins, etc.) which is a large effort and could delay delivering new capabilities. We have an ambitious target timeline for initial deliverables, so we must use our resources efficiently.
- Integration vs. Duplication: Reusing existing, proven components is desirable to reduce duplicate work. SK already provides many integrations (AI services, vector memory, logging, etc.). Creating a new framework would duplicate much of this functionality in a new project, whereas evolving SK could modify these in place.
- Technical Goals – Multi-Agent Workflows: The primary feature goal is to support complex multi-agent workflows with a great developer experience (easy orchestration, elegant APIs, cloud-ready deployment). The chosen approach must facilitate this “workflow engine” and provide a short path from prototyping to deployment to scale as the key value proposition.
- Architecture Maintainability: We aim to simplify the architecture for long-term maintainability. Notably, the current SK contains a central “Kernel” component that manages calls; the new design proposes removing that to make agent components more modular and flexible. We need to decide if this overhaul is done within SK or via a new codebase.
- Multi-Language Support: In the future, we want to support multiple programming languages/environments. The decision should consider how easily the approach can be extended beyond C# (SK is .NET-centric). A well-structured core (with clear AI and agent primitives) could be implemented in other languages, whereas a one-off new framework might initially target only one language.
-
- … <!-- numbers of drivers can vary -->

## Considered Options


- **Option 1: Create a New Agent Framework (from scratch)**
    - Develop an entirely new orchestration framework, independent of Semantic Kernel. This would involve setting up a new repository and migrating or rewriting functionality from SK/Autogen as needed.

- **Option 2: Evolve Semantic Kernel to Version 2.0**
    - Treat this effort as the next major release of Semantic Kernel, incorporating the new agent framework design. SK would undergo significant refactoring (e.g., removal of the Kernel component, API changes) and be released as Semantic Kernel 2.0 (potentially under a new name to reflect its agent-focused improvements). AutoGen's AgentChat will be re-platformed on SK 2.0.

- **Option 3: Create new Microsoft.Extensions packages for Agent primitives and shared implementations**
    - A new `Microsoft.Extensions.Agents.Abstractions` (prefix could be `Microsoft.Extensions.AI.Agents` or `Microsoft.Extensions.AG`) package would contain the Agent primitives and would only depend on `Microsoft.Extensions.AI.Abstractions` (and other abstractions packages) to keep it lightweight to encourage reuse and implementations to be created. E.g. existing Agent client packages could implement the abstractions. Note: This is the same approach we used to update the Semantic Kernel vector data connectors to build on `Microsoft.Extensions.VectorData` (the SK vector data conneectors now only depend on M.E.VD).

## Decision Outcome


Chosen Option: Evolve Semantic Kernel to Version 2.0.

The team reached consensus that building on the existing Semantic Kernel is the optimal path, rather than creating a net-new framework. In other words, the new “agent framework” will be delivered as Semantic Kernel 2.0 – a major evolution of the current SK, containing the redesigned agent orchestration capabilities. Naming will be decided separately.

Justification: This choice best addresses the decision drivers:

- It leverages SK’s existing strengths and codebase. We don’t waste time rebuilding features that SK already provides (AI connectors, memory abstractions, etc.), allowing us to focus on the new workflow engine and architectural clean-up.
- It provides a stronger story for current SK users and stakeholders. Rather than asking teams to throw away SK and adopt a new product, we’re improving the product they’re invested in.
- It offers continuity for AG users and stakeholders who can continue to use a re-platformed AgentChat API.
- We can unify the SK and Autogen communities. By folding Autogen’s ideas into SK 2.0 (and possibly keeping an experimental layer for cutting-edge features), we show Autogen users that the best parts of Autogen live on, and SK users that their framework is getting even better. This avoids a split where Autogen enthusiasts and SK loyalists go down different paths.
- The new agent design is conceptually an evolution of SK’s approach already. The high-level interface for agents in the new design is very similar to SK’s existing agents; we mostly need to remove/replace the low-level kernel component and improve the workflow API. This means SK is a natural foundation for the changes, reinforcing the decision to build on it.
- We preserve the ability to rebrand and reshape the framework as needed. Since this is a major version change, we can rename components or even the product itself (for example, dropping “Kernel” from the name in the future) to align with the new vision. We get the benefits of a “new” framework in terms of repositioning, without abandoning the old one’s assets.
- While there will be breaking changes, we can manage them via a structured upgrade path and good documentation, which is preferable to an abrupt discontinuation of SK. This option balances innovation with continuity.
- In summary, evolving SK meets our goals with less risk to user adoption. The decision was informally agreed upon in the Scrum-of-Scrums meeting on June 3, 2025, pending documentation in this ADR and further careful planning.


<!-- This is an optional element. Feel free to remove. -->

### Consequences


- Good, because unified platform for users: We converge efforts onto a single framework, simplifying our offerings. Users of SK can migrate to 2.0 without learning a whole new product, and Autogen users will get a more robust supported platform that incorporates their needs. This unity strengthens our community and product focus.
- Good, because minimal duplicate work: By building on SK, we re-use as much as possible. This reduces development time compared to starting over. Features like connectors and memory storage will only need tweaks instead of complete rewrites, allowing the team to deliver the new capabilities faster.
- Good, because clearer customer messaging: It’s easier to communicate “Semantic Kernel 2.0 – now with advanced multi-agent support” than to explain a brand new framework’s purpose1. The evolution story instills confidence that this is a matured improvement on a known foundation, rather than an experimental gamble.
- Good, because opportunity to rebrand: The changes (like removing the kernel concept) give a rationale to rename or reposition the product. We could launch SK 2.0 under a new name (e.g., “Name pending Agent Framework”) to signal the fresh focus, which could attract users who had reservations about SK while still acknowledging SK’s proven lineage.
- Bad, because significant refactor needed: Undertaking these changes within SK is not trivial. We must carefully refactor or remove core pieces (e.g., the Kernel class, plugin model adjustments). This has a risk of introducing bugs or instability if not managed well, since we’re altering the engine of an existing project.
- Bad, because scope creep and timeline risk: Making SK into 2.0 could expand in scope—once we start modifying SK, we might uncover many components to change or improve (e.g., removing kernel touches a lot of subsystems). We must be diligent to limit the 2.0 changes to what’s necessary for the new agent capabilities; otherwise we risk missing our 2-3 month target for initial release
- Bad, because breaking changes for existing users: Current SK 1.x users will face some migration effort. APIs will change (for example, usage of the kernel object will be replaced) and some features might be deprecated. Without proper guidance, this could frustrate users; we’ll need to mitigate this with clear documentation and perhaps tooling to assist upgrades.
- Bad, because potential perception issues: Some in the Autogen community might still perceive SK 2.0 as “Semantic Kernel” (the thing they deliberately didn’t use) in new clothes. If we fail to convince them, they might be hesitant to adopt the unified framework1. We have to manage communication carefully (possibly emphasizing the new name and the involvement of Autogen contributors in SK 2.0 development to build trust).


<!-- numbers of consequences can vary -->

<!-- This is an optional element. Feel free to remove. -->

## Validation


To ensure the success of this decision, we will validate the implementation of SK 2.0 in several ways:

- Prototype Testing: Early on, we will build a simple multi-agent workflow demo using the SK 2.0 code (after the kernel removal and new API are in place). This prototype will validate that the new approach indeed simplifies the developer experience for orchestrating agents (as intended) and that performance is acceptable. If the prototype shows problems (e.g., workflow API is confusing or execution is slow), we will iterate on the design. We will evaluate Magentic-One as prototype candidate .
- Internal Dogfooding: We’ll encourage team members and close collaborators (including those who built with Autogen) to try migrating a small project to SK 2.0. Their feedback will be invaluable to verify that the framework meets real-world needs and that the migration process is reasonable. For example, an Autogen sample will be ported to SK 2.0 to ensure that all necessary capabilities are present or that acceptable alternatives exist.
- Community Feedback (Preview Release): Before full release, we plan to release a preview of SK 2.0 to a subset of external users (possibly the open-source community on GitHub). We will gather feedback on whether the new version resolves previous pain points and how users feel about the change. Positive feedback will confirm our approach; any negative feedback (e.g., missing features or confusion) will guide final adjustments.
- Documentation and Review: We will create comprehensive documentation, including an upgrade guide from SK 1.x to 2.0, and have it reviewed by engineers not on the core team to ensure it’s clear. As part of validation, if an engineer can follow the guide to successfully upgrade an SK 1.x project (or incorporate Autogen-like functionality) without direct help, that indicates our approach is working as intended. Additionally, architecture reviews (possibly with the .NET platform team) will be conducted to validate that the new design is sound and aligns with our long-term maintenance goals (e.g., separation of concerns, ability to extend to other languages).

By executing these validation steps, we aim to catch any shortcomings early and build confidence that the decision to evolve SK is yielding a framework that truly combines the best of SK and Autogen. Only if significant, unresolvable issues arise during validation would we reconsider our decision.


<!-- This is an optional element. Feel free to remove. -->

## Pros and Cons of the Options

### Option 1: Create a New Agent Framework (from scratch)

**Description:** Start a completely new project/repository for the agent orchestration framework. The new framework would not carry any legacy baggage from Semantic Kernel. We would migrate useful pieces from SK or Autogen manually or rewrite them in a cleaner way as needed. The end product would be brand-new in branding and possibly in design.

- Good, because fresh start with no legacy constraints: The team could design the framework exactly as desired, without being limited by SK’s existing architecture. This clean-slate approach might result in a more streamlined codebase, since we include only what is needed for agents and can implement modern patterns from scratch.
- Good, because no immediate backwards-compatibility issues: A new framework would not have to maintain compatibility with SK’s API. We could introduce breaking changes freely in the initial design, which means we can optimize the API for the future without concern for deprecating old methods. (However, this is a short-term advantage, as we’d still need to support the new framework’s users once it’s released.)
- Neutral, because opportunity for new branding: A new project allows a completely new name and branding from day one, which could distance it from any negative perceptions of SK. This could attract users who decided early on against SK. (That said, we can also achieve rebranding with a major SK release, so this alone isn’t a decisive advantage over Option 2.)
- Bad, because high development and maintenance effort: Building a new framework means duplicating a lot of work that’s already been done in SK1. We’d need to port or reinvent essential components (AI service integrations, memory store, skill/plugin system, etc.). This could significantly slow down delivering the new features since the team’s capacity would be split between reimplementing old features and creating new ones.
- Bad, because fragmented user base and community: Introducing a new framework while SK exists would split our community. SK users might not switch (or not immediately), and Autogen users might or might not adopt the new one. We would end up supporting two frameworks (at least during a transition) – which is resource-intensive and could confuse documentation and messaging (“Which one should I use?”).
- Bad, because weak value proposition to stakeholders: It might be hard to justify why a completely new framework is needed. We would face questions like “Why couldn’t this be done in SK?” or “What is so different that warranted a new product?” Both internal stakeholders and external users might be skeptical, potentially slowing adoption. Without a clear, undeniable differentiator, a new framework might struggle to gain traction over SK (which is already known).
- Bad, because migration pain: Eventually, if we intend the new framework to replace SK, all SK users would be forced to migrate anyway. Since the new framework would have a different API, this could entail significant refactoring for users. Some might delay or refuse migration, leading to a long tail of SK 1.x to support or simply unhappy former users.

### Option 2: Evolve Semantic Kernel to Version 2.0 (chosen)

**Description:** Use Semantic Kernel as the foundation and incorporate the new agent framework design into it, releasing the result as a major new version. This involves “forking” or creating a development branch of SK, implementing changes like removing the Kernel component, improving the agent interfaces, and integrating Autogen’s workflow ideas. The end product remains Semantic Kernel in essence, but significantly revamped for the agent use-case. It may be renamed upon release (e.g., SK Agents 2.0 or similar) to reflect the changes.

- Good, because builds on proven technology: We carry forward all the useful and working parts of Semantic Kernel. This provides immediate support for a variety of features (e.g., existing connectors to OpenAI, memory providers, logging, etc.) in the new version without extra work. The team can focus on new capabilities and necessary refactoring, rather than starting everything from scratch.
- Good, because easier adoption and migration: Since it’s an evolution, current SK users can upgrade to 2.0 following a guide, instead of having to switch to a different framework. They maintain confidence that their investment in learning SK was not wasted. Autogen users will see that their feedback led to improvements in a widely-supported platform. Overall, it positions the change as an upgrade for everyone, not a replacement that might leave some behind.
- Good, because combined community and support: All documentation, samples, and forum discussions can converge on one unified framework. The energy that would’ve been split between SK and a new framework instead goes into one product. Over time, this should yield a stronger community and better support (more contributors, more tutorials, unified GitHub repo, etc.), benefiting users and the project’s longevity.
- Good, because retains option to adjust branding: We can release SK 2.0 under a new name if desired (for example, dropping the word “Kernel” as many suggested). This way, we get the benefit of a new identity to appeal to those who had reservations about SK, while still providing a familiar upgrade path. Essentially, SK 2.0 could be marketed almost like a new framework, but with the credibility of the SK project’s history (it’s a “version 2” of a Microsoft-backed OSS framework, which many enterprises will appreciate over a 1.0 of an unknown).
- Neutral, because requires deprecation of some SK features: We will likely trim or change certain SK features that are not core to the new direction (for instance, if SK had a certain pattern for single-agent that doesn’t fit the new model, or some integration that we decide to drop). This is a natural part of a major version change and can be communicated as such. As long as we document alternatives, this is manageable, but it’s something to plan for (hence neutral: neither strictly good nor bad in itself).
- Bad, because carries legacy complexity: Even though we plan to remove the kernel component, SK’s code structure and some design decisions were made with that kernel-centric approach. Refactoring within an existing codebase can be more complex than writing anew due to interdependencies. We might encounter challenges aligning SK’s old patterns with the new agent patterns, leading to technical debt that has to be carefully paid down during the evolution.
- Bad, because Autogen users might hesitate to adopt SK: There might be a perception that SK 2.0 is “SK” which they intentionally avoided. We will have to overcome this by making SK 2.0 feel like a fresh experience (perhaps via naming and demonstrating the improvements). If we fail, we might not capture 100% of the Autogen audience, though we believe most will come if the framework meets their needs.
- Bad, because dependency on SK’s release process: Evolving SK means we continue within the SK project’s governance and processes. If there were any inefficiencies or slow processes in SK’s pipeline (like release cycles, legal reviews for third-party contributions, etc.), those remain factors. A new project could have been an opportunity to streamline from scratch. We’ll mitigate this by improving SK’s processes where needed as part of the 2.0 overhaul.

Despite these drawbacks, the consensus was that the pros of Option 2 outweigh the cons, which is why Option 2 was selected.

### Option 3: Create new Microsoft.Extensions packages for Agent primitives and shared implementations**

**Description:** A new `Microsoft.Extensions.Agents.Abstractions` (prefix could be `Microsoft.Extensions.AI.Agents` or `Microsoft.Extensions.AG`) package would contain the Agent primitives and would only depend on `Microsoft.Extensions.AI.Abstractions` (and other abstractions packages) to keep it lightweight to encoourage reuse and implementations to be created. E.g. existing Agent client packages could implement the abstractions. A new `Microsoft.Extensions.Agents` package would contain OOB implementations e.g. a `ChatClientAgent` which uses an `IChatClient` and supports the `AITool`'s supported by M.E.AI i.e. `AIFunction`, `HostedCodeInterpreterTool`, `HostedWebSearchTool` (this list of tools can be extended over time).

**Note: We would partner with the .Net team to build the new `Microsoft.Extensions.Agents.Abstractions`package.**

The Semantic Kernel Agent Framework would be updated in phases to build on the `Microsoft.Extensions.Agents.Abstractions`. Note: This is the same approach we used to update the Semantic Kernel vector data connectors to build on `Microsoft.Extensions.VectorData` (the SK vector data conneectors now only depend on M.E.VD). The phases aproach would work like this:

- **Phase 1:** Introduce the new `Microsoft.Extensions.Agents.Abstractions`. Semantic Kernel Agent Framework is updated to implement/extend the associated `Agent` primitive. This would be a binary breaking change but we have options e.g. introduce an `IAgent` rather than a base class or keep the existing GA API surface in existing agent implementations or take the breaking change early.
- **Phase 2:** Update Semantic Kernel Agent Framework orchestration and Process Framework to use the new Agent abstractions. At this point we can obsolete the existing GA API surface.
- **Phase 3:** Clean up Semantic Kernel Agent Framework to remove all experimental code e.g. `AgentChannel` etc.
- **Phase 4:** Clean up Semantic Kernel Agent Framework to remove all obsolete code.

- Good, because it builds on the proven pattern of using a `Microsoft.Extensions.XXX.Abstractions`. This will strengthen Microsoft's AI developer eco-system by providing new primitives for Agents.
- Good, because provides an upgrade path for developers using the existing GA Semantic Kernel Agent Framework.
- Good, because the Semantic Kernel team has experience with this approach having successfully introduced the `Microsoft.Extensions.VectorData.Abstractions` and updated the associated Semantic Kernel connectors.
- Good, because it avoids confusion if we introduce new packages contain Agent implementations.
- Neutral, because graduating a new `Microsoft.Extensions.Agents.Abstractions` package will take time and may not be acheiveable in our preferred time frame. This won't be bad for customers as it will give them longer to adopt the new patterns.
- Bad, because Python doesn't have `Microsoft.Extensions.XXX.Abstractions` so there will be a lot of work to introduce this pattern for Python.
- Bad, because it eliminates any concerns about adopting Semantic Kernel abstractions. We have had feedback that other 1st and 3rd party .Net teams prefer to have seperate packages for abstractions that are owned by the .Net team.


## More Information


This decision was discussed and formulated during the Scrum of Scrums meeting on June 3, 2025. The team present included the SK engineering leads and representatives of the Autogen effort, ensuring that the perspectives of both frameworks were considered. Everyone acknowledged the importance of not fracturing our developer community and of delivering value quickly.
Next Steps & Implementation Plan: Now that we’ve decided to proceed with Semantic Kernel 2.0, the plan is to:

- Initiate a Semantic Kernel 2.0 branch/repo: We will create a development branch (or a forked repository) for SK 2.0 work. The initial focus will be on implementing the new agent orchestration core and removing the existing kernel component in a safe manner1. We may start by forking SK into a new temporary repository (perhaps called “agent-framework” internally) to freely refactor, and later consider merging back or replacing SK’s main branch with 2.0.
- Port Autogen concepts: We’ll identify key features and lessons from Autogen (like multi-step reasoning patterns, AgentChat UI, etc.) that need to be integrated. Autogen’s AgentChat application will remain as an experimental playground but will be retrofitted to use SK 2.0 underneath once it’s ready1. This will considering dropping “Kernel” from the name to emphasize the agent-oriented nature (for example, Adaptive Agents Framework, or similarly rebranded). The naming decision will be finalized with input from marketing/branding teams and is outside the scope of this ADR, but is acknowledged as important1.
- Communication plan: Before launching SK 2.0, we’ll prepare material to explain the change to both SK users and Autogen users. This will include blog posts, repository README updates, and possibly webinars to introduce the new version. The communication will stress that this is the successor of both SK and Autogen efforts, and highlight improvements and changes. We will also clarify the support timeline: for instance, how long SK 1.x will receive critical fixes, and that Autogen repository will shift focus to experimental extensions on top of SK 2.0 (rather than being a parallel framework).
- Timeline: Our goal is to have a preview of SK 2.0 around beginning of July. Full production-ready release might follow by September after we incorporate feedback from the preview. We are mindful of the short timeline, so we will prioritize changes that are essential for multi-agent support and defer nice-to-have refactors to later minor versions if needed1. Regular check-ins (perhaps weekly) will track progress on removing the kernel, implementing the new APIs, and testing integration.

By taking these steps, we will implement the decision in a controlled and transparent way. This ADR will be revisited only if major obstacles arise. Otherwise, it will serve as a record of our rationale and a guide for the team as we move forward with Semantic Kernel 2.0 as the unified agent framework.

