"""Structured output the model returns. Every step cites a passage and quotes it; code checks
each quote against the passage before an engineer sees the answer."""

from pydantic import BaseModel, Field


class Cite(BaseModel):
    passage: str = Field(description="The passage reference exactly as given, e.g. 'KB-101 §2'.")
    quote: str = Field(description="Words copied exactly from that passage.")


class Step(BaseModel):
    text: str = Field(description="One instruction or fact, in plain words.")
    cites: list[Cite] = Field(description="The passage text that supports it.")


class Answer(BaseModel):
    answerable: bool = Field(description="True only if the passages explain how to solve the "
                             "question.")
    steps: list[Step] = Field(description="The answer as short steps, each supported by a "
                              "quote. Empty if not answerable.")
    ticket_summary: str = Field(description="If not answerable (or only partly), a one-line "
                                "ticket description for the support team. Otherwise ''.")


class TicketQuote(BaseModel):
    ticket: str = Field(description="Ticket id exactly as given, e.g. INC000123.")
    quote: str = Field(description="Words copied exactly from that ticket's text.")


class Finding(BaseModel):
    text: str = Field(description="One sentence.")
    quotes: list[TicketQuote] = Field(description="Ticket text that supports it.")


class ProblemReview(BaseModel):
    name: str = Field(description="Short problem name an engineer would recognize, e.g. "
                      "'Released BOMs not reaching SAP'.")
    summary: str = Field(description="One sentence: what users experience.")
    root_cause: Finding = Field(description="The most likely underlying cause the tickets "
                                "point to, with the quotes that suggest it. Say 'likely'.")
    evidence: list[Finding] = Field(description="2-4 observations from the tickets.")
    fix: str = Field(description="One change to the system or process that would stop these "
                     "tickets, not a workaround.")


class DraftStep(BaseModel):
    text: str = Field(description="One step, in plain words.")
    quotes: list[TicketQuote] = Field(description="Resolution or ticket text that supports "
                                      "the step.")


class ArticleDraft(BaseModel):
    title: str
    applies_when: str = Field(description="One sentence: the symptom this article is for.")
    steps: list[DraftStep] = Field(description="What to do, only as far as the tickets show.")
    unknowns: list[str] = Field(description="What the tickets do not say and the article "
                                "owner must fill in (forms, approvers, timings).")
