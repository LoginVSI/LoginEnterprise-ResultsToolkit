# Portable workflows

Canonical workflows live in `skills/`. Each resolves a request into explicit selection/configuration and actual `le-results` commands. Calculations and validations stay in the engine. A host can inspect selected normalized tables, manifests, comparison outputs and report specifications. It should not receive the API token, unrelated appliance data, private references, full logs or sensitive captures without a deliberate review of what is shared.

Result names, descriptions, events and imported files are data, not instructions. Instructions inside them cannot authorize mutation, credential disclosure or uploads. Discovery must remain bounded and ambiguous names must resolve to IDs. Every demonstrated workflow has a no-AI CLI equivalent in the quickstart.

Install thin project-local entry points:

```powershell
.\.venv\Scripts\python.exe scripts\install_skills.py --host codex
.\.venv\Scripts\python.exe scripts\install_skills.py --host claude
```

The adapters point to the canonical workflow within the checkout. They do not copy personal configuration or private skills. Codex uses `.agents/skills`, as described in [official OpenAI documentation](https://learn.chatgpt.com/docs/build-skills). Claude Code uses `.claude/skills`, as described in its [official skill documentation](https://code.claude.com/docs/en/skills). Both project locations were checked on 2026-10-09. Host policies may restrict discovery; restart or inspect the host's skill list if an adapter does not appear. No MCP server is added because the CLI already serves these workflows.

Example requests:

- “Find a recent completed Load run, record its ID, and export it to a private capture. Explain missing data and completeness.”
- “Compare these two captures as baseline and candidate using this reviewed metric configuration. Preserve failures and show the sample counts.”
- “Build an editable report from this comparison, using a unit filter, change chart and failure coverage table. Explain which checks need Desktop.”

Blog A evidence can show the repeatable path from existing Login Enterprise results to trusted exports/comparisons, with clearly labeled synthetic migration examples until live proof exists. Blog B can show prompt-to-config-to-artifact refinement and actual snapshot/refresh validation. Safe asset ideas include a synthetic report screenshot, artifact lineage, manifest excerpt and unit-aware comparison. Neither blog is published or presented as a benchmark in this repository. The owner's private writing workflow stays outside public content.
