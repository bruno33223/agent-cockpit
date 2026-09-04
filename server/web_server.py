import os
import sys
import json
import asyncio
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))
from state_store import db

app = FastAPI(title="Agent Cockpit Offline Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        # Envia estado inicial completo ao conectar
        await websocket.send_text(json.dumps({
            "event": "STATE_FULL",
            "payload": db.get_state()
        }, ensure_ascii=False))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    def broadcast_sync(self, event_type: str, payload: dict):
        """Chamado pelo StateStore a partir de qualquer thread."""
        if self.loop and self.active_connections:
            asyncio.run_coroutine_threadsafe(
                self._broadcast(event_type, payload),
                self.loop
            )

    async def _broadcast(self, event_type: str, payload: dict):
        message = json.dumps({"event": event_type, "payload": payload}, ensure_ascii=False)
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        for d in disconnected:
            self.disconnect(d)

manager = ConnectionManager()

# Registra o broadcast no StateStore para eventos automáticos
db.register_listener(manager.broadcast_sync)

@app.on_event("startup")
async def startup_event():
    manager.loop = asyncio.get_running_loop()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data_text = await websocket.receive_text()
            try:
                msg = json.loads(data_text)
                action = msg.get("action")
                if action == "USER_STEERING":
                    text = msg.get("text", "")
                    if text.strip():
                        db.add_user_steering(text.strip())
                elif action == "RESET_STATE":
                    db.reset_state()
                elif action == "APPROVE_GATE":
                    gate = msg.get("gate", "gate_ship_approved")
                    db.approve_gate(gate, "web_user")
                elif action == "GET_STATE":
                    await websocket.send_text(json.dumps({
                        "event": "STATE_FULL",
                        "payload": db.get_state()
                    }, ensure_ascii=False))
            except Exception as e:
                print(f"[WebSocket] Erro ao processar mensagem do cliente: {e}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/api/state")
def get_state():
    return db.get_state()

class SteeringPayload(BaseModel):
    text: str

@app.post("/api/steering")
def post_steering(payload: SteeringPayload):
    if not payload.text.strip():
        return {"error": "Texto não pode ser vazio"}
    msg = db.add_user_steering(payload.text.strip())
    return {"status": "ok", "message": msg}

@app.post("/api/reset")
def post_reset():
    state = db.reset_state()
    return {"status": "ok", "state": state}

@app.get("/api/health")
def get_health():
    return {"status": "healthy", "service": "agent-cockpit"}

@app.get("/api/graph")
def get_graph():
    from code_graph import get_graph_elements_for_ui
    return get_graph_elements_for_ui(".")

@app.get("/api/metrics")
def get_metrics():
    return db.get_metrics()

class GateApprovalPayload(BaseModel):
    gate: str = "gate_ship_approved"
    approved_by: str = "user"

@app.post("/api/gates/approve")
def post_approve_gate(payload: GateApprovalPayload):
    return db.approve_gate(payload.gate, payload.approved_by)

@app.get("/api/handoff")
def get_handoff():
    import workflow_lock
    data = workflow_lock.read_latest_handoff(".")
    if not data:
        return {"status": "NO_HANDOFF_FOUND", "content": "# Nenhum HANDOFF.md encontrado\nExecute a tool MCP `generate_handoff` na conclusão do Épico."}
    return data

# Monta arquivos estáticos do dashboard visual
WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))
if os.path.exists(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
