import asyncio
import aiohttp
import random

APIFY_TOKEN = "Apify_api_VdtditXCTU64coUmrjkzKnUGh8c1B70H6zCA"
BOT_TOKEN = "1780243306:E05ncdTVuEvF6s-s_9-RzU854yvZF9D89vM"
COREGRAM_URL = "http://31.77.9.111:8081"

WORDS_DB = {
    4: [
        "home", "scan", "core", "node", "byte", "mesh", "wave", "apex", 
        "neon", "bolt", "echo", "luna", "star", "flux", "zero", "zoom", 
        "chat", "cast", "deck", "dock", "grid", "halo", "icon", "jump", 
        "link", "mine", "nest", "port", "ring", "soar", "tech", "vibe", 
        "wise", "zone", "flow", "sync", "data", "code", "safe"
    ],
    5: [
        "label", "okay", "agent", "audio", "audit", "brand", "cable", 
        "cloud", "craft", "cyber", "delta", "digit", "drift", "drive", 
        "email", "event", "fiber", "flora", "frame", "graph", "input", 
        "lance", "laser", "logic", "major", "media", "micro", "model", 
        "motor", "nexus", "orbit", "panel", "pixel", "radar", "radio", 
        "rotor", "scope", "smart", "spark", "speed", "stack", "steam", 
        "storm", "swift", "token", "turbo", "ultra", "vector", "voice"
    ],
    6: [
        "manager", "action", "admin", "agency", "beacon", "binary", 
        "bridge", "buffer", "carbon", "client", "cipher", "coding", 
        "column", "credit", "crypto", "device", "engine", "factor", 
        "format", "galaxy", "global", "growth", "impact", "kernel", 
        "matrix", "mobile", "module", "motion", "object", "online", 
        "packet", "portal", "python", "reader", "record", "render", 
        "router", "schema", "search", "secure", "server", "signal", 
        "source", "status", "stream", "switch", "system", "thread", 
        "widget", "wizard", "worker"
    ],
    "8_10": [
        "network", "platform", "terminal", "protocol", "software", 
        "database", "analytics", "security", "engineer", "solution", 
        "hardware", "interface", "workspace", "dashboard", "framework"
    ]
}

async def generate_and_check(target=10, length_option=6):
    if isinstance(length_option, int) or (isinstance(length_option, str) and length_option.isdigit()):
        l_int = int(length_option)
        pool = WORDS_DB.get(l_int, WORDS_DB[6])
    else:
        pool = WORDS_DB.get(length_option, WORDS_DB[6])

    candidates = list(pool)
    random.shuffle(candidates)

    free_found = []
    connector = aiohttp.TCPConnector(limit=25)
    async with aiohttp.ClientSession(connector=connector) as session:
        sem = asyncio.Semaphore(15)

        async def check_one(u):
            async with sem:
                url = f"{COREGRAM_URL}/bot{BOT_TOKEN}/getChat"
                payload = {"chat_id": f"@{u}"}
                try:
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=4)) as r:
                        data = await r.json(content_type=None)
                        if not data.get("ok"):
                            desc = data.get("description", "").lower()
                            if "chat not found" in desc or "chat_id_invalid" in desc:
                                return u
                except Exception:
                    pass
                return None

        tasks = [check_one(u) for u in candidates[:target * 4]]
        results = await asyncio.gather(*tasks)
        free_found = [u for u in results if u]

    return free_found[:target]
