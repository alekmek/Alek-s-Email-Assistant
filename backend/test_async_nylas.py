"""Quick test to verify async Nylas service works."""
import asyncio
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_search():
    from app.services.nylas_service import get_nylas_service
    import time

    print("Testing async search_emails...")
    nylas = get_nylas_service()

    # Get current timestamp for last 24 hours
    current_time = int(time.time())
    received_after = current_time - 86400  # 24 hours ago

    print(f"Searching for emails after {received_after} (24 hours ago)")

    try:
        results = await nylas.search_emails(
            received_after=received_after,
            limit=5
        )
        print(f"Success! Found {len(results)} emails")
        for email in results[:3]:
            print(f"  - {email.get('subject', 'No subject')[:50]}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_search())
