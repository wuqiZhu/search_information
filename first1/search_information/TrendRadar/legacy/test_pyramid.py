#!/usr/bin/env python3
"""
测试金字塔模型配置
"""
import yaml

# 加载配置
with open('config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 检查关键词
keywords = config.get('keywords', {})
print('=== 金字塔模型关键词配置 ===\n')

for category, kws in keywords.items():
    print(f'{category}: {len(kws)} 个关键词')
    for kw in kws:
        print(f'  - {kw}')
    print()

# 检查权重配置
print('=== 权重配置 ===\n')
weights = {
    'ai_company': 1.2,    # 第2层：AI公司与基金
    'welfare': 1.0,       # 第3层：福利
    'industry': 0.8       # 第4层：嵌入式行业
}

for category, weight in weights.items():
    print(f'{category}: {weight}')

print('\n=== 配置验证完成 ===')
