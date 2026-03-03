from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from audio_engine.engine import AudioEngine
from bt_manager.manager import BTManager

app = FastAPI(title="BTAudioMixer API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bt = BTManager()
audio = AudioEngine()


class GainUpdate(BaseModel):
    phone_gain: float = Field(ge=0, le=1)
    peloton_gain: float = Field(ge=0, le=1)
    master_gain: float = Field(ge=0, le=1)


class RoleAssign(BaseModel):
    role: str
    mac: str


class RoleRequest(BaseModel):
    role: str


class NodeAssign(BaseModel):
    phone_node: str | None = None
    peloton_node: str | None = None
    output_node: str | None = None


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/status")
def status():
    return {
        "bluetooth": bt.refresh_status(),
        "audio": audio.status(),
    }


@app.post("/bt/assign")
def bt_assign(payload: RoleAssign):
    try:
        return bt.assign_role(payload.role, payload.mac)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/bt/pair")
def bt_pair(payload: RoleRequest):
    try:
        return bt.pair(payload.role)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/bt/connect")
def bt_connect(payload: RoleRequest):
    try:
        return bt.connect(payload.role)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/bt/disconnect")
def bt_disconnect(payload: RoleRequest):
    try:
        return bt.disconnect(payload.role)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/bt/reconnect-all")
def bt_reconnect_all():
    try:
        return bt.reconnect_all()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/audio/gains")
def audio_gains(payload: GainUpdate):
    return audio.set_gains(payload.phone_gain, payload.peloton_gain, payload.master_gain)


@app.post("/audio/nodes")
def audio_nodes(payload: NodeAssign):
    return audio.set_nodes(payload.phone_node, payload.peloton_node, payload.output_node)


@app.get("/audio/activity")
def audio_activity():
    return audio.activity()


app.mount("/ui", StaticFiles(directory="ui", html=True), name="ui")


@app.get("/")
def root():
    return FileResponse("ui/index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8787, reload=False)
