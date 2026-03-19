#!/usr/bin/env python3
"""
MiroFish ProMax Lite - 輕量版模擬
不依賴 OASIS，直接用 OpenAI client 跑模擬
"""

import json
import os
import sys
import random
import argparse
import time
from datetime import datetime
from pathlib import Path
from openai import OpenAI


def load_config(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_news_cache(cache_path):
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('items', [])
    return []


def get_news_broadcast(news_items, round_num, every_n=5):
    """Get news broadcast for this round"""
    if round_num % every_n != 0 or not news_items:
        return None
    # Pick 2-3 random news items
    selected = random.sample(news_items, min(3, len(news_items)))
    text = "\n".join([f"📰 {item.get('title', item.get('text', ''))}" for item in selected])
    return text


def run_agent_round(client, agent, context, news_broadcast, model):
    """Run one round for one agent"""
    system_prompt = agent['system_prompt']
    
    if news_broadcast:
        system_prompt += f"\n\n## 系统广播\n{news_broadcast}"
    
    # Build context message
    if context:
        context_text = "最近的讨论:\n" + "\n".join(context[-10:])
    else:
        context_text = "讨论刚开始，请发表你的观点。"
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{context_text}\n\n请以 {agent['entity_name']} 的身份发一条帖子（2-4句话），表达你对深圳北站片区房价的看法："}
            ],
            temperature=0.8,
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[Error: {e}]"


def run_simulation(config, output_dir, model, max_rounds=30, verbose=True):
    """Run the main simulation loop"""
    
    # Setup
    os.makedirs(output_dir, exist_ok=True)
    
    # Load API key from .env
    env_path = Path(__file__).parent.parent.parent / '.env'
    api_key = None
    base_url = None
    
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('LLM_API_KEY='):
                    api_key = line.split('=', 1)[1].strip().strip('"')
                elif line.startswith('LLM_BASE_URL='):
                    base_url = line.split('=', 1)[1].strip().strip('"')
    
    if not api_key:
        api_key = os.environ.get('LLM_API_KEY')
    if not base_url:
        base_url = os.environ.get('LLM_BASE_URL')
    
    if not api_key:
        print("❌ No API key found. Set LLM_API_KEY in .env or environment.")
        sys.exit(1)
    
    # Initialize client
    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)
    
    # Load news
    news_path = Path(__file__).parent.parent.parent.parent / 'analysis' / 'real_estate' / 'news_cache.json'
    news_items = load_news_cache(str(news_path))
    if verbose:
        print(f"📰 Loaded {len(news_items)} news items")
    
    # Get agents
    agents = config['agent_configs']
    if verbose:
        print(f"👥 {len(agents)} agents configured")
        print(f"🏙️ Area: {config['area']}, Price: {config['current_price']}")
        print(f"🎯 Running {max_rounds} rounds...")
    
    # Open output files
    twitter_file = os.path.join(output_dir, 'twitter_conversations_log.md')
    reddit_file = os.path.join(output_dir, 'reddit_conversations_log.md')
    csv_file = os.path.join(output_dir, 'social_media_posts.csv')
    
    context = []
    all_posts = []
    start_time = time.time()
    
    with open(twitter_file, 'w', encoding='utf-8') as tf, \
         open(reddit_file, 'w', encoding='utf-8') as rf:
        
        tf.write(f"# Twitter 模擬記錄 - {config['area']}\n\n")
        tf.write(f"**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        tf.write(f"**均價**: {config['current_price']} 萬/平米 | **心理底部**: {config['base_price']} 萬/平米\n\n---\n\n")
        
        rf.write(f"# Reddit 模擬記錄 - {config['area']}\n\n")
        rf.write(f"**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        rf.write(f"**均價**: {config['current_price']} 萬/平米 | **心理底部**: {config['base_price']} 萬/平米\n\n---\n\n")
        
        for round_num in range(1, max_rounds + 1):
            # Pick 3-5 active agents this round
            active_count = random.randint(3, min(5, len(agents)))
            active_agents = random.sample(agents, active_count)
            
            news_broadcast = get_news_broadcast(news_items, round_num)
            if news_broadcast and verbose:
                print(f"\n📡 Round {round_num} - News broadcast injected")
            
            for agent in active_agents:
                post = run_agent_round(client, agent, context, news_broadcast, model)
                
                # Format for Twitter
                tf.write(f"## Round {round_num} | @{agent['entity_name']} ({agent['role_type']})\n")
                tf.write(f"{post}\n\n")
                
                # Format for Reddit
                rf.write(f"### r/深圳房市 | Round {round_num}\n")
                rf.write(f"**u/{agent['entity_name']}** ({agent['role_type']}):\n")
                rf.write(f"{post}\n\n---\n\n")
                
                # Add to context
                context.append(f"{agent['entity_name']}: {post}")
                all_posts.append({
                    'round': round_num,
                    'agent': agent['entity_name'],
                    'role': agent['role_type'],
                    'platform': random.choice(['twitter', 'reddit']),
                    'content': post
                })
                
                if verbose:
                    print(f"  💬 {agent['entity_name']}: {post[:60]}...")
            
            # Save progress every 10 rounds
            if round_num % 10 == 0:
                elapsed = time.time() - start_time
                print(f"\n⏱️ Round {round_num}/{max_rounds} done ({elapsed:.0f}s elapsed)")
    
    # Save CSV
    with open(csv_file, 'w', encoding='utf-8') as cf:
        cf.write("round,agent,role,platform,content\n")
        for p in all_posts:
            content = p['content'].replace('"', '""')
            cf.write(f"{p['round']},{p['agent']},{p['role']},{p['platform']},\"{content}\"\n")
    
    # Save state
    state_file = os.path.join(output_dir, 'run_state.json')
    with open(state_file, 'w', encoding='utf-8') as sf:
        json.dump({
            'simulation_id': config.get('simulation_id', 'promax_lite'),
            'area': config['area'],
            'current_price': config['current_price'],
            'base_price': config['base_price'],
            'total_rounds': max_rounds,
            'total_posts': len(all_posts),
            'agents_count': len(agents),
            'completed_at': datetime.now().isoformat(),
            'model': model,
            'output_dir': output_dir
        }, sf, ensure_ascii=False, indent=2)
    
    elapsed = time.time() - start_time
    print(f"\n✅ Simulation complete!")
    print(f"📊 {len(all_posts)} posts across {max_rounds} rounds")
    print(f"⏱️ Total time: {elapsed:.0f}s")
    print(f"📁 Output: {output_dir}")
    
    return all_posts


def main():
    parser = argparse.ArgumentParser(description='MiroFish ProMax Lite Simulation')
    parser.add_argument('--config', required=True, help='Path to simulation_config.json')
    parser.add_argument('--output', required=True, help='Output directory')
    parser.add_argument('--model', default='qwen-plus', help='LLM model name')
    parser.add_argument('--rounds', type=int, default=30, help='Number of rounds')
    parser.add_argument('--quiet', action='store_true', help='Less output')
    args = parser.parse_args()
    
    config = load_config(args.config)
    run_simulation(config, args.output, args.model, args.rounds, verbose=not args.quiet)


if __name__ == '__main__':
    main()
