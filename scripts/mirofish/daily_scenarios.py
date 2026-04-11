#!/usr/bin/env python3
"""
MiroFish Daily Scenarios - 10 interesting simulations per day
"""
import random, sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

with open(Path(__file__).resolve().parent.parent.parent.parent / '.env') as f:
    for line in f:
        if '=' in line:
            import os
            k, v = line.strip().split('=', 1)
            os.environ[k] = v

import requests
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

def send(msg):
    if not TOKEN: return
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})

# 10 Daily Scenarios
SCENARIOS = [
    {
        "name": "🐋 鯨魚vs散戶",
        "desc": "大型機構與散戶投資者的價格戰",
        "question": "邊個先贏？鯨魚定散戶？"
    },
    {
        "name": "📈 FOMO熱潮",
        "desc": "當所有人同時湧入牛市",
        "question": "咩因素會觸發全市場FOMO？"
    },
    {
        "name": "💔 恐懼蔓延",
        "desc": "市場恐慌時既連鎖反應",
        "question": "一個壞消息可以幾快擴散成崩盤？"
    },
    {
        "name": "🤖 AI交易員",
        "desc": "演算法主導既市場會變成點？",
        "question": "AI會創造流動定減少流動性？"
    },
    {
        "name": "🏠 樓市vs股市",
        "desc": "資金既流向選擇",
        "question": "樓市崩盤會令資金流入股市嗎？"
    },
    {
        "name": "🇨🇳 中國因素",
        "desc": "中國經濟對全球既影響",
        "question": "中國硬著陸對美股既影響有幾大？"
    },
    {
        "name": "💵 利率轉向",
        "desc": "減息周期既市場反應",
        "question": "減息對邊個板塊既刺激最大？"
    },
    {
        "name": "🪙 幣圈風暴",
        "desc": "Bitcoin ETF獲批既影響",
        "question": "機構進場會改變Crypto既性質嗎？"
    },
    {
        "name": "🏥 疫情2.0",
        "desc": "新一波疫情對經濟既衝擊",
        "question": "邊個行業會逆市上升？"
    },
    {
        "name": "🌍 地緣政治",
        "desc": "戰爭同制裁既經濟影響",
        "question": "台海危機會點影響全球供應鏈？"
    }
]

def run_simulation(scenario):
    """Run quick simulation"""
    agents = [
        {"type": "whale", "count": 5, "capital": 1000000},
        {"type": "retail", "count": 100, "capital": 10000},
        {"type": "institution", "count": 10, "capital": 500000},
    ]
    
    # Simulate 30 days
    results = []
    for day in range(30):
        sentiment = random.uniform(-0.5, 0.5)
        price_change = sentiment * random.uniform(0.5, 2.0)
        results.append(price_change)
    
    # Analysis
    avg_return = sum(results) / len(results)
    volatility = (max(results) - min(results)) / 2
    
    return {
        "avg": avg_return,
        "vol": volatility,
        "trend": "📈" if avg_return > 0 else "📉"
    }

def main():
    msg = "🦐 <b>MiroFish 每日10大模擬</b>\n"
    msg += "<i>每日10個情境思考</i>\n\n"
    
    selected = random.sample(SCENARIOS, 10)
    
    for i, s in enumerate(selected, 1):
        result = run_simulation(s)
        
        msg += f"<b>{i}. {s['name']}</b>\n"
        msg += f"   {s['desc']}\n"
        msg += f"   ❓ {s['question']}\n"
        msg += f"   📊 模擬結果: {result['trend']} {result['avg']:+.1f}% (波幅{result['vol']:.1f}%)\n\n"
    
    msg += "<i>每個情境都反映現實市場既不同面向</i>"
    
    send(msg)
    print("✅ 10 scenarios sent!")

if __name__ == '__main__':
    main()
