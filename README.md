# UVA Smart Planner

Constraint-aware daily planner for UVA students, built as a Django monolith.

## Features
- Import fixed events from `.ics` calendar files.
- Extract syllabus text from PDF and DOCX uploads.
- Create and review task candidates before scheduling.
- Generate a daily time-blocked plan with OR-Tools CP-SAT.
- Apply updates and replan the remaining day.
- Inspect replan logs, schedule snapshots, and conflict reports.

## Stack
- Django
- SQLite
- HTMX
- FullCalendar
- icalendar
- pdfplumber
- python-docx
- OR-Tools CP-SAT

## Local Setup
1. Install dependencies:
   `python -m pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and adjust values if needed.
3. Run migrations:
   `python manage.py migrate`
4. Optional demo seed:
   `python manage.py seed_demo`
5. Start the app:
   `python manage.py runserver`

## Codex Auth
This project is prepared to reuse local Codex CLI auth metadata. Run `codex --login` on the host machine first if you want the app to detect a local session. The current implementation includes credential discovery and cache mirroring, plus deterministic fallbacks for extraction, patch parsing, and summaries.

## Demo Flow
1. Visit `/profile/` and confirm your routine settings.
2. Upload an ICS file at `/calendar/upload/`.
3. Upload a syllabus PDF or DOCX at `/syllabus/upload/`.
4. Review uncertain tasks at `/tasks/review/`.
5. Generate a schedule at `/schedule/`.
6. Submit a natural-language or JSON update to trigger replanning.

## Management Commands
- `python manage.py seed_demo`
- `python manage.py reset_demo`

## Current Limitations
- Codex network calls are stubbed behind deterministic fallbacks.
- Recurring ICS handling covers common RRULE cases but is not exhaustive.
- Replanning currently supports the highest-value patch types first: add event, mark done, and change estimate.