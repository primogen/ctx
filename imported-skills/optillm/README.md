# OptiLLM Harness Import

OptiLLM is cataloged as a harness because it wraps model calls with an
OpenAI-compatible optimizing inference proxy. It is useful when a user wants
their own local/API model route plus reasoning-time techniques such as
best-of-N, self-consistency, MCTS, mixture-of-agents, routing, privacy, memory,
or MCP client support.

This import intentionally keeps only metadata and install guidance. The actual
project stays upstream at
https://github.com/algorithmicsuperintelligence/optillm.

## ctx usage

1. Add the catalog record with `ctx-harness-add --from-json harness-record.json`.
2. Rebuild graph/wiki artifacts when releasing recommendations.
3. Use `ctx-harness-install optillm --dry-run` before installing.

## Recommendation fit

Prefer OptiLLM for:

- OpenAI-compatible API proxy workflows.
- Multi-provider reasoning improvement without training.
- Localhost or Docker proxy runtime.
- Users who want model routing, privacy, memory, MCP client, or search plugins.

Avoid recommending it when the user needs a full coding-agent workbench with
workspace lifecycle management; in that case, recommend an agent harness such
as LangGraph, OpenAI Agents SDK, CrewAI, or a generated custom harness PRD.
