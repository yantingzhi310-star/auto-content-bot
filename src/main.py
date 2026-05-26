#!/usr/bin/env python3
"""
每日热点内容生成器
每天自动搜集三大平台热点 → 用 AI 生成选题和脚本 → 推送到飞书
"""

import os
import re
import json
import requests
import html
from datetime import datetime

# ─── 环境变量 ───
AI_API_KEY = os.environ.get("AI_API_KEY", "")
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")

# ─── 热点数据采集 ───

def fetch_weibo_hot():
    """从微博热搜API获取实时热点"""
    try:
        resp = requests.get(
            "https://weibo.com/ajax/side/hotSearch",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://weibo.com/",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            realtime = data.get("data", {}).get("realtime", [])
            hotgov = data.get("data", {}).get("hotgov", {})
            topics = []
            for item in realtime[:20]:
                word = item.get("word", "")
                rank = item.get("rank", 0)
                hot_num = item.get("num", 0)
                if word:
                    topics.append({"rank": rank, "word": word, "hot": hot_num})
            return topics
    except Exception as e:
        print(f"  微博抓取失败: {e}")
    return []


def fetch_douyin_hot():
    """从第三方抖音热点聚合获取数据"""
    sources = [
        "https://www.cxw123.com/hot/7.html",
    ]
    for url in sources:
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if resp.status_code == 200:
                text = resp.text
                # 简单解析：提取<a>标签中的文本
                items = re.findall(r'<a[^>]*>([^<]+)</a>', text)
                topics = []
                for i, item in enumerate(items[:20]):
                    word = html.unescape(item.strip())
                    if word and len(word) > 2:
                        topics.append({"rank": i + 1, "word": word})
                if topics:
                    return topics
        except Exception as e:
            print(f"  抖音抓取失败: {e}")
            continue
    return []


def fetch_all_trending():
    """从所有可用源抓取热点"""
    print(">> 正在采集热点数据...")
    result = {}

    wb = fetch_weibo_hot()
    if wb:
        result["微博热搜"] = wb
        print(f"  微博: {len(wb)} 条")

    dy = fetch_douyin_hot()
    if dy:
        result["抖音热点"] = dy
        print(f"  抖音: {len(dy)} 条")

    return result


# ─── AI API 调用 ───

def call_ai_api(prompt, system=""):
    """调用 AI API (自动适配 Anthropic / OpenAI 兼容格式)"""
    headers = {
        "Content-Type": "application/json",
    }

    # 检测 key 格式，自动选择 API
    if AI_API_KEY.startswith("sk-ant"):
        # Anthropic API
        headers["x-api-key"] = AI_API_KEY
        headers["anthropic-version"] = "2023-06-01"
        body = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 4000,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers, json=body, timeout=120,
        )
        if resp.status_code != 200:
            raise Exception(f"Anthropic API {resp.status_code}: {resp.text[:300]}")
        return resp.json()["content"][0]["text"]

    else:
        # OpenAI 兼容格式 (DeepSeek / OpenAI / 其他)
        headers["Authorization"] = f"Bearer {AI_API_KEY}"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # 尝试 DeepSeek
        try:
            body = {
                "model": "deepseek-chat",
                "max_tokens": 4000,
                "messages": messages,
            }
            resp = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers=headers, json=body, timeout=120,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            print(f"  DeepSeek 失败 ({resp.status_code})，尝试 OpenAI...")
        except Exception as e:
            print(f"  DeepSeek 错误: {e}")

        # Fallback: OpenAI
        body = {
            "model": "gpt-4o",
            "max_tokens": 4000,
            "messages": messages,
        }
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers, json=body, timeout=120,
        )
        if resp.status_code != 200:
            raise Exception(f"API 全部失败: {resp.status_code} {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]["content"]


# ─── 内容生成 ───

def build_prompt(trending_data):
    """构造生成提示词"""
    today = datetime.now().strftime("%Y年%m月%d日")

    # 格式化热点数据
    hot_text = ""
    if trending_data:
        for platform, topics in trending_data.items():
            hot_text += f"\n【{platform}】\n"
            for t in topics:
                word = t.get("word", "")
                rank = t.get("rank", "")
                hot = t.get("hot", "")
                if hot:
                    hot_text += f"  #{rank} {word} (热度:{hot})\n"
                else:
                    hot_text += f"  #{rank} {word}\n"
    else:
        hot_text = "\n  (今日热点数据未获取到，请基于你的知识生成近期热门话题)"

    prompt = f"""你是短视频运营专家，今天是 {today}。

今天采集到的热点数据如下，请分析并产出内容：

{hot_text}

要求：
1. 从中选出 TOP5 最适合做「不露脸短视频」的选题
2. 每个选题写清楚：参考标题 + 内容形式（解说/盘点/配音画面等）+ 脚本框架
3. 从5个中选最优的1个，写出完整60秒脚本（含时间轴、画面描述、台词）
4. 每个选题都必须是「不露脸」也能做的

输出格式：
━━━━━━━━━━━━━━━━━━
# TOP5 选题推荐

## 选题1：标题
形式：xxx
脚本框架：xxx

## 选题2：...
...

━━━━━━━━━━━━━━━━━━
# 优选完整脚本

| 时间 | 画面 | 台词 |
...
━━━━━━━━━━━━━━━━━━
# 可做封面的金句
- ...
"""
    return prompt


# ─── 飞书推送 ───

def send_feishu(text, title=None):
    """发送消息到飞书"""
    if title:
        msg = f"{title}\n━━━━━━━━━━━━━━━━━━\n\n{text}"
    else:
        msg = text

    payload = {"msg_type": "text", "content": {"text": msg[:3000]}}
    resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
    result = resp.json()
    if result.get("code") != 0:
        print(f"  飞书推送警告: {result}")
    return result


def send_feishu_card(trending, content, date_cn):
    """发送飞书卡片消息（结构化展示：热点 + TOP5 + 脚本 + 金句）"""
    # 解析 AI 输出中的各个段落
    sections = content.split("━━━━━━━━━━━━━━━━━━")
    top5_text = ""
    script_text = ""
    quotes_text = ""

    for section in sections:
        s = section.strip()
        if "TOP5" in s[:50]:
            top5_text = s
        elif "优选完整脚本" in s[:50]:
            script_text = s
        elif "封面金句" in s[:50]:
            quotes_text = s

    # 热点概览
    hot_lines = []
    if trending:
        for platform, topics in trending.items():
            names = [f"#{t.get('word', '')}" for t in topics[:5]]
            hot_lines.append(f"**{platform}**\n" + " ".join(names))
    hot_md = "\n".join(hot_lines) if hot_lines else "（暂无数据）"

    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**🔥 今日热点**\n{hot_md}"}},
        {"tag": "hr"},
    ]

    if top5_text:
        clean = top5_text.replace("# TOP5 选题推荐", "").replace("## ", "").strip()
        if len(clean) > 1500:
            clean = clean[:1500] + "\n..."
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**🎯 TOP5 选题推荐**\n{clean}"}})
        elements.append({"tag": "hr"})

    if script_text:
        clean = script_text.replace("# 优选完整脚本", "").strip()
        preview = clean[:500]
        if len(clean) > 500:
            preview += "\n...（完整脚本已保存至 GitHub）"
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**📜 优选脚本（节选）**\n{preview}"}})
        elements.append({"tag": "hr"})

    if quotes_text:
        clean = quotes_text.replace("# 可做封面的金句", "").strip()
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**💡 封面金句**\n{clean}"}})
        elements.append({"tag": "hr"})

    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": f"📎 完整内容已保存至 GitHub · {date_cn}"}],
    })

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📡 {date_cn} 热点选题推荐"},
                "template": "blue",
            },
            "elements": elements,
        },
    }

    resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
    result = resp.json()
    if result.get("code") != 0:
        print(f"  飞书推送警告: {result}")
    return result


# ─── 本地保存 ───

def save_output(today, content, trending_data):
    """保存内容到本地文件"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = f"{OUTPUT_DIR}/{today}.md"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# 每日热点与选题 [{today}]\n\n")
        f.write("## 采集的热点数据\n\n")
        if trending_data:
            for platform, topics in trending_data.items():
                f.write(f"### {platform}\n")
                for t in topics:
                    word = t.get("word", "")
                    rank = t.get("rank", "")
                    hot = t.get("hot", "")
                    if hot:
                        f.write(f"{rank}. {word} (热度:{hot})\n")
                    else:
                        f.write(f"{rank}. {word}\n")
                f.write("\n")
        else:
            f.write("热点数据未获取到\n\n")
        f.write("---\n\n")
        f.write(content)

    print(f"  已保存: {filepath}")
    return filepath


# ─── 主流程 ───

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"")
    print(f"{'='*40}")
    print(f"  每日热点内容生成  [{today}]")
    print(f"{'='*40}")
    print(f"")

    # 验证配置
    if not AI_API_KEY:
        print("  ❌ 未设置 AI_API_KEY")
        sys.exit(1)
    if not FEISHU_WEBHOOK:
        print("  ❌ 未设置 FEISHU_WEBHOOK")
        sys.exit(1)

    # Step 1: 抓取热点
    trending = fetch_all_trending()

    # Step 2: 生成内容
    print(">> AI 正在生成选题和脚本...")
    prompt = build_prompt(trending)
    system_prompt = (
        "你是一个短视频运营专家，擅长从热点中挖掘爆款选题。"
        "输出要简洁、直接、可执行。每次只输出今天的内容。"
    )

    try:
        content = call_ai_api(prompt, system_prompt)
        print(f"  AI 生成完成 ({len(content)} 字符)")
    except Exception as e:
        print(f"  ❌ AI 调用失败: {e}")
        send_feishu(f"⚠️ {today} 内容生成失败:\n{str(e)[:200]}")
        return

    # Step 3: 保存本地
    save_output(today, content, trending)

    # Step 4: 推飞书（卡片消息，一条展示全部）
    print(">> 推送到飞书...")
    try:
        date_cn = datetime.now().strftime("%m月%d日")
        send_feishu_card(trending, content, date_cn)
        print("  卡片消息 ✓")
    except Exception as e:
        print(f"  ❌ 飞书推送失败: {e}")

    print(f"\n✅ 今日任务完成！")
    print(f"  输出文件: {OUTPUT_DIR}/{today}.md")
    print(f"")


if __name__ == "__main__":
    import sys
    main()
