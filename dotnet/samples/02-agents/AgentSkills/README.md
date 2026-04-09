# AgentSkills Samples

Samples demonstrating Agent Skills capabilities. Each sample shows a different way to define and use skills.

| Sample | Description |
|--------|-------------|
| [Agent_Step01_FileBasedSkills](Agent_Step01_FileBasedSkills/) | Define skills as `SKILL.md` files on disk with reference documents. Uses a unit-converter skill. |
| [Agent_Step02_CodeDefinedSkills](Agent_Step02_CodeDefinedSkills/) | Define skills entirely in C# code using `AgentInlineSkill`, with static/dynamic resources and scripts. |
| [Agent_Step03_ClassBasedSkills](Agent_Step03_ClassBasedSkills/) | Define skills as C# classes using `AgentClassSkill`. |
| [Agent_Step04_MixedSkills](Agent_Step04_MixedSkills/) | **(Advanced)** Combine file-based, code-defined, and class-based skills using `AgentSkillsProviderBuilder`. |
| [Agent_Step05_SkillsWithDI](Agent_Step05_SkillsWithDI/) | Use Dependency Injection with both code-defined (`AgentInlineSkill`) and class-based (`AgentClassSkill`) skills. |

## Key Concepts

### Skill Types

| Aspect | File-Based | Code-Defined | Class-Based |
|--------|-----------|--------------|-------------|
| Definition | `SKILL.md` files on disk | `AgentInlineSkill` instances in C# | Classes extending `AgentClassSkill` |
| Resources | All files in skill directory (filtered by extension) | `AddResource` (static value or delegate-backed) | `CreateResource` factory methods |
| Scripts | Supported via script runner delegate | `AddScript` delegates | `CreateScript` factory methods |
| Discovery | Automatic from directory path | Explicit via constructor | Explicit via constructor |
| Dynamic content | No (static files only) | Yes (factory delegates) | Yes (factory delegates) |
| Sharing pattern | Copy skill directory | Inline or shared instances | Package in shared assemblies/NuGet |
| DI support | No | Yes (via `IServiceProvider` parameter) | Yes (via `IServiceProvider` parameter) |

### `AgentSkillsProvider` vs `AgentSkillsProviderBuilder`

For single-source scenarios, use the `AgentSkillsProvider` constructors directly — they accept a skill directory path, a set of skills, or a custom source.

Use `AgentSkillsProviderBuilder` for advanced scenarios where simple constructors are insufficient:

- **Mixed skill types** — combine file-based, code-defined, and class-based skills in one provider
- **Multiple file script runners** — use different script runners for different file skill directories
- **Skill filtering** — include or exclude skills using a predicate

See [Agent_Step04_MixedSkills](Agent_Step04_MixedSkills/) for a working example.
