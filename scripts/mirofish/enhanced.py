#!/usr/bin/env python3
"""
MiroFish 增強版 - 更多智能體、更多角色、儲存為中文MD
"""
import random, os, sys
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

# 環境變量
with open(Path(__file__).resolve().parent.parent.parent.parent / '.env') as f:
    for line in f:
        if '=' in line:
            k, v = line.strip().split('=', 1)
            os.environ[k] = v

import requests
MIRO_TOKEN = os.environ.get('MIROFISH_BOT_TOKEN', '')

# 更多智能體類型
AGENTS = {
    # 傳統角色
    "科技巨鱷": {"type": "whale", "bias": "bull", "capital": 10000000, "aggression": 0.9},
    "淡友巨鱷": {"type": "whale", "bias": "bear", "capital": 10000000, "aggression": 0.9},
    "華爾街機構": {"type": "institution", "bias": "neutral", "capital": 5000000, "aggression": 0.3},
    "散戶大軍": {"type": "retail", "bias": "bull", "capital": 100000, "aggression": 0.7},
    "恐懼散戶": {"type": "retail", "bias": "bear", "capital": 100000, "aggression": 0.6},
    "價值投資者": {"type": "investor", "bias": "value", "capital": 500000, "aggression": 0.2},
    "趨勢追蹤者": {"type": "trader", "bias": "momentum", "capital": 300000, "aggression": 0.8},
    "反轉交易者": {"type": "contrarian", "bias": "contrarian", "capital": 200000, "aggression": 0.7},
    
    # 新角色
    "AI量化基金": {"type": "ai", "bias": "neutral", "capital": 8000000, "aggression": 0.95},
    "幣圈鯨魚": {"type": "crypto", "bias": "bull", "capital": 3000000, "aggression": 0.85},
    "中國大媽": {"type": "china", "bias": "bull", "capital": 2000000, "aggression": 0.6},
    "退休基金": {"type": "fund", "bias": "value", "capital": 10000000, "aggression": 0.1},
    "對沖基金": {"type": "hedge", "bias": "neutral", "capital": 5000000, "aggression": 0.8},
    "ETF機器": {"type": "etf", "bias": "neutral", "capital": 3000000, "aggression": 0.2},
    "內幕人士": {"type": "insider", "bias": "bull", "capital": 1000000, "aggression": 0.9},
    "IPO獵人": {"type": "speculator", "bias": "bull", "capital": 500000, "aggression": 0.95},
    "股息獵人": {"type": "income", "bias": "value", "capital": 800000, "aggression": 0.15},
    "期權賣家": {"type": "options", "bias": "neutral", "capital": 2000000, "aggression": 0.4},
    "抄底高手": {"type": "bottom", "bias": "contrarian", "capital": 500000, "aggression": 0.7},
}

class MiroSim:
    def __init__(self, rounds=30):
        self.round = 0
        self.rounds = rounds
        self.agents = []
        self.price = 100.0
        self.history = []
        
        # 創建智能體
        for name, props in AGENTS.items():
            for i in range(3):  # 每種3個
                self.agents.append({
                    "name": f"{name}_{i}",
                    **props,
                    "trades": 0,
                    "pnl": 0
                })
    
    def run_round(self):
        """運行一輪"""
        self.round += 1
        
        # 市場新聞情緒
        sentiment = random.uniform(-0.5, 0.5)
        
        # 每個智能體決策
        for agent in self.agents:
            action = self.decide(agent, sentiment)
            if action:
                agent["trades"] += 1
                agent["pnl"] += action["pnl"]
                self.price += action["impact"]
        
        # 記錄歷史
        self.history.append({
            "round": self.round,
            "price": self.price,
            "sentiment": sentiment,
            "total_trades": sum(a["trades"] for a in self.agents),
            "whale_pnl": sum(a["pnl"] for a in self.agents if a["type"] in ["whale", "hedge"]),
            "retail_pnl": sum(a["pnl"] for a in self.agents if a["type"] == "retail"),
        })
    
    def decide(self, agent, sentiment):
        """智能體決策"""
        bias = agent["bias"]
        agg = agent["aggression"]
        
        # 決策概率
        if bias == "bull":
            prob = 0.5 + sentiment * 0.2 + random.random() * agg * 0.3
        elif bias == "bear":
            prob = 0.5 - sentiment * 0.2 - random.random() * agg * 0.3
        elif bias == "contrarian":
            prob = 0.5 - sentiment * 0.3
        else:
            prob = 0.5 + (random.random() - 0.5) * agg
        
        size = agent["capital"] * random.uniform(0.01, 0.05) / self.price
        
        if random.random() < prob:
            return {"action": "BUY", "size": size, "impact": size * 0.02, "pnl": size * random.uniform(-0.05, 0.1)}
        elif random.random() < 0.2:
            return {"action": "SELL", "size": size, "impact": -size * 0.02, "pnl": size * random.uniform(-0.05, 0.05)}
        return None

def save_chinese_report(sim, scenario_name):
    """儲存為中文MD"""
    filename = f"analysis/MiroFish_{scenario_name}_{datetime.now().strftime('%Y%m%d')}.md"
    
    content = f"""# 🦐 MiroFish 模擬報告：{scenario_name}
## {datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## 模擬設置

### 智能體數量：{len(sim.agents)} 個

| 類型 | 數量 | 角色描述 |
|------|------|----------|
| 科技巨鱷 | 3 | 大型科技股投資者 |
| 淡友巨鱷 | 3 | 對沖基金空頭 |
| 華爾街機構 | 3 | 傳統機構投資者 |
| 散戶大軍 | 3 | 散戶投資者 |
| AI量化基金 | 3 | 演算法交易 |
| 幣圈鯨魚 | 3 | Crypto投資者 |
| 對沖基金 | 3 | 積極對沖 |
| ... | ... | ... |

---

## 模擬結果

### 價格走勢

| 輪次 | 價格 | 市場情緒 | 總交易 |
|------|------|----------|--------|
"""
    
    for h in sim.history[::5]:  # 每5輪顯示
        sentiment_emoji = "🟢" if h["sentiment"] > 0 else "🔴"
        content += f"| {h['round']} | ${h['price']:.2f} | {sentiment_emoji} {h['sentiment']:+.2f} | {h['total_trades']} |\n"
    
    content += f"""

### 智能體表現

| 智能體 | 總交易 | 盈虧 |
|--------|--------|------|
"""
    
    # 分組統計
    by_type = {}
    for a in sim.agents:
        t = a["type"]
        if t not in by_type:
            by_type[t] = {"trades": 0, "pnl": 0}
        by_type[t]["trades"] += a["trades"]
        by_type[t]["pnl"] += a["pnl"]
    
    for t, stats in sorted(by_type.items(), key=lambda x: x[1]["pnl"], reverse=True):
        emoji = "🟢" if stats["pnl"] > 0 else "🔴"
        content += f"| {t} | {stats['trades']} | {emoji} ${stats['pnl']:,.0f} |\n"
    
    content += f"""

---

## 洞察分析

### 市場行為

1. **價格發現**：{sim.history[-1]['whale_pnl'] > sim.history[-1]['retail_pnl'] and "鯨魚主導定價" or "散戶影響市場"}
2. **趨勢強度": {"強" if abs(sim.history[-1]["price"] - 100) > 10 else "溫和"}
3. **交易頻率": {sum(h['total_trades'] for h in sim.history)} 次

### 智能體互動

"""
    
    # 找出最佳和最差
    best = max(sim.agents, key=lambda x: x["pnl"])
    worst = min(sim.agents, key=lambda x: x["pnl"])
    
    content += f"- 🏆 最佳表現：{best['name']} (${best['pnl']:,.0f})\n"
    content += f"- 💔 最差表現：{worst['name']} (${worst['pnl']:,.0f})\n"
    
    content += f"""

---

## 模擬結論

{"價格呈現上漲趨勢，市場情緒偏多" if sim.history[-1]["price"] > 100 else "價格呈現下跌趨勢，市場情緒偏空"}

總交易次數：{sum(h['total_trades'] for h in sim.history)}
平均每輪交易：{sum(h['total_trades'] for h in sim.history) / sim.rounds:.1f}

---

*模擬時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    with open(str(Path(__file__).resolve().parent.parent.parent.parent / filename), 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filename

def run_scenario(name, rounds=30):
    """運行情境"""
    sim = MiroSim(rounds=rounds)
    for _ in range(rounds):
        sim.run_round()
    
    filename = save_chinese_report(sim, name)
    return sim, filename

def send_telegram(sim, name):
    """發送到Telegram"""
    if not MIRO_TOKEN:
        print("No token")
        return
    
    msg = f"🦐 <b>MiroFish: {name}</b>\n\n"
    
    # 價格變化
    change = sim.history[-1]["price"] - 100
    emoji = "🟢" if change > 0 else "🔴"
    msg += f"📊 價格: ${sim.history[-1]['price']:.2f} ({emoji} {change:+.1f}%)\n\n"
    
    # 智能體表現
    msg += "<b>智能體表現:</b>\n"
    
    by_type = {}
    for a in sim.agents:
        t = a["type"]
        if t not in by_type:
            by_type[t] = 0
        by_type[t] += a["pnl"]
    
    for t, pnl in sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:5]:
        e = "🟢" if pnl > 0 else "🔴"
        msg += f"• {t}: {e} ${pnl:,.0f}\n"
    
    requests.post(f"https://api.telegram.org/bot{MIRO_TOKEN}/sendMessage",
        json={"chat_id": "-1003713254306", "text": msg, "parse_mode": "HTML"})

if __name__ == '__main__':
    # 運行10個情境
    scenarios = [
        "鯨魚大戰散戶",
        "AI量化崩潰",
        "中國資金湧入",
        "機構vs散戶",
        "幣圈風暴",
        "恐懼蔓延",
        "FOMO狂潮",
        "價值投資vs趨勢",
        "期權轟炸",
        "抄底輪迴"
    ]
    
    for name in scenarios:
        print(f"Running: {name}")
        sim, filename = run_scenario(name)
        send_telegram(sim, name)
        print(f"  → {filename}")
