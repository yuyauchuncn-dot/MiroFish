#!/usr/bin/env python3
"""
MiroFish AI Impact Simulation
Simulates the long-term impact of AI on employment and the economy
"""
import random, sys, os
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

# Load telegram
with open(Path(__file__).resolve().parent.parent.parent.parent / '.env') as f:
    for line in f:
        if '=' in line:
            k, v = line.strip().split('=', 1)
            os.environ[k] = v

import requests
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

def send(msg):
    if not TOKEN: return
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})

# AI Impact Agent Types
AI_AGENTS = {
    "tech_worker": {
        "name": "Tech Worker",
        "initial_count": 1000,
        "income": 80000,
        "replaced_by_ai": 0.3,
        "adaptable": 0.4,
    },
    "blue_collar": {
        "name": "Blue Collar",
        "initial_count": 2000,
        "income": 45000,
        "replaced_by_ai": 0.6,
        "adaptable": 0.2,
    },
    "service_worker": {
        "name": "Service Worker",
        "initial_count": 1500,
        "income": 35000,
        "replaced_by_ai": 0.5,
        "adaptable": 0.3,
    },
    "creative": {
        "name": "Creative/Writer",
        "initial_count": 500,
        "income": 55000,
        "replaced_by_ai": 0.4,
        "adaptable": 0.4,
    },
    "manager": {
        "name": "Manager",
        "initial_count": 800,
        "income": 95000,
        "replaced_by_ai": 0.25,
        "adaptable": 0.5,
    },
    "healthcare": {
        "name": "Healthcare",
        "initial_count": 600,
        "income": 75000,
        "replaced_by_ai": 0.2,
        "adaptable": 0.6,
    },
}

class EconomySimulation:
    def __init__(self):
        self.year = 2026
        self.agents = {}
        self.gdp = 25000000000
        self.unemployment_rate = 4.0
        self.ai_maturity = 0.1
        
        for agent_type, props in AI_AGENTS.items():
            self.agents[agent_type] = {
                'count': props['initial_count'],
                'employed': props['initial_count'],
                'displaced': 0,
                'adapted': 0,
                'income': props['income'],
                'replaced': props['replaced_by_ai'],
                'adaptable': props['adaptable']
            }
    
    def evolve_ai(self):
        self.ai_maturity = min(1.0, self.ai_maturity + 0.15)
    
    def simulate_year(self):
        self.year += 1
        
        # GDP growth
        ai_contribution = self.ai_maturity * 0.03
        self.gdp *= (1 + 0.02 + ai_contribution)
        
        # Automation
        for agent_type, agent in self.agents.items():
            props = AI_AGENTS[agent_type]
            replace_rate = props['replaced_by_ai'] * self.ai_maturity
            
            displaced = int(agent['employed'] * replace_rate * 0.1)
            agent['displaced'] += displaced
            agent['employed'] -= displaced
            
            adaptable = int(displaced * props['adaptable'])
            agent['adapted'] += adaptable
            agent['employed'] += adaptable
        
        total_employed = sum(a['employed'] for a in self.agents.values())
        total_workforce = sum(a['count'] for a in self.agents.values())
        self.unemployment_rate = (total_workforce - total_employed) / total_workforce * 100
        
        return {
            'year': self.year,
            'ai_maturity': self.ai_maturity,
            'unemployment': self.unemployment_rate,
            'displaced': sum(a['displaced'] for a in self.agents.values()),
            'employed': sum(a['employed'] for a in self.agents.values()),
        }

def run_simulation():
    sim = EconomySimulation()
    snapshots = []
    for year in range(20):
        snap = sim.simulate_year()
        sim.evolve_ai()
        snapshots.append(snap)
    return snapshots

def analyze_results(snapshots):
    final = snapshots[-1]
    initial = snapshots[0]
    
    max_unemployment = max(s['unemployment'] for s in snapshots)
    max_year = [s['year'] for s in snapshots if s['unemployment'] == max_unemployment][0]
    
    recovery_year = None
    for s in snapshots:
        if s['unemployment'] <= 6.0 and s['year'] > 2030:
            recovery_year = s['year']
            break
    
    total_displaced = final['displaced']
    total_adapted = sum(snapshots[-1][k] for k in ['employed'])  # Simplified
    
    return {
        'peak_unemployment': max_unemployment,
        'peak_year': max_year,
        'recovery_year': recovery_year or 'Never',
        'final_unemployment': final['unemployment'],
        'total_displaced': total_displaced,
        'gdp_growth': (snapshots[-1]['ai_maturity'] * 300),
        'ai_maturity': final['ai_maturity'],
    }

def main():
    snapshots = run_simulation()
    analysis = analyze_results(snapshots)
    
    msg = f"🦾 <b>MiroFish: AI Impact Simulation</b>\n"
    msg += f"<i>20-Year Projection (2026-2046)</i>\n\n"
    
    msg += f"<b>📊 Key Findings:</b>\n\n"
    msg += f"🏔️ Peak Unemployment: {analysis['peak_unemployment']:.1f}% ({analysis['peak_year']})\n"
    msg += f"📉 Workers Impacted: {analysis['total_displaced']:,.0f}\n"
    msg += f"💚 Recovery Year: {analysis['recovery_year']}\n"
    msg += f"📈 Final Unemployment: {analysis['final_unemployment']:.1f}%\n"
    msg += f"🤖 AI Maturity: {analysis['ai_maturity']*100:.0f}%\n\n"
    
    msg += f"<b>🔮 The End State (2046):</b>\n\n"
    
    if analysis['final_unemployment'] < 8:
        msg += "✅ <b>UTOPIAN:</b> AI creates more jobs than it destroys.\n"
        msg += "   Humans focus on creativity, care, and meaning.\n"
    elif analysis['final_unemployment'] < 15:
        msg += "⚠️ <b>TRANSITIONAL:</b> Short-term pain, long-term gain.\n"
        msg += "   UBI and reskilling stabilize society.\n"
    else:
        msg += "⚠️ <b>NEEDS ACTION:</b> Mass displacement requires intervention.\n"
    
    send(msg)
    print("✅ Sent!")

if __name__ == '__main__':
    main()
