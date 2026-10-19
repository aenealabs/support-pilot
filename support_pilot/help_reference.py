"""The Help reference: rules, checks, and settings, built from the code that uses them.

Answer checks come from assist.py and kb.py, problem grouping from clustering.py, and trends
from tickets.py, so the reference cannot say something the app does not do. SETTINGS
documents every environment setting; a test fails if the code reads one not listed here.
"""

from mission_control import ReferenceSection

from support_pilot.assist import MIN_QUOTE
from support_pilot.clustering import MERGE, MIN_SIZE, THRESHOLD
from support_pilot.kb import PASSAGES
from support_pilot.problem_ai import SAMPLE
from support_pilot.tickets import COVERED_SHARE, RISING_MIN, RISING_RATIO

SETTINGS = {
    "SP_DB_PATH": "Where the app keeps its database (SQLite file).",
    "SP_LLM_PROVIDER": "replay (offline demo, recorded answers), anthropic (Claude API), or "
                       "foundry (Claude on Microsoft Foundry).",
    "SP_MODEL": "The Claude model (or Foundry deployment).",
    "SP_RECORD": "true to save live answers and reviews as recordings for the offline demo.",
    "ANTHROPIC_API_KEY": "Claude API key, when SP_LLM_PROVIDER=anthropic.",
    "ANTHROPIC_FOUNDRY_RESOURCE": "The Microsoft Foundry resource, when SP_LLM_PROVIDER=foundry.",
    "ANTHROPIC_FOUNDRY_API_KEY": "Key for Claude on Microsoft Foundry; without it, Azure sign-in "
                                 "(managed identity) is used.",
    "SP_AUTH": "demo (pick a fictional person) or oidc (single sign-on).",
    "SP_OIDC_METADATA_URL": "Your identity provider's OpenID Connect metadata address.",
    "SP_OIDC_CLIENT_ID": "The app registration's client ID.",
    "SP_OIDC_CLIENT_SECRET": "The app registration's client secret.",
    "SP_SESSION_SECRET": "A long random value that signs the sign-in cookie.",
    "SP_SESSION_HTTPS_ONLY": "false only for local testing over plain http.",
    "SP_APPROVER_ROLE": "The app role for support leads, who review problems and approve "
                        "articles.",
    "SP_APPROVER_EMAILS": "Comma-separated emails that are approvers even without the role.",
    "SP_BACKLOG_URL": "Backlog Pilot's address, to send problems to its inbox.",
    "SP_LEADERSHIP_URL": "Leadership Pilot's address (older single-link menu).",
    "SP_SUITE_TOKEN": "The shared Mission Control token; the same value as BP_SUITE_TOKEN.",
    "SP_PUBLIC_URL": "This app's own address, so items sent to the inbox link back here.",
    "MISSION_CONTROL_APPS": "The suite's apps and addresses, the same in every app.",
}


def reference() -> list[ReferenceSection]:
    from support_pilot.app import MAX_QUESTION  # app imports this module

    pct = lambda x: f"{round(100 * x)}%"  # noqa: E731
    return [
        ReferenceSection("Answer checks", [
            ("Sources", f"Code finds the {PASSAGES} most relevant article passages (full-text "
                        "search); the AI may cite only those"),
            ("Quotes", f"Every step quotes its passage word for word (at least {MIN_QUOTE} "
                       "characters; case, spacing, and formatting ignored)"),
            ("A step that fails", "Removed, and the removal is shown"),
            ("Withheld", "If the AI says the articles do not cover the question, or no step "
                         "survives the checks, no answer is shown; the engineer gets a "
                         "ready-to-paste ticket instead"),
            ("Questions", f"Up to {MAX_QUESTION} characters"),
        ], columns=("Rule", "How it works")),
        ReferenceSection("Recurring problems", [
            ("Grouping", "Tickets grouped by their words (TF-IDF), without AI; numbers, part "
                         "numbers, file names, and ticket ids are ignored"),
            ("Joining a group", f"Similarity of {pct(THRESHOLD)} or more to the group's center"),
            ("Same problem", f"Groups whose centers are {pct(MERGE)} or more similar are merged"),
            ("Problem", f"A group of at least {MIN_SIZE} tickets"),
            ("Rising", f"The last 3 months have at least {RISING_RATIO} times the tickets of the "
                       f"3 before, and at least {RISING_MIN} more"),
            ("Covered by an article", f"An article is linked on at least {pct(COVERED_SHARE)} of "
                                      "the problem's tickets; otherwise it is a knowledge gap"),
        ], columns=("Rule", "How it works")),
        ReferenceSection("AI reviews and drafts", [
            ("Likely root cause", f"From the {SAMPLE} most recent tickets; every ticket id and "
                                  "quote is checked. Labeled a likely cause to investigate"),
            ("Draft article", "Only steps the ticket resolutions show, each quoted and checked, "
                              "plus the questions the tickets leave open"),
            ("Approving a draft", "Publishes it with its checked steps; Ask can answer from it"),
            ("Rejecting a draft", "Needs a reason"),
        ], columns=("Item", "Rule")),
        ReferenceSection("Settings", sorted(SETTINGS.items()),
                         columns=("Setting", "What it does"),
                         intro="Environment settings (or a .env file next to the app)."),
    ]
