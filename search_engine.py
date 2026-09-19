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
CODAS = [
    "","n","r","s","t","l","m","x","v","z","n","r","s"
]
VOWEL_GROUPS = ["a","e","i","o","u","ae","ai","ei","ia","io","oa","ou"]

BAD = {
    "fuck","shit","porn","sex","nazi","hitler","kkk","admin","telegram",
    "support","official","scam","casino","bet","crypto"
}

LAST_SERVER_RESPONSE = "Запросов еще не было"

def get_last_error():
    global LAST_SERVER_RESPONSE
    return LAST_SERVER_RESPONSE

def syllable():
    onset = random.choice(ONSETS)
    vowel = random.choice(VOWEL_GROUPS)
    coda = random.choice(CODAS)
    return onset + vowel + coda

def generate_candidate(length):
    for _ in range(40):
        parts = []
        while len("".join(parts)) < length:
            parts.append(syllable())
        s = "".join(parts)[:length]
        if len(s) == length:
            return s
    return None

def pronounce_score(s):
    score = 50.0
    v = sum(c in VOWELS for c in s)
    ratio = v / len(s)

    if 0.30 <= ratio <= 0.60:
        score += 18
    else:
        score -= 15

    for i in range(len(s)-1):
        a, b = s[i], s[i+1]
        if a not in VOWELS and b not in VOWELS: score -= 9
        if a in VOWELS and b in VOWELS: score -= 2

    if len(set(s)) == len(s): score += 8
    elif len(set(s)) >= len(s)-1: score += 3

    if any(s.count(ch) >= 3 for ch in s): score -= 18
    if re.search(r"(.)\1\1", s): score -= 20

    common_pairs = ["ve","va","vi","vo","vu","le","la","li","lo","lu",
                    "ra","re","ri","ro","ru","ne","no","na","el","av",
                    "or","ix","ex","on","en"]
    score += sum(3 for p in common_pairs if p in s)
    ugly = ["qx","qz","zx","xq","wq","jv","qv","qj","vv","ww"]
    score -= sum(20 for p in ugly if p in s)

    return score

def brand_score(s):
    score = pronounce_score(s)
    if s[0] in VOWELS: score += 4
    if s[-1] in VOWELS: score += 6
    if s[-1] in "xyz": score += 3
    if s.isalpha(): score += 5
    if any(s.count(ch) > 2 for ch in set(s)): score -= 12
    return score

def valid_candidate(s):
    return (
        bool(s)
        and s.isascii()
        and s.isalpha()
        and s not in BAD
        and not any(x in s for x in BAD)
    )

async def check_username(session, username):
    global LAST_SERVER_RESPONSE
    clean_username = username.lstrip("@").strip()
    url = f"{COREGRAM_URL}/bot{BOT_TOKEN}/getChat"
    params = {"chat_id": f"@{clean_username}"}
    
    try:
        async with session.get(
            url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=5),
        ) as r:
            text = await r.text()
            LAST_SERVER_RESPONSE = f"@{clean_username} | HTTP {r.status} | {text}"
            
            try:
                data = await r.json(content_type=None)
            except Exception:
                return False

            if not data.get("ok"):
                desc = data.get("description", "").lower()
                if "chat not found" in desc:
                    return True
            return False
            
    except Exception as e:
        LAST_SERVER_RESPONSE = f"Ошибка сети @{clean_username}: {e}"
        return False

async def generate_and_check(target=10, length_option=6):
    pool = {}
    attempts = max(8000, target * 1500)

    # Определяем нужную длину или диапазон
    if isinstance(length_option, int):
        lengths = [length_option]
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
    check_pool = ranked[:max(200, target * 30)]

    connector = aiohttp.TCPConnector(limit=25)
    async with aiohttp.ClientSession(connector=connector) as session:
        sem = asyncio.Semaphore(15)

        async def one(u):
            async with sem:
                ok = await check_username(session, u)
                return u if ok else None

        results = await asyncio.gather(*(one(u) for u in check_pool))

    free = [u for u in results if u]
    random.shuffle(free)
    free.sort(key=lambda x: brand_score(x), reverse=True)

    return free[:target]
