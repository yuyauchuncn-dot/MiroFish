#!/usr/bin/env python3
"""
MiroFish LLM-Powered Bot - Uses LLM to generate relevant agents and topics
"""
import os, sys, requests, json, random
from datetime import datetime

TOKEN = "8536830590:AAFEFFHDI5ENeGD92dlHJ8RiEmmcaQDkCm0"
CHAT_ID = "-1003713254306"
STATE_FILE = str(Path(__file__).resolve().parent.parent.parent.parent / 'data' / 'mirofish_state.json')

os.makedirs(str(Path(__file__).resolve().parent.parent.parent.parent / 'data'), exist_ok=True)

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except: return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def send(msg, chat_id=CHAT_ID):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"})

def ask_llm(prompt):
    """Use OpenAI-compatible API to generate content"""
    try:
        # Use OpenRouter or similar
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {os.environ.get('OPENROUTER_KEY', '')}",
            "Content-Type": "application/json"
        }
        
        # Try free tier or skip if no key
        if not os.environ.get('OPENROUTER_KEY'):
            return None
            
        data = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500
        }
        
        r = requests.post(url, headers=headers, json=data, timeout=30)
        if r.status_code == 200:
            return r.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"LLM Error: {e}")
    return None

def generate_agents_with_llm(keyword):
    """Use LLM to generate relevant agents for any topic"""
    prompt = f"""Generate 5 different types of agents/debaters for discussing "{keyword}".

Each agent should have:
- Name (in Chinese)
- Their perspective/belief
- How strongly they believe (1-10)

Format as JSON list:
[
  {{"name": "名稱", "role": "角色描述", "belief": "觀點", "strength": 1-10}},
  ...
]

Return ONLY valid JSON, no other text."""

    # Try LLM first
    result = ask_llm(prompt)
    
    if result:
        try:
            agents = json.loads(result)
            return agents
        except:
            pass
    
    # Fallback: generic debaters
    return [
        {"name": "支持者", "role": "支持方", "belief": f"{keyword}很好", "strength": 8},
        {"name": "反對者", "role": "反對方", "belief": f"{keyword}有問題", "strength": 7},
        {"name": "中立者", "role": "分析師", "belief": "需要更多證據", "strength": 5},
        {"name": "愛好者", "role": "粉絲", "belief": f"最鍾意{keyword}", "strength": 9},
        {"name": "懷疑者", "role": "質疑者", "belief": "持保留態度", "strength": 6},
    ]

def generate_topics_with_llm(keyword):
    """Use LLM to generate relevant discussion topics"""
    prompt = f"""Generate 5 interesting discussion topics/debate questions about "{keyword}".

These should be thought-provoking questions that people would actually debate.
Format as JSON list of strings:
["topic 1", "topic 2", ...]"""

    result = ask_llm(prompt)
    
    if result:
        try:
            topics = json.loads(result)
            return topics
        except:
            pass
    
    # Fallback
    return [
        f"{keyword}的未來發展",
        f"{keyword}的優缺點",
        f"{keyword} vs 替代品",
        f"點評{keyword}",
        f"{keyword}熱潮"
    ]

def simulate_discussion(agents, topic):
    """Simulate a discussion/debate"""
    # Each agent states their position
    statements = []
    for agent in agents:
        stance = random.choice(["同意", "反對", "部分同意", "中立"])
        statements.append({
            "agent": agent["name"],
            "stance": stance,
            "belief": agent["belief"]
        })
    
    # Determine consensus
    agrees = sum(1 for s in statements if s["stance"] in ["同意", "部分同意"])
    consensus = agrees / len(statements) * 100
    
    return {
        "topic": topic,
        "statements": statements,
        "consensus": consensus,
        "winner": max(agents, key=lambda x: x["strength"])["name"]
    }

def handle_message(text, chat_id):
    text = text.strip()
    state = load_state()
    
    # /start
    if text == "/start":
        save_state({})
        return "🦐 <b>MiroFish Bot</b>\n\n生成任何主題既討論！\n/topic <關鍵詞>\n/topic food\n/topic 深圳\n/topic music"
    
    # /topic command
    if text.startswith("/topic "):
        keyword = text[7:].strip()
        
        # Generate with LLM
        topics = generate_topics_with_llm(keyword)
        agents = generate_agents_with_llm(keyword)
        
        state["awaiting"] = "choice"
        state["topics"] = topics
        state["agents"] = agents
        state["keyword"] = keyword
        save_state(state)
        
        msg = f"🧠 <b>「{keyword}」既5個討論主題：</b>\n\n"
        for i, t in enumerate(topics, 1):
            msg += f"{i}. {t}\n"
        msg += "\n<b>選擇：</b>1-5 / all / new"
        
        send(msg, chat_id)
        return None
    
    # Choice handling
    if state.get("awaiting") == "choice":
        topics = state.get("topics", [])
        agents = state.get("agents", [])
        
        if text.isdigit() and 1 <= int(text) <= len(topics):
            topic = topics[int(text) - 1]
            result = simulate_discussion(agents, topic)
            
            emoji = "🟢" if result["consensus"] > 60 else "🔴" if result["consensus"] < 40 else "🟡"
            
            msg = f"🦐 <b>{topic}</b>\n\n"
            msg += f"📊 共識度：{emoji} {result['consensus']:.0f}%\n\n"
            msg += "<b>各方觀點：</b>\n"
            for s in result["statements"]:
                msg += f"• {s['agent']} ({s['stance']}): {s['belief']}\n"
            
            msg += f"\n🏆 觀點最強：{result['winner']}"
            
            send(msg, chat_id)
            
        elif text.lower() == "all":
            results = [simulate_discussion(agents, t) for t in topics]
            
            msg = f"✅ <b>完成{len(topics)}個討論：</b>\n\n"
            for r in results:
                emoji = "🟢" if r["consensus"] > 60 else "🔴" if r["consensus"] < 40 else "🟡"
                msg += f"• {r['topic'][:30]}: {emoji} {r['consensus']:.0f}%\n"
            
            send(msg, chat_id)
            
        elif text.lower() == "new":
            keyword = state.get("keyword", "topic")
            topics = generate_topics_with_llm(keyword + " debate")
            state["topics"] = topics
            save_state(state)
            
            msg = "🔄 <b>新主題：</b>\n\n"
            for i, t in enumerate(topics, 1):
                msg += f"{i}. {t}\n"
            msg += "\n選擇：1-5 / all / new"
            
            send(msg, chat_id)
        
        save_state({})
        return None
    
    return "❓ /topic <關鍵詞>"

def polling():
    offset = 0
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates?timeout=60&offset={offset}", timeout=65)
            data = r.json()
            
            if data.get("ok"):
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    
                    if "message" in update:
                        msg = update["message"]
                        text = msg.get("text", "")
                        chat_id = msg["chat"]["id"]
                        
                        reply = handle_message(text, chat_id)
                        if reply:
                            send(reply, chat_id)
                            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    print("Starting LLM-powered MiroFish...")
    polling()
