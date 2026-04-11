#!/usr/bin/env python3
"""MiroFish Daily - 深度分析版"""
import random, os, sys
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
with open(Path(__file__).resolve().parent.parent.parent.parent / '.env') as f:
    for line in f:
        if '=' in line:
            k, v = line.strip().split('=', 1)
            os.environ[k] = v

MIRO_TOKEN = "8536830590:AAFEFFHDI5ENeGD92dlHJ8RiEmmcaQDkCm0"
CHAT_ID = "-1003713254306"

import requests

def send(msg):
    requests.post(f"https://api.telegram.org/bot{MIRO_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})

# 15種深度智能體
AGENTS = {
    "養老金基金": {"capital": 50000000, "strategy": "價值", "desc": "長線穩健"},
    "主權基金": {"capital": 80000000, "strategy": "配置", "desc": "全球分散"},
    "對沖基金": {"type": "hedge", "capital": 15000000, "strategy": "絕對回報"},
    "量化基金": {"type": "quant", "capital": 10000000, "strategy": "系統化"},
    "華爾街老手": {"type": "pro", "capital": 5000000, "strategy": "自主"},
    "價值投資": {"type": "value", "capital": 3000000, "strategy": "基本面"},
    "趨勢追蹤": {"type": "momentum", "capital": 2000000, "strategy": "技術面"},
    "ETF機器": {"type": "etf", "capital": 8000000, "strategy": "被動"},
    "內幕人士": {"type": "insider", "capital": 5000000, "strategy": "消息"},
    "幣圈鯨魚": {"type": "crypto", "capital": 3000000, "strategy": "高風險"},
    "中國大媽": {"type": "china", "capital": 2000000, "strategy": "跟風"},
    "退休理財": {"type": "retire", "capital": 1000000, "strategy": "保守"},
    "IPO獵人": {"type": "ipo", "capital": 500000, "strategy": "投機"},
    "期權沽家": {"type": "vol", "capital": 2000000, "strategy": "波幅"},
    "抄底王": {"type": "bottom", "capital": 1000000, "strategy": "逆勢"},
}

def run_scenario(scenario_name):
    """運行60日模擬"""
    price = 100.0
    history = []
    agent_results = []
    
    # 初始化智能體
    agents = []
    for name, props in AGENTS.items():
        agents.append({
            "name": name,
            "capital": props["capital"],
            "strategy": props["strategy"],
            "cash": props["capital"],
            "shares": 0,
            "trades": 0,
            "pnl": 0
        })
    
    # 60日模擬
    for day in range(60):
        sentiment = random.uniform(-0.5, 0.5)
        
        # 每個智能體決策
        for a in agents:
            decision = random.random()
            
            # 根據策略決定
            if a["strategy"] == "價值" and price < 95:
                if decision < 0.7:  # 70%買入
                    shares = a["cash"] * 0.1 / price
                    a["shares"] += shares
                    a["cash"] -= shares * price
                    a["trades"] += 1
                    
            elif a["strategy"] == "趨勢" and sentiment > 0.3:
                if decision < 0.6:
                    shares = a["cash"] * 0.2 / price
                    a["shares"] += shares
                    a["cash"] -= shares * price
                    a["trades"] += 1
                    
            elif a["strategy"] == "投機":
                if decision < 0.4:
                    shares = a["cash"] * 0.3 / price
                    a["shares"] += shares
                    a["cash"] -= shares * price
                    a["trades"] += 1
            
            elif a["strategy"] == "被動":
                if decision < 0.1:  # 很少交易
                    shares = a["cash"] * 0.05 / price
                    a["shares"] += shares
                    a["cash"] -= shares * price
                    a["trades"] += 1
        
        # 價格變化
        price *= (1 + sentiment * 0.03 + random.uniform(-0.015, 0.015))
        
        # 記錄
        history.append({"day": day+1, "price": price, "sentiment": sentiment})
    
    # 計算結果
    for a in agents:
        final_value = a["cash"] + a["shares"] * price
        a["final_value"] = final_value
        a["return"] = (final_value - a["capital"]) / a["capital"] * 100
    
    return {
        "scenario": scenario_name,
        "initial_price": 100.0,
        "final_price": price,
        "change": (price - 100) / 100 * 100,
        "history": history,
        "agents": sorted(agents, key=lambda x: x["return"], reverse=True)
    }

def save_report(report):
    """儲存MD"""
    filename = f"analysis/MiroFish_Daily_{report['scenario']}_{datetime.now().strftime('%Y%m%d')}.md"
    
    content = f"""# 🦐 MiroFish 每日深度模擬：{report['scenario']}
## {datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## 📊 模擬結果

| 指標 | 數值 |
|------|------|
| 模擬天數 | 60日 |
| 初始價格 | ${report['initial_price']:.2f} |
| 最終價格 | ${report['final_price']:.2f} |
| 價格變化 | {report['change']:+.1f}% |

---

## 🏆 智能體表現排名

| 排名 | 投資者 | 策略 | 初始資金 | 最終價值 | 回報率 |
|------|--------|------|----------|----------|--------|
"""
    
    for i, a in enumerate(report["agents"], 1):
        emoji = "🟢" if a["return"] > 0 else "🔴"
        content += f"| {i} | {a['name']} | {a['strategy']} | ${a['capital']:,} | ${a['final_value']:,.0f} | {emoji} {a['return']:+.1f}% |\n"
    
    content += f"""

---

## 📈 價格走勢

| 週次 | 價格 | 變化 |
|------|------|------|
"""
    
    for h in report["history"][::7]:
        change = (h["price"] - 100) / 100 * 100
        content += f"| Week {h['day']//7+1} | ${h['price']:.2f} | {change:+.1f}% |\n"
    
    content += f"""

---

## 🔍 深度洞察

### 市場特徵
- 價格變化：{report['change']:+.1f}%
- 市場情緒：{"偏多" if report['change'] > 0 else "偏空"}

### 贏家策略分析
"""
    
    winners = [a for a in report["agents"] if a["return"] > 0]
    losers = [a for a in report["agents"] if a["return"] <= 0]
    
    if winners:
        content += f"- 最佳：{winners[0]['name']} ({winners[0]['strategy']}策略)\n"
        content += f"- 勝出原因：{winners[0]['strategy']}策略在{"上漲" if report['change'] > 0 else "下跌"}市場中表現良好\n"
    
    if losers:
        content += f"\n### 輸家教訓\n"
        content += f"- 最差：{losers[-1]['name']} ({losers[-1]['strategy']}策略)\n"
        content += f"- 教訓：{losers[-1]['strategy']}策略需要更好既風險管理\n"
    
    content += f"""

---

## 💡 投資啟示

1. **策略選擇**：{report['agents'][0]['strategy']}策略在今次模擬中表現最好
2. **風險控制**：{"積極策略" if report['agents'][0]['return'] > 10 else "穩健策略"}獲得較好回報
3. **市場認知**：{"順勢" if report['change'] > 0 else "逆勢"}操作更有效

---

*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    filepath = str(Path(__file__).resolve().parent.parent.parent.parent / filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filepath

def send_telegram(report, filepath):
    """發送精簡版到Telegram"""
    emoji = "🟢" if report['change'] > 0 else "🔴"
    
    msg = f"""🦐 <b>{report['scenario']}</b>

📊 價格：{emoji} {report['change']:+.1f}% (60日)

🏆 <b>Top 3</b>
"""
    
    for i, a in enumerate(report["agents"][:3], 1):
        msg += f"{i}. {a['name']}: {a['return']:+.1f}%\n"
    
    msg += f"\n💡 <b>Key Insight</b>\n"
    msg += f"• 最佳策略：{report['agents'][0]['strategy']}\n"
    msg += f"• 建議：{"順勢" if report['change'] > 0 else "逆勢"}操作\n"
    
    msg += f"\n📁 完整報告：{filepath}"
    
    send(msg)

# Run 10 scenarios
if __name__ == '__main__':
    scenarios = [
        "鯨魚大戰散戶",
        "AI量化崩潰",
        "中國資金湧入",
        "機構vs散戶",
        "幣圈風暴",
        "恐懼蔓延",
        "FOMO狂潮",
        "價值vs趨勢",
        "期權轟炸",
        "抄底輪迴"
    ]
    
    for name in scenarios:
        print(f"Running: {name}")
        report = run_scenario(name)
        filepath = save_report(report)
        send_telegram(report, filepath)
        print(f"  → {filepath}")
