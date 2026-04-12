#!/usr/bin/env python3
"""MiroFish Interactive Bot - Topic-specific agents"""
import os, sys, requests, json, random
from pathlib import Path
from datetime import datetime

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1003713254306")
_MONO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent  # scripts/mirofish → mirofish → monorepo
STATE_FILE = str(_MONO_ROOT / "data" / "mirofish_state.json")
os.makedirs(str(_MONO_ROOT / "data"), exist_ok=True)

# Topic-specific agents
TOPIC_AGENTS = {
    "food": [
        {"name": "米其林廚師", "role": "美食家", "style": "講究"},
        {"name": "街頭小食老闆", "role": "實用派", "style": "實際"},
        {"name": "營養師", "role": "健康專家", "style": "科學"},
        {"name": "美食博主", "role": "網紅", "style": "流量"},
        {"name": "環保人士", "role": "永續論者", "style": "道德"},
    ],
    "music": [
        {"name": "古典音樂家", "role": "傳統派", "style": "優雅"},
        {"name": "獨立音樂人", "role": "地下", "style": "另類"},
        {"name": "流行歌手", "role": "商業", "style": "主流"},
        {"name": "音樂製作人", "role": "技術", "style": "專業"},
        {"name": "樂評人", "role": "評論", "style": "分析"},
    ],
    "travel": [
        {"name": "背包客", "role": "窮遊", "style": "自由"},
        {"name": "商務旅客", "role": "效率", "style": "快速"},
        {"name": "酒店試睡員", "role": "體驗", "style": "舒適"},
        {"name": "航空公司", "role": "服務", "style": "品質"},
        {"name": "導遊", "role": "專業", "style": "導覽"},
    ],
    "tech": [
        {"name": "程式員", "role": "開發者", "style": "技術"},
        {"name": "Startup創辦人", "role": "企業家", "style": "顛覆"},
        {"name": "VC投資者", "role": "資本", "style": "商業"},
        {"name": "科技評論員", "role": "觀察", "style": "分析"},
        {"name": "用戶", "role": "市場", "style": "實用"},
    ],
    "深圳": [
        {"name": "深圳業主", "role": "地產商", "style": "投資"},
        {"name": "科技从业员", "role": "工程師", "style": "創新"},
        {"name": "香港投資者", "role": "跨境", "style": "務實"},
        {"name": "創業者", "role": "Startup", "style": "冒險"},
        {"name": "規劃師", "role": "政府", "style": "宏觀"},
    ],
    "default": [
        {"name": "樂觀者", "role": "正面", "style": "積極"},
        {"name": "悲觀者", "role": "負面", "style": "保守"},
        {"name": "中立者", "role": "客觀", "style": "分析"},
        {"name": "愛好者", "role": "狂熱", "style": "激情"},
        {"name": "懷疑者", "role": "質疑", "style": "批判"},
    ]
}

# Discussion topics per topic
TOPIC_DISCUSSIONS = {
    "food": [
        "邊種食物最好食？",
        "街邊小吃定高級餐廳？",
        "健康定口味重要？",
        "外賣會取代堂食？",
        "咩係真正既美食？",
    ],
    "music": [
        "串流平台破壞音樂？",
        "古典定流行更有價值？",
        "獨立音樂人既出路？",
        "AI會取代音樂人？",
        "演唱會既意義？",
    ],
    "travel": [
        "窮遊定豪華遊？",
        "自由行定旅行團？",
        "酒店定民宿好？",
        "航空服務質素下降？",
        "旅行既意義係咩？",
    ],
    "深圳": [
        "深圳樓市仲有前途？",
        "深港融合好唔好？",
        "深圳創業既機會？",
        "前海發展方向？",
        "深圳定香港更適合居住？",
    ],
    "default": [
        "呢個Topic既未來？",
        "支持定反對？",
        "優點同缺點？",
        "點樣影響日常生活？",
        "值唔值得關注？",
    ]
}

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

def get_agents(keyword):
    """Get topic-specific agents"""
    keyword = keyword.lower()
    for topic, agents in TOPIC_AGENTS.items():
        if topic in keyword:
            return agents
    return TOPIC_AGENTS["default"]

def get_topics(keyword):
    """Get topic-specific discussions"""
    keyword = keyword.lower()
    for topic, topics in TOPIC_DISCUSSIONS.items():
        if topic in keyword:
            return topics
    return TOPIC_DISCUSSIONS["default"]

def run_discussion(topic, agents):
    """Simulate discussion"""
    statements = []
    for agent in agents:
        stances = ["完全同意", "同意", "部分同意", "中立", "不同意", "強烈反對"]
        stance = random.choice(stances)
        statements.append({
            "agent": agent["name"],
            "role": agent["role"],
            "stance": stance,
            "style": agent["style"]
        })
    
    # Calculate consensus
    positive = sum(1 for s in statements if "同意" in s["stance"])
    consensus = positive / len(statements) * 100
    
    return {
        "topic": topic,
        "statements": statements,
        "consensus": consensus,
        "winner": max(agents, key=lambda x: len(x["name"]))["name"]
    }

def handle_message(text, chat_id):
    text = text.strip()
    state = load_state()
    
    if text == "/start":
        save_state({})
        return "🦐 <b>MiroFish Bot</b>\n\n/topic <關鍵詞>\n/topic food\n/topic music\n/topic 深圳"
    
    if text.startswith("/topic "):
        keyword = text[7:].strip()
        topics = get_topics(keyword)
        agents = get_agents(keyword)
        
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
    
    if state.get("awaiting") == "choice":
        topics = state.get("topics", [])
        agents = state.get("agents", [])
        
        if text.isdigit() and 1 <= int(text) <= len(topics):
            topic = topics[int(text) - 1]
            result = run_discussion(topic, agents)
            
            emoji = "🟢" if result["consensus"] > 60 else "🔴" if result["consensus"] < 40 else "🟡"
            
            msg = f"🦐 <b>{topic}</b>\n\n"
            msg += f"📊 共識：{emoji} {result['consensus']:.0f}%\n\n"
            msg += "<b>各方觀點：</b>\n"
            for s in result["statements"]:
                msg += f"• {s['agent']} ({s['role']}): {s['stance']}\n"
            
            msg += f"\n🏆 {result['winner']}既觀點最影響討論"
            
            send(msg, chat_id)
            
        elif text.lower() == "all":
            results = [run_discussion(t, agents) for t in topics]
            
            msg = f"✅ <b>完成{len(topics)}個討論：</b>\n\n"
            for r in results:
                emoji = "🟢" if r["consensus"] > 60 else "🔴" if r["consensus"] < 40 else "🟡"
                msg += f"• {r['topic'][:25]}: {emoji} {r['consensus']:.0f}%\n"
            
            send(msg, chat_id)
            
        elif text.lower() == "new":
            keyword = state.get("keyword", "default")
            topics = get_topics(keyword + "_new")
            
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
    if len(sys.argv) > 1:
        print(handle_message(sys.argv[1], "test"))
    else:
        print("Starting...")
        polling()
