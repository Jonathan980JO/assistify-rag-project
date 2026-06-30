# Documentation

Active documentation for the **Assistify RAG** public-release branch. Historical phase reports and deprecated development notes live under [`archive/`](archive/).

## Getting started

| Document | Description |
|----------|-------------|
| [SETUP_WINDOWS.md](SETUP_WINDOWS.md) | Windows install, conda env, launcher, and day-to-day runbook |
| [CANONICAL_PROJECT_PATH.md](CANONICAL_PROJECT_PATH.md) | Project root, runtime data paths, and preflight checks |
| [WINDOWS_TROUBLESHOOTING.md](WINDOWS_TROUBLESHOOTING.md) | Additional Windows-specific fixes |
| [../LAUNCHER_README.md](../LAUNCHER_README.md) | `start_main_servers.py` launcher reference |

## Architecture

| Document | Description |
|----------|-------------|
| [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) | End-to-end technical architecture |
| [ARCHITECTURE_DISCOVERY.md](ARCHITECTURE_DISCOVERY.md) | Codebase inventory and service map |
| [TENANT_SELECTOR_ARCHITECTURE.md](TENANT_SELECTOR_ARCHITECTURE.md) | Per-conversation tenant selection |
| [FRONTEND_TECHNICAL_SPEC.md](FRONTEND_TECHNICAL_SPEC.md) | React/Next.js UI structure and routes |
| [RAG_RETRIEVAL.md](RAG_RETRIEVAL.md) | Retrieval pipeline details |
| [TOON_IMPLEMENTATION.md](TOON_IMPLEMENTATION.md) | TOON context format (token savings) |
| [DIAGRAMS.md](DIAGRAMS.md) | Consolidated Mermaid diagrams |
| [diagrams/](diagrams/) | Individual sequence, activity, class, and process diagrams |

## Security & compliance

| Document | Description |
|----------|-------------|
| [SECURITY_IMPLEMENTATION.md](SECURITY_IMPLEMENTATION.md) | Security controls overview |
| [OWASP_IMPLEMENTATION_REPORT.md](OWASP_IMPLEMENTATION_REPORT.md) | OWASP Top 10 mapping |
| [QUICK_SECURITY_SETUP.md](QUICK_SECURITY_SETUP.md) | Fast security hardening checklist |
| [RESPONSE_VALIDATION_SETUP.md](RESPONSE_VALIDATION_SETUP.md) | LLM response validation setup |

## Integrations & features

| Document | Description |
|----------|-------------|
| [GOOGLE_OAUTH_SETUP.md](GOOGLE_OAUTH_SETUP.md) | Google OAuth 2.0 configuration |
| [EMAILJS_SETUP.md](EMAILJS_SETUP.md) | EmailJS for OTP and notifications |
| [FASTER_WHISPER_SETUP.md](FASTER_WHISPER_SETUP.md) | Speech-to-text (faster-whisper) setup |
| [PROFILE_AND_PASSWORD_RESET.md](PROFILE_AND_PASSWORD_RESET.md) | Profile, password reset, and email change flows |

## Project reference

| Document | Description |
|----------|-------------|
| [PROJECT_BRIEFING.md](PROJECT_BRIEFING.md) | Project overview and technical briefing |
| [ACTUAL_SYSTEM_IMPLEMENTATION.md](ACTUAL_SYSTEM_IMPLEMENTATION.md) | Implementation deep-dive |
| [TEST_PLAN.md](TEST_PLAN.md) | Test strategy and manual checks |
| [ACRONYMS_LIST.md](ACRONYMS_LIST.md) | Terminology and acronyms |
| [IEEE_STANDARDS_CHECKLIST.md](IEEE_STANDARDS_CHECKLIST.md) | Documentation standards checklist |
| [TABLE_OF_CONTENTS_TEMPLATE.md](TABLE_OF_CONTENTS_TEMPLATE.md) | TOC template for long documents |

## Archive

| Location | Contents |
|----------|----------|
| [archive/](archive/) | Phase reports, cleanup plans, evidence bundles |
| [archive/deprecated/](archive/deprecated/) | Superseded release notes, audit reports, migration notes |

Do not treat archived documents as current runbooks unless explicitly linked from an active doc above.
