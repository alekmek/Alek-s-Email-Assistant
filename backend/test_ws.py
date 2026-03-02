#!/usr/bin/env python3
"""Test the WebSocket audio endpoint directly."""

import asyncio
import json
import sys
import wave
import io
import struct

import websockets


async def test_websocket():
    """Test the WebSocket connection and audio pipeline."""
    uri = "ws://localhost:8000/ws/audio"

    print(f"Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as ws:
            print("Connected!")

            # Read initial messages
            for _ in range(3):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(msg)
                    print(f"Received: {data}")
                except asyncio.TimeoutError:
                    print("Timeout waiting for message")
                    break

            # Send start_listening signal
            print("\nSending start_listening...")
            await ws.send(json.dumps({"type": "start_listening"}))

            # Read state change
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                data = json.loads(msg)
                print(f"State response: {data}")
            except asyncio.TimeoutError:
                print("Timeout waiting for state change")

            # Generate a simple audio chunk (silence with some noise)
            # PCM 16-bit mono 16kHz
            sample_rate = 16000
            duration = 0.5  # seconds
            num_samples = int(sample_rate * duration)

            # Create audio data - simple sine wave at 440Hz to simulate speech
            import math
            frequency = 440
            audio_data = []
            for i in range(num_samples):
                sample = int(32767 * 0.3 * math.sin(2 * math.pi * frequency * i / sample_rate))
                audio_data.append(struct.pack('<h', sample))

            audio_bytes = b''.join(audio_data)

            print(f"\nSending audio chunk ({len(audio_bytes)} bytes)...")
            await ws.send(audio_bytes)

            # Wait and read any responses
            print("Waiting for transcription...")
            for _ in range(5):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    if isinstance(msg, bytes):
                        print(f"Received audio bytes: {len(msg)} bytes")
                    else:
                        data = json.loads(msg)
                        print(f"Received: {data}")
                except asyncio.TimeoutError:
                    print("Timeout")
                    break

            # Send end_of_speech signal
            print("\nSending end_of_speech...")
            await ws.send(json.dumps({"type": "end_of_speech"}))

            # Wait for response
            print("Waiting for LLM response...")
            received_count = 0
            for _ in range(30):  # Wait up to 30 * 2 = 60 seconds
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    if isinstance(msg, bytes):
                        print(f"Received audio bytes: {len(msg)} bytes")
                        received_count += 1
                    else:
                        data = json.loads(msg)
                        print(f"Received: {data}")
                        received_count += 1
                        if data.get("type") == "state" and data.get("data") == "idle":
                            print("Got idle state - response complete!")
                            break
                except asyncio.TimeoutError:
                    if received_count == 0:
                        print(".", end="", flush=True)
                    else:
                        print("Timeout after receiving data")
                        break

            print(f"\nTotal messages received: {received_count}")
            print("Test complete!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    result = asyncio.run(test_websocket())
    sys.exit(0 if result else 1)
