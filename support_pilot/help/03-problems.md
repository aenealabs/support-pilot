# Recurring problems

Tickets grouped into problems by their words, without AI, so the numbers can be trusted.

## How tickets are grouped

Each ticket's words are compared with the others (TF-IDF); tickets that are similar enough
form a group, and groups worded differently but about the same thing are merged. Numbers,
part numbers, and file names are ignored. Small groups stay unclustered.

## Reading a problem

Each problem shows its volume, a 12-month trend, the business units affected, time to
resolve, and whether an article covers it. **Rising** problems (sharply up on the previous
quarter) are flagged by rule, and **knowledge gaps** (no article linked on enough of its
tickets) are listed by volume: write those articles next.

## Likely root cause

A support lead can ask the AI for a name engineers recognize, the likely cause the tickets
point to, and one fix to the system or process, quoting tickets for every claim. Code checks
each ticket id and quote. It is labeled a likely cause to investigate: the AI sees ticket
text, not the systems.

## Draft articles

For a knowledge gap, the AI drafts an article from how agents actually resolved the tickets:
only steps the resolutions show, each quoted and checked, plus the questions the tickets leave
open. A support lead approves it, which publishes it so Ask can answer from it, or rejects it
with a reason.

## Fix the cause

**Send to Backlog Pilot** puts the problem in Backlog Pilot's inbox with its numbers and
recent tickets, so the cause is fixed rather than each ticket.
