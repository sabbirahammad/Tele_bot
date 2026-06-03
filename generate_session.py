import asyncio

# Python 3.12+ compatibility fix for Pyrogram
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client

async def main():
    print("\n--- Telegram Session Generator ---")
    try:
        api_id = int(input("Enter your API_ID: ").strip())
        api_hash = input("Enter your API_HASH: ").strip()
    except ValueError:
        print("❌ Error: API_ID must be a numeric value.")
        return

    print("\nLogging in... Please follow the Telegram prompts.")
    async with Client("my_account", api_id=api_id, api_hash=api_hash, in_memory=True) as app:
        session_string = await app.export_session_string()
        print("\n--- YOUR STRING SESSION ---")
        print(session_string)
        print("---------------------------\n")
        print("Copy the string above and add it to your .env file like this:")
        print("STRING_SESSION=the_string_you_copied")

if __name__ == "__main__":
    asyncio.run(main())
