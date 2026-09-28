# App Radar — Claude handoff

## Goal

Maintain an English internal website that checks the US iPhone Top Free charts for Games, Finance, Shopping, Casino, Sports, Social Networking, Utilities, and Entertainment.

## Qualification rule

- Use a rolling 30-calendar-day window across all eight categories.
- An app qualifies when it appears today and its App ID was absent from every recorded monitored category during the previous 30 calendar days.
- The comparison is cross-category. Changing categories does not make an app new.
- Tracking starts with the complete 2026-09-28 baseline. Earlier unrecorded dates count as no appearance.
- Retain only the latest 30 dated records.
- An app can qualify again after 30 full days without a recorded appearance.
- Publish leads only when all eight current charts were collected. On a partial day, publish no leads but retain IDs from successful categories to suppress false future requalification.

## Important files

- `app-radar/radar.py`: collector entry point.
- `app-radar/rolling.py`: rolling-window state and qualification logic.
- `app-radar/rolling-state.json`: current history required for continuity.
- `app-radar/test_rolling.py`: rule tests.
- `app-radar-site/build_data.py`: exports safe public data.
- `app-radar-site/dist/`: static English website.
- `automation.toml`: reference copy of the current Codex schedule and workflow. It is not directly portable to Claude.

## Daily workflow

1. Run `python3 app-radar/radar.py` from this package's parent directory or run `python3 radar.py` inside `app-radar`.
2. Run `python3 app-radar-site/build_data.py`.
3. Publish `app-radar-site/dist` with the chosen hosting provider.
4. Schedule this for 09:00 Europe/Rome every day.

The collector requires outbound HTTPS access to `itunes.apple.com`. The current OpenAI Sites publication uses `git.chatgpt-team.site`, but Claude will need a different hosting/deployment integration unless it can operate the existing OpenAI Sites project.

Current public URL: https://app-radar-mq.yellowbeansss.chatgpt.site

## What Claude needs to decide

- Where the daily job will run.
- Which hosting provider will replace or update the current OpenAI Sites deployment.
- How unattended network access and secrets are configured in that environment.

Do not reset or discard `rolling-state.json` unless the owner explicitly wants to restart the 30-day history.
