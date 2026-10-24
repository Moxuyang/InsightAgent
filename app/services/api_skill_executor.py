"""API技能执行引擎 —— 调用外部API并提取响应"""
import json
import urllib.parse
import requests


def execute_api_skill(skill, query: str) -> dict:
    """执行一个 API 调用类型的技能

    Args:
        skill: 技能记录dict，需包含 api_url, api_method, api_headers, api_body_template, api_response_path
        query: 用户输入的问题（已去掉@提及部分）

    Returns:
        {"success": True/False, "content": "...", "error": "..."}
    """
    api_url = (skill.get('api_url') or '').strip()
    if not api_url:
        return {"success": False, "error": "该技能未配置API地址，请在技能管理中设置"}

    # 提取查询关键词
    clean_query = (query or '').strip()
    keyword = _extract_keyword(clean_query)
    encoded_query = urllib.parse.quote(clean_query, safe='')
    encoded_keyword = urllib.parse.quote(keyword, safe='')

    api_method = (skill.get('api_method') or 'POST').strip().upper()
    api_headers_str = skill.get('api_headers') or '{}'
    body_template = skill.get('api_body_template') or ''
    response_path = (skill.get('api_response_path') or '').strip()

    # 解析headers
    try:
        headers = json.loads(api_headers_str) if isinstance(api_headers_str, str) else api_headers_str
    except json.JSONDecodeError:
        headers = {}

    # 确保 Content-Type
    if 'Content-Type' not in headers and 'content-type' not in headers:
        headers['Content-Type'] = 'application/json'
    if 'User-Agent' not in headers:
        headers['User-Agent'] = 'InsightAgent/1.0'

    # ---- 填充 URL 中的占位符（支持更多占位符类型） ----
    final_url = api_url
    has_url_placeholder = any(p in api_url for p in ['{query}', '{keyword}', '{q}', '{word}', '{text}', '{input}'])
    final_url = final_url.replace('{query}', encoded_query)
    final_url = final_url.replace('{keyword}', encoded_keyword)
    final_url = final_url.replace('{q}', encoded_query)
    final_url = final_url.replace('{word}', encoded_keyword)
    final_url = final_url.replace('{text}', encoded_query)
    final_url = final_url.replace('{input}', encoded_query)

    # ---- 填充请求体模板 ----
    request_body = None
    if body_template:
        filled_body = body_template
        for placeholder in ['{query}', '{keyword}', '{q}', '{word}', '{text}', '{input}']:
            val = encoded_keyword if placeholder in ('{keyword}', '{word}') else encoded_query
            filled_body = filled_body.replace(placeholder, val)
        # 也直接用原始值替换（非URL编码）
        filled_body = filled_body.replace('{query_raw}', clean_query).replace('{keyword_raw}', keyword)
        try:
            request_body = json.loads(filled_body)
        except json.JSONDecodeError:
            request_body = filled_body

    try:
        if api_method == 'GET':
            params = None
            if not has_url_placeholder:
                # URL中没有占位符时，自动把query作为参数传过去
                params = _build_auto_params(final_url, clean_query, keyword)
            resp = requests.get(final_url, headers=headers, params=params, timeout=30)
        elif api_method == 'POST':
            if request_body and isinstance(request_body, dict):
                resp = requests.post(final_url, headers=headers, json=request_body, timeout=30)
            elif request_body:
                resp = requests.post(final_url, headers=headers, data=request_body, timeout=30)
            else:
                # 无请求体模板时，自动构造 {"query": query}
                resp = requests.post(final_url, headers=headers, json={'query': clean_query}, timeout=30)
        else:
            return {"success": False, "error": f"不支持的HTTP方法: {api_method}"}

        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or 'utf-8'

        # 提取响应内容
        try:
            resp_data = resp.json()
        except (json.JSONDecodeError, ValueError):
            resp_data = resp.text

        # 根据 response_path 提取目标字段
        if response_path and isinstance(resp_data, dict):
            content = _extract_by_path(resp_data, response_path)
            if content is None:
                content = json.dumps(resp_data, ensure_ascii=False, indent=2)
        elif isinstance(resp_data, dict):
            content = _auto_extract(resp_data)
        else:
            content = resp_data

        # 确保 content 是字符串
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, indent=2)

        # 如果是字典且包含常用字段，美化输出
        if isinstance(resp_data, dict) and not response_path:
            content = _format_api_result(resp_data)

        return {"success": True, "content": content}

    except requests.exceptions.Timeout:
        return {"success": False, "error": f"API请求超时(30s)，请稍后重试"}
    except requests.exceptions.ConnectionError as e:
        return {"success": False, "error": f"API连接失败，请检查API地址是否正确"}
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else '未知'
        return {"success": False, "error": f"API返回HTTP错误（{status}），请检查接口配置或稍后重试"}
    except Exception as e:
        return {"success": False, "error": f"API调用异常: {str(e)[:300]}"}


def _extract_keyword(query: str) -> str:
    """从用户查询中提取核心关键词（用于替换 {keyword} 占位符）"""
    query = query.strip()
    # 去掉常见的语气词前缀：查询、查一下、帮我查、什么是、搜索等
    prefixes = ['查询 ', '查一下 ', '帮我查 ', '查询', '查一下', '帮我查', '搜索 ', '什么是 ', '什么是',
                '查询:', '搜索:', '查:', '翻译 ', '翻译', '解释 ', '解释']
    for prefix in sorted(prefixes, key=len, reverse=True):
        if query.startswith(prefix):
            query = query[len(prefix):].strip()
            break
    return query


def _build_auto_params(url: str, query: str, keyword: str) -> dict:
    """当URL没有占位符时，自动推测参数名"""
    # 常见的参数名映射
    param_candidates = ['query', 'q', 'word', 'keyword', 'kw', 'text', 'wd', 'search', 'input', 'content']
    # 默认使用几个最常见的
    if keyword:
        return {'q': query, 'word': keyword, 'keyword': keyword}
    return {'q': query, 'query': query}


def _auto_extract(data: dict) -> str:
    """自动从响应中提取最有价值的内容"""
    # 优先提取字段
    priority_keys = ['result', 'data', 'content', 'answer', 'reply', 'text', 'msg', 'message', 'response']
    for key in priority_keys:
        val = data.get(key)
        if val is not None and val != '':
            if isinstance(val, str):
                return val
            if isinstance(val, (dict, list)):
                return json.dumps(val, ensure_ascii=False, indent=2)
    return json.dumps(data, ensure_ascii=False, indent=2)


def _format_api_result(data: dict) -> str:
    """将API返回结果格式化为可读文本"""
    if isinstance(data.get('current'), dict) and 'temperature_2m' in data['current'] and 'current_units' in data:
        current, units = data['current'], data['current_units']
        labels = {'temperature_2m': '气温', 'apparent_temperature': '体感温度',
                  'relative_humidity_2m': '相对湿度', 'wind_speed_10m': '风速',
                  'precipitation': '降水量'}
        parts = ['### 当前天气', f"数据时间：{current.get('time', '未提供')}（{data.get('timezone', '未提供时区')}）",
                 f"位置：纬度 {data.get('latitude', '未知')}，经度 {data.get('longitude', '未知')}",
                 '| 指标 | 数值 |', '| --- | --- |']
        for key, label in labels.items():
            if current.get(key) is not None:
                parts.append(f"| {label} | {current[key]} {units.get(key, '')} |")
        parts.append('数据来源：[Open-Meteo](https://open-meteo.com/)。当前条件为天气模型数据，并非现场传感器读数。')
        return '\n\n'.join(parts[:3]) + '\n\n' + '\n'.join(parts[3:-1]) + '\n\n' + parts[-1]
    # 如果 data 中有 code 和 msg，先判断状态
    code = data.get('code')
    message = data.get('msg') or data.get('message', '')

    inner = data.get('data') or data.get('result') or data.get('content') or {}
    if isinstance(inner, dict):
        parts = []
        # 尝试格式化常见的词典/百科类响应
        if 'word' in inner:
            parts.append(f"📖 单词: {inner['word']}")
        if 'accent' in inner:
            parts.append(f"🔊 音标: {inner['accent']}")
        if 'mean_cn' in inner:
            parts.append(f"📝 中文释义: {inner['mean_cn']}")
        if 'mean_en' in inner:
            parts.append(f"📝 英文释义: {inner['mean_en']}")
        if 'sentence' in inner:
            parts.append(f"💬 例句: {inner['sentence']}")
        if 'sentence_trans' in inner:
            parts.append(f"🔤 翻译: {inner['sentence_trans']}")
        if 'sentence_phrase' in inner:
            parts.append(f"🏷️ 短语: {inner['sentence_phrase']}")

        if parts:
            return '\n'.join(parts)

        # 百科类
        if 'title' in inner:
            parts.append(f"📚 {inner['title']}")
        if 'summary' in inner:
            parts.append(inner['summary'])
        if 'content' in inner:
            parts.append(inner['content'])
        if 'detail' in inner:
            parts.append(inner['detail'])

        if parts:
            return '\n\n'.join(parts)

        # 通用：列出所有字段
        return '\n'.join([f"• {k}: {v}" for k, v in inner.items()
                          if not k.startswith('_') and v not in (None, '', [], {})])
    elif isinstance(inner, list):
        return json.dumps(inner, ensure_ascii=False, indent=2)
    elif isinstance(inner, str):
        return inner

    return json.dumps(data, ensure_ascii=False, indent=2)


def _extract_by_path(data, path: str):
    """按点分路径提取嵌套字段，如 "data.result.content" """
    keys = path.split('.')
    current = data
    for key in keys:
        key = key.strip()
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list) and key.isdigit():
            idx = int(key)
            if 0 <= idx < len(current):
                current = current[idx]
            else:
                return None
        else:
            return None
    return current


def find_api_skills(employee_info: dict) -> list:
    """从员工信息中筛选出 function_call 类型的技能"""
    skill_details = employee_info.get('skill_details', [])
    return [s for s in skill_details if s.get('skill_type') == 'function_call' and s.get('api_url', '').strip()]
