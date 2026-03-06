import asyncio
import json
import os
from datetime import datetime
from aiohttp import web, WSMsgType

PORT = int(os.environ.get("PORT", 8765))

rooms = {}

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
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    addr = request.remote
    log(f"+ Connected: {addr}")
    room_code = None

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    log(f"  Bad JSON from {addr}")
                    continue

                t = data.get("type")

                if t == "host":
                    if room_code and room_code in rooms:
                        del rooms[room_code]
                    code = data.get("room", "").strip().upper()
                    if not code or len(code) != 6:
                        await safe_send(ws, {"type": "error", "message": "Invalid room code."})
                        continue
                    if code in rooms:
                        await safe_send(ws, {"type": "error", "message": "Room already exists."})
                        continue
                    rooms[code] = {"host": ws, "guest": None}
                    room_code = code
                    log(f"  Room created: {code} by {addr}")
                    await safe_send(ws, {"type": "room_created", "room": code})

                elif t == "join":
                    code = data.get("room", "").strip().upper()
                    if code not in rooms:
                        await safe_send(ws, {"type": "error", "message": f"Room '{code}' not found."})
                        continue
                    if rooms[code]["guest"] is not None:
                        await safe_send(ws, {"type": "error", "message": "Room is full."})
                        continue
                    rooms[code]["guest"] = ws
                    room_code = code
                    log(f"  {addr} joined room {code} — game starting")
                    await safe_send(rooms[code]["host"], {"type": "start", "player": 1})
                    await safe_send(ws,                  {"type": "start", "player": 2})

                elif t == "move":
                    if not room_code or room_code not in rooms:
                        continue
                    room   = rooms[room_code]
                    target = room["guest"] if ws is room["host"] else room["host"]
                    if target:
                        await safe_send(target, {"type": "move", "col": data["col"]})

                elif t == "restart":
                    if not room_code or room_code not in rooms:
                        continue
                    room   = rooms[room_code]
                    target = room["guest"] if ws is room["host"] else room["host"]
                    if target:
                        await safe_send(target, {"type": "restart"})

                else:
                    log(f"  Unknown type '{t}' from {addr}")

            elif msg.type == WSMsgType.ERROR:
                log(f"  WS error: {ws.exception()}")
                break

    finally:
        log(f"- Disconnected: {addr}")
        if room_code and room_code in rooms:
            room  = rooms[room_code]
            other = room["guest"] if ws is room["host"] else room["host"]
            if other:
                await safe_send(other, {"type": "opponent_left"})
            del rooms[room_code]
            log(f"  Room {room_code} closed")

    return ws


app = web.Application()
app.router.add_get("/",   index)               # serves the game
app.router.add_get("/ws", websocket_handler)   # WebSocket

if __name__ == "__main__":
    log(f"Connect Four server starting on port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)
