# Support Pilot

Support Pilot answers engineers' PLM, CAD vault, and PLM-SAP questions only from the
knowledge base, and turns recurring tickets into problems to fix.

## What it is for

- **Ask, with sources.** An engineer asks a question; the answer quotes the articles for
  every step, or is withheld when the articles do not cover it.
- **Recurring problems.** Tickets are grouped into problems by their words, with volume,
  trend, and whether an article covers each one, so the team fixes causes and writes the
  missing articles.

## Who does what

| Who | Does what |
| --- | --- |
| **Code** | Retrieves the article passages, checks every quote, groups tickets, computes trends, and flags rising problems and knowledge gaps. |
| **The AI** | Answers only from the passages code retrieved; suggests a likely root cause for a problem; drafts articles for knowledge gaps. Every ticket id and quote it cites is checked. |
| **A support lead (approver)** | Requests reviews and drafts, approves or rejects drafts (rejecting needs a reason), sends problems to Backlog Pilot, and imports tickets. |
| **The audit log** | Records every question, review, draft decision, hand-off, import, and refused attempt. |

## A typical week

1. Engineers use **Ask**; withheld answers become tickets that say what was searched.
2. Open **Recurring problems** and look at what is rising and what no article covers.
3. Review a problem's likely cause, and draft the missing article.
4. Approve the draft (it is published and Ask can use it), or reject it with a reason.
5. Send the problem to Backlog Pilot to fix the cause.

The full rules and thresholds are in the [rules and settings reference](reference).
