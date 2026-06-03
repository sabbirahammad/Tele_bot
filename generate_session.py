import asyncio
from pyrogram import Client

# You can replace these with input prompts if you prefer
API_ID = input("Enter your API_ID: ")
API_HASH = input("Enter your API_HASH: ")

async def main():
    async with Client("my_account", api_id=API_ID, api_hash=API_HASH, in_memory=True) as app:
        session_string = await app.export_session_string()
        print("\n--- YOUR STRING SESSION ---")
        print(session_string)
        print("---------------------------\n")
        print("Copy the string above and add it to your .env file like this:")
        print("STRING_SESSION=the_string_you_copied")

if __name__ == "__main__":
    asyncio.run(main())
