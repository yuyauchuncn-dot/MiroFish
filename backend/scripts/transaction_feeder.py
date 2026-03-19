#!/usr/bin/env python3
"""
Transaction Data Feeder for MiroFish
Converts CSV transaction data into market broadcast format for simulation injection.
"""

import csv
import json
from collections import defaultdict
from pathlib import Path


def load_transactions(csv_path, quality='valid'):
    """Load and filter transaction data from CSV"""
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if r['data_quality'] == quality]
    return rows


def generate_monthly_report(rows, target_districts=None):
    """Generate monthly market reports from transaction data"""
    monthly = defaultdict(lambda: {
        'count': 0, 'prices': [], 'areas': [], 'unit_prices': [], 'rents': [],
        'districts': defaultdict(lambda: {'count': 0, 'prices': []}),
        'layouts': Counter()
    })
    from collections import Counter
    
    for r in rows:
        date = r['date'].strip().strip('"')
        district = r['district'].strip().strip('"')
        
        if target_districts and district not in target_districts:
            continue
        
        if '/' not in date:
            continue
        parts = date.split('/')
        if len(parts) < 2:
            continue
        month_key = f"{parts[0]}/{parts[1]}"
        
        monthly[month_key]['count'] += 1
        monthly[month_key]['districts'][district]['count'] += 1
        
        try:
            price = float(r['total_price_wan']) if r['total_price_wan'] else 0
            if price > 0:
                monthly[month_key]['prices'].append(price)
                monthly[month_key]['districts'][district]['prices'].append(price)
        except: pass
        
        try:
            area = float(r['area_sqm']) if r['area_sqm'] else 0
            if area > 0: monthly[month_key]['areas'].append(area)
        except: pass
        
        try:
            up = float(r['unit_price_wan']) if r['unit_price_wan'] else 0
            if up > 0: monthly[month_key]['unit_prices'].append(up)
        except: pass
        
        try:
            rent = float(r['monthly_rent_yuan']) if r['monthly_rent_yuan'] else 0
            if rent > 0: monthly[month_key]['rents'].append(rent)
        except: pass
        
        layout = r['layout'].strip().strip('"')
        if layout:
            monthly[month_key]['layouts'][layout] += 1
    
    return dict(monthly)


def format_broadcast(month_key, data, district_name='深圳'):
    """Format monthly data as a news broadcast for MiroFish agents"""
    count = data['count']
    avg_price = sum(data['prices'])/len(data['prices']) if data['prices'] else 0
    median_price = sorted(data['prices'])[len(data['prices'])//2] if data['prices'] else 0
    avg_area = sum(data['areas'])/len(data['areas']) if data['areas'] else 0
    avg_unit_price = sum(data['unit_prices'])/len(data['unit_prices']) if data['unit_prices'] else 0
    avg_rent = sum(data['rents'])/len(data['rents']) if data['rents'] else 0
    
    # Top layouts
    top_layouts = data['layouts'].most_common(3) if hasattr(data['layouts'], 'most_common') else []
    layout_str = '、'.join([f"{l}({c}套)" for l, c in top_layouts])
    
    # Build broadcast message
    msg = f"📊 {district_name} {month_key} 市場數據："
    msg += f"\n• 成交 {count} 套"
    if avg_price > 0:
        msg += f"，均價 {avg_price:.0f} 萬，中位數 {median_price:.0f} 萬"
    if avg_unit_price > 0:
        msg += f"\n• 單價 {avg_unit_price:.2f} 萬/平米"
    if avg_area > 0:
        msg += f"，平均面積 {avg_area:.0f} 平米"
    if avg_rent > 0:
        msg += f"\n• 平均月租 {avg_rent:.0f} 元"
    if layout_str:
        msg += f"\n• 主力戶型：{layout_str}"
    
    return msg


def generate_broadcasts(csv_path, target_districts=None, output_path=None):
    """Generate all broadcasts and save to JSON"""
    rows = load_transactions(csv_path)
    monthly = generate_monthly_report(rows, target_districts)
    
    broadcasts = []
    for month_key in sorted(monthly.keys()):
        data = monthly[month_key]
        district_name = '、'.join(target_districts) if target_districts else '深圳'
        msg = format_broadcast(month_key, data, district_name)
        broadcasts.append({
            'month': month_key,
            'message': msg,
            'stats': {
                'count': data['count'],
                'avg_price': sum(data['prices'])/len(data['prices']) if data['prices'] else 0,
                'median_price': sorted(data['prices'])[len(data['prices'])//2] if data['prices'] else 0,
            }
        })
    
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(broadcasts, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved {len(broadcasts)} broadcasts to {output_path}")
    
    return broadcasts


if __name__ == '__main__':
    import sys
    csv_path = sys.argv[1] if len(sys.argv) > 1 else '/Users/dereky/gemini/real_estate/sz/analysis/xhs_extracted_cleaned.csv'
    
    # Generate for Longhua district
    print("=== 龍華片區市場廣播 ===\n")
    broadcasts = generate_broadcasts(
        csv_path,
        target_districts=['红山', '龙华中心', '龙华', '上塘', '民治', '深圳北', '观澜', '大浪'],
        output_path='/Users/dereky/gemini/analysis/real_estate/longhua_broadcasts.json'
    )
    for b in broadcasts:
        print(b['message'])
        print()
