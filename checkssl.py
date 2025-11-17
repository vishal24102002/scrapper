import sys
import telethon
from telethon import TelegramClient
from datetime import datetime, timedelta
import asyncio

print(f"Test Script is using Python executable: {sys.executable}")
print(f"Telethon version in test script: {telethon.__version__}")

api_id = '20246401'      # Replace with your actual API ID
api_hash = '9c6efb78efef1f68619351aedeede551'  # Replace with your actual API Hash
chat = 'QDisclosure17'     # Replace with a valid chat name or ID you have access to

async def test_iter_messages():
    async with TelegramClient('test_session', api_id, api_hash) as client:
        await client.start()
        start_datetime = datetime(2024, 10, 1)
        end_datetime = datetime(2024, 10, 2)
        try:
            async for message in client.iter_messages(
                chat,
                min_date=start_datetime,
                max_date=end_datetime
            ):
                print(f"Message ID: {message.id}, Date: {message.date}, Text: {message.text}")
        except TypeError as e:
            print(f"TypeError encountered: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

asyncio.run(test_iter_messages())
