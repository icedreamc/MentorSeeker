import os
import json
import httpx
from bs4 import BeautifulSoup
import markdownify
from openai import OpenAI
from dotenv import load_dotenv
from ddgs import DDGS
import time
from urllib.parse import urljoin
from pathlib import Path
import argparse
from collections.abc import Callable

BASE_DIR = Path(__file__).resolve().parent
# 加载 backend/.env 中的环境变量
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# 初始化 OpenAI 客户端
client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)
MODEL_NAME = os.getenv("LLM_MODEL", "gpt-5-mini")

def search_duckduckgo(query: str, max_results=5):
    """ 使用鸭子搜索进行检索 """
    try:
        print(f"[{query}] 正在搜索引擎检索...")
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return results
    except Exception as e:
        print(f"搜索出错: {e}")
        return []

def get_website_content(url: str):
    """ 获取网页 HTML 并转换为带链接的 Markdown 以便于 LLM 理解 """
    print(f"正在获取网页内容: {url} ...")
    try:
        # 使用 httpx 获取 HTML (模拟浏览器请求头防屏蔽)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)
        response.raise_for_status()
        
        # 解析 HTML 并清理无关标签
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "meta", "noscript", "svg"]):
            tag.decompose()
            
        extracted_links = []
        # 遍历并将所有相对链接转换为绝对链接（保证LLM有完整的URL可点击）
        for a in soup.find_all('a', href=True):
            href = urljoin(url, a['href'])
            a['href'] = href
            text = a.get_text(strip=True)
            if text and href.startswith('http'):
                extracted_links.append(f"- [{text}]({href})")
            
        # 转换为 Markdown 保留网页结构和超链接
        raw_markdown = markdownify.markdownify(str(soup), heading_style="ATX")
        
        # 空白行压缩
        lines = [line.strip() for line in raw_markdown.split('\n') if line.strip()]
        compact_markdown = '\n'.join(lines)
        
        # 截取字符限制，防止超出大模型文本限制
        truncated_md = compact_markdown[:20000]
        
        # 将链接整理成一个列表附加到结尾，帮助 Agent 更好地发现可跳转路由
        unique_links = []
        seen_links = set()
        for link in extracted_links:
            if link not in seen_links:
                unique_links.append(link)
                seen_links.add(link)
        
        links_section = "\n\n### 页面可用导航链接参考 ###\n" + "\n".join(unique_links[:300])
        return truncated_md + links_section
        
    except Exception as e:
        return f"获取或处理网页时出错: {e}"

def call_nav_agent(url: str, page_content: str, links: list, school: str, research_direction: str, is_zh: bool) -> dict:
    """
    导航 Agent: 根据网页内容和链接，对提供的链接进行打分，并判断当前页是否有抽取价值。
    """
    if is_zh:
        system_prompt = f"你是一名导航者。任务是为【{school}】寻找与【{research_direction}】相关的导师信息页面。\n请阅读以下页面内容和可用链接。对可用链接评估其导向导师名单的可能性（不考虑个人主页，只考虑学院、系、所等机构页面）（0-10分）。\n判断当前页面是否大概率包含多名导师的列表（is_target_page）。\n请严格返回JSON格式：\n{{\"is_target_page\": true/false, \"scored_links\": [{{\"url\": \"...\", \"score\": \"...\"}}]}}"
    else:
        system_prompt = f"You are a Navigator. Your task is to find faculty pages for 【{school}】 related to 【{research_direction}】.\nRead the page content and available links. Score the links (0-10) based on how likely they lead to a faculty list (do not consider personal homepage, only consider institutional pages such as college, department, institute, etc.).\nDetermine if the current page itself likely contains a faculty list (is_target_page).\nReturn strict JSON:\n{{\"is_target_page\": true/false, \"scored_links\": [{{\"url\": \"...\", \"score\": \"...\"}}]}}"

    prompt_content = f"当前URL: {url}\n\n页面内容截断:\n{page_content}\n\n当前页面包含的链接:\n{json.dumps(links, ensure_ascii=False)}"

    print(f"[Nav Agent] 正在分析页面并对链接打分: {url}...")
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_content}
        ],
        response_format={"type": "json_object"}
    )
    try:
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print("[Nav Agent] JSON解析失败:", e)
        return {"is_target_page": False, "scored_links": []}

def call_extract_agent(url: str, page_content: str, school: str, research_direction: str, is_zh: bool) -> list:
    """
    提取 Agent: 专注从判定为高价值的页面文本中提取结构化导师数据。
    """
    if is_zh:
        system_prompt = f"你是一名数据提取者。请从以下页面文本中提取所有可能属于【{school}】且研究涉及【{research_direction}】（哪怕只有一点相关）的导师信息。\n请返回严格的JSON列表格式：\n{{\"data\": [{{\"name\": \"...\", \"title\": \"...\", \"research_direction\": \"...\", \"profile_url\": \"...\"}}]}}"
    else:
        system_prompt = f"You are a Data Extractor. Extract all faculty members from the text belonging to 【{school}】 whose research relates to 【{research_direction}】.\nReturn strict JSON format:\n{{\"data\": [{{\"name\": \"...\", \"title\": \"...\", \"research_direction\": \"...\", \"profile_url\": \"...\"}}]}}"

    prompt_content = f"来源URL: {url}\n\n页面内容截断:\n{page_content}"
    
    print(f"[Extract Agent] 正在从目标页提取数据: {url}...")
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_content}
        ],
        response_format={"type": "json_object"}
    )
    try:
        res = json.loads(response.choices[0].message.content)
        return res.get("data", [])
    except Exception as e:
        print("[Extract Agent] JSON解析失败:", e)
        return []

def curiosity_driven_search(
    school: str,
    research_direction: str,
    max_steps: int = 10,
    target_mentor_count: int = 40,
    output_dir: str = ".",
    output_filename: str | None = None,
    should_stop: Callable[[], bool] | None = None,
):
    """ 好奇心驱动的主循环函数 """
    print(f"=== 开始“好奇心驱动”搜寻: {school} | {research_direction} ===")
    
    visited_urls = set()
    extracted_mentors = []
    seen_names = set() # 用于去重
    
    # 简单的中英文检测逻辑：如果包含中文字符则认为是中文搜索，否则是英文
    def is_chinese_input(text):
        return any('\u4e00' <= char <= '\u9fff' for char in text)
        
    is_zh = is_chinese_input(school) or is_chinese_input(research_direction)
    
    # 初始化 URL Priority Pool，格式: {url: score}
    url_pool = {}
    
    if is_zh:
        search_query = f"{school} {research_direction} 院系官网"
    else:
        search_query = f"{school} {research_direction} faculty"
        
    search_results = search_duckduckgo(search_query, max_results=20)
    # 对初始搜索结果进行过滤和 LLM 打分
    initial_links = []
    for res in search_results:
        href = res.get('href', '')
        if href and 'edu' in href.lower():
            title = res.get('title', '')
            snippet = res.get('body', '')
            initial_links.append(f"[{title}]({href}) - {snippet}")
            
    if initial_links:
        print("[Nav Agent] 正在对鸭子搜索返回的初始结果进行评估...")
        nav_result = call_nav_agent("DuckDuckGo Initial Search", "这是搜索引擎返回的初始候选链接", initial_links, school, research_direction, is_zh)
        scored_links = nav_result.get("scored_links", [])
        for link_info in scored_links:
            nxt_url = link_info.get("url")
            score = link_info.get("score", 0)
            try:
                score = float(score)
            except (ValueError, TypeError):
                score = 0.0
            if nxt_url and nxt_url.startswith("http") and 'edu' in nxt_url.lower():
                url_pool[nxt_url] = score
            
    step = 0
    print(url_pool)
    while step < max_steps and url_pool:
        if should_stop and should_stop():
            print("🛑 收到中止请求，提前结束 discovery。")
            break

        # 1. Pop 最高分的 URL
        current_url = max(url_pool, key=url_pool.get)
        current_score = url_pool.pop(current_url)
        print(current_url)
        if current_url in visited_urls:
            continue
            
        step += 1
        print(f"\n--- 第 {step} 回合 ---")
        print(f"🔗 访问 URL (Score: {current_score}): {current_url}")
        
        visited_urls.add(current_url)
        page_content = get_website_content(current_url)
        
        if "获取或处理网页时出错" in page_content:
            print(f"⚠️ 无法有效读取该页面内容跳过。")
            continue
            
        # 提取页面原始链接（传给 LLM 打分，不超过150个防止Token爆炸）
        import re
        links_in_md = re.findall(r'\[.*?\]\((https?://.*?)\)', page_content)
        unique_links_list = list(dict.fromkeys(links_in_md))[:150]
        
        # 2. 调用 Nav Agent
        nav_result = call_nav_agent(current_url, page_content, unique_links_list, school, research_direction, is_zh)
        is_target_page = nav_result.get("is_target_page", False)
        scored_links = nav_result.get("scored_links", [])
        
        # 将新打分的链接合并到 Pool
        for link_info in scored_links:
            nxt_url = link_info.get("url")
            score = link_info.get("score", 0)
            try:
                score = float(score)
            except (ValueError, TypeError):
                score = 0.0
            if nxt_url and nxt_url.startswith("http") and 'edu' in nxt_url.lower() and nxt_url not in visited_urls:
                # 保留历史最高打分
                url_pool[nxt_url] = max(score, url_pool.get(nxt_url, 0.0))
                
        print(f"[Nav Agent] 是否建议提取: {is_target_page} | 补充了 {len(scored_links)} 个新链接到候选池。目前候选池大小: {len(url_pool)}")
        
        # 3. 如果是目标页，调用 Extract Agent
        if is_target_page:
            extracted_data = call_extract_agent(current_url, page_content, school, research_direction, is_zh)
            
            new_mentors = []
            for mentor in extracted_data:
                name = mentor.get('name')
                if name and name not in seen_names:
                    seen_names.add(name)
                    new_mentors.append(mentor)
                    
            if new_mentors:
                print(f"📥 成功提取到 {len(new_mentors)} 位导师信息！")
                for mentor in new_mentors:
                    print(f"   - {mentor.get('name')} | {mentor.get('title')}")
                extracted_mentors.extend(new_mentors)
                
        # 判断是否找够了
        if len(extracted_mentors) >= target_mentor_count: # 给个上限
             print("🏁 已收集到足够的导师信息，任务结束。")
             break

    # 保存最终提取的数据为 JSON 文件
    if not output_filename:
        output_filename = f"mentor_search_result_{school}_{research_direction}.json".replace(" ", "_")
    output_path = Path(output_dir) / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(extracted_mentors, f, ensure_ascii=False, indent=4)
        
    print(f"\n🎉 搜寻阶段完毕！共收集到 {len(extracted_mentors)} 位导师。结果已输出保存至: {output_path}")
    return str(output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MentorSeeker discovery pipeline")
    parser.add_argument("--school", default="HKUST", help="School name")
    parser.add_argument("--direction", default="data science", help="Research direction")
    parser.add_argument("--max-steps", type=int, default=10, help="Max visited pages")
    parser.add_argument("--target-mentors", type=int, default=40, help="Target mentor count")
    parser.add_argument("--output-dir", default=".", help="Output directory")
    parser.add_argument("--output-filename", default=None, help="Optional output filename")
    args = parser.parse_args()

    curiosity_driven_search(
        args.school,
        args.direction,
        max_steps=args.max_steps,
        target_mentor_count=args.target_mentors,
        output_dir=args.output_dir,
        output_filename=args.output_filename,
    )
