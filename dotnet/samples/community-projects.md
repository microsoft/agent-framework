# Community projects for Agent Framework .NET

This page lists published, community-maintained projects that integrate with
the Agent Framework .NET SDK. Entries are reviewed against the
[community project catalog criteria](../../.github/skills/community-projects/SKILL.md).

> [!IMPORTANT]
> The projects on this page are created and maintained outside the Microsoft
> Agent Framework team. Microsoft doesn't own, test, or support these projects.
> Listing a project doesn't imply Microsoft endorsement or confirm compatibility
> with any Agent Framework version. For compatibility information, support, and
> issue handling, contact the project maintainer through the project's
> repository and issue tracker.
> For security concerns, follow the maintainer's security reporting guidance.

## Tools

| Name | Brief description | Scenarios | Project | Issues |
| --- | --- | --- | --- | --- |
| Cohesivity | Backend services built for AI agents, available over MCP with an anonymous account: hosting, Postgres, email, storage, containers, LLMs, voice and external APIs. | Provisioning a database or cache from an agent over MCP with no token; a temporary tenant the user can claim later | [Cohesivity with Agent Framework](https://github.com/cohesivity-org/cohesivity-mcp#microsoft-agent-framework) | [Open an issue](https://github.com/cohesivity-org/cohesivity-mcp/issues/new/choose) |

## Vector stores

| Name | Brief description | Scenarios | Project | Issues |
| --- | --- | --- | --- | --- |
| CommunityToolkit.VectorData.Chroma | A Microsoft.Extensions.VectorData provider for Chroma and Chroma Cloud, built on ChromaDotNet.Client. | Chat history memory with `ChatHistoryMemoryProvider`; RAG with `TextSearchProvider`; hybrid search on Chroma Cloud | [CommunityToolkit.VectorData.Chroma](https://www.nuget.org/packages/CommunityToolkit.VectorData.Chroma) | [Open an issue](https://github.com/CommunityToolkit/AI/issues/new) |
