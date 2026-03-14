# Lebanon Conflict Tracker 2026

An interactive map tracking Israeli military operations and other conflict events in Lebanon during 2026.

## Features

- **Interactive Leaflet.js map** with event markers color-coded by type
- **Day-by-day timeline sidebar** with event details
- **Date filter pills** to isolate events by day
- **Live stats** — killed, wounded, displaced, conflict duration
- **Dark/light map toggle**
- **Daily auto-update** via cron script pulling from RSS feeds

## Event Types

| Type | Color | Description |
|------|-------|-------------|
| `strike` | Red | Airstrike |
| `ground` | Orange | Ground operation |
| `hvt` | Dark red | High-value target elimination |
| `disp` | Purple | Displacement event |
| `phos` | Yellow | White phosphorus use |
| `unifil` | Blue | UNIFIL incident |
| `hezbollah` | Green | Hezbollah attack |
| `infra` | Orange | Infrastructure strike |

## Files

- `index.html` — The full interactive map (self-contained, no build step)
- `cron/update_map.py` — Daily updater script: fetches RSS feeds, detects new events, injects into map HTML
- `cron/update_log.json` — Log of daily update runs

## Live Site

[Lebanon Conflict Tracker 2026](https://www.perplexity.ai/computer/a/lebanon-conflict-tracker-2026-YksfibPwQ9e87qNCoNqBxw)

## Data Sources

- Al Jazeera
- Reuters
- BBC Middle East
- The Guardian
- Lebanese Health Ministry
- IDF statements
- UN / UNIFIL reports

## Coverage

Conflict began **March 2, 2026** following Hezbollah rocket fire after the killing of Iranian Supreme Leader Khamenei. Currently tracking **50+ events** across Mar 2–14.

## Tech Stack

- [Leaflet.js](https://leafletjs.com/) 1.9.4
- CartoDB dark/light tiles
- Pure HTML/CSS/JS — no framework, no build step
- Python 3 cron updater
