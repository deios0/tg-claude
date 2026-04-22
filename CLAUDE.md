---
category: private
description: Minimal Telegram bot with Claude AI tool-use integration (Docker/Python)
name: tg-claude
repo: deios0/tg-claude
stack:
- docker
- python
updated_at: '2026-03-30'
zone: personal
---



# tg-claude

## Workspace Rules
> Part of CCode workspace. Read and follow:
> - `Hub/rules/common.md` — applies to ALL projects
> - `Hub/rules/private.md` — Private-specific rules

> Minimal but complete Telegram bot with Claude tool use. Clone, configure, launch.

## Tech Stack

Docker,Python

## Development Commands

```bash
pip install -r requirements.txt

docker compose up -d
```

## Project Structure

```
  app/
  data/
  Dockerfile
  README.md
  docker-compose.yml
  docker-compose.yml
```

## Key Files

- `README.md`
- `.env.example` — environment template
- `docker-compose.yml` — container setup

## Dev Protocol

See `Hub/playbook/dev-protocol.md` for the canonical Dev Protocol (git workflow, testing, secrets, authorship, Brain/learning hooks, cross-project boundaries).

## Brain Lessons
<!-- brain:managed — do not edit manually, Brain Service updates this section -->
