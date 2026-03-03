from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="BTAudioMixer API", version="0.1.0")

class MixerState(BaseModel):
    phone_gain: float = 0.5
    peloton_gain: float = 0.5
    master_gain: float = 0.8
    phone_connected: bool = False
    peloton_connected: bool = False
    headphones_connected: bool = False

STATE = MixerState()

@app.get('/health')
def health():
    return {"ok": True}

@app.get('/state', response_model=MixerState)
def get_state():
    return STATE

@app.post('/state', response_model=MixerState)
def set_state(next_state: MixerState):
    global STATE
    STATE = next_state
    return STATE
