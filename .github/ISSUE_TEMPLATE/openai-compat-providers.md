---
name: "Support OpenAI-compat providers via adapter"
about: "Add support for providers using OpenAI-compatible endpoints (GPT-4o, Mistral, Groq)"
title: "feat: Support OpenAI-compat providers via openai SDK adapter"
labels: ["enhancement", "good first issue"]
assignees: []
---

## Summary

The current harness assumes Anthropic-compatible endpoints. OpenAI's API format is different enough that an adapter layer would open up GPT-4o, Mistral (via La Plateforme), and Groq.

## Scope

- One new wrapper (`bin/wrappers/openai_compat.sh`) that translates between Claude Code's Anthropic format and OpenAI's format
- One new TOML entry per provider
- Documentation in docs/PROVIDERS.md

## Design considerations

- The adapter could use the `openai` Python SDK to translate requests
- Or it could use a lightweight HTTP proxy that rewrites the request/response format
- Tool-use mapping between Anthropic and OpenAI formats needs careful handling

## Acceptance criteria

- [ ] At least one OpenAI-compat provider dispatches and completes a task
- [ ] Tool use (Read, Write, Edit, Bash) works through the adapter
- [ ] Status reporting follows the same protocol
- [ ] Documentation covers setup and caveats
