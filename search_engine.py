import asyncio
import math
import random
import re
import aiohttp

BOT_TOKEN = "1780243306:E05ncdTVuEvF6s-s_9-RzU854yvZF9D89vM"
COREGRAM_URL = "http://31.77.9.111:8081"

VOWELS = "aioue"
CONSONANTS = "bcdfghjklmnprstvwxz"

ONSETS = [
    "b","br","c","cr","d","dr","f","fr","g","gr","h","j","k","kr",
    "l","m","n","p","pr","r","s","sk","sl","sm","sn","st","t","tr",
    "v","vr","w","x","z","zl","zn"
]
CODAS = ["","n","r","s","t","l","m","x","v","z"]
VOWEL_GROUPS = ["a","e","i","o","u","ae","ai","ei","ia","io","oa","ou"]

BAD = {
    "fuck","shit","porn","sex","nazi","hitler","kkk","admin","telegram",
    "support","official","scam","casino","bet","crypto"
}

def syllable():
    return random.choice(ONSETS) + random.choice(VOWEL_GROUPS) + random.choice(CODAS)

def generate_candidate(length):
    for _ in range(40):
        parts = []
        while len("".join(parts)) < length:
            parts.append(syllable())
        s = "".join(parts)[:length]
        if len(s) == length:
            return s
    return None

def brand_score(s):
    score = 50.0
    v = sum(c in VOWELS for c in s)
    ratio = v / len(s)
    if 0.30 <= ratio <= 0.60: score += 18
    else: score -= 15
    if s[0] in VOWELS: score += 4
    if s[-1] in VOWELS: score += 6
    return score

def valid_candidate(s):
    return bool(s) and s.isascii() and s.isalpha() and s not in BAD

async def check_username(session, username):
    clean_username = username.lstrip("@").strip()
    url = f"{COREGRAM_URL}/bot{BOT_TOKEN}/getChat"
    params = {"chat_id": f"@{clean_username}"}
    
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=4)) as r:
            try:
                data = await r.json(content_type=None)
            except Exception:
                return False

            if not data.get("ok"):
                desc = data.get("description", "").lower()
                if "chat not found" in desc or "chat_id_invalid" in desc:
                    return True
            return False
    except Exception:
        return False

async def generate_and_check(target=10, length_option=6):
    pool = {}
    attempts = max(10000, target * 2000)

    if isinstance(length_option, int) or (isinstance(length_option, str) and length_option.isdigit()):
        lengths = [int(length_option)]
        weights = [100]
    elif length_option == "8_10":
        lengths = [8, 9, 10]
        weights = [40, 35, 25]
    else:
        lengths = [6]
        weights = [100]

    for _ in range(attempts):
        length = random.choices(lengths, weights=weights)[0]
        s = generate_candidate(length)
        if not s or not valid_candidate(s) or len(s) != length:
            continue
        score = brand_score(s) + random.uniform(-2.0, 2.0)
        pool[s] = max(score, pool.get(s, -999))

    ranked = sorted(pool, key=pool.get, reverse=True)
    check_pool = ranked[:max(300, target * 40)]

    connector = aiohttp.TCPConnector(limit=30)
    async with aiohttp.ClientSession(connector=connector) as session:
        sem = asyncio.Semaphore(20)

        async def one(u):
            async with sem:
                ok = await check_username(session, u)
                return u if ok else None

        results = await asyncio.gather(*(one(u) for u in check_pool))

    free = [u for u in results if u]
    random.shuffle(free)
    free.sort(key=lambda x: brand_score(x), reverse=True)

    return free[:target]
