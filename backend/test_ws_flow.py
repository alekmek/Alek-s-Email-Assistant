"""Test WebSocket flow to debug the stuck state issue."""
import asyncio
import json
import websockets
import struct
import numpy as np

async def test_flow():
    """Test the WebSocket flow with a simple message."""
    uri = "ws://localhost:8000/ws/audio"

    print("Connecting to WebSocket...")
    async with websockets.connect(uri) as ws:
        print("Connected!")

        # Wait for initial state
        initial = await ws.recv()
        print(f"Initial message: {initial}")

        # Start listening
        print("\nSending start_listening...")
        await ws.send(json.dumps({"type": "start_listening"}))

        # Generate some fake audio (silence for simplicity)
        # We need to simulate speech that will trigger STT
        # Actually, let's just send some audio frames and then end_of_speech

        # Generate 2 seconds of audio at 16kHz, 16-bit
        duration = 2  # seconds
        sample_rate = 16000
        samples = int(duration * sample_rate)

        # Generate a simple tone (440Hz) that might be interpreted as speech
        t = np.linspace(0, duration, samples, dtype=np.float32)
        tone = (np.sin(2 * np.pi * 440 * t) * 0.3 * 32767).astype(np.int16)
        audio_bytes = tone.tobytes()

        # Send audio in chunks
        chunk_size = 8192
        print(f"\nSending {len(audio_bytes)} bytes of audio in {len(audio_bytes) // chunk_size} chunks...")

        for i in range(0, len(audio_bytes), chunk_size):
            chunk = audio_bytes[i:i+chunk_size]
            await ws.send(chunk)
            await asyncio.sleep(0.05)  # Small delay between chunks

        # End speech
        print("\nSending end_of_speech...")
        await ws.send(json.dumps({"type": "end_of_speech"}))

        # Wait for responses
        print("\nWaiting for responses (30 second timeout)...")
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                if isinstance(msg, bytes):
                    print(f"  Audio: {len(msg)} bytes")
                else:
                    data = json.loads(msg)
                    print(f"  JSON: {data}")
                    if data.get("type") == "state" and data.get("data") == "idle":
                        print("\n>>> Got idle state! Flow completed successfully.")
                        break
        except asyncio.TimeoutError:
            print("\n>>> TIMEOUT! Never received idle state - flow is stuck!")
        except Exception as e:
            print(f"\n>>> Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_flow())
