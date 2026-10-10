# Login Enterprise Results Toolkit

Turn a selected Login Enterprise result into inspectable evidence, a repeatable comparison, and an editable report.

This is a **public, unsupported community preview**. It is under active development and is not a Login VSI supported product. Josh is the product and technical owner of this initiative.

Login Enterprise already has charts, comparisons, exports and PDF reporting. This toolkit helps when you need to repeat retrieval, retain provenance, adapt datasets for another tool, or assemble a report from explicit scenario definitions.

The Python engine provides `le-results` commands for profiles, encrypted credential enrollment, connection diagnostics, bounded discovery, selection, capture, comparison and report generation. PowerShell wrappers and optional AI skills call that engine. JSON/CSV exports and HTML reports work independently of Power BI or an AI subscription.

Start with the [offline quickstart](docs/quickstart.md). It generates a clearly labeled synthetic Windows migration example, retains a candidate execution failure, and reconciles the comparison against known source values. A security-agent variant is also available.

Power BI has two adapters: a local-file snapshot project and a refreshable project with independently authored Power Query acquisition. Both generate editable PBIP/PBIR reports and model.bim definitions. Snapshot files pass the public schemas; **Desktop refresh and live appliance acceptance are pending**. Generated files alone do not establish that they work in Desktop.

The explicit API adapter targets `/publicApi/v8-preview`. There is no v7 fallback. Login Enterprise 6.9.2 and Power BI Desktop 2.158.1304.0 remain validation targets until the recorded acceptance checks pass. See the [capability matrix](docs/capabilities.md) and [progress/evidence](docs/progress.md) for the precise status.

- [Installation and CLI walkthrough](docs/quickstart.md)
- [Power BI snapshot and refreshable reporting](docs/powerbi.md)
- [Data dictionary and comparison rules](docs/data-dictionary.md)
- [Architecture and tradeoffs](docs/architecture.md)
- [API/reference provenance](docs/api-notes.md)
- [Credential handling and troubleshooting](docs/troubleshooting.md)
- [Portable AI workflows and no-AI equivalents](docs/ai-workflows.md)
- [Read-only live acceptance](docs/live-validation.md)
- [Contributor guidance](CONTRIBUTING.md) and [independent Claude audit](docs/claude-audit.md)

No license was present in the initial checkout. Licensing is an unresolved owner decision. Public visibility does not establish permission to reuse upstream code or assets. This toolkit copies no source or assets from LE-PBI-Connector.
