import asyncio
import aiohttp
import urllib.parse

GPLINKS_API = "c6c60266f958ad52b6999f348e63d1f2bc6fc629"
url = "https://t.me/SmartFileFly_bot?start=show_cats"
encoded_url = urllib.parse.quote(url) # URL এনকোড করা হলো

async def test_gplinks():
    urls_to_test = [
        f"https://gplinks.com/api?api={GPLINKS_API}&url={encoded_url}",
        f"https://gplinks.co/api?api={GPLINKS_API}&url={encoded_url}",
        f"https://api.gplinks.com/api?api={GPLINKS_API}&url={encoded_url}",
        f"https://api.gplinks.in/api?api={GPLINKS_API}&url={encoded_url}"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0",
    }
    
    async with aiohttp.ClientSession() as session:
        for api_url in urls_to_test:
            try:
                async with session.get(api_url, headers=headers, timeout=5) as response:
                    print(f"Testing {api_url}")
                    print(f"Status: {response.status}")
                    if response.status == 200:
                        print(await response.text())
            except Exception as e:
                print(f"Error testing {api_url}: {e}")

if __name__ == "__main__":
    asyncio.run(test_gplinks())
