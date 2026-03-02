"""
Test script to simulate the voice conversation flow and identify issues.
"""
import asyncio
import json
import websockets
import sys

async def test_conversation_flow():
    uri = "ws://localhost:8000/ws/audio"

    print("=" * 60)
    print("VOICE FLOW TEST")
    print("=" * 60)

    try:
        async with websockets.connect(uri) as ws:
            print("\n[1] Connected to WebSocket")

            # Collect all messages for a period
            messages_received = []

            async def receive_messages(duration=2):
                """Receive messages for a duration"""
                end_time = asyncio.get_event_loop().time() + duration
                while asyncio.get_event_loop().time() < end_time:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        if isinstance(msg, bytes):
                            messages_received.append(f"[AUDIO] {len(msg)} bytes")
                            print(f"    <- [AUDIO] {len(msg)} bytes")
                        else:
                            data = json.loads(msg)
                            messages_received.append(data)
                            print(f"    <- {data}")
                    except asyncio.TimeoutError:
                        pass
                    except Exception as e:
                        print(f"    <- [ERROR] {e}")
                        break

            # Wait for initial state
            print("\n[2] Waiting for initial state...")
            await receive_messages(2)

            # Send start_listening
            print("\n[3] Sending start_listening signal...")
            await ws.send(json.dumps({"type": "start_listening"}))
            await receive_messages(1)

            # Check if we got listening state
            listening_received = any(
                isinstance(m, dict) and m.get("type") == "state" and m.get("data") == "listening"
                for m in messages_received
            )
            print(f"    Listening state received: {listening_received}")

            # Simulate sending some audio (silence)
            print("\n[4] Sending simulated audio (silence)...")
            silence = bytes(8192)  # Empty audio buffer
            for i in range(5):
                await ws.send(silence)
                await asyncio.sleep(0.1)
            print("    Sent 5 audio chunks")

            # Send end_of_speech
            print("\n[5] Sending end_of_speech signal...")
            await ws.send(json.dumps({"type": "end_of_speech"}))

            # Wait for processing and response
            print("\n[6] Waiting for response (up to 30 seconds)...")
            await receive_messages(30)

            # Analyze results
            print("\n" + "=" * 60)
            print("ANALYSIS")
            print("=" * 60)

            states_received = [
                m.get("data") for m in messages_received
                if isinstance(m, dict) and m.get("type") == "state"
            ]
            print(f"\nStates received: {states_received}")

            transcripts = [
                m for m in messages_received
                if isinstance(m, dict) and m.get("type") == "transcript"
            ]
            print(f"Transcripts received: {len(transcripts)}")

            audio_chunks = [m for m in messages_received if isinstance(m, str) and "[AUDIO]" in m]
            print(f"Audio chunks received: {len(audio_chunks)}")

            # Check for issues
            print("\n" + "=" * 60)
            print("ISSUES FOUND")
            print("=" * 60)

            if "listening" not in states_received:
                print("- ISSUE: Never received 'listening' state after start_listening")

            if "speaking" not in states_received:
                print("- ISSUE: Never received 'speaking' state (TTS may not be starting)")

            if "idle" not in states_received[-3:] if len(states_received) > 0 else True:
                print("- ISSUE: Did not end in 'idle' state")

            if len(audio_chunks) == 0:
                print("- ISSUE: No audio response received")

            if not any(issues := []):
                print("- No obvious issues detected in this test")

            print("\n" + "=" * 60)
            print("TEST COMPLETE")
            print("=" * 60)

    except Exception as e:
        print(f"\n[ERROR] Connection failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_conversation_flow())
