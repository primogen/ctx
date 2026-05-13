# AGENTS.md Protocol Import

AGENTS.md defines a predictable repository file for coding-agent instructions:
environment tips, test commands, style rules, PR policy, and project-specific
constraints.

ctx benefits from this protocol in two ways:

1. The skill router can recommend an `agents-md-protocol` skill when a repo has
   weak or missing agent-facing instructions.
2. Harness users can expose the same file as durable context to non-Claude-Code
   agents without encoding policy in chat history.

This import is metadata-only and synthesized into a ctx skill.
