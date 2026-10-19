# Support Pilot

Answers engineers' PLM, CAD vault, and PLM-SAP questions from the knowledge base, with every
step quoted from an article, and turns recurring tickets into problems to fix. Part of
**Mission Control**, with Backlog Pilot, Leadership Pilot, and PLM Insight: same stack,
Brightlayer UI styling, and governance rules (code retrieves and counts, the model answers
only from what code retrieved, code checks every quote, a person decides).

## Quick start

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
.venv/bin/python -m support_pilot.app      # http://127.0.0.1:8030
```

The demo loads a fictional knowledge base (23 articles) and about 1,900 fictional tickets over
12 months (`scripts/generate_tickets.py`; seeded, so they are the same everywhere).

## Built-in Help

**Help** in the side menu explains every screen, and the **?** in the app bar opens the
section about the screen you are on. The **rules and settings reference** is generated from
the same constants the rules run on, so it always matches what the app does; tests fail if a
screen has no help section or a setting is undocumented. Every app also serves the shared
*How Mission Control works* guide (from `mission-control-common`).

Across the suite, overriding a proposed score, rating, placement, or fix, rejecting a draft,
or dropping anything the AI drafted needs a reason; rewording a draft keeps the AI's original
beside it. Every refused attempt is audited, including actions tried without signing in and
failed sign-ins.

## What M1 does

- **Ask, with sources.** Code finds the most relevant article passages (SQLite full-text
  search). The model answers only from them, and each step must quote its passage. Code
  checks every quote word for word; a step that does not check out is removed and the removal
  is shown.
- **No answer rather than a guess.** If the articles do not cover the question, the answer is
  withheld and the engineer gets a ready-to-paste ticket that says what was searched. In the
  demo, "access to the export-controlled drawings folder" is withheld: no article covers it.
- **Deflection, measured.** Every question is logged as answered or withheld, and the
  engineer can say whether it solved the problem.
- **Recurring problems, without AI.** Tickets are grouped by their words (TF-IDF and a
  deterministic clustering), with volume, a 12-month trend, business units, time to resolve,
  and whether an article covers each problem. Rising problems are flagged by rule (at least
  1.5 times the previous quarter and 15 more tickets).
- **Knowledge gaps.** Problems no article covers, by ticket volume: write these articles next.
- **Fix the cause.** A support lead sends a problem to Backlog Pilot's intake inbox with its
  numbers and recent tickets.

On the demo tickets, the grouping recovers the 14 planted issues exactly (each group is one
issue, none split) and flags only the planted rise in BOM transfer failures after the SAP
cutover. The thresholds were tuned on this generated data; real ticket text will need its own
tuning.

## What M2 adds

- **Likely root cause, checked.** For each recurring problem the AI gives a name engineers
  recognize, the likely cause the tickets point to, and one fix to the system or process,
  quoting tickets for every claim; code checks each ticket id and quote. It is labeled a
  likely cause to investigate: the AI sees ticket text, not the systems.
- **Draft articles for knowledge gaps.** From how agents actually resolved the tickets, the
  AI drafts an article: only steps the resolutions show (each quoted and checked), plus the
  questions the tickets leave open (forms, approvers, timings). A support lead approves or
  rejects it; an approved draft is published with its checked steps, and Ask answers from it.

## Roadmap

- **M1 (done):** Ask with checked quotes, recurring problems, knowledge gaps, hand-off to
  Backlog Pilot.
- **M2 (this release):** checked root-cause reviews; reviewed draft articles for gaps.
- **M3:** polish.

## Data and branding

All articles, tickets, people, and part numbers are fictional. The UI uses the open-source
Brightlayer UI color and theme values (BSD-3-Clause); see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This is an independent project, not affiliated with or endorsed by Eaton.

## License

Released under the [MIT License](LICENSE). Third-party components keep their own licenses; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
