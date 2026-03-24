"""
api/main_api.py
FastAPI web server for the Multi-Agent System.
Run: uvicorn api.main_api:app --host 0.0.0.0 --port 8000 --reload
Access from Android: http://<PC_LOCAL_IP>:8000
"""
import asyncio
import json
import os
import sys
import uuid
import secrets
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import io
import zipfile

# Ensure project root is importable
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # so workspace/ paths resolve correctly

from dotenv import load_dotenv
load_dotenv()

from core.base_agent import LOG_QUEUE
WEB_PASSWORD = os.getenv("WEB_PASSWORD")

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not WEB_PASSWORD:
        warning_msg = "⚠ WEB_PASSWORD not set — running in open mode (local dev)"
        try:
            print(warning_msg)
        except UnicodeEncodeError:
            print("WEB_PASSWORD not set -- running in open mode (local dev)")
    yield


app = FastAPI(title="Multi-Agent System API", version="1.0.0", lifespan=lifespan)

# CORS origins from environment (comma-separated)
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (index.html, manifest, icons)
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Auth config ────────────────────────────────────────────────────────────
SESSION_TOKEN = "mas_session"          # cookie name
# NOTE: In-memory session store is acceptable for local/dev usage only.
# In production, use a persistent/session backend (Redis/DB/etc.).
SESSION_STORE: dict[str, dict] = {}
# Public paths that don't need auth
PUBLIC = {"/login", "/health", "/static"}

from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not WEB_PASSWORD:
            return await call_next(request)
        path = request.url.path
        # Allow public paths
        if path == "/login" or path.startswith("/static") or path == "/health":
            return await call_next(request)
        # Check cookie
        token = request.cookies.get(SESSION_TOKEN)
        if not token or token not in SESSION_STORE:
            return RedirectResponse(url="/login", status_code=302)
        return await call_next(request)

app.add_middleware(AuthMiddleware)

# ── Login page ─────────────────────────────────────────────────────────────
LOGIN_HTML = """<!DOCTYPE html><html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Giriş — Multi-Agent AI</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f0f1a;color:#e2e8f0;font-family:-apple-system,sans-serif;
min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.card{background:#1a1a2e;border:1px solid #2d2d4e;border-radius:20px;padding:32px 24px;
width:100%;max-width:360px;text-align:center}
.logo{font-size:48px;margin-bottom:12px}
h1{font-size:20px;font-weight:700;margin-bottom:4px}
p{color:#64748b;font-size:13px;margin-bottom:24px}
input{width:100%;background:#0f0f1a;border:1px solid #2d2d4e;border-radius:12px;
padding:14px;color:#e2e8f0;font-size:16px;outline:none;margin-bottom:14px;
text-align:center;letter-spacing:4px}
input:focus{border-color:#7c3aed}
button{width:100%;background:linear-gradient(135deg,#7c3aed,#9333ea);border:none;
border-radius:12px;color:#fff;font-size:16px;font-weight:700;padding:14px;cursor:pointer}
button:active{opacity:.85}
.err{color:#ef4444;font-size:13px;margin-top:12px;display:none}
</style></head><body>
<div class="card">
  <div class="logo">🤖</div>
  <h1>Multi-Agent AI</h1>
  <p>Devam etmek için şifre girin</p>
  <form method="POST" action="/login">
    <input type="password" name="password" placeholder="••••••••" autofocus autocomplete="off">
    <button type="submit">Giriş Yap →</button>
  </form>
  %ERROR%
</div></body></html>"""

def _issue_session_redirect(url: str = "/") -> RedirectResponse:
    session_token = secrets.token_urlsafe(32)
    SESSION_STORE[session_token] = {
        "created_at": datetime.now().isoformat(),
    }
    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(
        SESSION_TOKEN,
        session_token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 30,
    )
    return response

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    if not WEB_PASSWORD:
        return _issue_session_redirect("/")
    return HTMLResponse(LOGIN_HTML.replace("%ERROR%", ""))

@app.post("/login")
async def login_submit(request: Request):
    if not WEB_PASSWORD:
        return _issue_session_redirect("/")

    form = await request.form()
    password = form.get("password", "")
    if password == WEB_PASSWORD:
        return _issue_session_redirect("/")
    html = LOGIN_HTML.replace("%ERROR%", '<p class="err" style="display:block">❌ Yanlış şifre</p>')
    return HTMLResponse(html, status_code=401)

@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get(SESSION_TOKEN)
    if token:
        SESSION_STORE.pop(token, None)
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(SESSION_TOKEN)
    return response



# ── In-memory session store ────────────────────────────────────────────────
sessions: dict[str, dict] = {}   # session_id → {status, logs, result}


# ── Request / Response models ──────────────────────────────────────────────
class GoalRequest(BaseModel):
    goal: str


# ── Helper ─────────────────────────────────────────────────────────────────
def _sync_session_with_orchestrator(session_id: str) -> dict | None:
    sess = sessions.get(session_id)
    if not sess:
        return None

    orch = sess.get("orchestrator")
    if not orch:
        return sess

    try:
        state = orch.get_state()
        sess["questions"] = orch.get_pending_questions()
        if state == "PAUSED":
            sess["status"] = "paused"
        elif sess.get("status") == "paused":
            sess["status"] = "running"
    except Exception:
        pass
    return sess


def _build_agents():
    from core.message_bus import bus
    from agents.planner_agent import PlannerAgent
    from agents.researcher_agent import ResearcherAgent
    from agents.coder_agent import CoderAgent
    from agents.critic_agent import CriticAgent
    from agents.executor_agent import ExecutorAgent
    return {
        "planner":    PlannerAgent(bus=bus),
        "researcher": ResearcherAgent(bus=bus),
        "coder":      CoderAgent(bus=bus),
        "critic":     CriticAgent(bus=bus),
        "executor":   ExecutorAgent(bus=bus),
    }


# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the mobile UI."""
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/run")
async def run_goal(req: GoalRequest):
    """Start a new goal in the background, return session_id immediately."""
    session_id = str(uuid.uuid4())[:8]
    sessions[session_id] = {
        "status": "running",
        "goal": req.goal,
        "logs": [],
        "result": None,
        "questions": [],
        "answers": {},
        "orchestrator": None,
        "started_at": datetime.now().isoformat(),
    }

    async def _background():
        from core.orchestrator import Orchestrator

        async def status_cb(msg: str):
            sessions[session_id]["logs"].append(msg)

        try:
            agents = _build_agents()
            orch = Orchestrator(agents=agents, status_callback=status_cb)
            sessions[session_id]["orchestrator"] = orch
            result = await orch.run(req.goal)
            sessions[session_id]["status"] = "done"
            sessions[session_id]["result"] = result.get("output", "")
        except Exception as e:
            sessions[session_id]["status"] = "error"
            sessions[session_id]["result"] = str(e)
        finally:
            if session_id in sessions:
                sessions[session_id]["orchestrator"] = None

    asyncio.create_task(_background())
    return {"session_id": session_id}


@app.get("/session/{session_id}/questions")
async def get_session_questions(session_id: str):
    sess = _sync_session_with_orchestrator(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "status": sess.get("status", "running"),
        "questions": sess.get("questions", []),
        "answers": sess.get("answers", {}),
    }


@app.post("/session/{session_id}/answers")
async def submit_session_answers(
    session_id: str,
    answers: dict[str, str] = Body(...),
):
    sess = _sync_session_with_orchestrator(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    if sess.get("status") in ("done", "error"):
        raise HTTPException(status_code=409, detail="Session is already finished")

    orch = sess.get("orchestrator")
    if not orch:
        raise HTTPException(status_code=409, detail="Orchestrator is not active")

    accepted, missing = orch.submit_clarification_answers(answers)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing answers for: {', '.join(missing)}",
        )
    if not accepted:
        raise HTTPException(status_code=409, detail="No pending clarification questions")

    sess["answers"].update({k: str(v) for k, v in answers.items() if str(v).strip()})
    sess["questions"] = orch.get_pending_questions()
    sess["status"] = "running"
    sess["logs"].append("📝 Kullanıcı cevapları alındı, akış devam ediyor.")
    return {"session_id": session_id, "status": "running", "accepted": list(sess["answers"].keys())}


@app.get("/stream/{session_id}")
async def stream_logs(session_id: str):
    """SSE endpoint — streams live logs to the browser."""
    async def event_generator() -> AsyncGenerator[str, None]:
        sent = 0
        while True:
            sess = sessions.get(session_id)
            if not sess:
                yield f"data: {json.dumps({'error': 'Session not found'})}\n\n"
                break

            logs = sess["logs"]
            while sent < len(logs):
                msg = logs[sent]
                yield f"data: {json.dumps({'log': msg})}\n\n"
                sent += 1

            if sess["status"] in ("done", "error"):
                yield f"data: {json.dumps({'status': sess['status'], 'result': sess['result']})}\n\n"
                break

            await asyncio.sleep(0.3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/logs/stream")
async def stream_agent_logs(request: Request):
    """SSE endpoint — streams live per-agent think/act/reflect log events."""

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(LOG_QUEUE.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                payload = {
                    "agent": event.agent_name,
                    "stage": event.stage,
                    "message": event.message,
                    "tokens": event.tokens_used,
                    "timestamp": event.timestamp,
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/sessions")
async def list_sessions():
    """Return summary of all sessions."""
    for sid in list(sessions.keys()):
        _sync_session_with_orchestrator(sid)

    return [
        {
            "session_id": sid,
            "goal": s["goal"][:60],
            "status": s["status"],
            "started_at": s.get("started_at", ""),
        }
        for sid, s in sessions.items()
    ]


@app.get("/projects")
async def list_projects():
    """List workspace projects with file names and summary."""
    workspace = ROOT / "workspace" / "projects"
    if not workspace.exists():
        return []
    projects = []
    for p in sorted(workspace.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_dir():
            src_files = list((p / "src").glob("*.py")) if (p / "src").exists() else []
            src_files = [f for f in src_files if f.name != ".gitkeep"]

            summary_path = p / "project_summary.txt"
            summary = summary_path.read_text(encoding="utf-8")[:300] if summary_path.exists() else ""

            projects.append({
                "name": p.name,
                "files": len(src_files),
                "file_names": [f.name for f in src_files],
                "has_summary": (p / "project_summary.txt").exists(),
                "summary": summary,
                "modified": p.stat().st_mtime,
            })
    return projects[:20]


@app.get("/project/{slug}/summary")
async def project_summary(slug: str):
    """Return project_summary.txt content."""
    path = ROOT / "workspace" / "projects" / slug / "project_summary.txt"
    if path.exists():
        return {"summary": path.read_text(encoding="utf-8")}
    return {"summary": "Özet bulunamadı."}


@app.get("/download/{project_slug}")
async def download_project(project_slug: str):
    """Projenin src/ ve tests/ klasörlerini ZIP olarak indir."""
    project_root = ROOT / "workspace" / "projects" / project_slug

    if not project_root.exists():
        raise HTTPException(404, f"Proje bulunamadı: {project_slug}")

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder in ["src", "tests", "docs"]:
            folder_path = project_root / folder
            if folder_path.exists():
                for file in folder_path.iterdir():
                    if file.is_file() and file.name != ".gitkeep":
                        arcname = f"{project_slug}/{folder}/{file.name}"
                        zf.write(file, arcname)

        for extra in ["plan.json", "project_summary.txt"]:
            extra_path = project_root / extra
            if extra_path.exists():
                zf.write(extra_path, f"{project_slug}/{extra}")

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={project_slug}.zip"
        }
    )


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
