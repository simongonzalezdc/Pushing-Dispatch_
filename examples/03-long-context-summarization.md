---
title: Summarize project documentation
executor: kimi
includes:
  - branch-safety
---

# Task

Read all markdown documentation in `docs/` and produce a comprehensive
summary at `docs/SUMMARY.md`.

The docs/ directory contains approximately 80,000 tokens of architecture
documentation, API specs, and design decisions. This task is routed to
Kimi because of the large input context (256K window).

## Output format

The summary should be structured as:

```markdown
# Documentation Summary

## Architecture Overview
(2-3 paragraphs summarizing the system architecture)

## Components
(one section per major component, 1-2 paragraphs each)

## API Surface
(list of endpoints/interfaces with one-line descriptions)

## Key Design Decisions
(bulleted list with rationale for each)

## Known Limitations
(bulleted list)
```

## Constraints

- Output should be under 3000 words
- Do not invent information not present in the source docs
- Link back to specific source files: `See [architecture.md](architecture.md)`
- Use the same terminology as the source docs
- Write in present tense

## Acceptance Criteria

- Every markdown file in docs/ has been read
- All major components are mentioned in the summary
- No hallucinated features or APIs
- Summary is useful as a quick-reference for new contributors
