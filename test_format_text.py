import asyncio, aiohttp
async def test():
    async with aiohttp.ClientSession() as session:
        resp = await session.get('https://api.gplinks.com/api', params={'api': 'c6c60266f958ad52b6999f348e63d1f2bc6fc629', 'url': 'https://t.me/SmartFileFly_bot?start=show_cats', 'format': 'text'})
        print(await resp.text())
asyncio.run(test())
