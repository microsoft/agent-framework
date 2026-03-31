# AgentSkills Samples

Samples demonstrating Agent Skills capabilities. Each sample shows a different way to define and use skills.

| Sample | Description |
|--------|-------------|
| [Agent_Step01_FileBasedSkills](Agent_Step01_FileBasedSkills/) | Define skills as `SKILL.md` files on disk with reference documents. Uses a unit-converter skill. |
| [Agent_Step02_CodeDefinedSkills](Agent_Step02_CodeDefinedSkills/) | Define skills entirely in C# code using `AgentInlineSkill`, with static/dynamic resources and scripts. |

## Key Concepts

### File-Based vs Code-Defined Skills

| Aspect | File-Based | Code-Defined |
|--------|-----------|--------------|
| Definition | `SKILL.md` files on disk | `AgentInlineSkill` instances in C# |
| Resources | All files in skill directory (filtered by extension) | `AddResource` (static value or delegate-backed) |
| Scripts | Supported via script executor delegate | `AddScript` delegates |
| Discovery | Automatic from directory path | Explicit via constructor |
| Dynamic content | No (static files only) | Yes (factory delegates) |
| Reusability | Copy skill directory | Inline or shared instances |

For single-source scenarios, use the `AgentSkillsProvider` constructors directly. To combine multiple skill types, use the `AgentSkillsProviderBuilder`.

