#!/usr/bin/env python3
"""Simple simulation runner for any topic"""
import random, os
from datetime import datetime

def run_sim(topic):
    """Run a simple simulation for any topic"""
    price = 100.0
    history = [price]
    
    # 60 days
    for day in range(60):
        # Random movement
        change = random.uniform(-0.05, 0.06)
        price *= (1 + change)
        history.append(price)
    
    final_change = (price - 100) / 100 * 100
    
    # Agents
    agents = [
        ("樂觀者", random.uniform(-5, 20)),
        ("悲觀者", random.uniform(-15, 10)),
        ("中立者", random.uniform(-5, 15)),
        ("激進者", random.uniform(-20, 25)),
        ("保守者", random.uniform(-3, 12)),
    ]
    agents.sort(key=lambda x: x[1], reverse=True)
    
    return {
        "topic": topic,
        "final_change": final_change,
        "history": history,
        "agents": agents,
        "winner": agents[0][0],
    }

# Test
if __name__ == "__main__":
    result = run_sim("測試主題")
    print(f"✅ {result['topic']}: {result['final_change']:+.1f}%")
    print(f"   Winner: {result['winner']}")
