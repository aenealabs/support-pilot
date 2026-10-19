import csv
import json
from collections import Counter
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from support_pilot.app import create_app
from support_pilot.assist import check
from support_pilot.clustering import cluster
from support_pilot.config import load_settings
from support_pilot.db import make_engine
from support_pilot.kb import Passage
from support_pilot.llm.replay import ReplayProvider
from support_pilot.models import Answer, Cite, Step
from support_pilot.record_demos import demo_inputs
from support_pilot.suite import SuiteClient, SuiteSettings

DEMO = load_settings().dataset_dir
P = Passage("KB-101", 2, "If the person is available",
            "1. In the CAD vault client, right-click the file and choose **Properties > "
            "Checked out by** to see who has it.")


def test_check_keeps_only_quoted_steps():
    answer = Answer(answerable=True, ticket_summary="", steps=[
        Step(text="See who has it.", cites=[Cite(passage="KB-101 §2",
                                                 quote="choose Properties > Checked out by")]),
        Step(text="Invented step.", cites=[Cite(passage="KB-101 §2", quote="reboot the server")]),
        Step(text="Wrong passage.",
             cites=[Cite(passage="KB-999 §1", quote="right-click the file")]),
        Step(text="No source.", cites=[])])
    result = check(answer, [P])
    assert [s.text for s in result.shown] == ["See who has it."]
    assert result.removed == 3 and result.outcome == "answered" and result.sources == ["KB-101 §2"]
    nothing = check(Answer(answerable=True, ticket_summary="", steps=answer.steps[1:]), [P])
    assert nothing.outcome == "withheld"  # nothing survived the check


def test_clustering_recovers_the_planted_problems():
    rows = list(csv.DictReader((DEMO / "tickets.csv").open()))
    planted = json.loads((DEMO / "tickets_planted.json").read_text())
    groups, left = cluster([f"{r['short_description']}. {r['description']}" for r in rows])
    issues = set(planted["issue"].values()) - {"other"}
    found = []
    for g in groups:
        c = Counter(planted["issue"][rows[i]["ticket"]] for i in g.members)
        top, n = c.most_common(1)[0]
        assert n / len(g.members) >= 0.95, (top, c)  # each problem is one planted issue
        found.append(top)
    assert sorted(found) == sorted(issues)  # every planted issue found, none split
    assert sum(planted["issue"][rows[i]["ticket"]] == "other" for i in left) >= 25


class Stub:
    name = "stub"

    def answer(self, input_text):
        assert "<passages>" in input_text
        ref = input_text.split("<passages>\n[")[1].split("]")[0]
        quote = input_text.split("<passages>\n")[1].split("\n")[1][:40]
        return Answer(answerable=True, ticket_summary="", steps=[
            Step(text="Do the first thing.", cites=[Cite(passage=ref, quote=quote)])])


@pytest.fixture
def client(tmp_path):
    settings = replace(load_settings(), db_path=str(tmp_path / "t.db"))
    sent = []
    suite = SuiteSettings(backlog_url="http://bp", token="t", public_url="http://sp")
    transport = httpx.MockTransport(lambda r: sent.append(json.loads(r.content))
                                    or httpx.Response(201, json={"id": 4}))
    c = TestClient(create_app(settings, engine=make_engine(settings.db_path), provider=Stub(),
                              suite=suite, suite_client=SuiteClient(suite, transport)))
    c.sent = sent
    return c


def test_ask_answers_with_sources_and_logs_feedback(client):
    page = client.post("/ask", data={"question": "Who has my CAD file checked out?"}).text
    assert "every quote checked" in page and "Sources" in page and "Did this solve it?" in page
    client.post("/ask/1/feedback", data={"solved": "yes"})
    page = client.get("/").text
    assert "1<small>/1</small>" in page
    assert "Ask a full question" in client.post("/ask", data={"question": "hi"}).text
    withheld = client.post("/ask", data={"question": "zzqx wwvv nonsense words here"}).text
    assert "No answer from the knowledge base" in withheld and "Open a ticket with this" in withheld


def test_problems_gaps_and_send_to_backlog(client):
    page = client.get("/problems").text
    gaps = page.split("Knowledge gaps")[1].split('<table class="problems">')[0]
    assert "export-controlled folder" in gaps and "Viewer shows old revision" in gaps
    assert "Where-used export times out" in gaps and gaps.count("list-item") == 3
    assert client.post("/problems/PRB-1/send").status_code == 403  # engineers cannot send
    client.cookies.set("sp_user", "lead")
    sent = client.post("/problems/PRB-1/send").text
    assert "Sent PRB-1 to Backlog Pilot" in sent
    assert client.sent[0]["title"].startswith("Recurring problem: ")
    assert "tickets in 12 months" in client.sent[0]["text"]
    assert ">Sent<" in client.get("/problems").text


def test_only_the_planted_rise_is_flagged(client):
    page = client.get("/problems").text
    rows = [r for r in page.split("<tr>") if "rising</span>" in r]
    assert len(rows) == 1 and "BOM" in rows[0]  # BOM transfer failures after the cutover


def test_offline_demo_answers_are_recorded():
    settings = load_settings()
    replay = ReplayProvider(settings.replay_dir)
    outcomes = []
    for _question, text, found in demo_inputs(settings):
        outcomes.append(check(replay.answer(text), found).outcome)
    assert outcomes[:5] == ["answered"] * 5
    assert outcomes[5] == "withheld"  # export-controlled folder access is a knowledge gap


class ProblemStub:
    """Quotes real ticket text, plus one quote nobody wrote."""

    name = "stub"

    def _lines(self, text):
        body = text.split("<tickets>\n")[1].split("\n</tickets>")[0]
        return [line.split(" | ") for line in body.splitlines()]

    def review_problem(self, text):
        from support_pilot.models import Finding, ProblemReview, TicketQuote
        a, b = self._lines(text)[:2]
        return ProblemReview(
            name="Stub name", summary="s",
            root_cause=Finding(text="Likely cause.", quotes=[TicketQuote(ticket=a[0],
                                                                         quote=a[1][:15])]),
            evidence=[Finding(text="Made up.", quotes=[TicketQuote(ticket=b[0],
                                                                   quote="never written")])],
            fix="Fix it.")

    def draft_article(self, text):
        from support_pilot.models import ArticleDraft, DraftStep, TicketQuote
        a = self._lines(text)[0]
        return ArticleDraft(title="How to get folder access", applies_when="When access fails.",
                            steps=[DraftStep(text="Open a ticket.", quotes=[
                                TicketQuote(ticket=a[0], quote=a[3][:20])]),
                                   DraftStep(text="Guess.", quotes=[])],
                            unknowns=["Which form to use"])


@pytest.fixture
def pclient(tmp_path):
    settings = replace(load_settings(), db_path=str(tmp_path / "t.db"))
    c = TestClient(create_app(settings, engine=make_engine(settings.db_path),
                              provider=ProblemStub()))
    c.cookies.set("sp_user", "lead")
    return c


def test_problem_review_is_checked(pclient):
    page = pclient.post("/problems/PRB-1/review", follow_redirects=True).text
    assert "Stub name" in page and "1 flagged" in page and "Quote not found" in page
    assert "Stub name" in pclient.get("/problems").text  # the AI name replaces the label


def test_gap_draft_is_reviewed_then_answers_questions(pclient):
    page = pclient.post("/problems/PRB-3/draft", follow_redirects=True).text  # a gap
    assert "How to get folder access" in page and "Not published." in page
    assert "Which form to use" in page
    assert "An article already covers" in pclient.post("/problems/PRB-1/draft").text
    rec = page.split('/draft/')[1].split('/decide')[0]
    assert "Say why" in pclient.post(f"/problems/PRB-3/draft/{rec}/decide",
                                     data={"decision": "reject"}).text
    page = pclient.post(f"/problems/PRB-3/draft/{rec}/decide",
                        data={"decision": "approve"}).text
    assert "Published as KB-901" in page
    data = pclient.get("/data").text
    assert "KB-901" in data and "How to get folder access" in data
    pclient.cookies.set("sp_user", "eng")
    assert pclient.post("/problems/PRB-3/draft").status_code == 403


def test_offline_demo_has_problem_reviews_and_gap_drafts():
    from support_pilot.problem_ai import problem_input
    from support_pilot.record_demos import demo_problems

    settings = load_settings()
    replay = ReplayProvider(settings.replay_dir)
    for p in demo_problems(settings):
        text = problem_input(p)
        assert replay.review_problem(text).name, p.key
        if not p.covered:
            assert replay.draft_article(text).steps, p.key
