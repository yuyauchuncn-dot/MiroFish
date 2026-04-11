#!/usr/bin/env python3
"""
MiroFish 深度分析版 - 更加詳細、更有深度
"""
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

# 深度智能體系統
AGENTS = {
    # 機構投資者
    "養老金基金": {"type": "pension", "capital": 50000000, "strategy": "long_term", "risk": 0.1},
    "共同基金": {"type": "mutual_fund", "capital": 20000000, "strategy": "balanced", "risk": 0.3},
    "對沖基金": {"type": "hedge", "capital": 15000000, "strategy": "absolute_return", "risk": 0.6},
    "量化基金": {"type": "quant", "capital": 10000000, "strategy": "systematic", "risk": 0.5},
    "主權基金": {"type": "sovereign", "capital": 80000000, "strategy": "strategic", "risk": 0.15},
    
    # 個人投資者
    "華爾街老手": {"type": "pro_trader", "capital": 5000000, "strategy": "discretionary", "risk": 0.5},
    "價值投資大師": {"type": "value", "capital": 3000000, "strategy": "bottom_up", "risk": 0.2},
    "趨勢交易者": {"type": "momentum", "capital": 2000000, "strategy": "technical", "risk": 0.7},
    "波段高手": {"type": "swing", "capital": 1000000, "strategy": "cycle", "risk": 0.5},
    "長線投資者": {"type": "long_term", "capital": 2000000, "strategy": "buy_hold", "risk": 0.25},
    
    # 特殊角色
    "內幕交易者": {"type": "insider", "capital": 5000000, "strategy": "information", "risk": 0.8},
    "ETF機器人": {"type": "etf", "capital": 8000000, "strategy": "passive", "risk": 0.2},
    "IPO獵人": {"type": "ipo", "capital": 500000, "strategy": "speculative", "risk": 0.9},
    "期權莊家": {"type": "market_maker", "capital": 10000000, "strategy": "volatility", "risk": 0.4},
    "風險套利者": {"type": "arb", "capital": 3000000, "strategy": "relative_value", "risk": 0.35},
}

class DeepSim:
    def __init__(self, days=60):
        self.day = 0
        self.days = days
        self.price = 100.0
        self.history = []
        self.agents = []
        
        # 創建智能體
        for name, props in AGENTS.items():
            self.agents.append({
                "name": name,
                "cash": props["capital"],
                "shares": 0,
                "cost_basis": 0,
                **props,
                "trades": [],
                "pnl_history": []
            })
    
    def simulate_day(self):
        self.day += 1
        market_sentiment = random.uniform(-0.5, 0.5)
        
        # 每個智能體決策
        daily_actions = []
        
        for agent in self.agents:
            action = self.agent_decide(agent, market_sentiment)
            if action:
                self.execute_trade(agent, action)
                daily_actions.append((agent["name"], action))
        
        # 更新價格
        price_change = sum(a[1]["shares"] * a[1]["action"] * 0.001 for a in daily_actions)
        self.price *= (1 + price_change + random.uniform(-0.02, 0.02))
        
        # 記錄
        self.history.append({
            "day": self.day,
            "price": self.price,
            "sentiment": market_sentiment,
            "actions": len(daily_actions),
            "volume": sum(abs(a[1]["shares"]) for a in daily_actions)
        })
    
    def agent_decide(self, agent, sentiment):
        """智能體決策邏輯"""
        strategy = agent["strategy"]
        
        if strategy == "long_term":
            if sentiment < -0.3:
                return {"action": 1, "shares": agent["cash"] * 0.1 / self.price}
        elif strategy == "momentum":
            if sentiment > 0.3:
                return {"action": 1, "shares": agent["cash"] * 0.2 / self.price}
        elif strategy == "value":
            if self.price < 95:
                return {"action": 1, "shares": agent["cash"] * 0.15 / self.price}
        elif strategy == "speculative":
            if random.random() < 0.3:
                return {"action": 1, "shares": agent["cash"] * 0.3 / self.price}
        
        return None
    
    def execute_trade(self, agent, action):
        agent["trades"].append(action)

def run_deep_simulation(name):
    """運行深度模擬"""
    sim = DeepSim(days=60)
    
    for _ in range(60):
        sim.simulate_day()
    
    return sim

def generate_deep_report(sim, scenario):
    """生成深度報告"""
    # 智能體表現排名
    agent_results = []
    for a in sim.agents:
        if a["trades"]:
            agent_results.append({
                "name": a["name"],
                "type": a["type"],
                "trades": len(a["trades"]),
                "final_value": a["cash"] + a["shares"] * sim.price,
                "strategy": a["strategy"]
            })
    
    agent_results.sort(key=lambda x: x["final_value"], reverse=True)
    
    # 計算key metrics
    total_volume = sum(h["volume"] for h in sim.history)
    avg_daily_volume = total_volume / len(sim.history)
    price_change = (sim.price - 100) / 100 * 100
    
    # 找出贏家和輸家
    winners = [a for a in agent_results if a["final_value"] > AGENTS[a["name"]]["capital"]][:3]
    losers = [a for a in agent_results if a["final_value"] < AGENTS[a["name"]]["capital"]][-3:][::-1]
    
    # 策略分析
    by_strategy = {}
    for a in agent_results:
        s = a["strategy"]
        if s not in by_strategy:
            by_strategy[s] = []
        by_strategy[s].append(a["final_value"])
    
    best_strategy = max(by_strategy.items(), key=lambda x: sum(x[1])/len(x[1]))[0]
    
    return {
        "scenario": scenario,
        "initial_price": 100.0,
        "final_price": sim.price,
        "price_change": price_change,
        "total_trades": len(agent_results[0]["trades"]) if agent_results else 0,
        "total_volume": total_volume,
        "best_strategy": best_strategy,
        "winners": winners,
        "losers": losers,
        "agent_results": agent_results[:10],
        "history": sim.history
    }

def save_deep_md(report, scenario):
    """儲存為MD"""
    filename = f"analysis/MiroFish_Deep_{scenario}_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    
    content = f"""# 🦐 MiroFish 深度模擬報告：{scenario}
## {datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## 📊 模擬概覽

| 指標 | 數值 |
|------|------|
| 模擬天數 | 60日 |
| 初始價格 | ${report['initial_price']:.2f} |
| 最終價格 | ${report['final_price']:.2f} |
| 價格變化 | {report['price_change']:+.1f}% |
| 總交易次數 | {report['total_trades']} |
| 總成交量 | {report['total_volume']:,.0f} |
| 最佳策略 | {report['best_strategy']} |

---

## 🏆 表現最佳 (Top 3)

| 排名 | 智能體 | 類型 | 策略 | 最終價值 |
|------|--------|------|------|----------|
"""
    
    for i, a in enumerate(report["winners"], 1):
        content += f"| {i} | {a['name']} | {a['type']} | {a['strategy']} | ${a['final_value']:,.0f} |\n"
    
    content += f"""

## 💔 表現最差 (Bottom 3)

| 排名 | 智能體 | 類型 | 策略 | 最終價值 |
|------|--------|------|------|----------|
"""
    
    for i, a in enumerate(report["losers"], 1):
        content += f"| {i} | {a['name']} | {a['type']} | {a['strategy']} | ${a['final_value']:,.0f} |\n"
    
    content += f"""

---

## 📈 價格走勢

| 時期 | 價格 | 變化 |
|------|------|------|
"""
    
    for i, h in enumerate(report["history"][::10]):
        change = (h["price"] - 100) / 100 * 100
        content += f"| Day {h['day']} | ${h['price']:.2f} | {change:+.1f}% |\n"
    
    content += f"""

---

## 🎯 策略分析

### 邊個策略最好？

**最佳策略：{report['best_strategy']}**

這個策略在模擬中表現最好，體現了：
- 適應市場環境的能力
- 風險管理的有效性
- 資金配置的效率

---

## 🔍 深度洞察

### 1. 價格發現機制
{"機構投資者主導定價" if report['price_change'] > 5 else "散戶投資者主導定價"}

### 2. 趨勢延續性
{"市場趨勢明確" if abs(report['price_change']) > 10 else "市場震盪為主"}

### 3. 風險回報
{"高風險策略回報較高" if report['winners'][0]['strategy'] in ['speculative', 'momentum'] else "穩健策略表現較好"}

---

## 💡 模擬結論

### 市場行為總結

1. **價格變化**：{report['price_change']:+.1f}%
2. **總交易量**：{report['total_volume']:,.0f}
3. **參與者**：{len(report['agent_results'])} 個智能體

### 投資啟示

- 採用{best_strategy}策略的投資者表現最佳
- {"順勢而為" if report['price_change'] > 0 else "逆勢抄底"}獲得較好回報
- 風險管理是關鍵

---

*報告生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    filepath = str(Path(__file__).resolve().parent.parent.parent.parent / filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filepath

def send_deep_telegram(report, filepath):
    """發送深度分析到Telegram"""
    price_emoji = "🟢" if report['price_change'] > 0 else "🔴"
    
    msg = f"""🦐 <b>MiroFish 深度分析：{report['scenario']}</b>

📊 <b>結果摘要</b>
• 價格：{price_emoji} {report['price_change']:+.1f}%
• 交易日：60天
• 總交易：{report['total_trades']}次

🏆 <b>Top 3</b>
"""
    
    for i, a in enumerate(report["winners"][:3], 1):
        msg += f"{i}. {a['name']}: +${a['final_value']-10000000:+,.0f}\n"
    
    msg += f"\n💡 <b>最佳策略</b>: {report['best_strategy']}\n"
    msg += f"\n📁 <b>完整報告</b>: {filepath}"
    
    send(msg)

# 主程序
if __name__ == '__main__':
    scenarios = [
        "機構主導",
        "散戶橫行", 
        "AI覺醒",
        "中國資金",
        "危機蔓延",
        "復甦之路",
        "板塊輪動",
        "政策市",
        "科技泡沫",
        "價值回歸"
    ]
    
    for name in scenarios:
        print(f"Running: {name}")
        sim = run_deep_simulation(name)
        report = generate_deep_report(sim, name)
        filepath = save_deep_md(report, name)
        send_deep_telegram(report, filepath)
        print(f"  → {filepath}")
