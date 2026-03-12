import json
import os
import sys
import glob
import random
import re
from openai import OpenAI

# 修复编码问题
if sys.platform == 'win32':
    import builtins
    original_open = builtins.open
    def custom_open(*args, **kwargs):
        if len(args) > 1 and 'b' not in args[1]:
            kwargs.setdefault('encoding', 'utf-8')
        elif 'mode' in kwargs and 'b' not in kwargs['mode']:
            kwargs.setdefault('encoding', 'utf-8')
        elif len(args) == 1 and 'mode' not in kwargs:
            kwargs.setdefault('encoding', 'utf-8')
        return original_open(*args, **kwargs)
    builtins.open = custom_open

def parse_vtt(filepath):
    """简单解析VTT文件，提取纯文本"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 移除 WEBVTT 头
        content = re.sub(r'^WEBVTT\n.*?\n', '', content, flags=re.MULTILINE | re.DOTALL)
        # 移除时间轴
        content = re.sub(r'[\d:\.]+ --> [\d:\.]+\n', '', content)
        # 移除 HTML 标签 (如 <c>)
        content = re.sub(r'<[^>]+>', '', content)
        # 移除空行
        lines = [line.strip() for line in content.split('\n') if line.strip() and not line.strip().isdigit()]
        
        # 去重（自动字幕经常有重复行）
        unique_lines = []
        last_line = ""
        for line in lines:
            if line != last_line:
                unique_lines.append(line)
                last_line = line
                
        return " ".join(unique_lines)
    except Exception as e:
        print(f"解析 {filepath} 失败: {e}")
        return ""

def summarize_to_news(text, client, model_name="gemini-2.5-flash"):
    """使用LLM将长文本总结为一条简短的“突发新闻”"""
    if not text:
        return ""
        
    prompt = f"""
请将以下视频字幕内容，提炼为一条适合在社交媒体上发布的“突发新闻”或“大V宏观点评”（字数在 100 字以内，语气要带有煽动性或权威感）。
如果内容涉及房地产、降息、失业或通缩，请重点突出。

内容素材：
{text[:4000]} # 截断防止超长
"""
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "你是一个财经新闻自媒体账号。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"LLM 提炼失败: {e}")
        return ""

def inject_news(config_path, vtt_dir, num_news=3):
    """向配置文件中注入外部新闻作为定时事件"""
    if not os.path.exists(config_path):
        print(f"配置文件不存在: {config_path}")
        return

    vtt_files = glob.glob(os.path.join(vtt_dir, "*.vtt"))
    if not vtt_files:
        print(f"在 {vtt_dir} 未找到任何 .vtt 字幕文件。请先运行下载脚本。")
        return

    print(f"找到 {len(vtt_files)} 个字幕文件，准备抽取 {num_news} 条作为外部干预事件...")

    # 随机抽取几个文件
    selected_files = random.sample(vtt_files, min(num_news, len(vtt_files)))
    
    # 初始化 LLM 客户端
    # 这里我们直接读取环境变量，MiroFish 的 .env 应该已配置
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))
    
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model_name = os.getenv("LLM_MODEL_NAME", "gemini-2.5-flash")
    
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    news_items = []
    for file in selected_files:
        print(f"正在处理: {os.path.basename(file)}...")
        text = parse_vtt(file)
        news = summarize_to_news(text, client, model_name)
        if news:
            news_items.append(news)
            print(f"  -> 提取新闻: {news[:50]}...")

    if not news_items:
        print("未能提取出任何新闻。")
        return

    # 读取原配置文件
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 寻找一个适合发新闻的 Agent (例如媒体大V，或者如果没有就用 Agent 0)
    agent_configs = config.get("agent_configs", [])
    media_agents = [a for a in agent_configs if "Media" in a.get("entity_type", "")]
    if media_agents:
        poster_id = media_agents[0].get("agent_id", 0)
    else:
        poster_id = 0

    total_rounds = (config["time_config"]["total_simulation_hours"] * 60) // config["time_config"]["minutes_per_round"]
    
    # 构建定时事件 (分散在模拟的前中后期)
    scheduled_events = config.get("event_config", {}).get("scheduled_events", [])
    
    for i, news in enumerate(news_items):
        # 均匀分布在整个模拟周期中
        trigger_round = int(total_rounds * ((i + 1) / (len(news_items) + 1)))
        
        event = {
            "round_num": trigger_round,
            "poster_agent_id": poster_id,
            "content": f"【外网宏观快讯】{news}"
        }
        scheduled_events.append(event)
        
    config["event_config"]["scheduled_events"] = scheduled_events
    
    # 写回配置
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        
    print(f"\n成功注入 {len(news_items)} 条外部宏观新闻到 {config_path}")
    print("在下次运行模拟时，这些新闻将在特定的 Round 自动触发！")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python inject_external_news.py <path_to_simulation_config.json> <path_to_vtt_directory>")
        sys.exit(1)
        
    inject_news(sys.argv[1], sys.argv[2])
