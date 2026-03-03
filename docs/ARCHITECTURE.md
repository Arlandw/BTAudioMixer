# Architecture (Draft)

## Signal path
1. iPhone A2DP sink -> PipeWire source node
2. Peloton A2DP sink -> PipeWire source node
3. Mix bus applies per-input gains + soft limiter
4. Mixed bus routed to A2DP source for headphones

## Service model
- `bt-manager.service`
- `audio-engine.service`
- `btamixer-api.service`
- `btamixer-ui.service`

## MVP milestones
- [x] repo scaffold
- [ ] BlueZ adapter role binding
- [ ] PipeWire links + gain controls
- [ ] touchscreen UI faders
- [ ] reconnection state machine
