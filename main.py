import os
import json
import asyncio
import logging
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import requests
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TELEGRAM_BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("CHAT_ID") or "").strip()
MIN_COINS = int((os.getenv("MIN_COINS") or "5").strip())

UPSTASH_URL = (os.getenv("UPSTASH_REDIS_REST_URL") or "").strip().rstrip("/")
UPSTASH_TOKEN = (os.getenv("UPSTASH_REDIS_REST_TOKEN") or "").strip()

BASE_URL = "https://dichvu321.com"
PAGE_URL = f"{BASE_URL}/en/tiktok-treasure-box-bot/"
PROXY_URL = f"{BASE_URL}/proxy.php"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
    "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1"
}

FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
    "Origin": BASE_URL,
    "Referer": PAGE_URL,
    "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin"
}

LOCAL_KEYS = set()
LIVE_BOXES = []  # Web sitesinde gösterilecek aktif sandık havuzu

HTML_PAGE = """<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hazine Sandığı Radarı</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 15px; }
        .header { text-align: center; margin-bottom: 20px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 15px; }
        .card { background: #1e293b; border-radius: 12px; padding: 16px; border: 1px solid #334155; position: relative; }
        .card.gold { border-color: #eab308; background: #232215; }
        .title { font-weight: bold; font-size: 1.1rem; margin-bottom: 8px; color: #38bdf8; }
        .gold .title { color: #facc15; }
        .timer { font-size: 1.8rem; font-weight: bold; font-family: monospace; color: #4ade80; text-align: center; margin: 10px 0; }
        .btn { display: block; text-align: center; background: #2563eb; color: white; text-decoration: none; padding: 10px; border-radius: 8px; font-weight: bold; margin-top: 10px; }
        .btn:hover { background: #1d4ed8; }
    </style>
</head>
<body>
    <div class="header">
        <h2>📦 Hazine Sandığı Canlı Radar</h2>
        <p style="color: #94a3b8; font-size: 0.9rem;">Aktif sandıklar canlı olarak geriye sayar.</p>
    </div>
    <div class="grid" id="boxGrid"></div>

    <script>
        async function updateData() {
            try {
                const res = await fetch('/api/boxes');
                const boxes = await res.json();
                const grid = document.getElementById('boxGrid');
                const now = Math.floor(Date.now() / 1000);
                grid.innerHTML = '';

                boxes.forEach(b => {
                    const rem = Math.max(0, b.target_time - now);
                    if (rem <= 0) return;
                    const mins = String(Math.floor(rem / 60)).padStart(2, '0');
                    const secs = String(rem % 60).padStart(2, '0');

                    const card = document.createElement('div');
                    card.className = b.is_gold ? 'card gold' : 'card';
                    card.innerHTML = `
                        <div class="title">${b.box_name}</div>
                        <div>👤 <b>Yayıncı:</b> @${b.username}</div>
                        <div>💎 <b>Coin:</b> ${b.coins}</div>
                        <div>👥 <b>Kişi:</b> ${b.can_open} | 👁️ <b>İzleyici:</b> ${b.viewers}</div>
                        <div class="timer">${mins}:${secs}</div>
                        <a href="https://www.tiktok.com/@${b.username}/live" target="_blank" class="btn">YAYINA GİT</a>
                    `;
                    grid.appendChild(card);
                });
            } catch(e) {}
        }
        setInterval(updateData, 1000);
        updateData();
    </script>
</body>
</html>
"""

class LiveDashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif self.path == "/api/boxes":
            now = int(time.time())
            # Süresi dolmuş sandıkları listeden temizle
            global LIVE_BOXES
            LIVE_BOXES = [b for b in LIVE_BOXES if b["target_time"] > now]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(LIVE_BOXES).encode("utf-8"))
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass

def run_dashboard_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), LiveDashboardHandler)
    server.serve_forever()

def is_seen(key):
    if key in LOCAL_KEYS:
        return True
    if UPSTASH_URL and UPSTASH_TOKEN:
        try:
            req_url = f"{UPSTASH_URL}/set/{key}/1/nx/ex/86400"
            headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
            res = requests.get(req_url, headers=headers, timeout=3).json()
            if res.get("result") is None:
                return True
        except Exception as e:
            logging.error(f"Redis Hatası: {e}")

    LOCAL_KEYS.add(key)
    if len(LOCAL_KEYS) > 10000:
        LOCAL_KEYS.clear()
    return False

def send_telegram(mesaj):
    if not TELEGRAM_BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mesaj,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logging.error(f"Telegram Hatası: {e}")

def get_ticket(session):
    session.get(PAGE_URL, headers=BROWSER_HEADERS, timeout=10)
    params = {"transport": "ws", "mode": "bootstrap", "stream": "all", "live": "33000"}
    res = session.post(PROXY_URL, params=params, headers=FETCH_HEADERS, timeout=10)
    try:
        data = res.json()
        if data.get("success") and "path" in data:
            return data["path"], session.cookies.get_dict()
    except Exception as e:
        logging.error(f"Bilet Ayrıştırma Hatası: {e}")
    return None, None

async def connect_ws(ws_url, ws_headers):
    try:
        return await websockets.connect(ws_url, additional_headers=ws_headers, ping_interval=None, ping_timeout=None)
    except TypeError:
        try:
            return await websockets.connect(ws_url, extra_headers=ws_headers, ping_interval=None, ping_timeout=None)
        except TypeError:
            return await websockets.connect(ws_url, ping_interval=None, ping_timeout=None)

async def run_bot():
    send_telegram("📦 <b>Hazine Sandığı Radarı Aktif!</b>\nCanlı Panel: https://hazinesandigi-1.onrender.com")
    session = requests.Session()

    while True:
        try:
            logging.info("🎫 Bilet talep ediliyor...")
            path, cookies = await asyncio.to_thread(get_ticket, session)

            if not path:
                await asyncio.sleep(4)
                continue

            ws_url = f"wss://dichvu321.com{path}"
            cookie_header = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            ws_headers = {
                "User-Agent": BROWSER_HEADERS["User-Agent"],
                "Origin": BASE_URL,
                "Cookie": cookie_header
            }

            ws = await connect_ws(ws_url, ws_headers)
            async with ws:
                logging.info("✅ Canlı WebSocket bağlı! Sandıklar dinleniyor...")
                while True:
                    msg = await ws.recv()
                    try:
                        raw = json.loads(msg)
                        msg_type = raw.get("type")

                        if msg_type == "ready":
                            covered = raw.get("data", {}).get("coveredLive", 0)
                            logging.info(f"💓 Aktif Dinlenen Canlı Yayın: {covered}")
                            continue

                        if msg_type == "demoEvents" and isinstance(raw.get("events"), list):
                            for item in raw["events"]:
                                if item.get("type", "box") == "goody_bag":
                                    continue

                                username = item.get("uniqueId")
                                if not username:
                                    continue

                                coins = int(item.get("coins") or 0)
                                if coins < MIN_COINS:
                                    continue

                                raw_ts = item.get("timestamp", 0)
                                key = f"box:{username}:{coins}:{raw_ts}"

                                if is_seen(key):
                                    continue

                                # Logda tüm paketi incelemek için:
                                logging.info(f"HAM SANDIK PAKETİ: {item}")

                                can_open = item.get("canOpen", 0)
                                viewers = item.get("viewerCount", 0)
                                b_type = item.get("businessType", 0)
                                is_gold = (b_type == 4)
                                box_name = "👑 ALTIN SANDIK" if is_gold else "📦 HAZİNE SANDIĞI"

                                # Varsayılan 3 dakika (180 sn) ileri hedef koyar (log verisi geldikten sonra tam süreye bağlanacaktır)
                                duration = int(item.get("duration") or item.get("leftTime") or 180)
                                target_time = int(time.time()) + duration

                                # Canlı Web Sitesi Listesine Ekle
                                LIVE_BOXES.append({
                                    "username": username,
                                    "coins": coins,
                                    "can_open": can_open,
                                    "viewers": viewers,
                                    "box_name": box_name,
                                    "is_gold": is_gold,
                                    "target_time": target_time
                                })

                                live_link = f"https://www.tiktok.com/@{username}/live"
                                viewers_str = f"👁️ <b>İzleyici:</b> {viewers}\n" if viewers else ""
                                people_str = f"👥 <b>Kişi Sayısı:</b> {can_open}\n" if can_open else ""

                                mesaj = (
                                    f"✨ <b>{box_name}</b>\n\n"
                                    f"👤 <b>Yayıncı:</b> @{username}\n"
                                    f"💎 <b>Coin:</b> {coins}\n"
                                    f"{people_str}"
                                    f"{viewers_str}\n"
                                    f"{live_link}"
                                )
                                send_telegram(mesaj)
                                logging.info(f"📦 İLETİLDİ: @{username} ({coins} Coin)")

                    except Exception as err:
                        logging.error(f"Ayrıştırma hatası: {err}")

        except Exception as e:
            logging.error(f"Soket döngüsü koptu: {e}")
            await asyncio.sleep(3)

if __name__ == "__main__":
    threading.Thread(target=run_dashboard_server, daemon=True).start()
    asyncio.run(run_bot())
