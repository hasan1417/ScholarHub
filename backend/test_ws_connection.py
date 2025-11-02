#!/usr/bin/env python3
"""
Test script to verify WebSocket endpoint is reachable
Run this while the backend is running to test the WebSocket connection.
"""

import asyncio
import websockets
import sys

async def test_websocket():
    # Test session ID (use a real one from your app)
    session_id = "7e7d2ca4-ea74-483d-97d5-adce8ef668bc"
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJnMjAyNDAzOTQwQGtmdXBtLmVkdS5zYSIsImV4cCI6MTc2MDU1MzM4NC41OTYyNjV9.jGjqXro_ynnD9ylBSq_P4QLV6qnoVs8DJRPsfhJm5uYn"

    uri = f"ws://localhost:8000/api/v1/collaboration/ws/{session_id}?token={token}&mode=yjs"

    print(f"🔌 Attempting to connect to: {uri}")
    print("=" * 80)

    try:
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket connected successfully!")
            print(f"   Connection state: {websocket.state}")

            # Wait a bit to see if server sends anything
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                print(f"📨 Received message: {message[:100]}...")
            except asyncio.TimeoutError:
                print("⏱️  No message received (timeout after 2s)")

            print("\n✅ WebSocket endpoint is WORKING!")

    except websockets.exceptions.InvalidStatusCode as e:
        print(f"❌ Invalid status code: {e.status_code}")
        print(f"   Headers: {e.headers}")
        if e.status_code == 403:
            print("   → Authentication failed (token invalid)")
        elif e.status_code == 404:
            print("   → Endpoint not found (check URL)")
        elif e.status_code == 1008:
            print("   → Server rejected connection (check backend logs)")

    except ConnectionRefusedError:
        print("❌ Connection refused!")
        print("   → Is the backend running on port 8000?")
        print("   → Run: uvicorn app.main:app --reload")

    except Exception as e:
        print(f"❌ Connection failed: {type(e).__name__}: {e}")

    print("=" * 80)

if __name__ == "__main__":
    print("\n🧪 WebSocket Connection Test")
    print("=" * 80)
    asyncio.run(test_websocket())
