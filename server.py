import asyncio
import json
import os
import websockets
from datetime import datetime

PORT = int(os.environ.get("PORT", 8765))

rooms = {}

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

async def safe_send(ws, data):
    try:
        await ws.send(json.dumps(data))
    except Exception:
        pass

async def handler(websocket):
    addr = websocket.remote_address
    log(f"+ Connected: {addr}")
    room_code = None

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                log(f"  Bad JSON from {addr}")
                continue

            t = msg.get("type")

            if t == "host":
                if room_code and room_code in rooms:
                    del rooms[room_code]

                code = msg.get("room", "").strip().upper()
                if not code or len(code) != 6:
                    await safe_send(websocket, {"type": "error", "message": "Invalid room code."})
                    continue

                if code in rooms:
                    await safe_send(websocket, {"type": "error", "message": "Room already exists."})
                    continue

                rooms[code] = {"host": websocket, "guest": None}
                room_code = code
                log(f"  Room created: {code} by {addr}")
                await safe_send(websocket, {"type": "room_created", "room": code})

            elif t == "join":
                code = msg.get("room", "").strip().upper()

                if code not in rooms:
                    await safe_send(websocket, {"type": "error", "message": f"Room '{code}' not found."})
                    continue

                if rooms[code]["guest"] is not None:
                    await safe_send(websocket, {"type": "error", "message": "Room is full."})
                    continue

                rooms[code]["guest"] = websocket
                room_code = code
                log(f"  {addr} joined room {code} — starting game")

                host_ws = rooms[code]["host"]
                await safe_send(host_ws,   {"type": "start", "player": 1})
                await safe_send(websocket, {"type": "start", "player": 2})

            elif t == "move":
                if not room_code or room_code not in rooms:
                    continue
                room   = rooms[room_code]
                target = room["guest"] if websocket is room["host"] else room["host"]
                if target:
                    await safe_send(target, {"type": "move", "col": msg["col"]})

            elif t == "restart":
                if not room_code or room_code not in rooms:
                    continue
                room   = rooms[room_code]
                target = room["guest"] if websocket is room["host"] else room["host"]
                if target:
                    await safe_send(target, {"type": "restart"})

            else:
                log(f"  Unknown type '{t}' from {addr}")

    except websockets.exceptions.ConnectionClosed:
        log(f"- Disconnected: {addr}")
    finally:
        if room_code and room_code in rooms:
            room  = rooms[room_code]
            other = room["guest"] if websocket is room["host"] else room["host"]
            if other:
                await safe_send(other, {"type": "opponent_left"})
            del rooms[room_code]
            log(f"  Room {room_code} closed")


async def main():
    log(f"Connect Four server starting on port {PORT}")
    async with websockets.serve(handler, "0.0.0.0", PORT):
        log(f"Listening on ws://0.0.0.0:{PORT}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
