#!/usr/bin/env python3
"""Simple webhook bot for MiroFish"""
from flask import Flask, request
import os, sys, json, requests, random

app = Flask(__name__)

TOKEN = "8536830590:AAFEFFHDI5ENeGD92dlHJ8RiEmmcaQDkCm0"
CHAT_ID = "-1003713254306"

TOPICS = {
    "深圳": ["深圳樓市泡沫", "前海發展", "深港科技競爭", "深圳創投", "深圳青年置業"],
    "music": ["Spotify壟斷", "Apple Music vs", "串流革命", "獨立音樂人", "演唱會經濟"],
    "AI": ["AI取代工作", "AI創業潮", "AI監管", "AI醫療", "AI教育"],
    "default": ["機構vs散戶", "FOMO狂潮", "恐懼蔓延", "價值回歸", "板塊輪動"]
}

def send(msg, chat_id=CHAT_ID):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"})

def run_sim(topic):
    price = 100
    for _ in range(60):
        price *= (1 + random.uniform(-0.03, 0.04))
    change = (price - 100) / 100 * 100
    return change

@app.route(f"/webhook/{TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json()
    
    if "message" in data:
        text = data["message"].get("text", "")
        chat_id = data["message"]["chat"]["id"]
        
        if text.startswith("/topic "):
            keyword = text[7:].strip().lower()
            topics = TOPICS.get(keyword, TOPICS["default"])
            
            msg = f"🧠 <b>關於「{text[7:]}」既5個主題：</b>\n\n"
            for i, t in enumerate(topics, 1):
                msg += f"{i}. {t}\n"
            msg += "\n請選擇：1-5 / all / new"
            send(msg, chat_id)
            
        elif text == "/start":
            send("🦕 MiroFish Bot\n/topic <關鍵詞>", chat_id)
    
    return "OK"

if __name__ == "__main__":
    # Set webhook
    webhook_url = f"https://your-domain.com/webhook/{TOKEN}"
    # requests.post(f"https://api.telegram.org/bot{TOKEN}/setWebhook", 
    #              json={"url": webhook_url})
    
    print("Bot ready! Use polling for now...")
    app.run(port=5000)
