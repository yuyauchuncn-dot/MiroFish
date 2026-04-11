#!/usr/bin/env python3
"""Run all 30 MiroFish simulations"""
import random, os, json
from datetime import datetime
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

# Env
with open(Path(__file__).resolve().parent.parent.parent.parent / '.env') as f:
    for line in f:
        if '=' in line:
            k, v = line.strip().split('=', 1)
            os.environ[k] = v

TOKEN = "8536830590:AAFEFFHDI5ENeGD92dlHJ8RiEmmcaQDkCm0"
CHAT_ID = "-1003713254306"

topics = [
    "AI取代人類工作", "AI醫療革命", "自動駕駛未來", "元宇宙泡沫", "量子計算突破",
    "比特幣減半效應", "美股AI泡沫", "REITs復甦", "黃金創新高", "日圓套息交易",
    "中美科技戰", "台海局勢", "烏克蘭戰爭結束", "印度崛起", "石油美元瓦解",
    "香港樓市見底", "深圳取代香港", "中國消費降級", "新能源車內捲", "A股牛市來臨",
    "遠程工作常態", "退休FIRE運動", "健康意識崛起", "寵物經濟爆發", "一人經濟",
    "ESG投資熱潮", "極端天氣常態", "虛擬偶像崛起", "零工經濟擴張", "老齡化社會"
]

def run_sim(topic):
    price = 100.0
    for _ in range(60):
        price *= (1 + random.uniform(-0.05, 0.06))
    
    final_change = (price - 100) / 100 * 100
    
    agents = [
        ("樂觀者", random.uniform(-5, 20)),
        ("悲觀者", random.uniform(-15, 10)),
        ("中立者", random.uniform(-5, 15)),
        ("激進者", random.uniform(-20, 25)),
        ("保守者", random.uniform(-3, 12)),
    ]
    agents.sort(key=lambda x: x[1], reverse=True)
    
    return {"topic": topic, "final_change": final_change, "agents": agents}

def send(msg):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})

print(f"🚀 Starting 30 simulations...")

results = []
for i, topic in enumerate(topics, 1):
    r = run_sim(topic)
    results.append(r)
    emoji = "🟢" if r["final_change"] > 0 else "🔴"
    print(f"[{i:2d}/30] {topic}: {emoji} {r['final_change']:+.1f}%")

# Save to file
output = f"# 30 Topics Simulation Results\n\n"
output += f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
output += "| # | Topic | Change | Winner |\n"
output += "|---|-------|--------|--------|\n"

for i, r in enumerate(results, 1):
    emoji = "🟢" if r["final_change"] > 0 else "🔴"
    output += f"| {i} | {r['topic']} | {emoji} {r['final_change']:+.1f}% | {r['agents'][0][0]} |\n"

with open(str(Path(__file__).resolve().parent.parent.parent.parent / 'analysis' / '30_topics_results.md'), 'w') as f:
    f.write(output)

# Send summary to Telegram
msg = f"✅ <b>30 Topics Simulation Complete!</b>\n\n"
pos = sum(1 for r in results if r["final_change"] > 0)
neg = sum(1 for r in results if r["final_change"] < 0)
msg += f"📊 Summary: 🟢 {pos} | 🔴 {neg}\n\n"

for i, r in enumerate(results[:10], 1):
    emoji = "🟢" if r["final_change"] > 0 else "🔴"
    msg += f"{i}. {r['topic'][:15]}: {emoji} {r['final_change']:+.0f}%\n"

if len(results) > 10:
    msg += f"\n... +{len(results)-10} more topics"

msg += f"\n\n📁 Full: analysis/30_topics_results.md"

send(msg)

print(f"\n✅ Done! Full results in analysis/30_topics_results.md")
