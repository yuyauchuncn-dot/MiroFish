#!/usr/bin/env python3
"""
MiroFish Advanced Scenarios
Simulate different market conditions and agent behaviors
"""
import random, sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

def scenario_crash():
    """Simulate market crash scenario"""
    agents = create_agents()
    
    # Negative sentiment cascade
    for day in range(10):
        sentiment = -0.8 - (day * 0.02)  # Increasingly negative
        simulate_day(agents, sentiment)
    
    return analyze_fear cascade()

def scenario_fomo():
    """Simulate FOMO rally"""
    agents = create_agents()
    
    for day in range(10):
        sentiment = 0.5 + (day * 0.05)  # Increasing FOMO
        simulate_day(agents, sentiment)
    
    return analyze_momentum()

def scenario_whale_vs_retail():
    """Whale vs Retail battle"""
    results = []
    
    for trial in range(5):
        whales_aggressive = random.uniform(0.8, 1.0)
        retail_aggressive = random.uniform(0.3, 0.6)
        
        whale_impact = whales_aggressive * 1000000 * 0.01
        retail_impact = retail_aggressive * 10000 * 0.01
        
        results.append({
            "whale": whale_impact,
            "retail": retail_impact,
            "winner": "whale" if whale_impact > retail_impact else "retail"
        })
    
    return results

def create_agents():
    return [
        {"type": "whale", "bias": "bull", "capital": 1000000},
        {"type": "whale", "bias": "bear", "capital": 1000000},
        {"type": "retail", "bias": "bull", "capital": 10000},
        {"type": "retail", "bias": "bear", "capital": 10000},
        {"type": "institution", "bias": "neutral", "capital": 500000},
    ]

def simulate_day(agents, sentiment):
    pass  # Simplified

def analyze_fear_cascade():
    return {"insight": "Fear cascades faster than greed. Whales exit first."}

def analyze_momentum():
    return {"insight": "FOMO creates self-reinforcing rallies."}

if __name__ == '__main__':
    print("=== MiroFish Scenarios ===")
    print("1. Crash Simulation")
    print("2. FOMO Rally")
    print("3. Whale vs Retail")
