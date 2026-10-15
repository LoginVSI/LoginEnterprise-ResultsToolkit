# Login Enterprise Results Toolkit

Turn a selected Login Enterprise result into inspectable evidence, a repeatable comparison, and an editable report.

This is a **public, unsupported community preview**. It is under active development and is not a Login VSI supported product. Josh, Technical Product Manager, is the product and technical owner of this initiative.

Login Enterprise already has charts, comparisons, exports and PDF reporting. This toolkit helps when you need to repeat retrieval, retain provenance, adapt datasets for another tool, or assemble a report from explicit scenario definitions.

The Python engine provides `le-results` commands for profiles, encrypted credential enrollment, connection diagnostics, bounded discovery, selection, capture, comparison and report generation. PowerShell wrappers and optional AI skills call that engine. JSON/CSV exports and HTML reports work independently of Power BI or an AI subscription.

Start with the [offline quickstart](docs/quickstart.md). It generates a clearly labeled synthetic Windows migration example, retains a candidate execution failure, and reconciles the comparison against known source values. A security-agent variant is also available.

Power BI has a local-file snapshot project and a refreshable project with independently authored Power Query acquisition. Both generate editable PBIP/PBIR reports and model.bim definitions. Actual capture reports pass the public schemas; **Desktop opening and refresh remain pending**. Generated files alone do not establish Desktop acceptance.

The explicit API adapter targets `/publicApi/v8-preview`. There is no v7 fallback. Verified HTTPS and bounded read-only capture have been exercised on Login Enterprise 6.9.2. Explicit resource sorting recovered endpoint requests; new captures are separate from the preserved earlier failures. Successful empty responses do not establish measured resource coverage. Desktop 2.158.1304.0 is installed; execution acceptance remains pending. See the [capability matrix](docs/capabilities.md) and [progress/evidence](docs/progress.md).

Broader discovery found populated resources and passing/failed application work in a retained Continuous window. Recommendations inspect source timestamps and full definitions separately; current collection health and new-data refresh remain unverified. Finite reports show timer/resource rows. A single-source refreshable project avoids inventing comparison roles. Native Application PDF retrieval uses the documented GET route without creating a report job.

## Requirements

| Workflow | Requirements |
|---|---|
| Offline exports, comparison and HTML | 64-bit Python 3.11 or newer, isolated environment, hash-locked runtime packages and toolkit installation. Python 3.11/3.14 are the verification matrix; other versions and ARM builds need separate verification. |
| Windows wrappers | Optional Windows PowerShell 5.1 or PowerShell 7. Activation is optional; wrappers invoke the checkout environment. |
| Clone or contribute | Git and a user-writable checkout. Git is not an engine runtime dependency. |
| Appliance results | HTTPS access, certificate/hostname trust, explicit v8-preview contract, result-read API permission and a token in a verified native vault. API permissions are separate from Windows administrator rights. |
| Native credentials | Windows Credential Manager, macOS Keychain or Linux Secret Service under the operating user. Windows persistence is exercised; native Linux/macOS proof remains pending. |
| Power BI | Optional Desktop for PBIP opening/refresh. Live reporting needs approved connector trust and separate Power Query Key enrollment. |
| AI requests | Optional supported AI host and portable skills. The same commands work without AI. |
| Development references | PDF/OpenAPI inputs are development-only. Customers do not need private references; sanitized contracts ship in the repository. |

Follow the [setup path](docs/quickstart.md), [readiness bootstrap](scripts/Test-LEResultsReadiness.ps1), [certificate workflow](docs/troubleshooting.md) and [editable example](examples/customer-workflow.ps1). Normal operation needs no machine-wide install, PATH edit, execution-policy change or root-certificate import. Actual standard-user proof is separate from a non-elevated administrator session.

- [Installation and CLI walkthrough](docs/quickstart.md)
- [Power BI snapshot and refreshable reporting](docs/powerbi.md)
- [Data dictionary and comparison rules](docs/data-dictionary.md)
- [Architecture and tradeoffs](docs/architecture.md)
- [API/reference provenance](docs/api-notes.md)
- [Credential handling and troubleshooting](docs/troubleshooting.md)
- [Portable AI workflows and no-AI equivalents](docs/ai-workflows.md)
- [Prompt gallery](docs/prompt-gallery.md)
- [Read-only live acceptance](docs/live-validation.md)
- [Customer workflows and failure behavior](docs/customer-workflows.md)
- [Compatibility and preview release checks](docs/release-readiness.md)
- [Optional time-series file export](docs/timeseries.md)
- [Contributor guidance](CONTRIBUTING.md) and [independent Claude audit](docs/claude-audit.md)

No license was present in the initial checkout. Licensing is an unresolved owner decision. Public visibility does not establish permission to reuse upstream code or assets. This toolkit copies no source or assets from LE-PBI-Connector.
