import asyncio
from loader import GPLINKS_API
import sys
import os

# Add current dir to path to import plugins
sys.path.append(os.getcwd())

from plugins.search import get_shortlink

async def test():
    url = await get_shortlink('https://t.me/SmartFileFly_bot?start=show_cats')
    print(f"Short URL: {url}")

asyncio.run(test())
