"""Realtime LaTeX smoke test (automation-ready).

This script logs into the ScholarHub backend, provisions a collaboration session for the given paper, and
bridges two Yjs websocket connections. It then applies a change on connection A and asserts that connection B
observes the update. Optionally, it can trigger a compile request without providing `latex_source` to validate
CRDT fallback behaviour.

Usage (example):

```bash
python ops/smoke-tests/realtime_smoke.py \
    --api http://localhost:8000/api/v1 \
    --ws ws://localhost:8000/api/v1 \
    --email demo@example.com --password secret \
    --paper-id 123e4567-e89b-12d3-a456-426614174000
```

Dependencies: `httpx`, `websockets`, `y_py`, `ypy-websocket`. Run inside the backend venv or install locally.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from typing import Optional

import httpx
import websockets
from websockets import WebSocketClientProtocol
from y_py import YDoc
from ypy_websocket.websocket_provider import WebsocketProvider


@dataclass
class ClientWebsocketAdapter:
    """Adapters websockets' client protocol to the ypy_websocket interface."""

    protocol: WebSocketClientProtocol

    @property
    def path(self) -> str:
        return self.protocol.path

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        return await self.recv()

    async def send(self, message: bytes) -> None:
        await self.protocol.send(message)

    async def recv(self) -> bytes:
        message = await self.protocol.recv()
        if isinstance(message, str):
            return message.encode()
        return message


async def login(api_base: str, email: str, password: str) -> str:
    async with httpx.AsyncClient(base_url=api_base, timeout=30.0) as client:
        response = await client.post('/login', json={'email': email, 'password': password})
        response.raise_for_status()
        return response.json()['access_token']


async def find_or_create_session(api_base: str, token: str, paper_id: str) -> str:
    headers = {'Authorization': f'Bearer {token}'}
    async with httpx.AsyncClient(base_url=api_base, headers=headers, timeout=30.0) as client:
        response = await client.post('/collaboration/sessions', json={'paper_id': paper_id})
        response.raise_for_status()
        return response.json()['id']


async def connect_provider(doc: YDoc, ws_url: str, stop_event: asyncio.Event) -> None:
    async with websockets.connect(ws_url, ping_interval=None) as protocol:
        adapter = ClientWebsocketAdapter(protocol)
        async with WebsocketProvider(doc, adapter):
            await stop_event.wait()


async def run_smoke(args: argparse.Namespace) -> None:
    api_base = args.api.rstrip('/')
    ws_base = args.ws.rstrip('/') if args.ws else api_base.replace('http', 'ws', 1)

    token = await login(api_base, args.email, args.password)
    session_id = await find_or_create_session(api_base, token, args.paper_id)
    ws_url = f"{ws_base}/collaboration/ws/{session_id}?token={token}&mode=yjs"

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    doc_a = YDoc()
    doc_b = YDoc()
    change_event = asyncio.Event()

    def on_b_update(_txn):
        loop.call_soon_threadsafe(change_event.set)

    doc_b.observe_after_transaction(on_b_update)

    task_a = asyncio.create_task(connect_provider(doc_a, ws_url, stop_event))
    task_b = asyncio.create_task(connect_provider(doc_b, ws_url, stop_event))

    await asyncio.sleep(1.0)

    sample_text = args.sample or 'Realtime smoke test snippet.'
    with doc_a.begin_transaction() as txn:
        y_text = doc_a.get_text('main')
        y_text.insert(txn, y_text.length, sample_text)

    await asyncio.wait_for(change_event.wait(), timeout=args.timeout)

    if not args.skip_compile:
        headers = {'Authorization': f'Bearer {token}'}
        payload = {'paper_id': args.paper_id, 'latex_source': ''}
        async with httpx.AsyncClient(base_url=api_base, headers=headers, timeout=60.0) as client:
            response = await client.post('/latex/compile', json=payload)
            response.raise_for_status()
            data = response.json()
            if not data.get('success'):
                raise RuntimeError('Compile fallback did not succeed: ' + json.dumps(data))

    stop_event.set()
    await asyncio.gather(task_a, task_b, return_exceptions=True)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Realtime smoke test')
    parser.add_argument('--api', default=os.getenv('SH_API_BASE', 'http://localhost:8000/api/v1'))
    parser.add_argument('--ws', default=os.getenv('SH_WS_BASE'))
    parser.add_argument('--email', required=True)
    parser.add_argument('--password', required=True)
    parser.add_argument('--paper-id', required=True)
    parser.add_argument('--sample', default='Realtime smoke test snippet.')
    parser.add_argument('--timeout', type=float, default=5.0)
    parser.add_argument('--skip-compile', action='store_true')
    args = parser.parse_args(argv)

    asyncio.run(run_smoke(args))
    print('✅ Realtime smoke test passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
