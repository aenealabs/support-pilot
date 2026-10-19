"""FastAPI web app: ask with checked citations, recurring problems, knowledge gaps."""

import json
import re
from datetime import date
from urllib.parse import urlparse

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from mission_control import STATIC_PATH, install, install_help
from sqlalchemy.engine import Engine
from sqlmodel import Session

from support_pilot import audit_search
from support_pilot.assist import AskStore, answer_input, check
from support_pilot.auth import (
    AuthSettings,
    User,
    load_auth_settings,
    user_from_claims,
    user_from_session,
    user_to_session,
)
from support_pilot.config import PACKAGE_DIR, Settings, load_settings
from support_pilot.db import audit, make_engine
from support_pilot.help_reference import reference
from support_pilot.kb import Article, KnowledgeBase
from support_pilot.llm import LLMError, LLMProvider, build_provider
from support_pilot.models import ArticleDraft, ProblemReview
from support_pilot.problem_ai import ProblemAiStore, check_draft, check_review, problem_input
from support_pilot.suite import SuiteClient, SuiteError, SuiteSettings, load_suite_settings
from support_pilot.tickets import ProblemError, TicketStore

USER_COOKIE = "sp_user"
# Each screen's help button opens the guide section about it (checked at start-up).
PAGE_HELP = {
    "ask.html": "ask#asking-a-question",
    "problems.html": "problems#reading-a-problem",
    "problem.html": "problems#likely-root-cause",
    "data.html": "data#tickets",
    "audit.html": "audit#searching",
    "restricted.html": "overview#who-does-what",
}
ITEM_KEYS = re.compile(r"PRB-\d+|KB-\d+|INC\d+", re.IGNORECASE)
MAX_QUESTION = 500


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else many or one + 's'}"


def _highlight(value: str, terms: list[str]) -> Markup:
    escaped = str(escape(value))
    if not terms:
        return Markup(escaped)
    pattern = re.compile("|".join(re.escape(str(escape(t))) for t in terms), re.IGNORECASE)
    return Markup(pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", escaped))


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def create_app(settings: Settings | None = None, engine: Engine | None = None,
               auth: AuthSettings | None = None, provider: LLMProvider | None = None,
               suite: SuiteSettings | None = None, suite_client: SuiteClient | None = None
               ) -> FastAPI:
    settings = settings or load_settings()
    engine = engine or make_engine(settings.db_path)
    auth = auth or load_auth_settings()
    provider = provider or build_provider(settings)
    suite = suite or load_suite_settings()
    suite_client = suite_client or SuiteClient(suite)
    ai_label = ("AI answer (recorded demo)" if provider.name == "replay"
                else f"AI answer ({settings.model})")
    kb = KnowledgeBase(engine, settings.dataset_dir / "kb")
    titles = {a.id: a.title for a in kb.articles.values()}
    tickets = TicketStore(engine)
    tickets.seed_if_empty(settings.dataset_dir, "Demo tickets (seed)")
    asks = AskStore(engine)
    pai = ProblemAiStore(engine)

    def publish(rec) -> None:
        draft = check_draft(ArticleDraft.model_validate_json(rec.output), rec.input_text)
        kb.add(Article(rec.article_id, "Approved draft", draft.draft.title,
                       f"# {draft.draft.title}\n\n{draft.markdown()}"))
        titles[rec.article_id] = draft.draft.title

    for rec in pai.approved():
        publish(rec)
    questions = json.loads((settings.dataset_dir / "questions.json").read_text())["questions"]
    users = [User(u["id"], u["name"], u["role"], u.get("approver", False))
             for u in json.loads(settings.users_path.read_text())["users"]]

    app = FastAPI(title="Support Pilot")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy",
                                    "camera=(), microphone=(), geolocation=()")
        return response

    if auth.mode == "oidc":
        _enable_oidc(app, auth)
    app.state.engine = engine
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    templates.env.globals.update(users=users, auth_mode=auth.mode,
                                 provider_name=provider.name, titles=titles,
                                 suite_connected=suite.connected)
    install(app, templates, "Support Pilot", suite.apps)
    templates.env.filters.update(
        plural=plural, highlight_terms=_highlight,
        dict_without=lambda params, key: {k: v for k, v in params.items() if k != key})

    def current_user(request: Request) -> User:
        if auth.mode == "oidc":
            user = user_from_session(request.session.get("user"))
            return user or User("anonymous", "Signed out", "", False)
        wanted = request.cookies.get(USER_COOKIE)
        return next((u for u in users if u.id == wanted), users[0])

    def actor(request: Request) -> str:
        return current_user(request).actor

    def render(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
        return templates.TemplateResponse(
            request, name, {"nav": name, "user": current_user(request), **context},
            status_code=status_code)

    install_help(app, templates, render, PACKAGE_DIR / "help", reference=reference,
                 page_help=PAGE_HELP)

    def restricted(request: Request, what: str) -> HTMLResponse | None:
        if current_user(request).approver:
            return None
        with Session(engine) as s:
            audit(s, actor(request), "access_denied", what)
            s.commit()
        return render(request, "restricted.html", status_code=403, what=what)

    # ---------- ask ----------

    def ask_view(request: Request, question: str = "", result=None, entry=None,
                 found=None, message: str = "", status_code: int = 200) -> HTMLResponse:
        return render(request, "ask.html", question=question, result=result, entry=entry,
                      found=found or [], questions=questions, message=message,
                      stats=asks.stats(), recent=asks.recent(8), status_code=status_code)

    @app.get("/", response_class=HTMLResponse)
    def ask_page(request: Request):
        return ask_view(request)

    @app.post("/ask", response_class=HTMLResponse)
    def ask(request: Request, question: str = Form("")):
        question = " ".join(question.split())[:MAX_QUESTION]
        if len(question) < 8:
            return ask_view(request, question, message="Ask a full question.", status_code=422)
        found = kb.search(question)
        if not found:
            empty = check(_withheld(), [])
            entry = asks.log(question, actor(request), empty, "no matching articles")
            return ask_view(request, question, empty, entry, found)
        try:
            answer = provider.answer(answer_input(question, found, titles))
        except LLMError as e:
            return ask_view(request, question, message=str(e))
        result = check(answer, found)
        entry = asks.log(question, actor(request), result, ai_label)
        return ask_view(request, question, result, entry, found)

    @app.post("/ask/{ask_id}/feedback", response_class=HTMLResponse)
    def feedback(request: Request, ask_id: int, solved: str = Form(...)):
        asks.feedback(ask_id, solved == "yes", actor(request))
        return RedirectResponse("/", status_code=303)

    # ---------- problems ----------

    def problems_view(request: Request, message: str = "", notice: str = "") -> HTMLResponse:
        found, left = tickets.analysis()
        ts = tickets.current()
        return render(request, "problems.html", problems=found, left=left, ts=ts,
                      handoffs=tickets.handoffs(), names=pai.names(ts.id) if ts else {},
                      message=message, notice=notice)

    def find_problem(key: str):
        found, _ = tickets.analysis()
        return next((x for x in found if x.key == key.upper()), None)

    def problem_view(request: Request, key: str, message: str = "", notice: str = "",
                     status_code: int = 200) -> HTMLResponse:
        problem = find_problem(key)
        if problem is None:
            return problems_view(request, message=f"{key} is not a current problem.")
        ts = tickets.current()
        review = pai.latest(ts.id, problem.label, "review")
        draft = pai.latest(ts.id, problem.label, "draft")
        return render(request, "problem.html", p=problem,
                      sent=tickets.handoffs().get(problem.label),
                      sample=sorted(problem.tickets, key=lambda t: t.created, reverse=True)[:12],
                      review=check_review(ProblemReview.model_validate_json(review.output),
                                          review.input_text) if review else None,
                      review_rec=review, draft_rec=draft,
                      draft=check_draft(ArticleDraft.model_validate_json(draft.output),
                                        draft.input_text) if draft else None,
                      message=message, notice=notice, status_code=status_code)

    @app.get("/problems", response_class=HTMLResponse)
    def problems_page(request: Request):
        return problems_view(request)

    @app.get("/problems/{key}", response_class=HTMLResponse)
    def problem_page(request: Request, key: str):
        return problem_view(request, key)

    @app.post("/problems/{key}/review", response_class=HTMLResponse)
    def review_problem(request: Request, key: str):
        if (denied := restricted(request, "problem review")) is not None:
            return denied
        problem = find_problem(key)
        if problem is None:
            return problems_view(request, message=f"{key} is not a current problem.")
        text = problem_input(problem)
        try:
            out = provider.review_problem(text)
        except LLMError as e:
            return problem_view(request, key, str(e))
        pai.save(tickets.current().id, problem.label, "review", text, out, actor(request),
                 ai_label.replace("answer", "review"))
        return RedirectResponse(f"/problems/{problem.key}#review", status_code=303)

    @app.post("/problems/{key}/draft", response_class=HTMLResponse)
    def draft_article(request: Request, key: str):
        if (denied := restricted(request, "article draft")) is not None:
            return denied
        problem = find_problem(key)
        if problem is None:
            return problems_view(request, message=f"{key} is not a current problem.")
        if problem.covered:
            return problem_view(request, key, "An article already covers this problem.")
        text = problem_input(problem)
        try:
            out = provider.draft_article(text)
        except LLMError as e:
            return problem_view(request, key, str(e))
        pai.save(tickets.current().id, problem.label, "draft", text, out, actor(request),
                 ai_label.replace("answer", "draft"))
        return RedirectResponse(f"/problems/{problem.key}#draft", status_code=303)

    @app.post("/problems/{key}/draft/{rec_id}/decide", response_class=HTMLResponse)
    def decide_draft(request: Request, key: str, rec_id: int, decision: str = Form(...),
                     reason: str = Form("")):
        if (denied := restricted(request, "article approval")) is not None:
            return denied
        try:
            rec = pai.decide(rec_id, decision == "approve", actor(request), reason)
        except ValueError as e:
            return problem_view(request, key, str(e), status_code=422)
        if rec.status == "approved":
            publish(rec)
            return problem_view(request, key, notice=f"Published as {rec.article_id}. Ask can "
                                                     "now answer from it.")
        return problem_view(request, key, notice="Draft rejected.")

    @app.post("/problems/{key}/send", response_class=HTMLResponse)
    def send_problem(request: Request, key: str):
        if (denied := restricted(request, "send to Backlog Pilot")) is not None:
            return denied
        found, _ = tickets.analysis()
        p = next((x for x in found if x.key == key.upper()), None)
        if p is None:
            return problems_view(request, message=f"{key} is not a current problem.")
        coverage = (f"Knowledge article {p.article} ({titles.get(p.article, '')}) is linked on "
                    f"{round(100 * p.article_share)}% of these tickets." if p.covered else
                    "No knowledge article covers it.")
        trend = (f" {p.recent} tickets in the last 3 months vs {p.before} in the 3 months "
                 "before." if p.before else "")
        examples = "\n".join(f"- {t.ticket}: {t.short_description}. {t.description}"
                             for t in sorted(p.tickets, key=lambda t: t.created)[-5:])
        text = (f"Recurring support problem: {len(p.tickets)} tickets in 12 months across "
                + ", ".join(f"{u} {n}" for u, n in p.units)
                + f"; median {p.median_hours} hours to resolve.{trend} {coverage} The request "
                  "is to fix the cause in the PLM or its integration, not the next ticket.\n\n"
                  f"Recent tickets:\n{examples}")
        try:
            remote = suite_client.send(f"Recurring problem: {p.label}", text, p.key,
                                       f"/problems/{p.key}", current_user(request).name)
        except SuiteError as e:
            return problems_view(request, message=str(e))
        tickets.record_handoff(p.label, remote, actor(request))
        return problems_view(request, notice=f"Sent {p.key} to Backlog Pilot's intake inbox.")

    # ---------- data ----------

    @app.get("/data", response_class=HTMLResponse)
    def data_page(request: Request, message: str = "", status_code: int = 200):
        return render(request, "data.html", ts=tickets.current(), articles=kb.articles,
                      passages=len(kb.passages), message=message, status_code=status_code)

    @app.post("/data", response_class=HTMLResponse)
    async def import_tickets(request: Request, file: UploadFile, name: str = Form("")):
        if (denied := restricted(request, "ticket import")) is not None:
            return denied
        try:
            tickets.load((await file.read()).decode("utf-8-sig"),
                         name.strip() or file.filename or "Imported tickets", None,
                         actor(request))
        except UnicodeDecodeError:
            return data_page(request, "Upload a UTF-8 CSV file.", 422)
        except ProblemError as e:
            return data_page(request, str(e), 422)
        return RedirectResponse("/problems", status_code=303)

    # ---------- audit, user ----------

    @app.get("/audit", response_class=HTMLResponse)
    def audit_log(request: Request, q: str = "", actor_filter: str = "", category: str = "",
                  item: str = "", since: str = "", until: str = "", page: int = 1):
        if (denied := restricted(request, "audit log")) is not None:
            return denied
        page_size = 50
        query = audit_search.AuditQuery(
            text=q, actor=actor_filter, categories=[category] if category else [],
            item_keys=[k.upper() for k in ITEM_KEYS.findall(item)],
            since=_parse_date(since), until=_parse_date(until))
        results = audit_search.search(engine, query, limit=page_size,
                                      offset=(max(page, 1) - 1) * page_size)
        return render(request, "audit.html", events=results.events, total=results.total,
                      page=max(page, 1), page_size=page_size, query=query, ask="",
                      plan=None, answer=None, cited=[], unverified=[], summary={},
                      message="", questions=[], people=audit_search.actors(engine),
                      categories=audit_search.CATEGORY_LABELS,
                      terms=[t for t in re.findall(r"\w+", query.text) if len(t) > 1])

    @app.post("/user")
    def switch_user(request: Request, user_id: str = Form(...)):
        back = urlparse(request.headers.get("referer", "")).path
        if not back.startswith("/") or back.startswith("//"):
            back = "/"
        response = RedirectResponse(back, status_code=303)
        if any(u.id == user_id for u in users):
            response.set_cookie(USER_COOKIE, user_id, httponly=True, samesite="lax")
        return response

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app


def _withheld():
    from support_pilot.models import Answer

    return Answer(answerable=False, steps=[], ticket_summary="")


PUBLIC_PATHS = ("/static", STATIC_PATH, "/login", "/auth/callback", "/logout", "/healthz")


def _enable_oidc(app: FastAPI, auth: AuthSettings) -> None:
    """Sign-in with Microsoft Entra ID (or any OpenID Connect provider)."""
    from authlib.integrations.starlette_client import OAuth
    from starlette.middleware.sessions import SessionMiddleware

    oauth = OAuth()
    oauth.register("oidc", server_metadata_url=auth.metadata_url, client_id=auth.client_id,
                   client_secret=auth.client_secret,
                   client_kwargs={"scope": "openid profile email"})

    @app.middleware("http")
    async def require_sign_in(request: Request, call_next):
        if request.url.path.startswith(PUBLIC_PATHS) or request.session.get("user"):
            return await call_next(request)
        if request.method == "GET" and "hx-request" not in request.headers:
            request.session["next"] = request.url.path  # a sign-in prompt, not a refusal
            return RedirectResponse("/login", status_code=303)
        with Session(request.app.state.engine) as s:  # an action tried without signing in
            audit(s, "not signed in", "access_denied",
                  f"{request.method} {request.url.path} from "
                  f"{request.client.host if request.client else 'unknown'}")
            s.commit()
        return HTMLResponse("Sign in required.", status_code=401)

    app.add_middleware(SessionMiddleware, secret_key=auth.session_secret, same_site="lax",
                       https_only=auth.https_only, max_age=8 * 3600)

    @app.get("/login")
    async def login(request: Request):
        return await oauth.oidc.authorize_redirect(request, request.url_for("auth_callback"))

    @app.get("/auth/callback", name="auth_callback")
    async def auth_callback(request: Request):
        try:
            token = await oauth.oidc.authorize_access_token(request)  # verifies the ID token
            user = user_from_claims(token["userinfo"], auth)
        except Exception as e:  # any failure (state, token, claims) is refused and audited
            with Session(request.app.state.engine) as s:
                audit(s, "not signed in", "sign_in_failed",
                      f"{type(e).__name__} from "
                      f"{request.client.host if request.client else 'unknown'}")
                s.commit()
            return HTMLResponse('Sign-in failed. <a href="/login">Try again</a>.',
                                status_code=401)
        request.session["user"] = user_to_session(user)
        with Session(request.app.state.engine) as s:
            audit(s, user.actor, "signed_in", user.email or user.id)
            s.commit()
        return RedirectResponse(request.session.pop("next", "/"), status_code=303)

    @app.get("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)


def main() -> None:
    import uvicorn

    uvicorn.run("support_pilot.app:create_app", factory=True, host="127.0.0.1", port=8030)


if __name__ == "__main__":
    main()
