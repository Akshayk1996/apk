# Mutual Fund Investment Proposal Generator (India)

This repository provides a CLI agent-style proposal generator for mutual fund advisors serving Indian retail clients.

## What it does

- Captures a complete risk-profiling questionnaire (as requested).
- Scores the client into Conservative / Moderate / Aggressive bands.
- Fetches scheme/NAV data from AMFI public feed with resilient fallback.
- Suggests risk-aligned fund buckets and SIP allocations.
- Produces a client-ready Markdown proposal that can be exported to PDF.

## Quick start

```bash
python3 proposal_agent.py --output proposal.md
```

The script will ask all required questions interactively.

## Non-interactive mode (recommended for workflows)

Prepare a JSON file with all `ClientProfile` fields and run:

```bash
python3 proposal_agent.py --input-json sample_client.json --output proposal.md
```

You can then convert markdown to PDF with any preferred tool (Pandoc, Typora, VS Code extension, etc.).

## AMFI source and fallback

The script first tries live AMFI endpoints:

- https://www.amfiindia.com/spages/NAVAll.txt
- https://portal.amfiindia.com/spages/NAVAll.txt

If both are blocked (common in restricted network environments), it auto-falls back to `data/amfi_sample_nav.txt` so proposal generation still succeeds.
