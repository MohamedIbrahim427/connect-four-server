import asyncio
import json
import os
from datetime import datetime
from aiohttp import web, WSMsgType

PORT = int(os.environ.get("PORT", 8765))

waiting_player = None   # holds the first ws waiting for a match
pairs = {}              # maps ws -> partner ws

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

async def safe_send(ws, data):
    try:
        await ws.send_str(json.dumps(data))
    except Exception:
        pass

# ── Serve the game HTML ──────────────────────────────────────────────
async def index(request):
    return web.FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))

# ── WebSocket handler ────────────────────────────────────────────────
async def websocket_handler(request):
    global waiting_player

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    addr = request.remote

    # ── Auto-matchmaking ─────────────────────────────────────────────
    if waiting_player is None:
        # First player — wait for a partner
        waiting_player = ws
        log(f"+ Player 1 waiting: {addr}")
        await safe_send(ws, {"type": "waiting"})
    else:
        # Second player — pair them up and start the game
        partner = waiting_player
        waiting_player = None

        pairs[ws]      = partner
        pairs[partner] = ws

        log(f"+ Player 2 joined: {addr} — game starting!")
        await safe_send(partner, {"type": "start", "player": 1})
        await safe_send(ws,      {"type": "start", "player": 2})

    # ── Message relay loop ───────────────────────────────────────────
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue

                t = data.get("type")
                partner = pairs.get(ws)

                if t in ("move", "restart") and partner:
                    await safe_send(partner, data)

            elif msg.type == WSMsgType.ERROR:
                break

    finally:
        log(f"- Disconnected: {addr}")

        # If they were still waiting, clear the slot
        if waiting_player is ws:
            waiting_player = None

        # Notify partner and clean up
        partner = pairs.pop(ws, None)
        if partner:
            pairs.pop(partner, None)
            await safe_send(partner, {"type": "opponent_left"})

    return ws


app = web.Application()
app.router.add_get("/",   index)
app.router.add_get("/ws", websocket_handler)

if __name__ == "__main__":
    log(f"Connect Four server starting on port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)
