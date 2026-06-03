import asyncio, aiohttp
async def test():
    async with aiohttp.ClientSession() as session:
        resp = await session.get('https://api.gplinks.com/api', params={'api': 'bad_api_key', 'url': 'https://t.me/SmartFileFly_bot?start=show_cats'})
        print(f"Status: {resp.status}")
        print(f"Body: '{await resp.text()}'")
asyncio.run(test())
