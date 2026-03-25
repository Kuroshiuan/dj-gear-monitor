import requests
from bs4 import BeautifulSoup
import time
import json
import os
from datetime import datetime, timedelta

# ================== 設定區 ==================
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
if not DISCORD_WEBHOOK:
    raise ValueError("請在 GitHub Secrets 設定 DISCORD_WEBHOOK")

MODELS = [
    "Vestax PDX-2000 mkii pro",
    "Vestax PDX-2300 mkii pro",
    "Vestax PDX-3000 30th",
    "Vestax PMC-08 pro",
    "Vestax PMC-07 pro ISP",
    "Stanton Str8-150"
]

SEEN_FILE = "seen_listings.json"
HEARTBEAT_FILE = "last_heartbeat.json"   # ← 新增：記錄上次心跳時間
CHECK_INTERVAL = 600  # GitHub 每 10 分鐘跑一次，這裡僅供參考

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Accept-Language": "ja-JP,zh-TW;q=0.9,en;q=0.8"
}

# 載入已看過的商品
if os.path.exists(SEEN_FILE):
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        seen = json.load(f)
else:
    seen = {"yahoo": [], "mercari": [], "ebay": []}

# 載入上次心跳時間（預設為 25 小時前，確保第一次執行會發心跳）
if os.path.exists(HEARTBEAT_FILE):
    with open(HEARTBEAT_FILE, "r", encoding="utf-8") as f:
        last_heartbeat = datetime.fromisoformat(json.load(f)["last"])
else:
    last_heartbeat = datetime.utcnow() - timedelta(hours=25)

def save_seen():
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)

def save_heartbeat():
    with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
        json.dump({"last": datetime.utcnow().isoformat()}, f, ensure_ascii=False, indent=2)

def send_discord(title, price, url, site, model, posted_time="未知", is_heartbeat=False):
    if is_heartbeat:
        embed = {
            "content": "✅ **DJ 設備監控程式正常運作中**",
            "embeds": [{
                "title": "目前無新刊登",
                "color": 0x00ccff,
                "description": "已完成掃描，所有網站都沒有符合條件的新二手 DJ 設備。",
                "timestamp": datetime.utcnow().isoformat()
            }]
        }
    else:
        embed = {
            "content": f"🚨 **新刊登！** {model}",
            "embeds": [{
                "title": title,
                "url": url,
                "color": 0x00ff00,
                "fields": [
                    {"name": "價格", "value": price, "inline": True},
                    {"name": "網站", "value": site, "inline": True},
                    {"name": "刊登時間", "value": posted_time, "inline": True}
                ],
                "timestamp": datetime.utcnow().isoformat()
            }]
        }
    try:
        requests.post(DISCORD_WEBHOOK, json=embed, timeout=10)
        print(f"✅ 已發送 Discord {'心跳' if is_heartbeat else '通知'}：{title if not is_heartbeat else '正常運作'}")
    except Exception as e:
        print(f"Discord 發送失敗: {e}")

# ================== 各網站爬蟲（2026 年最新結構） ==================
def search_yahoo(model):
    keyword = model.replace(" ", "+")
    url = f"https://auctions.yahoo.co.jp/search/search?va=%22{keyword}%22&s1=new&o1=d&n=100"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
        items = soup.select("div.Product")
        for item in items:
            link_tag = item.select_one("a.Product__titleLink")
            if not link_tag: continue
            title = link_tag.get_text(strip=True)
            link = link_tag["href"]
            price_tag = item.select_one("span.Product__price")
            price = price_tag.get_text(strip=True) if price_tag else "價格未顯示"
            if any(m.lower() in title.lower() for m in MODELS):
                if link not in seen["yahoo"]:
                    seen["yahoo"].append(link)
                    save_seen()
                    send_discord(title, price, link, "🇯🇵 Yahoo 拍賣", model)
    except Exception as e:
        print(f"Yahoo 錯誤: {e}")

def search_mercari(model):
    keyword = model.replace(" ", "%20")
    url = f"https://jp.mercari.com/search?keyword=%22{keyword}%22&sort=created_desc"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
        items = soup.select("div.mui-1v4q0e0, div.item-cell")
        for item in items:
            link_tag = item.select_one("a")
            if not link_tag: continue
            title = link_tag.get_text(strip=True)
            link = "https://jp.mercari.com" + link_tag["href"]
            price_tag = item.select_one("div.price, span.price")
            price = price_tag.get_text(strip=True) if price_tag else "價格未顯示"
            if any(m.lower() in title.lower() for m in MODELS):
                if link not in seen["mercari"]:
                    seen["mercari"].append(link)
                    save_seen()
                    send_discord(title, price, link, "🇯🇵 Mercari", model)
    except Exception as e:
        print(f"Mercari 錯誤: {e}")

def search_ebay(model):
    keyword = model.replace(" ", "+")
    url = f"https://www.ebay.com/sch/i.html?_nkw=%22{keyword}%22&_sacat=0&LH_TitleDesc=0&_sop=12"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
        items = soup.select("div.s-item__info")
        for item in items:
            link_tag = item.select_one("a.s-item__link")
            if not link_tag: continue
            title = link_tag.get_text(strip=True)
            link = link_tag["href"]
            price_tag = item.select_one("span.s-item__price")
            price = price_tag.get_text(strip=True) if price_tag else "價格未顯示"
            if any(m.lower() in title.lower() for m in MODELS):
                if link not in seen["ebay"]:
                    seen["ebay"].append(link)
                    save_seen()
                    send_discord(title, price, link, "🇺🇸 eBay", model)
    except Exception as e:
        print(f"eBay 錯誤: {e}")

# ================== 主程式 ==================
print(f"🎛️ DJ 設備監控程式啟動 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

for model in MODELS:
    print(f"   搜尋 → {model}")
    search_yahoo(model)
    search_mercari(model)
    search_ebay(model)
    time.sleep(3)

print("掃描完成")

# 檢查是否需要發心跳訊息（每 24 小時一次）
if datetime.utcnow() - last_heartbeat > timedelta(hours=24):
    send_discord("", "", "", "", "", is_heartbeat=True)
    save_heartbeat()
    print("❤️ 已發送 24 小時心跳訊息")

save_seen()
