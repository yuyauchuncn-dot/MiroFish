#!/usr/bin/env python3
"""
MiroFish Agent-Based Market Analysis Bot
Analyzes how individual agent actions create emergent market behavior
"""
import os, sys, json, random, subprocess
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
with open(Path(__file__).resolve().parent.parent.parent.parent / '.env') as f:
    for line in f:
        if '=' in line:
            k, v = line.strip().split('=', 1)
            os.environ[k] = v

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

def send(msg):
    if not TOKEN: return
    import requests
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})

# Agent Types
AGENT_TYPES = {
    "bull_whale": {"type": "whale", "bias": "bull", "aggression": 0.9, "capital": 1000000},
    "bear_whale": {"type": "whale", "bias": "bear", "aggression": 0.9, "capital": 1000000},
    "retail_fomo": {"type": "retail", "bias": "bull", "aggression": 0.7, "capital": 10000},
    "retail_fear": {"type": "retail", "bias": "bear", "aggression": 0.6, "capital": 10000},
    "institution": {"type": "institution", "bias": "neutral", "aggression": 0.4, "capital": 500000},
    "contrarian": {"type": "speculator", "bias": "contrarian", "aggression": 0.8, "capital": 50000},
}

def simulate_market_day(agents, news_sentiment=0):
    """Simulate one day of market with agent interactions"""
    trades = []
    price = 100.0
    
    for agent in agents:
        action = decide_action(agent, news_sentiment, price)
        if action:
            trades.append(action)
            price += action['impact']
    
    return {"price": price, "trades": trades, "volume": len(trades)}

def decide_action(agent, sentiment, price):
    """Agent decides to buy/sell based on type"""
    import random
    
    bias = agent['bias']
    agg = agent['aggression']
    
    # Decision factor
    if bias == "bull":
        prob_buy = 0.5 + (sentiment * 0.2) + (random.random() * agg * 0.3)
    elif bias == "bear":
        prob_buy = 0.5 - (sentiment * 0.2) - (random.random() * agg * 0.3)
    else:  # neutral/contrarian
        prob_buy = 0.5 + (random.random() - 0.5) * agg
    
    if random.random() < prob_buy:
        size = agent['capital'] * random.uniform(0.01, 0.1) / price
        return {
            "agent": agent['name'],
            "type": agent['type'],
            "action": "BUY",
            "size": size,
            "impact": size * 0.01 * agg
        }
    elif random.random() < 0.3:
        size = agent['capital'] * random.uniform(0.01, 0.05) / price
        return {
            "agent": agent['name'],
            "type": agent['type'],
            "action": "SELL",
            "size": size,
            "impact": -size * 0.01 * agg
        }
    return None

def run_simulation():
    """Run agent-based market simulation"""
    # Create agents
    agents = []
    for name, props in AGENT_TYPES.items():
        for i in range(3):  # 3 of each type
            agents.append({
                "name": f"{name}_{i}",
                **props
            })
    
    # Simulate 30 days
    results = []
    for day in range(30):
        # Random news sentiment (-1 to 1)
        sentiment = random.uniform(-0.5, 0.5)
        result = simulate_market_day(agents, sentiment)
        results.append(result)
    
    return results

def analyze_emergent_behavior(results):
    """Analyze how individual actions create market behavior"""
    bullish_days = sum(1 for r in results if r['price'] > 100)
    bearish_days = sum(1 for r in results if r['price'] < 100)
    
    # Calculate whale impact
    whale_impact = sum(
        sum(t['impact'] for t in r['trades'] if t['type'] == 'whale')
        for r in results
    )
    
    retail_impact = sum(
        sum(t['impact'] for t in r['trades'] if t['type'] == 'retail')
        for r in results
    )
    
    return {
        "bullish_days": bullish_days,
        "bearish_days": bearish_days,
        "whale_impact": whale_impact,
        "retail_impact": retail_impact,
        "total_volume": sum(r['volume'] for r in results),
    }

def mirofish_analysis():
    """Main analysis"""
    results = run_simulation()
    analysis = analyze_emergent_behavior(results)
    
    msg = f"🦐 <b>MiroFish Agent Analysis</b>\n\n"
    msg += f"<b>30-Day Simulation Results:</b>\n\n"
    msg += f"📈 Bullish Days: {analysis['bullish_days']}\n"
    msg += f"📉 Bearish Days: {analysis['bearish_days']}\n\n"
    
    msg += f"<b>Agent Impact:</b>\n"
    msg += f"🐋 Whales: {analysis['whale_impact']:+.2f}%\n"
    msg += f"🐟 Retail: {analysis['retail_impact']:+.2f}%\n"
    msg += f"📊 Total Volume: {analysis['total_volume']} trades\n\n"
    
    msg += f"<b>Emergent Insight:</b>\n"
    if analysis['whale_impact'] > analysis['retail_impact']:
        msg += "Whales dominate price discovery. Retail follows."
    else:
        msg += "Retail activity drives sentiment. Institutions arbitrage."
    
    send(msg)
    print("✅ MiroFish analysis sent!")

if __name__ == '__main__':
    mirofish_analysis()
