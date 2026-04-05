"""
api/dashboard_ws.py
WebSocket real-time event bus for the MAOS live dashboard.

Exposes:
  GET  /ws/dashboard          – WebSocket stream (JSON events)
  GET  /api/dashboard/state   – REST snapshot of current state

Import and call from anywhere:
    from api.dashboard_ws import event_bus
    asyncio.ensure_future(event_bus.broadcast({"type": "...", ...}))
"""
import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Singleton Event Bus
# ---------------------------------------------------------------------------

class DashboardEventBus:
    """
    Central broadcast hub for MAOS dashboard events.

    Usage (from orchestrator / agents):
        from api.dashboard_ws import event_bus
        asyncio.ensure_future(event_bus.broadcast({"type": "agent_status", ...}))
    """

    def __init__(self):
        self._clients: set[WebSocket] = set()
        # Keep last 100 events for state-replay on new connections
        self._recent_events: deque[dict] = deque(maxlen=100)
        # Per-agent last-known state
        self._agent_states: dict[str, dict] = {
            name: {"agent": name, "status": "idle", "model": "", "ts": ""}
            for name in [
                "planner", "researcher", "executor", "coder",
                "coder_fast", "critic", "optimizer",
            ]
        }
        self._current_task: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def broadcast(self, event: dict) -> None:
        """Fire-and-forget broadcast to all connected WebSocket clients."""
        if not isinstance(event, dict):
            return

        # Stamp with UTC time if missing
        if "ts" not in event:
            event["ts"] = datetime.now(timezone.utc).strftime("%H:%M:%S")

        # Update cached state for replaying to new clients
        self._recent_events.append(event)
        self._update_state(event)

        if not self._clients:
            return

        payload = json.dumps(event, ensure_ascii=False)
        dead: set[WebSocket] = set()

        for ws in list(self._clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)

        self._clients -= dead

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_state(self, event: dict) -> None:
        """Keep agent_states and current_task up-to-date from each event."""
        etype = event.get("type", "")

        if etype == "agent_status":
            agent = event.get("agent", "")
            if agent and agent in self._agent_states:
                self._agent_states[agent] = {
                    "agent": agent,
                    "status": event.get("status", "idle"),
                    "model": event.get("model", self._agent_states[agent].get("model", "")),
                    "ts": event.get("ts", ""),
                }

        elif etype == "task_start":
            self._current_task = event.get("task", "")

    def _snapshot(self) -> dict:
        """Build the current state snapshot sent to new connections."""
        return {
            "type": "snapshot",
            "agents": list(self._agent_states.values()),
            "current_task": self._current_task,
            "recent_events": list(self._recent_events),
            "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        }

    # ------------------------------------------------------------------
    # WebSocket lifecycle
    # ------------------------------------------------------------------

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        # Send full state snapshot immediately
        try:
            await ws.send_text(json.dumps(self._snapshot(), ensure_ascii=False))
        except Exception:
            pass
        logger.info("[Dashboard WS] client connected — total %d", len(self._clients))

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)
        logger.info("[Dashboard WS] client disconnected — total %d", len(self._clients))


# Module-level singleton
event_bus = DashboardEventBus()


# ---------------------------------------------------------------------------
# Convenience helper for fire-and-forget usage outside async context
# ---------------------------------------------------------------------------

def ws_broadcast(event: dict) -> None:
    """
    Thread/sync-safe wrapper — schedules broadcast on the running event loop.
    Silently does nothing if no loop is running.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(event_bus.broadcast(event))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# Allowed inbound WebSocket message types from clients
_ALLOWED_WS_TYPES = {"ping", "pong", "subscribe", "unsubscribe"}
_MAX_WS_MESSAGE_LEN = 1024  # Max message size from client


@router.websocket("/ws/dashboard")
async def websocket_dashboard(ws: WebSocket):
    """WebSocket endpoint — streams all MAOS events as JSON lines."""
    await event_bus.connect(ws)
    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=30.0)

                # Size check
                if len(data) > _MAX_WS_MESSAGE_LEN:
                    await ws.send_text(json.dumps({"type": "error", "message": "Message too large"}))
                    continue

                # Simple string commands
                if data in ("ping", "pong"):
                    await ws.send_text(json.dumps({"type": "pong"}))
                    continue

                # JSON payload validation
                try:
                    msg = json.loads(data)
                except (json.JSONDecodeError, ValueError):
                    await ws.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                    continue

                if not isinstance(msg, dict):
                    await ws.send_text(json.dumps({"type": "error", "message": "Expected JSON object"}))
                    continue

                msg_type = msg.get("type", "")
                if msg_type not in _ALLOWED_WS_TYPES:
                    await ws.send_text(json.dumps({"type": "error", "message": f"Unknown type: {msg_type}"}))
                    continue

                # Handle known types
                if msg_type == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))

            except asyncio.TimeoutError:
                try:
                    await ws.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        event_bus.disconnect(ws)


@router.get("/api/dashboard/state")
async def dashboard_state():
    """REST snapshot — used by the HTML dashboard on initial load."""
    return event_bus._snapshot()
