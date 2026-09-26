"""FastAPI app: WebSocket stream at /ws, health at /health.

Run with:  python -m mirage.server
"""

from __future__ import annotations

import asyncio
import itertools
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from ..config import DetectorConfig, RuntimeConfig, SimConfig, load_dotenv
from .protocol import dumps
from .runtime import Runtime

# Messages the UI can afford to miss when it falls behind (the next one
# supersedes them). Everything else is always delivered.
DROPPABLE = {"tick", "terrain", "status"}


class Client:
    def __init__(self, ws: WebSocket, cid: str) -> None:
        self.ws = ws
        self.id = cid
        self.queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=48)

    def offer(self, kind: str, text: str) -> None:
        if self.queue.full():
            if kind in DROPPABLE:
                return
            # Behind: throw away superseded messages, keep the rest in order.
            keep = []
            while not self.queue.empty():
                item = self.queue.get_nowait()
                if item[0] not in DROPPABLE:
                    keep.append(item)
            for item in keep[-(self.queue.maxsize - 1):]:
                self.queue.put_nowait(item)
        self.queue.put_nowait((kind, text))


class Hub:
    def __init__(self) -> None:
        self.clients: dict[str, Client] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self._ids = itertools.count(1)

    def new_id(self) -> str:
        return f"c{next(self._ids)}"

    def publish(self, msg: dict, target: str | None = None) -> None:
        """Thread-safe: called from the runtime thread."""
        if self.loop is None:
            return
        text = dumps(msg)
        self.loop.call_soon_threadsafe(self._dispatch, msg.get("type", ""), text, target)

    def _dispatch(self, kind: str, text: str, target: str | None) -> None:
        if target is not None:
            client = self.clients.get(target)
            if client:
                client.offer(kind, text)
            return
        for client in list(self.clients.values()):
            client.offer(kind, text)


hub = Hub()
load_dotenv()
runtime = Runtime(SimConfig.from_env(), DetectorConfig.from_env(), RuntimeConfig.from_env(), hub.publish)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    hub.loop = asyncio.get_running_loop()
    if os.environ.get("MIRAGE_CHAIN", "1") != "0":
        try:
            from .chain import ChainBridge

            runtime.chain = ChainBridge.from_env(hub.publish)
        except Exception as exc:  # the chain is optional; everything else still runs
            print(f"[mirage] chain bridge disabled: {exc}")
    runtime.start()
    yield
    runtime.stop()
    if runtime.chain is not None:
        runtime.chain.stop()


app = FastAPI(title="MIRAGE", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health() -> dict:
    return {"status": runtime.status, "progress": runtime.progress, "world": runtime.world_id,
            "tick": runtime.world.sim.tick if runtime.world else 0, "clients": len(hub.clients)}


async def _sender(client: Client) -> None:
    while True:
        _, text = await client.queue.get()
        await client.ws.send_text(text)


@app.websocket("/ws")
async def stream(ws: WebSocket) -> None:
    await ws.accept()
    client = Client(ws, hub.new_id())
    hub.clients[client.id] = client
    sender = asyncio.create_task(_sender(client))
    try:
        client.offer("hello", dumps(runtime.hello()))
        client.offer("snapshot", dumps(await asyncio.to_thread(runtime.snapshot)))
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict):
                runtime.submit(msg, client.id)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        sender.cancel()
        hub.clients.pop(client.id, None)
