# Context Network Maintenance Guide

## Purpose
This document describes how to maintain and evolve the context network for the Microsoft Agent Framework project.

## Classification
- **Domain:** Meta
- **Stability:** Stable
- **Abstraction:** Procedural
- **Confidence:** Established

## Maintenance Principles

### Keep It Current
The context network is only valuable if it reflects current reality. Outdated information is worse than no information.

### Update Alongside Changes
When making changes to the project, update the context network in the same PR when possible.

### Review Regularly
Schedule regular reviews to identify outdated or missing information.

### Document Changes
Track significant changes to the context network in the [updates index](updates/index.md).

## Regular Maintenance Tasks

### Daily (For Active Development)
- Update work in progress in [planning](../planning/)
- Add new decisions to [decisions](../decisions/)
- Document design choices in [design](../design/)

### Weekly
- Review and integrate accumulated changes
- Update domain indexes if significant changes occurred
- Check for broken internal links

### Monthly
- Review all index files for accuracy
- Identify gaps in documentation
- Update navigation paths if structure changed
- Review and update relationship networks

### Quarterly
- Comprehensive review of all documentation
- Identify outdated content and update or archive
- Evaluate structure effectiveness
- Consider structural improvements

## Update Procedures

### Adding New Documentation

1. **Create the Document**
   - Use appropriate template if available
   - Follow structure from similar documents
   - Include all required sections (Purpose, Classification, Relationship Network, etc.)

2. **Update Indexes**
   - Add entry to relevant index file
   - Update navigation paths if needed
   - Ensure proper categorization

3. **Update Relationship Networks**
   - Identify related documents
   - Update bidirectional links
   - Document dependencies

4. **Record the Change**
   - Add entry to [updates index](updates/index.md)
   - Note what was added and why

### Updating Existing Documentation

1. **Make Changes**
   - Update content sections as needed
   - Maintain consistent structure
   - Keep metadata format consistent

2. **Update Metadata**
   - Update "Last Updated" date
   - Add entry to "Change History"
   - Note what changed and why

3. **Check Related Documents**
   - Verify relationship network is still accurate
   - Update related documents if needed
   - Fix any broken references

4. **Record the Change**
   - Add entry to [updates index](updates/index.md)
   - Describe the update

### Deprecating Documentation

1. **Mark as Deprecated**
   - Add deprecation notice at top
   - Explain why it's deprecated
   - Link to replacement if available

2. **Update Links**
   - Update documents that link to deprecated content
   - Redirect to current information

3. **Archive or Remove**
   - Move to archive section if historical value
   - Remove if no longer relevant
   - Update indexes accordingly

4. **Record the Change**
   - Document deprecation in updates index

## Quality Standards

### All Documents Should Have

- **Purpose Statement**: Clear explanation of document's function
- **Classification**: Domain, stability, abstraction, confidence
- **Structured Content**: Organized with clear headings
- **Relationship Network**: Links to related documents
- **Navigation Guidance**: Common use cases and next steps
- **Metadata**: Creation date, last update, change history

### Content Quality

- **Accurate**: Reflects current state of project
- **Clear**: Easy to understand
- **Concise**: No unnecessary verbosity
- **Complete**: Covers topic adequately
- **Consistent**: Follows established patterns

### Structure Quality

- **Navigable**: Easy to find information
- **Connected**: Proper relationship networks
- **Organized**: Logical grouping and hierarchy
- **Indexed**: All documents listed in appropriate indexes

## Structural Evolution

### When to Change Structure

Consider structural changes when:
- A section grows too large to navigate effectively
- New patterns emerge that don't fit current structure
- Multiple contributors report navigation difficulties
- Similar information is scattered across multiple locations

### Making Structural Changes

1. **Propose Change**
   - Document the problem
   - Propose solution
   - Discuss with maintainers

2. **Plan Migration**
   - Identify affected documents
   - Plan new structure
   - Identify link updates needed

3. **Execute Migration**
   - Create new structure
   - Move documents
   - Update all links
   - Update indexes

4. **Verify**
   - Check all links work
   - Test navigation paths
   - Get feedback from users

5. **Document**
   - Record structural change in updates
   - Update this maintenance guide if process changed

## Link Maintenance

### Checking Links

Regularly verify:
- Internal links between documents
- Links to project files (when appropriate)
- External links (if any)

### Fixing Broken Links

1. Identify broken link
2. Find current location of referenced content
3. Update link or remove if content gone
4. Check for other instances of same broken link

## Roles and Responsibilities

### All Contributors
- Update context network when making changes
- Keep documentation current with code changes
- Report gaps or outdated information

### Maintainers
- Review PRs for context network updates
- Ensure quality standards are met
- Coordinate larger structural changes
- Perform regular reviews

### Architecture Owners
- Maintain decision records
- Review and approve ADRs
- Ensure architectural documentation is current

## Templates and Standards

### Document Templates

Available templates:
- [ADR Template](../decisions/adr-template.md)
- [ADR Short Template](../decisions/adr-short-template.md)
- [Spec Template](../specs/spec-template.md)

### Naming Conventions

- **Files**: Use `kebab-case-names.md`
- **Directories**: Use lowercase with hyphens
- **ADRs**: Number sequentially: `NNNN-title.md`
- **Specs**: Number sequentially: `NNN-title.md`

## Relationship Network
- **Prerequisite Information**: None
- **Related Information**:
  - [Discovery Guide](../discovery.md)
  - [Updates Index](updates/index.md)
- **Dependent Information**: All context network documents

## Navigation Guidance
- **Access Context**: When maintaining or improving the context network
- **Common Next Steps**:
  - View changes → [Updates Index](updates/index.md)
  - Add content → Follow procedures in this guide
  - Navigate → [Discovery Guide](../discovery.md)
- **Related Tasks**: Documentation maintenance, structure improvements, quality assurance

## Metadata
- **Created:** 2025-10-11
- **Last Updated:** 2025-10-11
- **Updated By:** Context Network Setup

## Change History
- 2025-10-11: Initial maintenance guide created during context network setup
