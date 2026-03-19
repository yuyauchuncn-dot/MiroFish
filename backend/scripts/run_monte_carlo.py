"""
蒙特卡洛仿真脚本 (Monte Carlo Consensus)
运行多次模拟并生成共识报告

功能：
- 运行同一配置的多次模拟
- 收集所有对话日志
- 识别多次运行中重复出现的关键预测
- 生成共识报告
"""

import os
import sys
import json
import argparse
import asyncio
import shutil
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
import logging

# 添加scripts目录到路径
_script_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.abspath(os.path.join(_script_dir, '..'))
sys.path.insert(0, _script_dir)
sys.path.insert(0, _backend_dir)

# 导入模拟运行器
from run_parallel_simulation import load_config, run_twitter_simulation, run_reddit_simulation
from action_logger import SimulationLogManager

logger = logging.getLogger(__name__)


class MonteCarloRunner:
    """蒙特卡洛仿真运行器"""
    
    def __init__(self, config_path: str, num_runs: int = 3, output_dir: str = None):
        """
        初始化运行器
        
        Args:
            config_path: simulation_config.json 路径
            num_runs: 运行次数
            output_dir: 输出目录（默认自动生成）
        """
        self.config_path = config_path
        self.config = load_config(config_path)
        self.num_runs = num_runs
        
        # 生成输出目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if output_dir:
            self.output_dir = output_dir
        else:
            sim_name = self.config.get('simulation_id', 'sim')
            self.output_dir = f"/Users/dereky/gemini/analysis/real_estate/{sim_name}_mc_{timestamp}_export"
        
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 每次运行的输出目录
        self.run_dirs: List[str] = []
        
        # 收集的所有对话日志
        self.all_conversations: List[Dict[str, Any]] = []
        
        # 共识结果
        self.consensus_report: Dict[str, Any] = {}
    
    def _create_run_config(self, run_num: int) -> str:
        """为每次运行创建独立的配置文件"""
        run_dir = os.path.join(self.output_dir, f"run_{run_num}")
        os.makedirs(run_dir, exist_ok=True)
        
        # 复制原始配置文件
        config_copy_path = os.path.join(run_dir, "simulation_config.json")
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # 添加运行标识
        config_data['simulation_id'] = f"{config_data.get('simulation_id', 'sim')}_run{run_num}"
        config_data['_monte_carlo_run'] = run_num
        
        with open(config_copy_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        
        # 复制或生成profile文件
        self._prepare_profiles(run_dir, config_data)
        
        self.run_dirs.append(run_dir)
        return config_copy_path
    
    def _prepare_profiles(self, run_dir: str, config_data: Dict):
        """准备profile文件（包含numeric anchors）"""
        from generate_profiles import generate_simulation_profiles
        
        # 生成新的profile（带numeric anchors）
        generate_simulation_profiles(
            config=config_data,
            output_dir=run_dir,
            add_numeric_anchors=True  # 启用数值锚点
        )
    
    async def run_single_simulation(self, run_num: int, config_path: str, max_rounds: int = None) -> Dict[str, Any]:
        """运行单次模拟"""
        run_dir = os.path.dirname(config_path)
        
        print(f"\n{'='*60}")
        print(f"开始第 {run_num}/{self.num_runs} 次模拟")
        print(f"配置: {config_path}")
        print(f"{'='*60}")
        
        # 创建日志管理器
        log_manager = SimulationLogManager(run_dir)
        twitter_logger = log_manager.get_twitter_logger()
        reddit_logger = log_manager.get_reddit_logger()
        
        # 运行Twitter模拟
        twitter_result = await run_twitter_simulation(
            config=self.config,
            simulation_dir=run_dir,
            action_logger=twitter_logger,
            main_logger=log_manager,
            max_rounds=max_rounds
        )
        
        # 运行Reddit模拟
        reddit_result = await run_reddit_simulation(
            config=self.config,
            simulation_dir=run_dir,
            action_logger=reddit_logger,
            main_logger=log_manager,
            max_rounds=max_rounds
        )
        
        return {
            'run_num': run_num,
            'run_dir': run_dir,
            'twitter_actions': twitter_result.total_actions if twitter_result else 0,
            'reddit_actions': reddit_result.total_actions if reddit_result else 0,
        }
    
    async def run_all(self, max_rounds: int = None) -> List[Dict[str, Any]]:
        """运行所有模拟"""
        results = []
        
        for run_num in range(1, self.num_runs + 1):
            # 创建运行配置
            config_copy_path = self._create_run_config(run_num)
            
            # 运行模拟
            result = await self.run_single_simulation(run_num, config_copy_path, max_rounds)
            results.append(result)
            
            # 收集对话日志
            self._collect_conversations(result['run_dir'])
            
            print(f"\n第 {run_num} 次模拟完成!")
            print(f"  Twitter动作: {result['twitter_actions']}")
            print(f"  Reddit动作: {result['reddit_actions']}")
        
        return results
    
    def _collect_conversations(self, run_dir: str):
        """从运行目录收集对话"""
        # 收集Twitter对话
        twitter_log = os.path.join(run_dir, "twitter", "actions.jsonl")
        if os.path.exists(twitter_log):
            with open(twitter_log, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        action = json.loads(line)
                        if action.get('action_type') in ['CREATE_POST', 'CREATE_COMMENT', 'QUOTE_POST']:
                            self.all_conversations.append({
                                'platform': 'twitter',
                                'run_dir': os.path.basename(run_dir),
                                **action
                            })
                    except json.JSONDecodeError:
                        continue
        
        # 收集Reddit对话
        reddit_log = os.path.join(run_dir, "reddit", "actions.jsonl")
        if os.path.exists(reddit_log):
            with open(reddit_log, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        action = json.loads(line)
                        if action.get('action_type') in ['CREATE_POST', 'CREATE_COMMENT']:
                            self.all_conversations.append({
                                'platform': 'reddit',
                                'run_dir': os.path.basename(run_dir),
                                **action
                            })
                    except json.JSONDecodeError:
                        continue
    
    def analyze_consensus(self) -> Dict[str, Any]:
        """分析共识 - 找出多次运行中重复出现的关键预测"""
        print("\n正在分析共识...")
        
        # 提取关键信息
        predictions = []
        price_mentions = []
        sentiment_by_role = defaultdict(list)
        
        for conv in self.all_conversations:
            content = conv.get('action_args', {}).get('content', '')
            agent_name = conv.get('agent_name', '')
            
            if not content:
                continue
            
            # 提取价格信息
            price_patterns = [
                r'(\d+\.?\d*)\s*[万万元]/[平米平]',
                r'单价\s*(\d+\.?\d*)',
                r'均价\s*(\d+\.?\d*)',
                r'(\d{5,6})\s*元',
            ]
            
            for pattern in price_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    try:
                        price = float(match)
                        if price < 100:  # 万/平米
                            price *= 10000  # 转为元/平米
                        price_mentions.append({
                            'price': price,
                            'content': content[:100],
                            'agent': agent_name,
                            'platform': conv['platform'],
                            'run': conv['run_dir']
                        })
                    except:
                        pass
            
            # 提取立场/预测
            if any(kw in content for kw in ['看涨', '买入', '抄底', '看好', '会涨', '上涨']):
                predictions.append({
                    'type': 'bullish',
                    'content': content[:200],
                    'agent': agent_name,
                    'platform': conv['platform'],
                    'run': conv['run_dir']
                })
                sentiment_by_role[agent_name].append('bullish')
            
            if any(kw in content for kw in ['看跌', '卖出', '抛售', '看空', '下跌', '下跌']):
                predictions.append({
                    'type': 'bearish',
                    'content': content[:200],
                    'agent': agent_name,
                    'platform': conv['platform'],
                    'run': conv['run_dir']
                })
                sentiment_by_role[agent_name].append('bearish')
        
        # 统计价格共识
        price_stats = self._analyze_price_consensus(price_mentions)
        
        # 统计预测共识
        prediction_consensus = self._analyze_prediction_consensus(predictions)
        
        # 整合报告
        self.consensus_report = {
            'timestamp': datetime.now().isoformat(),
            'num_runs': self.num_runs,
            'total_conversations': len(self.all_conversations),
            'price_analysis': price_stats,
            'prediction_consensus': prediction_consensus,
            'sample_conversations': self.all_conversations[:20],  # 保留样本
        }
        
        return self.consensus_report
    
    def _analyze_price_consensus(self, price_mentions: List[Dict]) -> Dict[str, Any]:
        """分析价格共识"""
        if not price_mentions:
            return {'status': 'no_data'}
        
        prices = [p['price'] for p in price_mentions]
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)
        
        # 找出最常提到的价格区间
        ranges = defaultdict(int)
        for price in prices:
            if price < 40000:
                ranges['<4万/平'] += 1
            elif price < 50000:
                ranges['4-5万/平'] += 1
            elif price < 60000:
                ranges['5-6万/平'] += 1
            elif price < 70000:
                ranges['6-7万/平'] += 1
            elif price < 80000:
                ranges['7-8万/平'] += 1
            else:
                ranges['>8万/平'] += 1
        
        # 找出多次提到的价格
        price_counts = defaultdict(int)
        for price in prices:
            # 四舍五入到千位
            rounded = round(price / 1000) * 1000
            price_counts[rounded] += 1
        
        recurring_prices = sorted(
            [(price, count) for price, count in price_counts.items() if count >= 2],
            key=lambda x: -x[1]
        )[:10]
        
        return {
            'avg_price_yuan_per_ping': avg_price,
            'min_price_yuan_per_ping': min_price,
            'max_price_yuan_per_ping': max_price,
            'price_ranges': dict(ranges),
            'recurring_prices': [{'price': p, 'count': c} for p, c in recurring_prices],
            'total_mentions': len(price_mentions),
        }
    
    def _analyze_prediction_consensus(self, predictions: List[Dict]) -> Dict[str, Any]:
        """分析预测共识"""
        if not predictions:
            return {'status': 'no_data'}
        
        bullish_count = sum(1 for p in predictions if p['type'] == 'bullish')
        bearish_count = sum(1 for p in predictions if p['type'] == 'bearish')
        
        # 按运行统计
        runs = set(p['run'] for p in predictions)
        run_stats = {}
        for run in runs:
            run_preds = [p for p in predictions if p['run'] == run]
            run_stats[run] = {
                'bullish': sum(1 for p in run_preds if p['type'] == 'bullish'),
                'bearish': sum(1 for p in run_preds if p['type'] == 'bearish'),
            }
        
        return {
            'total_bullish': bullish_count,
            'total_bearish': bearish_count,
            'sentiment_ratio': bullish_count / bearish_count if bearish_count > 0 else float('inf'),
            'by_run': run_stats,
        }
    
    def generate_report(self) -> str:
        """生成共识报告"""
        if not self.consensus_report:
            self.analyze_consensus()
        
        report = f"""# 蒙特卡洛仿真共识报告

**生成时间:** {self.consensus_report['timestamp']}
**运行次数:** {self.consensus_report['num_runs']}
**总对话数:** {self.consensus_report['total_conversations']}

---

## 1. 价格共识分析

"""
        
        price_analysis = self.consensus_report.get('price_analysis', {})
        if price_analysis.get('status') == 'no_data':
            report += "未提取到价格数据\n"
        else:
            report += f"""### 价格统计

- **平均价格:** {price_analysis.get('avg_price_yuan_per_ping', 0):,.0f} 元/平米 ({price_analysis.get('avg_price_yuan_per_ping', 0)/10000:.2f} 万/平米)
- **最低价格:** {price_analysis.get('min_price_yuan_per_ping', 0):,.0f} 元/平米
- **最高价格:** {price_analysis.get('max_price_yuan_per_ping', 0):,.0f} 元/平米
- **总提及次数:** {price_analysis.get('total_mentions', 0)}

### 价格区间分布

"""
            for range_name, count in price_analysis.get('price_ranges', {}).items():
                report += f"- {range_name}: {count} 次\n"
            
            report += "\n### 反复出现的关键价格\n\n"
            for item in price_analysis.get('recurring_prices', [])[:5]:
                report += f"- **{item['price']/10000:.1f} 万/平米**: 出现 {item['count']} 次\n"
        
        report += """

## 2. 预测共识分析

"""
        
        pred_consensus = self.consensus_report.get('prediction_consensus', {})
        if pred_consensus.get('status') == 'no_data':
            report += "未提取到预测数据\n"
        else:
            report += f"""### 整体情绪

- **看涨/看多:** {pred_consensus.get('total_bullish', 0)} 次
- **看跌/看空:** {pred_consensus.get('total_bearish', 0)} 次
- **多空比:** {pred_consensus.get('sentiment_ratio', 0):.2f}

### 各次运行的情绪分布

"""
            for run, stats in pred_consensus.get('by_run', {}).items():
                report += f"- {run}: 看涨 {stats['bullish']} 次, 看跌 {stats['bearish']} 次\n"
        
        report += """

## 3. 关键预测摘要

"""
        
        # 提取最关键的预测
        key_predictions = []
        for conv in self.all_conversations:
            content = conv.get('action_args', {}).get('content', '')
            if any(kw in content for kw in ['底部', '支撑', '跌破', '抄底', '上涨', '下跌', '预期']):
                if len(content) > 50 and len(content) < 500:
                    key_predictions.append(conv)
        
        for i, pred in enumerate(key_predictions[:10]):
            report += f"""### {i+1}. {pred['agent_name']} ({pred['platform']})

{pred['action_args'].get('content', '')[:300]}

---
"""
        
        report += f"""

## 4. 运行详情

"""
        for run_dir in self.run_dirs:
            report += f"- {os.path.basename(run_dir)}\n"
        
        return report
    
    def save_outputs(self):
        """保存所有输出"""
        # 保存共识报告
        report_path = os.path.join(self.output_dir, "consensus_report.md")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(self.generate_report())
        
        # 保存详细JSON数据
        data_path = os.path.join(self.output_dir, "consensus_data.json")
        # 移除过大的样本数据以节省空间
        save_data = self.consensus_report.copy()
        save_data['sample_conversations'] = save_data.get('sample_conversations', [])[:50]
        
        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        
        # 保存所有对话
        conv_path = os.path.join(self.output_dir, "all_conversations.jsonl")
        with open(conv_path, 'w', encoding='utf-8') as f:
            for conv in self.all_conversations:
                f.write(json.dumps(conv, ensure_ascii=False) + '\n')
        
        print(f"\n输出已保存到: {self.output_dir}")
        print(f"  - {report_path}")
        print(f"  - {data_path}")
        print(f"  - {conv_path}")


async def main():
    parser = argparse.ArgumentParser(description='蒙特卡洛仿真共识分析')
    parser.add_argument('--config', type=str, required=True,
                       help='simulation_config.json 路径')
    parser.add_argument('--runs', type=int, default=3,
                       help='运行次数 (默认3)')
    parser.add_argument('--max-rounds', type=int, default=None,
                       help='每次模拟的最大轮数')
    parser.add_argument('--output', type=str, default=None,
                       help='输出目录')
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("="*60)
    print("蒙特卡洛仿真共识分析")
    print(f"配置文件: {args.config}")
    print(f"运行次数: {args.runs}")
    print(f"最大轮数: {args.max_rounds or '无限制'}")
    print("="*60)
    
    # 创建运行器
    runner = MonteCarloRunner(
        config_path=args.config,
        num_runs=args.runs,
        output_dir=args.output
    )
    
    # 运行所有模拟
    await runner.run_all(max_rounds=args.max_rounds)
    
    # 分析共识
    runner.analyze_consensus()
    
    # 保存输出
    runner.save_outputs()
    
    # 打印报告
    print("\n" + "="*60)
    print("共识报告摘要")
    print("="*60)
    print(runner.generate_report()[:2000])


if __name__ == '__main__':
    asyncio.run(main())
