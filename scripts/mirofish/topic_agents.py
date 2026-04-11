"""
MiroFish Agent Templates by Topic Category
"""

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
    "default": [
        {"name": "樂觀者", "role": "正面", "style": "積極"},
        {"name": "悲觀者", "role": "負面", "style": "保守"},
        {"name": "中立者", "role": "客觀", "style": "分析"},
        {"name": "愛好者", "role": "狂熱", "style": "激情"},
        {"name": "懷疑者", "role": "質疑", "style": "批判"},
    ]
}

def get_agents_for_topic(keyword):
    """Get relevant agents based on topic keyword"""
    keyword = keyword.lower()
    
    for topic, agents in TOPIC_AGENTS.items():
        if topic in keyword:
            return agents
    
    return TOPIC_AGENTS["default"]
