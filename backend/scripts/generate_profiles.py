"""
模拟配置文件生成器 - ProMax版本
支持生成带有数值锚点（Numeric Anchors）的Agent配置

功能：
- 生成simulation_config.json
- 生成Twitter/Reddit profiles
- 添加金融状态跟踪（cash_balance, monthly_expenses, panic_index）
- 支持从agents配置文件读取
"""

import os
import sys
import json
import random
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

# 添加scripts目录到路径
_script_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.abspath(os.path.join(_script_dir, '..'))
sys.path.insert(0, _script_dir)
sys.path.insert(0, _backend_dir)


# ============================================================
# 数值锚点配置 (Numeric Anchors Configuration)
# ============================================================

# 角色类型对应的金融状态模板
FINANCIAL_TEMPLATES = {
    # 刚需客 - 现金有限，月供压力大
    "刚需客": {
        "cash_range": (50, 200),  # 万元
        "monthly_expenses_range": (0.8, 1.5),  # 万元/月
        "panic_range": (60, 95),  # 恐慌指数
        "disposition": "anxious",
    },
    # 置换客 - 有房但需要卖房置换
    "置换客": {
        "cash_range": (100, 500),
        "monthly_expenses_range": (1.0, 2.5),
        "panic_range": (40, 80),
        "disposition": "cautious",
    },
    # 长线投资客 - 资金充足，观望为主
    "长线投资客": {
        "cash_range": (500, 2000),
        "monthly_expenses_range": (0.5, 1.5),
        "panic_range": (10, 40),
        "disposition": "cold_blooded",
    },
    # 短线炒家 - 高杠杆，高风险
    "短线炒家": {
        "cash_range": (200, 800),
        "monthly_expenses_range": (2.0, 5.0),
        "panic_range": (50, 90),
        "disposition": "aggressive",
    },
    # 房产中介 - 靠佣金吃饭
    "中介": {
        "cash_range": (30, 150),
        "monthly_expenses_range": (0.5, 1.2),
        "panic_range": (30, 70),
        "disposition": "pragmatic",
    },
    # 分析师 - 理性分析
    "分析师": {
        "cash_range": (100, 400),
        "monthly_expenses_range": (0.8, 1.8),
        "panic_range": (20, 50),
        "disposition": "analytical",
    },
}

# 地区配置
AREA_CONFIG = {
    "深圳北站": {
        "current_price": 6.4,  # 万/平米
        "base_price": 6.0,  # 底部支撑价
        "price_range": (5.5, 7.5),  # 预期波动范围
    },
    "龙华": {
        "current_price": 5.5,
        "base_price": 4.5,
        "price_range": (4.0, 6.5),
    },
    "福田": {
        "current_price": 9.4,
        "base_price": 8.0,
        "price_range": (7.5, 11.0),
    },
    "南山": {
        "current_price": 10.5,
        "base_price": 9.0,
        "price_range": (8.5, 12.5),
    },
}


def generate_financial_state(role_type: str) -> Dict[str, Any]:
    """
    为特定角色类型生成金融状态
    
    Args:
        role_type: 角色类型
        
    Returns:
        包含金融状态的字典
    """
    template = FINANCIAL_TEMPLATES.get(role_type, FINANCIAL_TEMPLATES["刚需客"])
    
    cash = random.uniform(*template["cash_range"])
    monthly_expenses = random.uniform(*template["monthly_expenses_range"])
    panic_index = random.uniform(*template["panic_range"])
    
    # 计算现金流可以支撑多少个月
    months_of_solvency = cash / monthly_expenses if monthly_expenses > 0 else 999
    
    # 如果现金很少，恐慌指数升高
    if cash < 100:
        panic_index = min(95, panic_index + (100 - cash) / 5)
    
    return {
        "cash_balance": round(cash, 2),  # 万元
        "monthly_expenses": round(monthly_expenses, 2),  # 万元/月
        "panic_index": round(panic_index, 1),  # 0-100
        "months_of_solvency": round(months_of_solvency, 1),
        "disposition": template["disposition"],
        # 额外计算：强制卖出阈值
        "force_sell_threshold": round(cash * 0.3, 2),  # 现金低于30%时考虑强制卖出
    }


def generate_agent_prompt_with_anchors(
    agent_config: Dict[str, Any],
    area_config: Dict[str, Any],
    financial_state: Dict[str, Any]
) -> str:
    """
    生成带有数值锚点的Agent提示词
    
    Args:
        agent_config: Agent配置
        area_config: 地区配置
        financial_state: 金融状态
        
    Returns:
        完整的system prompt
    """
    role = agent_config.get("role_type", "刚需客")
    entity_name = agent_config.get("entity_name", "Agent")
    background = agent_config.get("background", "")
    
    current_price = area_config.get("current_price", 6.4)
    base_price = area_config.get("base_price", 6.0)
    
    # 数值锚点部分
    numeric_anchors = f"""
## 你的财务状态 (数值锚点)

你必须时刻关注自己的财务状况，在做出任何房产决策前必须先核算：

1. **现金余额**: {financial_state['cash_balance']} 万元
2. **每月固定支出**: {financial_state['monthly_expenses']} 万元/月
3. **恐慌指数**: {financial_state['panic_index']}/100 (越高表示越焦虑)
4. **资金可支撑月数**: {financial_state['months_of_solvency']} 个月

### 强制卖出规则

如果你的现金余额低于 **{financial_state['force_sell_threshold']} 万元** (即现金的30%)，你将失去看多或观望的资格，**必须执行卖出或观望卖出**。这是你最后的流动性保障。

### 决策规则

- 如果你的恐慌指数 > 70：你倾向于卖出或保持观望
- 如果你的恐慌指数 < 30：你更可能考虑买入或持有
- 如果现金为负：你必须卖出，没有任何例外

## 市场锚点

- 当前均价: {current_price} 万/平米
- 心理底部: {base_price} 万/平米
- 你的策略应该围绕这些价格锚点展开
"""
    
    # 基础prompt
    base_prompt = f"""你是一个名为 {entity_name} 的{role}。

## 背景

{background}

## 关键行为准则

1. 你必须用第一人称发言，像一个真实的人
2. 在发表关于房价的观点前，先检查你的财务状态
3. 如果你财务状况紧张（现金不足），你必须表达担忧或考虑卖出
4. 保持角色的真实性，不要总是唱多或唱空
5. 可以和其他角色互动、争论

{numeric_anchors}

## 当前话题

近期房地产市场讨论热点：
- 增值税2年免征政策
- 信贷政策宽松
- 深圳北站区域房价走势
- 龙华边缘片区置换问题

请积极参与讨论，表达你真实的观点和担忧。"""

    return base_prompt


def generate_simulation_config(
    area: str = "深圳北站",
    num_agents: int = 30,
    simulation_hours: int = 72,
    output_dir: str = ".",
    agents_config_path: str = None,
    add_numeric_anchors: bool = True,
) -> Dict[str, Any]:
    """
    生成模拟配置文件
    
    Args:
        area: 地区名称
        num_agents: Agent数量
        simulation_hours: 模拟时长（小时）
        output_dir: 输出目录
        agents_config_path: Agent配置文件路径（可选）
        add_numeric_anchors: 是否添加数值锚点
        
    Returns:
        完整配置字典
    """
    # 获取地区配置
    area_cfg = AREA_CONFIG.get(area, AREA_CONFIG["深圳北站"])
    
    # 加载或生成agent配置
    if agents_config_path and os.path.exists(agents_config_path):
        with open(agents_config_path, 'r', encoding='utf-8') as f:
            agents = json.load(f)
    else:
        agents = generate_default_agents(num_agents, area)
    
    # 构建agent_configs
    agent_configs = []
    for i, agent in enumerate(agents[:num_agents]):
        agent_id = i
        
        # 生成金融状态（如果启用数值锚点）
        financial_state = {}
        if add_numeric_anchors:
            financial_state = generate_financial_state(agent.get("role_type", "刚需客"))
        
        agent_config = {
            "agent_id": agent_id,
            "entity_name": agent.get("entity_name", f"Agent_{agent_id}"),
            "role_type": agent.get("role_type", "刚需客"),
            "background": agent.get("background", ""),
            "active_hours": agent.get("active_hours", list(range(8, 23))),
            "activity_level": agent.get("activity_level", 0.7),
        }
        
        # 添加数值锚点
        if add_numeric_anchors:
            agent_config["financial_state"] = financial_state
            agent_config["system_prompt"] = generate_agent_prompt_with_anchors(
                agent_config, area_cfg, financial_state
            )
        
        agent_configs.append(agent_config)
    
    # 时间配置
    time_config = {
        "total_simulation_hours": simulation_hours,
        "minutes_per_round": 30,
        "agents_per_hour_min": 5,
        "agents_per_hour_max": 15,
        "peak_hours": [9, 10, 11, 14, 15, 20, 21, 22],
        "off_peak_hours": [0, 1, 2, 3, 4, 5],
        "peak_activity_multiplier": 1.5,
        "off_peak_activity_multiplier": 0.3,
    }
    
    # 事件配置
    event_config = {
        "initial_posts": [
            {
                "poster_agent_id": 0,
                "content": f"刚刚得到消息，深圳北站片区次新房现在均价{area_cfg['current_price']}万/平米，大家怎么看？增值税2年免征是不是利好？"
            },
            {
                "poster_agent_id": 5,
                "content": f"龙华边缘片区的房子要不要现在卖掉置换到深圳北站？怕踩踏又怕踏空，好纠结..."
            },
            {
                "poster_agent_id": 10,
                "content": f"短线来看政策利好，但长线还是要看底部支撑。6万/平米能不能撑住？"
            },
        ]
    }
    
    config = {
        "simulation_id": f"shenzhen_north_{datetime.now().strftime('%Y%m%d')}",
        "area": area,
        "current_price": area_cfg["current_price"],
        "base_price": area_cfg["base_price"],
        "time_config": time_config,
        "agent_configs": agent_configs,
        "event_config": event_config,
        "promax": {
            "numeric_anchors_enabled": add_numeric_anchors,
            "financial_state_tracking": add_numeric_anchors,
            "news_feed_enabled": True,
            "monte_carlo_runs": 1,
        }
    }
    
    # 保存配置
    config_path = os.path.join(output_dir, "simulation_config.json")
    os.makedirs(output_dir, exist_ok=True)
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    print(f"配置已保存: {config_path}")
    
    # 生成profiles
    generate_simulation_profiles(config, output_dir, add_numeric_anchors)
    
    return config


def generate_default_agents(num_agents: int, area: str) -> List[Dict[str, Any]]:
    """生成默认的Agent配置"""
    agents = []
    
    # 角色分布
    roles = [
        ("刚需客", 10),   # 10人 - 福田/南山外溢刚需
        ("置换客", 8),    # 8人 - 龙华边缘置换
        ("长线投资客", 5), # 5人 - 大资金长线
        ("短线炒家", 3),  # 3人 - 短线操作
        ("中介", 2),     # 2人 - 房产中介
        ("分析师", 2),    # 2人 - 市场分析师
    ]
    
    agent_idx = 0
    for role_type, count in roles:
        for i in range(count):
            background = get_background_for_role(role_type, i, area)
            agents.append({
                "entity_name": f"{role_type}_{i+1}",
                "role_type": role_type,
                "background": background,
                "active_hours": list(range(8, 23)),
                "activity_level": 0.5 + random.random() * 0.4,
            })
            agent_idx += 1
    
    return agents


def get_background_for_role(role_type: str, index: int, area: str) -> str:
    """为特定角色生成背景描述"""
    
    backgrounds = {
        "刚需客": [
            "在福田上班的白领，月薪2万，首付家里支持200万，想在深圳北站买婚房",
            "南山科技园程序员，首付150万，月供能力1.5万，怕踏空又怕站岗",
            "福田CBD白领，夫妻双职工，首付300万，想买学位房",
            "来深5年刚需，家庭支持有限，首付150万，犹豫要不要买龙华",
            "福田刚需客，手握200万首付，纠结要不要等跌到6万以下",
        ],
        "置换客": [
            "龙华大浪业主，想卖掉旧房换深圳北站次新房，担心卖不掉",
            "龙华边缘业主，当前挂牌无人问津，非常焦虑",
            "观澜业主，想置换到深圳北站，怕连环单断裂",
            "龙华老业主，之前高位接盘，现在想割肉置换",
            "边缘片区业主，担心房价下跌想尽快出逃",
        ],
        "长线投资客": [
            "手握500万现金的长线投资者，只等跌破6万入场捡尸",
            "资深投资客，经历过2015年股灾，不会轻易入场",
            "机构资金代表，只看绝对价值安全垫",
            "职业房东，只买笋盘，不追高",
            "价值投资者，关注租金回报率和长期持有价值",
        ],
        "短线炒家": [
            "短线炒家，高杠杆操作，快进快出",
            "职业抄家，专做笋盘，持有周期3-6个月",
            "杠杆玩家，用经营贷炒房，现金流压力大",
        ],
        "中介": [
            "资深中介，专注深圳北站片区，了解市场一线动态",
            "龙华区域中介，经历过疯狂时期，现在劝客户理性",
        ],
        "分析师": [
            "财经博主，专注房地产板块分析，观点相对客观",
            "房产研究员，擅长数据分析，给出专业建议",
        ],
    }
    
    options = backgrounds.get(role_type, ["普通购房者"])
    return options[index % len(options)]


def generate_simulation_profiles(
    config: Dict[str, Any],
    output_dir: str,
    add_numeric_anchors: bool = True
):
    """
    生成Twitter和Reddit的profile文件
    
    Args:
        config: 模拟配置
        output_dir: 输出目录
        add_numeric_anchors: 是否添加数值锚点
    """
    import csv
    
    agent_configs = config.get("agent_configs", [])
    
    # ========== 生成 Twitter Profiles (CSV) ==========
    twitter_profiles_path = os.path.join(output_dir, "twitter_profiles.csv")
    
    with open(twitter_profiles_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['agent_id', 'name', 'bio', 'system_prompt'])
        
        for agent in agent_configs:
            name = agent.get("entity_name", f"Agent_{agent.get('agent_id')}")
            role = agent.get("role_type", "购房者")
            background = agent.get("background", "")
            
            # 如果有system_prompt就使用，否则生成
            system_prompt = agent.get("system_prompt", 
                f"你是一个名为 {name} 的{role}。{background}。请积极参与关于房价的讨论。"
            )
            
            # 添加数值锚点信息到bio
            if add_numeric_anchors and "financial_state" in agent:
                fin = agent["financial_state"]
                bio_extra = f" | 现金:{fin['cash_balance']}万 | 恐慌指数:{fin['panic_index']}"
            else:
                bio_extra = ""
            
            bio = f"{role} | {background[:50]}{bio_extra}"
            
            writer.writerow([agent.get('agent_id'), name, bio, system_prompt])
    
    print(f"Twitter profiles已保存: {twitter_profiles_path}")
    
    # ========== 生成 Reddit Profiles (JSON) ==========
    reddit_profiles_path = os.path.join(output_dir, "reddit_profiles.json")
    
    reddit_profiles = []
    for agent in agent_configs:
        name = agent.get("entity_name", f"Agent_{agent.get('agent_id')}")
        role = agent.get("role_type", "购房者")
        background = agent.get("background", "")
        
        # 如果有system_prompt就使用
        system_prompt = agent.get("system_prompt",
            f"你是一个名为 {name} 的{role}。{background}。请积极参与讨论。"
        )
        
        # 添加数值锚点信息
        if add_numeric_anchors and "financial_state" in agent:
            fin = agent["financial_state"]
            bio_extra = f" | 现金:{fin['cash_balance']}万 | 月支出:{fin['monthly_expenses']}万 | 恐慌:{fin['panic_index']}"
        else:
            bio_extra = ""
        
        profile = {
            "agent_id": agent.get('agent_id'),
            "name": name,
            "description": f"{role} - {background[:80]}{bio_extra}",
            "system_prompt": system_prompt,
        }
        reddit_profiles.append(profile)
    
    with open(reddit_profiles_path, 'w', encoding='utf-8') as f:
        json.dump(reddit_profiles, f, ensure_ascii=False, indent=2)
    
    print(f"Reddit profiles已保存: {reddit_profiles_path}")


def main():
    parser = argparse.ArgumentParser(description='生成MiroFish ProMax模拟配置')
    parser.add_argument('--area', type=str, default='深圳北站',
                       help='地区名称')
    parser.add_argument('--agents', type=int, default=30,
                       help='Agent数量')
    parser.add_argument('--hours', type=int, default=72,
                       help='模拟时长（小时）')
    parser.add_argument('--output', type=str, default='.',
                       help='输出目录')
    parser.add_argument('--agents-config', type=str, default=None,
                       help='Agent配置文件路径(JSON)')
    parser.add_argument('--no-anchors', action='store_true',
                       help='禁用数值锚点')
    
    args = parser.parse_args()
    
    generate_simulation_config(
        area=args.area,
        num_agents=args.agents,
        simulation_hours=args.hours,
        output_dir=args.output,
        agents_config_path=args.agents_config,
        add_numeric_anchors=not args.no_anchors,
    )


if __name__ == '__main__':
    main()
