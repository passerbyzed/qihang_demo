# -*- coding: utf-8 -*-
"""
启航家庭教育 - 夜间私信 AI 分析后端
接入 DeepSeek API，实现意图识别、风险分级、首响生成
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import re
import os
from openai import OpenAI

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# ============ 配置 ============
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', 'YOUR_API_KEY_HERE')  # 从环境变量读取，或在此填入
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# 加载知识库
with open('knowledge_base.json', 'r', encoding='utf-8') as f:
    KB = json.load(f)

# ============ 工具函数 ============

def check_crisis(text):
    """检查是否命中危机关键词，返回 (is_crisis, crisis_type, keywords_hit)"""
    for crisis_type, keywords in KB['crisis_keywords'].items():
        for kw in keywords:
            if kw in text:
                return True, crisis_type, kw
    return False, None, None

def detect_intent(text):
    """意图识别：基于关键词匹配"""
    scores = {}
    for intent, keywords in KB['intent_patterns'].items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[intent] = score

    if not scores:
        return '咨询'  # 默认

    return max(scores, key=scores.get)

def retrieve_kb(text, intent, crisis_type=None):
    """检索相关知识库条目"""
    relevant = []

    # 如果是危机，优先危机知识库
    if crisis_type:
        relevant = [kb for kb in KB['knowledge_items'] if kb['category'] == '危机应对']
        return relevant[:3]  # 最多返回 3 条

    # 否则基于关键词匹配
    for kb_item in KB['knowledge_items']:
        trigger_kws = kb_item.get('trigger_keywords', [])
        if any(kw in text for kw in trigger_kws):
            relevant.append(kb_item)

    # 如果没匹配到，按意图返回对应分类
    if not relevant:
        category_map = {
            '问价格': '价格政策',
            '问课程': '课程设置',
            '抱怨/退费': '投诉处理',
            '随口问': '校区信息',
            '医疗越界': '医疗边界'
        }
        category = category_map.get(intent)
        if category:
            relevant = [kb for kb in KB['knowledge_items'] if kb['category'] == category]

    return relevant[:3]  # 最多返回 3 条

def calculate_risk_heat(text, intent, is_crisis):
    """计算风险级别和热度"""
    # 风险级别
    if is_crisis:
        risk = 3
    elif intent in ['抱怨/退费', '医疗越界']:
        risk = 2
    else:
        risk = 1

    # 热度（基于问号、感叹号、迫切程度词）
    heat_keywords = ['急', '马上', '今天', '立刻', '怎么办', '帮帮我']
    heat_score = sum(1 for kw in heat_keywords if kw in text)
    heat_score += text.count('?') + text.count('？') + text.count('!') + text.count('！')

    if heat_score >= 3:
        heat = 3
    elif heat_score >= 1:
        heat = 2
    else:
        heat = 1

    return risk, heat

# ============ API 端点 ============

@app.route('/api/analyze', methods=['POST'])
def analyze_message():
    """
    分析用户消息
    输入: { "text": "...", "platform": "微信", "who": "家长·李女士" }
    输出: { "intent", "risk", "heat", "basis", "advice", "kb_items", "first_response" }
    """
    try:
        data = request.json
        text = data.get('text', '')
        platform = data.get('platform', '微信')
        who = data.get('who', '家长')

        if not text:
            return jsonify({'error': '消息内容不能为空'}), 400

        # 1. 危机检测
        is_crisis, crisis_type, crisis_kw = check_crisis(text)

        # 2. 意图识别
        if is_crisis and crisis_type == 'self_harm':
            intent = '求方案'
        elif is_crisis and crisis_type == 'medical':
            intent = '医疗越界'
        else:
            intent = detect_intent(text)

        # 3. 风险和热度
        risk, heat = calculate_risk_heat(text, intent, is_crisis)

        # 4. 检索知识库
        kb_items = retrieve_kb(text, intent, crisis_type if is_crisis else None)

        # 5. 生成首响
        first_response, kb_source = generate_first_response(
            text, intent, risk, is_crisis, crisis_type, kb_items, who
        )

        # 6. 生成判断依据
        if is_crisis:
            basis = f'命中危机词「{crisis_kw}」→ 立即停应答转人工'
        elif risk == 2:
            basis = f'命中「{intent}」类敏感词 → 转人工处理'
        else:
            basis = f'意图：{intent}，未命中风险词'

        # 7. 生成建议动作
        advice = generate_advice(intent, risk, is_crisis)

        # 8. 确定接手人
        if risk == 3:
            owner = '组长 小彤'
        elif risk == 2:
            owner = '组长 小彤'
        else:
            owner = '客服 小林'

        return jsonify({
            'intent': intent,
            'risk': risk,
            'heat': heat,
            'basis': basis,
            'advice': advice,
            'owner': owner,
            'first_response': first_response,
            'kb_source': kb_source,
            'kb_items': [{'n': kb['title'], 's': kb['content']} for kb in kb_items],
            'should_stop_ai': risk >= 3  # 风险 3 级立即停应答
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def generate_first_response(text, intent, risk, is_crisis, crisis_type, kb_items, who):
    """生成首响回复"""

    # 如果有固定模板，直接返回
    for kb in kb_items:
        if kb.get('response_template'):
            return kb['response_template'], kb['title']

    # 否则调用 DeepSeek 生成
    kb_context = '\n\n'.join([f"【{kb['title']}】\n{kb['content']}" for kb in kb_items])

    system_prompt = f"""你是启航家庭教育的在线助教，负责夜间私信首次响应。

**严格遵守以下规则：**
1. 风险 3 级（自伤/暴力）：只做安全确认 + 转人工，禁止推课
2. 风险 2 级（投诉/医疗）：只做安抚 + 转接，不承诺方案
3. 普通咨询：根据知识库回答，不编造信息
4. 回复限 60 字内，分 2-3 句，亲切但不过度热情
5. 不用「亲 / 亲爱的 / 么么哒」等词

当前用户意图：{intent}
风险级别：{risk}
是否危机：{is_crisis}

**知识库参考：**
{kb_context if kb_context else '（无相关知识库）'}
"""

    user_prompt = f"用户消息：{text}\n\n请生成首响回复（60 字内）："

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )

        reply = response.choices[0].message.content.strip()
        kb_source = kb_items[0]['title'] if kb_items else 'AI 生成（无匹配知识库）'

        return reply, kb_source

    except Exception as e:
        # API 调用失败时的兜底回复
        fallback = "收到你的消息，我们会尽快安排老师联系你。"
        return fallback, f'兜底回复（API 错误：{str(e)}）'

def generate_advice(intent, risk, is_crisis):
    """生成建议动作"""
    if is_crisis:
        return '今天上午 10 点前电话回访，先问孩子当下的安全情况，不推课'
    elif intent == '问价格':
        return '标准价可直接答，转顾问约试听时段'
    elif intent == '抱怨/退费':
        return '只做安抚与转接，不承诺方案；当日转校长'
    elif intent == '医疗越界':
        return '固定话术拒绝判断 + 立即转人工，建议就医'
    elif intent == '问课程':
        return '按 FAQ 原文答课程设置，邀约体验课'
    else:
        return '按知识库回答，邀约到店或留联系方式'

@app.route('/api/continue', methods=['POST'])
def continue_conversation():
    """
    AI 继续回复（第 2-3 轮）
    输入: { "text": "用户消息", "history": [...], "intent": "...", "kb_items": [...] }
    输出: { "response": "...", "kb_source": "..." }
    """
    try:
        data = request.json
        text = data.get('text', '')
        history = data.get('history', [])
        intent = data.get('intent', '')
        kb_items = data.get('kb_items', [])

        # 构建对话历史
        messages = [
            {"role": "system", "content": f"""你是启航家庭教育的在线助教。
当前对话意图：{intent}
**限制：**
- 每条回复 ≤ 50 字
- 不承诺优惠、不代签合同
- 不确定的信息说"让顾问老师确认"
"""}
        ]

        for h in history:
            messages.append({"role": "user" if h.get('role') == 'user' else "assistant", "content": h['content']})

        messages.append({"role": "user", "content": text})

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.4,
            max_tokens=150
        )

        reply = response.choices[0].message.content.strip()

        return jsonify({
            'response': reply,
            'kb_source': 'AI 追加回复'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({'status': 'ok', 'message': '启航 AI 后端运行中'})

if __name__ == '__main__':
    print('=' * 50)
    print('启航家庭教育 AI 后端服务启动')
    print('访问地址: http://localhost:5000')
    print('=' * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)
