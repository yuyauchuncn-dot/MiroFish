"""
外部新闻注入模块 (News Feeder)
从YouTube transcripts中提取宏观/房地产相关新闻，注入模拟环境

功能：
- 读取YouTube VTT/TXT字幕文件
- 提取与模拟主题相关的新闻片段
- 格式化后作为"系统广播"消息注入模拟
"""

import os
import re
import json
import random
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# 支持的字幕文件格式
SUPPORTED_FORMATS = ['.vtt', '.txt', '.srt']

# 关键词过滤器 - 只提取与这些主题相关的内容
RELEVANT_KEYWORDS = [
    # 房地产相关
    '房地产', '房价', '楼市', '买房', '卖房', '成交量', '挂牌', '首付', '房贷', '利率',
    '开发商', '土拍', '地价', '新房的', '二手房', '租金', '租售比', '限购', '限贷',
    '深圳', '上海', '北京', '广州', '杭州', '南京', '成都', '武汉', '龙华', '南山', '福田',
    # 宏观经济相关
    'GDP', '经济', '宏观', 'CPI', 'PPI', '通胀', '通缩', '降息', '加息', '存款准备金',
    '信贷', 'M2', '社融', 'PMI', '就业', '失业', '裁员', '收入', '消费', '居民',
    # 政策相关
    '政策', '调控', '会议', '文件', '规定', '措施', '补贴', '免税', '增值税', '契税',
    'LPR', '基准利率', '央行', '财政部', '住建部', '银保监会',
    # 市场情绪
    '恐慌', '焦虑', '抄底', '踏空', '观望', '预期', '信心', '利空', '利好', '支撑', '跌破',
]

# 排除的噪音词汇（可能是视频标题但不包含实质内容）
NOISE_PATTERNS = [
    r'^第?\d+[期集]',
    r'^\s*[\d:.]+\s*$',  # 只有时间戳
    r'^→',  # 箭头开头的跳转标记
]


class NewsItem:
    """新闻条目"""
    def __init__(self, source_file: str, timestamp: str, content: str, relevance_score: float = 0.0):
        self.source_file = source_file
        self.timestamp = timestamp  # 视频时间戳
        self.content = content.strip()
        self.relevance_score = relevance_score
        self.broadcast_format = None
    
    def to_broadcast_message(self, round_num: int) -> str:
        """转换为系统广播消息格式"""
        # 提取视频标题作为来源
        source_name = os.path.basename(self.source_file)
        # 移除文件扩展名和ID
        source_name = re.sub(r'\s*\[.*?\]\..*$', '', source_name)
        source_name = re.sub(r'^\d+-\s*', '', source_name)
        
        self.broadcast_format = f"""【系统广播 - 第{round_num}轮】
📰 来源: {source_name}
⏰ 视频位置: {self.timestamp}
📝 内容: {self.content[:200]}{'...' if len(self.content) > 200 else ''}
"""
        return self.broadcast_format
    
    def __repr__(self):
        return f"NewsItem({self.source_file}, {self.timestamp[:20]}..., score={self.relevance_score:.2f})"


class NewsFeeder:
    """新闻投喂器"""
    
    def __init__(self, transcripts_dir: str, cache_file: str = None):
        """
        初始化新闻投喂器
        
        Args:
            transcripts_dir: YouTube字幕文件目录
            cache_file: 新闻缓存文件路径（可选，用于存储已处理的新闻）
        """
        self.transcripts_dir = transcripts_dir
        self.cache_file = cache_file
        self.news_items: List[NewsItem] = []
        self.used_indices: set = set()
        
        # 加载已有的新闻缓存
        if cache_file and os.path.exists(cache_file):
            self._load_cache()
    
    def _load_cache(self):
        """从缓存文件加载已处理的新闻"""
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 恢复NewsItem对象
                self.news_items = [
                    NewsItem(
                        source_file=item['source_file'],
                        timestamp=item['timestamp'],
                        content=item['content'],
                        relevance_score=item.get('relevance_score', 0.0)
                    )
                    for item in data.get('news_items', [])
                ]
                self.used_indices = set(data.get('used_indices', []))
            logger.info(f"从缓存加载了 {len(self.news_items)} 条新闻")
        except Exception as e:
            logger.warning(f"加载新闻缓存失败: {e}")
    
    def _save_cache(self):
        """保存新闻到缓存文件"""
        if not self.cache_file:
            return
        
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            data = {
                'news_items': [
                    {
                        'source_file': item.source_file,
                        'timestamp': item.timestamp,
                        'content': item.content,
                        'relevance_score': item.relevance_score
                    }
                    for item in self.news_items
                ],
                'used_indices': list(self.used_indices)
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"新闻缓存已保存: {len(self.news_items)} 条")
        except Exception as e:
            logger.warning(f"保存新闻缓存失败: {e}")
    
    def scan_transcripts(self) -> int:
        """
        扫描字幕目录，提取相关新闻
        
        Returns:
            提取的新闻数量
        """
        if not os.path.exists(self.transcripts_dir):
            logger.warning(f"字幕目录不存在: {self.transcripts_dir}")
            return 0
        
        transcript_files = []
        for root, dirs, files in os.walk(self.transcripts_dir):
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext in SUPPORTED_FORMATS:
                    transcript_files.append(os.path.join(root, filename))
        
        logger.info(f"找到 {len(transcript_files)} 个字幕文件")
        
        self.news_items = []
        for filepath in transcript_files:
            items = self._parse_transcript_file(filepath)
            self.news_items.extend(items)
        
        # 按相关性评分排序
        self.news_items.sort(key=lambda x: x.relevance_score, reverse=True)
        
        # 保存缓存
        self._save_cache()
        
        logger.info(f"提取了 {len(self.news_items)} 条相关新闻")
        return len(self.news_items)
    
    def _parse_transcript_file(self, filepath: str) -> List[NewsItem]:
        """解析单个字幕文件"""
        items = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(filepath, 'r', encoding='gbk') as f:
                    content = f.read()
            except Exception as e:
                logger.warning(f"无法读取文件 {filepath}: {e}")
                return items
        
        # 根据文件类型选择解析方法
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.vtt':
            items = self._parse_vtt(content, filepath)
        elif ext == '.srt':
            items = self._parse_srt(content, filepath)
        else:
            items = self._parse_txt(content, filepath)
        
        return items
    
    def _parse_vtt(self, content: str, filepath: str) -> List[NewsItem]:
        """解析VTT格式字幕"""
        items = []
        
        # VTT格式: 时间 --> 时间 \n 文本
        # 示例: 00:00:01.000 --> 00:00:05.000\n文本
        
        # 移除WEBVTT头部
        content = re.sub(r'^WEBVTT.*?\n\n', '', content, flags=re.IGNORECASE)
        
        # 分割每个字幕块
        blocks = re.split(r'\n\n+', content)
        
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) < 2:
                continue
            
            # 解析时间戳
            timestamp_line = lines[0]
            if ' --> ' not in timestamp_line:
                continue
            
            timestamp = timestamp_line.split(' --> ')[0]
            
            # 文本内容（可能有多行）
            text = ' '.join(lines[1:])
            
            # 清理文本
            text = self._clean_text(text)
            if not text or len(text) < 20:
                continue
            
            # 计算相关性
            relevance = self._calculate_relevance(text)
            if relevance > 0:
                items.append(NewsItem(filepath, timestamp, text, relevance))
        
        return items
    
    def _parse_srt(self, content: str, filepath: str) -> List[NewsItem]:
        """解析SRT格式字幕"""
        items = []
        
        # SRT格式: 序号 \n 时间 --> 时间 \n 文本
        blocks = re.split(r'\n\n+', content)
        
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue
            
            # 找到时间戳行
            timestamp_line = None
            text_start_idx = 2
            for i, line in enumerate(lines):
                if ' --> ' in line:
                    timestamp_line = line
                    text_start_idx = i + 1
                    break
            
            if not timestamp_line:
                continue
            
            timestamp = timestamp_line.split(' --> ')[0]
            text = ' '.join(lines[text_start_idx:])
            
            # 清理文本
            text = self._clean_text(text)
            if not text or len(text) < 20:
                continue
            
            # 计算相关性
            relevance = self._calculate_relevance(text)
            if relevance > 0:
                items.append(NewsItem(filepath, timestamp, text, relevance))
        
        return items
    
    def _parse_txt(self, content: str, filepath: str) -> List[NewsItem]:
        """解析纯文本格式字幕"""
        items = []
        
        # 简单处理：按行分割，过滤短行
        lines = content.split('\n')
        
        current_text = []
        timestamp = "00:00:00"
        
        for line in lines:
            line = line.strip()
            
            # 尝试检测时间戳（格式: 00:00:00 或类似）
            time_match = re.match(r'^(\d{1,2}:\d{2}(:\d{2})?)', line)
            if time_match:
                # 保存之前的文本
                if current_text:
                    text = ' '.join(current_text)
                    relevance = self._calculate_relevance(text)
                    if relevance > 0 and len(text) >= 20:
                        items.append(NewsItem(filepath, timestamp, text, relevance))
                    current_text = []
                
                timestamp = time_match.group(1)
                # 移除时间戳后继续
                line = line[time_match.end():].strip()
            
            if line:
                current_text.append(line)
        
        # 处理最后一块
        if current_text:
            text = ' '.join(current_text)
            relevance = self._calculate_relevance(text)
            if relevance > 0 and len(text) >= 20:
                items.append(NewsItem(filepath, timestamp, text, relevance))
        
        return items
    
    def _clean_text(self, text: str) -> str:
        """清理文本内容"""
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        
        # 移除 VTT/SRT 格式标记
        text = re.sub(r'<c\.[^>]+>', '', text)
        text = re.sub(r'<\/?[^>]+>', '', text)
        
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text)
        
        # 移除噪音模式
        for pattern in NOISE_PATTERNS:
            text = re.sub(pattern, '', text)
        
        return text.strip()
    
    def _calculate_relevance(self, text: str) -> float:
        """计算文本与模拟主题的相关性"""
        score = 0.0
        text_lower = text.lower()
        
        for keyword in RELEVANT_KEYWORDS:
            if keyword.lower() in text_lower:
                # 房地产核心词得分更高
                if keyword in ['房地产', '房价', '楼市', '买房', '卖房', '成交量', '挂牌', '首付', '房贷', '利率']:
                    score += 2.0
                # 政策词得分次高
                elif keyword in ['政策', '调控', 'LPR', '央行', '财政部', '住建部', '降息', '加息']:
                    score += 1.5
                # 宏观经济词
                elif keyword in ['GDP', '经济', '宏观', 'CPI', 'PPI', '通胀', '通缩', '信贷', '就业', '失业', '裁员']:
                    score += 1.0
                # 地域词
                elif keyword in ['深圳', '上海', '北京', '广州', '杭州', '南京', '成都', '武汉', '龙华', '南山', '福田']:
                    score += 0.5
                # 其他相关词
                else:
                    score += 0.3
        
        # 惩罚过长或过短的文本
        text_len = len(text)
        if text_len < 30:
            score *= 0.5
        elif text_len > 500:
            score *= 0.7
        
        return score
    
    def get_broadcast_for_round(self, round_num: int, inject_every_n_rounds: int = 10) -> Optional[str]:
        """
        获取指定轮数的广播消息
        
        Args:
            round_num: 当前轮数（从1开始）
            inject_every_n_rounds: 每多少轮注入一次新闻
            
        Returns:
            广播消息字符串，如果没有新闻则返回None
        """
        # 检查是否应该注入新闻
        if round_num % inject_every_n_rounds != 0:
            return None
        
        if not self.news_items:
            return None
        
        # 随机选择一条未使用的新闻
        available_indices = set(range(len(self.news_items))) - self.used_indices
        if not available_indices:
            # 如果都用过了，重置
            available_indices = set(range(len(self.news_items)))
            self.used_indices.clear()
        
        # 选择相关性较高的新闻
        selected_idx = random.choice(list(available_indices))
        self.used_indices.add(selected_idx)
        
        news_item = self.news_items[selected_idx]
        
        # 保存缓存
        self._save_cache()
        
        return news_item.to_broadcast_message(round_num)
    
    def get_sample_news(self, n: int = 5) -> List[NewsItem]:
        """获取样本新闻（用于预览）"""
        if not self.news_items:
            return []
        return self.news_items[:min(n, len(self.news_items))]


def main():
    """测试新闻投喂器"""
    import argparse
    
    parser = argparse.ArgumentParser(description='测试新闻投喂器')
    parser.add_argument('--dir', type=str, 
                       default='/Users/dereky/gemini/youtube_downloads/老厉害',
                       help='字幕文件目录')
    parser.add_argument('--cache', type=str,
                       default='/Users/dereky/gemini/analysis/real_estate/news_cache.json',
                       help='缓存文件路径')
    parser.add_argument('--sample', type=int, default=5,
                       help='显示样本数量')
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    feeder = NewsFeeder(args.dir, args.cache)
    
    # 扫描并提取新闻
    count = feeder.scan_transcripts()
    print(f"\n提取了 {count} 条相关新闻")
    
    # 显示样本
    print("\n=== 样本新闻 ===")
    for i, item in enumerate(feeder.get_sample_news(args.sample)):
        print(f"\n[{i+1}] 相关度: {item.relevance_score:.2f}")
        print(f"    来源: {os.path.basename(item.source_file)}")
        print(f"    时间: {item.timestamp}")
        print(f"    内容: {item.content[:150]}...")


if __name__ == '__main__':
    main()
