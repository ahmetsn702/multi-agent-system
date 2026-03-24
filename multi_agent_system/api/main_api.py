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
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
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

app = FastAPI(title="Multi-Agent System API", version="1.0.0")

# Allow all origins (local network access from Android browser)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (index.html, manifest, icons)
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Dashboard WebSocket router
from api.dashboard_ws import router as _dashboard_ws_router  # noqa: E402
app.include_router(_dashboard_ws_router)

# ── Auth config ────────────────────────────────────────────────────────────
WEB_PASSWORD = os.getenv("WEB_PASSWORD")  # Must be set in .env
SESSION_TOKEN = "mas_session"          # cookie name
# Public paths that don't need auth
PUBLIC = {"/login", "/health", "/static", "/ws/dashboard", "/api/dashboard/state"}

# ── Brute Force Koruması ────────────────────────────────────────────────────
MAX_ATTEMPTS = 5          # Maks hatalı deneme
LOCKOUT_MINUTES = 15      # Kilitleme süresi (dakika)
_login_attempts: dict[str, list] = {}  # ip -> [timestamp, ...]

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def _is_locked(ip: str) -> tuple[bool, int]:
    """IP kilitli mi? (kilitli_mi, kalan_saniye)"""
    now = datetime.now()
    cutoff = now - timedelta(minutes=LOCKOUT_MINUTES)
    attempts = [t for t in _login_attempts.get(ip, []) if t > cutoff]
    _login_attempts[ip] = attempts
    if len(attempts) >= MAX_ATTEMPTS:
        oldest = min(attempts)
        unlock_at = oldest + timedelta(minutes=LOCKOUT_MINUTES)
        remaining = int((unlock_at - now).total_seconds())
        return True, max(remaining, 0)
    return False, 0

def _record_failed(ip: str):
    if ip not in _login_attempts:
        _login_attempts[ip] = []
    _login_attempts[ip].append(datetime.now())

def _clear_attempts(ip: str):
    _login_attempts.pop(ip, None)

from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Allow public paths
        if (
            path == "/login"
            or path.startswith("/static")
            or path == "/health"
            or path == "/ws/dashboard"
            or path.startswith("/api/dashboard")
        ):
            return await call_next(request)
        # Check cookie
        token = request.cookies.get(SESSION_TOKEN)
        if token != WEB_PASSWORD:
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

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return HTMLResponse(LOGIN_HTML.replace("%ERROR%", ""))

@app.post("/login")
async def login_submit(request: Request):
    ip = _get_client_ip(request)
    locked, remaining = _is_locked(ip)
    if locked:
        mins = remaining // 60
        secs = remaining % 60
        msg = f'<p class="err" style="display:block">🔒 Çok fazla hatalı deneme! {mins}d {secs}s sonra tekrar dene.</p>'
        return HTMLResponse(LOGIN_HTML.replace("%ERROR%", msg), status_code=429)
    form = await request.form()
    password = form.get("password", "")
    if password == WEB_PASSWORD:
        _clear_attempts(ip)
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(SESSION_TOKEN, WEB_PASSWORD, httponly=True, max_age=86400*30)
        return response
    _record_failed(ip)
    locked2, _ = _is_locked(ip)
    remaining_attempts = MAX_ATTEMPTS - len(_login_attempts.get(ip, []))
    if locked2:
        msg = f'<p class="err" style="display:block">🔒 Hesap {LOCKOUT_MINUTES} dakika kilitlendi!</p>'
    else:
        msg = f'<p class="err" style="display:block">❌ Yanlış şifre ({remaining_attempts} hakkın kaldı)</p>'
    return HTMLResponse(LOGIN_HTML.replace("%ERROR%", msg), status_code=401)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(SESSION_TOKEN)
    return response



# ── In-memory session store ────────────────────────────────────────────────
sessions: dict[str, dict] = {}   # session_id → {status, logs, result}


# ── Request / Response models ──────────────────────────────────────────────
class GoalRequest(BaseModel):
    goal: str


# ── Helper ─────────────────────────────────────────────────────────────────
def _build_agents():
    from core.message_bus import bus
    from agents.planner_agent import PlannerAgent
    from agents.researcher_agent import ResearcherAgent
    from agents.coder_agent import CoderAgent
    from agents.critic_agent import CriticAgent
    from agents.executor_agent import ExecutorAgent
    from agents.analyzer_agent import AnalyzerAgent
    return {
        "planner":    PlannerAgent(bus=bus),
        "researcher": ResearcherAgent(bus=bus),
        "coder":      CoderAgent(agent_id="coder", bus=bus),
        "coder_fast": CoderAgent(agent_id="coder_fast", bus=bus),
        "critic":     CriticAgent(bus=bus),
        "executor":   ExecutorAgent(bus=bus),
        "analyzer":   AnalyzerAgent(bus=bus),
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
        "started_at": datetime.now().isoformat(),
    }

    async def _background():
        from core.orchestrator import Orchestrator

        async def status_cb(msg: str):
            sessions[session_id]["logs"].append(msg)

        try:
            agents = _build_agents()
            orch = Orchestrator(agents=agents, status_callback=status_cb)
            result = await orch.run(req.goal)
            sessions[session_id]["status"] = "done"
            sessions[session_id]["result"] = result.get("output", "")
        except Exception as e:
            sessions[session_id]["status"] = "error"
            sessions[session_id]["result"] = str(e)

    asyncio.create_task(_background())
    return {"session_id": session_id}


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


@app.get("/sessions")
async def list_sessions():
    """Return summary of all sessions."""
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
            summary_text = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""
            summary = summary_text[:300] if summary_text else ""
            
            pylint_score = None
            if summary_text:
                import re
                match = re.search(r"Kod Kalitesi\s*:\s*([0-9.]+)/10\s*\(Pylint\)", summary_text)
                if match:
                    pylint_score = match.group(1)

            projects.append({
                "name": p.name,
                "files": len(src_files),
                "file_names": [f.name for f in src_files],
                "has_summary": (p / "project_summary.txt").exists(),
                "summary": summary,
                "pylint_score": pylint_score,
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


# ── Reverse Engineering: /analyze endpoint ──────────────────────────────────

@app.post("/analyze")
async def analyze_project_endpoint(request: Request):
    """
    Mevcut projeyi analiz et — klasör yolu, ZIP veya GitHub URL kabul eder.
    Body: { "source": "yol_ya_da_url", "question": "isteğe bağlı soru" }
    """
    body = await request.json()
    source = body.get("source", "").strip()
    question = body.get("question", "Bu projeyi analiz et ve sorunları bul")

    if not source:
        raise HTTPException(400, "source alanı boş olamaz")

    from agents.analyzer_agent import AnalyzerAgent
    from core.base_agent import Task

    analyzer = AnalyzerAgent()
    task = Task(
        task_id="analyze_api",
        description=question,
        assigned_to="analyzer",
        context={"source": source},
    )

    try:
        response = await analyzer.run(task)
        if not response.success:
            raise HTTPException(500, f"Analiz hatası: {response.error}")

        content = response.content
        return {
            "project_name": content.get("project_name"),
            "source": source,
            "stats": content.get("stats"),
            "project_purpose": content.get("project_purpose"),
            "tech_stack": content.get("tech_stack"),
            "bugs_found": content.get("bugs_found"),
            "missing_features": content.get("missing_features"),
            "security_issues": content.get("security_issues"),
            "fix_plan": content.get("fix_plan"),
            "summary": content.get("summary"),
            "structure": content.get("structure"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Beklenmeyen hata: {e}")



@app.post("/plan")
async def create_plan(request: Request):
    """
    Hedefi al, plan üret, kullanıcıya göster. Çalıştırma.
    """
    body = await request.json()
    goal = body.get("goal", "").strip()
    
    if not goal:
        raise HTTPException(400, "Hedef boş olamaz")
    
    from agents.planner_agent import PlannerAgent
    from core.message_bus import bus
    
    planner = PlannerAgent(bus=bus)
    
    # Planı üret ama çalıştırma
    plan_result = await planner.create_plan(goal)
    
    return {
        "goal": goal,
        "plan": plan_result,
        "phases": _format_phases(plan_result),
        "summary": _plan_summary(plan_result),
    }


@app.post("/run-with-plan")
async def run_with_plan(request: Request):
    """
    Onaylanan veya düzenlenmiş planı çalıştır (SSE stream).
    """
    body = await request.json()
    goal = body.get("goal", "").strip()
    approved_plan = body.get("plan")           # Kullanıcının onayladığı plan
    user_feedback = body.get("feedback", "")   # Kullanıcının yorumları
    
    if not goal:
        raise HTTPException(400, "Hedef boş olamaz")
    
    # Feedback varsa planı güncelle
    if user_feedback:
        goal = f"{goal}\n\nKullanıcı notu: {user_feedback}"
    
    async def event_generator():
        from core.orchestrator import Orchestrator
        import json
        import asyncio
        
        log_queue = asyncio.Queue()
        
        async def log_callback(message: str, level: str = "info"):
            await log_queue.put({"message": message, "level": level})
        
        async def run():
            try:
                agents = _build_agents()
                orch = Orchestrator(agents=agents, status_callback=log_callback)
                
                # Onaylı planı yükle
                if approved_plan:
                    orch.preloaded_plan = approved_plan
                
                result = await orch.run(user_goal=goal)
                await log_queue.put({"done": True, "result": result})
            except Exception as e:
                await log_queue.put({"done": True, "error": str(e)})
        
        task = asyncio.create_task(run())
        
        while True:
            try:
                item = await asyncio.wait_for(log_queue.get(), timeout=1.0)
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if item.get("done"):
                    break
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'ping': True})}\n\n"
        
        await task
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _format_phases(plan_result: dict) -> list:
    """Plan sonucunu okunabilir faz listesine çevir."""
    phases = []
    raw_phases = plan_result.get("phases", [])
    
    for i, phase in enumerate(raw_phases, 1):
        tasks = phase.get("tasks", [])
        phases.append({
            "phase_number": i,
            "name": phase.get("name", f"Faz {i}"),
            "task_count": len(tasks),
            "tasks": [
                {
                    "id": t.task_id if hasattr(t, 'task_id') else f"t{j}",
                    "description": t.description if hasattr(t, 'description') else str(t),
                    "agent": t.assigned_to if hasattr(t, 'assigned_to') else "",
                }
                for j, t in enumerate(tasks, 1)
            ],
        })
    
    return phases


def _plan_summary(plan_result: dict) -> str:
    """Plan özeti üret."""
    phases = plan_result.get("phases", [])
    tasks = plan_result.get("tasks", [])
    
    if phases:
        total_tasks = sum(len(p.get("tasks", [])) for p in phases)
        return f"{len(phases)} faz, {total_tasks} görev"
    else:
        return f"{len(tasks)} görev"


# ── V5: Dashboard & API endpoints ─────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MAOS V5 — Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  body { font-family: 'Inter', sans-serif; background: #0a0a12; }
  .glass { background: rgba(255,255,255,0.04); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.08); }
  .glow { box-shadow: 0 0 30px rgba(124,58,237,0.15); }
  .pulse-dot { animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.5;transform:scale(1.2)} }
  .badge-running { background:#7c3aed22; color:#a78bfa; border:1px solid #7c3aed44; }
  .badge-done    { background:#05966922; color:#34d399; border:1px solid #05966944; }
  .badge-error   { background:#dc262622; color:#f87171; border:1px solid #dc262644; }
  .stat-card:hover { transform:translateY(-2px); transition:all .3s ease; }
  .progress-bar { background: linear-gradient(90deg, #7c3aed, #9333ea); border-radius:4px; height:6px; transition: width 0.5s ease; }
  ::-webkit-scrollbar { width:5px } ::-webkit-scrollbar-track { background:#111 } ::-webkit-scrollbar-thumb { background:#7c3aed; border-radius:5px }
</style>
</head>
<body class="min-h-screen text-gray-100 p-4 md:p-8">

<!-- Header -->
<div class="flex items-center justify-between mb-8">
  <div class="flex items-center gap-3">
    <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-600 to-purple-700 flex items-center justify-center text-xl">🤖</div>
    <div>
      <h1 class="text-xl font-bold text-white">MAOS V5 Dashboard</h1>
      <p class="text-xs text-gray-500">Multi-Agent Orchestration System</p>
    </div>
  </div>
  <div class="flex items-center gap-2 text-xs text-gray-400">
    <span class="pulse-dot w-2 h-2 rounded-full bg-green-400 inline-block"></span>
    <span id="last-update">Yükleniyor...</span>
    <span class="ml-2 text-gray-600">• 10s yenileme</span>
  </div>
</div>

<!-- Stat Cards -->
<div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8" id="stat-cards">
  <div class="glass rounded-2xl p-5 stat-card glow">
    <div class="text-gray-400 text-xs font-medium mb-1">Toplam Oturum</div>
    <div class="text-3xl font-bold text-white" id="total-sessions">—</div>
    <div class="text-xs text-violet-400 mt-1">tüm zamanlar</div>
  </div>
  <div class="glass rounded-2xl p-5 stat-card">
    <div class="text-gray-400 text-xs font-medium mb-1">Aktif Oturum</div>
    <div class="text-3xl font-bold text-green-400" id="active-sessions">—</div>
    <div class="text-xs text-gray-500 mt-1">şu an çalışıyor</div>
  </div>
  <div class="glass rounded-2xl p-5 stat-card">
    <div class="text-gray-400 text-xs font-medium mb-1">Toplam Maliyet</div>
    <div class="text-3xl font-bold text-amber-400" id="total-cost">—</div>
    <div class="text-xs text-gray-500 mt-1">USD</div>
  </div>
  <div class="glass rounded-2xl p-5 stat-card">
    <div class="text-gray-400 text-xs font-medium mb-1">Toplam Token</div>
    <div class="text-3xl font-bold text-sky-400" id="total-tokens">—</div>
    <div class="text-xs text-gray-500 mt-1">kullanılan</div>
  </div>
</div>

<div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">

<!-- Sessions -->
<div class="glass rounded-2xl p-6">
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-sm font-semibold text-gray-300">📋 Son Oturumlar</h2>
    <span class="text-xs text-gray-500" id="session-count">—</span>
  </div>
  <div id="sessions-list" class="space-y-3 max-h-80 overflow-y-auto pr-1">
    <div class="text-gray-600 text-sm text-center py-8">Yükleniyor...</div>
  </div>
</div>

<!-- Model Token Usage -->
<div class="glass rounded-2xl p-6">
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-sm font-semibold text-gray-300">💰 Agent & Maliyet</h2>
    <span class="text-xs text-gray-500">model bazlı</span>
  </div>
  <div id="costs-list" class="space-y-3 max-h-80 overflow-y-auto pr-1">
    <div class="text-gray-600 text-sm text-center py-8">Yükleniyor...</div>
  </div>
</div>

</div>

<!-- Tasks -->
<div class="glass rounded-2xl p-6">
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-sm font-semibold text-gray-300">⚡ Son Görevler</h2>
    <a href="/" class="text-xs text-violet-400 hover:text-violet-300 transition">→ Ana Sayfa</a>
  </div>
  <div id="tasks-list" class="space-y-2 max-h-60 overflow-y-auto pr-1">
    <div class="text-gray-600 text-sm text-center py-8">Yükleniyor...</div>
  </div>
</div>

<script>
function badge(status) {
  const cls = status === 'running' ? 'badge-running' : status === 'done' ? 'badge-done' : 'badge-error';
  const label = status === 'running' ? '● Çalışıyor' : status === 'done' ? '✓ Tamamlandı' : '✗ Hata';
  return `<span class="text-xs px-2 py-0.5 rounded-full font-medium ${cls}">${label}</span>`;
}
function fmtNum(n) {
  if (n >= 1000000) return (n/1000000).toFixed(1)+'M';
  if (n >= 1000) return (n/1000).toFixed(1)+'K';
  return n.toString();
}
function fmtTime(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('tr-TR', {hour:'2-digit',minute:'2-digit',day:'2-digit',month:'short'}); }
  catch { return iso; }
}

async function refresh() {
  try {
    const [sesRes, costRes, taskRes] = await Promise.all([
      fetch('/api/sessions'), fetch('/api/costs'), fetch('/api/tasks')
    ]);
    const sessions = await sesRes.json();
    const costs    = await costRes.json();
    const tasks    = await taskRes.json();

    // Stats
    document.getElementById('total-sessions').textContent = sessions.length;
    document.getElementById('active-sessions').textContent = sessions.filter(s=>s.status==='running').length;
    document.getElementById('total-cost').textContent = '$' + costs.total_cost_usd.toFixed(4);
    document.getElementById('total-tokens').textContent = fmtNum(costs.total_tokens);
    document.getElementById('session-count').textContent = sessions.length + ' oturum';

    // Sessions
    const sl = document.getElementById('sessions-list');
    if (sessions.length === 0) {
      sl.innerHTML = '<div class="text-gray-600 text-sm text-center py-8">Henüz oturum yok</div>';
    } else {
      sl.innerHTML = sessions.slice(0,15).map(s => `
        <div class="flex items-center justify-between gap-3 bg-white/[0.03] rounded-xl px-4 py-3 hover:bg-white/[0.05] transition">
          <div class="flex-1 min-w-0">
            <div class="text-sm text-gray-200 truncate font-medium">${s.goal || '—'}</div>
            <div class="text-xs text-gray-500 mt-0.5">${fmtTime(s.started_at)}</div>
          </div>
          ${badge(s.status)}
        </div>`).join('');
    }

    // Costs
    const cl = document.getElementById('costs-list');
    const agents = Object.entries(costs.by_agent || {});
    if (agents.length === 0) {
      cl.innerHTML = '<div class="text-gray-600 text-sm text-center py-8">Henüz token kullanımı yok</div>';
    } else {
      const maxCost = Math.max(...agents.map(([,v])=>v.total_cost), 0.0001);
      cl.innerHTML = agents.sort((a,b)=>b[1].total_cost-a[1].total_cost).map(([agent,v]) => `
        <div class="bg-white/[0.03] rounded-xl px-4 py-3">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-medium text-gray-200">${agent}</span>
            <span class="text-xs text-amber-400 font-semibold">$${v.total_cost.toFixed(5)}</span>
          </div>
          <div class="bg-white/5 rounded-full overflow-hidden">
            <div class="progress-bar" style="width:${Math.min(100,(v.total_cost/maxCost)*100)}%"></div>
          </div>
          <div class="flex gap-3 mt-2 text-xs text-gray-500">
            <span>↑ ${fmtNum(v.prompt_tokens)} in</span>
            <span>↓ ${fmtNum(v.completion_tokens)} out</span>
            <span>Σ ${fmtNum(v.total_tokens)}</span>
          </div>
        </div>`).join('');
    }

    // Tasks
    const tl = document.getElementById('tasks-list');
    if (tasks.length === 0) {
      tl.innerHTML = '<div class="text-gray-600 text-sm text-center py-8">Henüz görev yok</div>';
    } else {
      tl.innerHTML = tasks.slice(0,20).map(t => `
        <div class="flex items-center gap-3 bg-white/[0.03] rounded-xl px-4 py-2.5 hover:bg-white/[0.05] transition">
          <div class="flex-1 min-w-0">
            <span class="text-sm text-gray-300 truncate">${t.description || '—'}</span>
            <span class="text-xs text-gray-600 ml-2">→ ${t.assigned_to || '?'}</span>
          </div>
          ${badge(t.status || 'done')}
        </div>`).join('');
    }

    document.getElementById('last-update').textContent = new Date().toLocaleTimeString('tr-TR');
  } catch(e) {
    console.error('Refresh error:', e);
  }
}

refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>"""


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """MAOS V5 Web Dashboard."""
    return HTMLResponse(DASHBOARD_HTML)


@app.get("/api/sessions")
async def api_sessions():
    """Tüm session'ları döndür (dashboard için)."""
    return [
        {
            "session_id": sid,
            "goal": s.get("goal", "")[:80],
            "status": s.get("status", "unknown"),
            "started_at": s.get("started_at", ""),
            "log_count": len(s.get("logs", [])),
        }
        for sid, s in sessions.items()
    ]


@app.get("/api/costs")
async def api_costs():
    """Token kullanımı ve maliyet istatistikleri (dashboard için)."""
    from core.llm_client import token_tracker
    by_agent = token_tracker.get_all()
    total_tokens = sum(v["total_tokens"] for v in by_agent.values())
    total_cost   = token_tracker.estimated_cost_usd()
    return {
        "total_cost_usd": total_cost,
        "total_tokens": total_tokens,
        "by_agent": by_agent,
        "session_count": len(sessions),
    }


@app.get("/api/tasks")
async def api_tasks():
    """Son görevlerin özetini döndür (dashboard için)."""
    tasks = []
    for sid, s in list(sessions.items())[-20:]:
        logs = s.get("logs", [])
        for log in logs:
            if isinstance(log, str) and ("→" in log or "✓" in log or "✗" in log):
                tasks.append({
                    "session_id": sid,
                    "description": log[:100],
                    "assigned_to": "",
                    "status": "done" if "✓" in log else ("error" if "✗" in log else "running"),
                })
    return tasks[-30:]


# ── V5: Memory Agent endpoints ─────────────────────────────────────────────

@app.get("/memory")
async def get_memory():
    """Tüm kayıtlı projeleri listele."""
    try:
        from core.memory_agent import get_memory_agent
        memory = get_memory_agent()
        projects = memory.list_all()
        return {"projects": projects}
    except Exception as e:
        raise HTTPException(500, f"Memory hatası: {e}")


@app.post("/memory/search")
async def search_memory(request: Request):
    """Belirli bir hedefe göre ilgili projeleri ara."""
    try:
        body = await request.json()
        goal = body.get("goal", "").strip()
        
        if not goal:
            raise HTTPException(400, "Hedef boş olamaz")
        
        from core.memory_agent import get_memory_agent
        memory = get_memory_agent()
        relevant = memory.search_relevant(goal, max_results=5)
        
        return {"goal": goal, "relevant_projects": relevant}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Arama hatası: {e}")
