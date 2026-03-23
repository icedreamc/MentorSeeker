import os
import json
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote
import markdownify
from pydantic import BaseModel, Field
from openai import OpenAI
from dotenv import load_dotenv
import time
import re
from pathlib import Path
import argparse
from collections.abc import Callable

BASE_DIR = Path(__file__).resolve().parent
# 加载 backend/.env 中的环境变量
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# 初始化环境变量和客户端
EMAIL = os.getenv("PROVIDER_EMAIL", "your_email@example.com")
COOKIE = os.getenv("BROWSER_COOKIE", "")
MODEL_NAME = os.getenv("LLM_MODEL", "gpt-4o-mini") # 确保使用支持 Structured Outputs 的模型

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)

# ==========================================
# 1. 定义 Pydantic 数据结构 (Google Scholar Agent 使用)
# ==========================================

class ProfileRouting(BaseModel):
    found: bool = Field(description="是否在页面中找到了匹配该导师和学校的个人主页链接")
    profile_url: str = Field(default="", description="导师的 Google Scholar 个人主页绝对链接")
    reason: str = Field(default="", description="提取该链接的理由，或者未找到的原因")

class Paper(BaseModel):
    title: str

class ScholarProfileData(BaseModel):
    name: str = Field(description="导师姓名")
    affiliation: str = Field(description="所在机构/学校")
    papers: list[Paper] = Field(default=[], description="页面上列出的论文列表")

# ==========================================
# 2. 网页抓取工具 (整合了 Cookie 与 Markdown 链接提炼)
# ==========================================

def get_website_content(url: str) -> str:
    """ 获取网页 HTML 并转换为带链接的 Markdown 以便于 LLM 理解 """
    print(f"   [Web Fetch] 正在抓取: {url} ...")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        if COOKIE:
            headers["Cookie"] = COOKIE

        response = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "meta", "noscript", "svg"]):
            tag.decompose()
            
        extracted_links = []
        for a in soup.find_all('a', href=True):
            href = urljoin(url, a['href'])
            a['href'] = href
            text = a.get_text(strip=True)
            if text and href.startswith('http'):
                extracted_links.append(f"- [{text}]({href})")
            
        raw_markdown = markdownify.markdownify(str(soup), heading_style="ATX")
        lines = [line.strip() for line in raw_markdown.split('\n') if line.strip()]
        compact_markdown = '\n'.join(lines)
        truncated_md = compact_markdown[:20000]
        
        unique_links = []
        seen_links = set()
        for link in extracted_links:
            if link not in seen_links:
                unique_links.append(link)
                seen_links.add(link)
        
        links_section = "\n\n### 页面可用导航链接参考 ###\n" + "\n".join(unique_links[:300])
        return truncated_md + links_section
        
    except Exception as e:
        print(f"   [Web Fetch Failed]: {e}")
        return ""

# ==========================================
# 3. Google Scholar Agent 核心逻辑
# ==========================================

def route_to_profile(name: str, school: str, search_page_markdown: str) -> str:
    print(f"   [Agent] LLM 1 正在寻找 {name} 的 Scholar 主页路由...")
    prompt = f"""
    你是一个智能网页导航助手。用户正在 Google Scholar 上搜索名为 "{name}"，学校机构为 "{school}" 的学者。
    下面是搜索结果页面的 Markdown 内容及提取出的超链接。
    请找出这位学者的 Google Scholar 个人主页链接。注意甄别同名学者。
    
    {search_page_markdown}
    """
    try:
        response = client.beta.chat.completions.parse(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "你是一个严谨的网页链接提取器。"},
                {"role": "user", "content": prompt}
            ],
            response_format=ProfileRouting,
        )
        result = response.choices[0].message.parsed
        if result.found and result.profile_url:
            print(f"   [Agent] [+] 路由成功: {result.profile_url}")
            return result.profile_url
    except Exception as e:
        print(f"   [Agent] 路由分析报错: {e}")
    return ""

def extract_profile_data(profile_markdown: str) -> ScholarProfileData:
    print(f"   [Agent] LLM 2 正在提取结构化学术数据...")
    prompt = f"""
    你是一个专业的数据提取 AI。下面是一位学者的 Google Scholar 个人主页的 Markdown 内容。
    请提取出该学者的姓名、机构、以及页面上列出的主要论文的标题。
    
    {profile_markdown}
    """
    response = client.beta.chat.completions.parse(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": "你是一个精准的数据提取器，严格按照 JSON Schema 输出数据。"},
            {"role": "user", "content": prompt}
        ],
        response_format=ScholarProfileData,
    )
    return response.choices[0].message.parsed

def search_google_scholar_agent(name: str, school: str) -> list:
    """ 编排 Agent，返回发现的论文标题列表 """
    query = f"{name}".replace(' ', '+')
    search_url = f"https://scholar.google.com/citations?view_op=search_authors&mauthors={query}"
    
    search_md = get_website_content(search_url)
    if not search_md: return []
        
    profile_url = route_to_profile(name, school, search_md)
    if not profile_url: return []
        
    profile_md = get_website_content(profile_url)
    if not profile_md: return []
        
    scholar_data = extract_profile_data(profile_md)
    # 提取标题并返回
    return [p.title for p in scholar_data.papers]

# ==========================================
# 4. 导师个人主页提取与补充 API
# ==========================================

def extract_mentor_profile(markdown_content: str, name: str) -> dict:
    prompt = f"""
你是一名学术信息提取助手。请根据提供的导师个人主页文本({name})，提取以下结构化信息。
要求输出严格的JSON格式：
{{
    "education": ["学士在哪读的...", "博士在哪读的..."], 
    "current_titles": ["教授", "系主任..."],
    "research_interests": ["方向1", "方向2"],
    "contact_email": "example@email.com",
    "recent_papers_mentioned_on_page": ["论文题目1", "论文题目2"], 
    "publication_page_links": ["http..."] 
}}
如果找不到，请返回空列表或空字符串。
"""
    try:
        res = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": markdown_content[:15000]}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        return {}

def merge_multiple_profiles(profiles_list: list) -> dict:
    if not profiles_list: return {}
    if len(profiles_list) == 1: return profiles_list[0]
        
    print(f"   [Profile Merge] 正在合并 {len(profiles_list)} 个来源的个人主页信息...")
    prompt = """
请将以下由同一个导师的多个不同个人主页提取出的结构化信息合并成一个单一的、最完整的信息结构并去重。
输出严格的JSON格式，包含字段: "education", "current_titles", "research_interests", "contact_email", "recent_papers_mentioned_on_page", "publication_page_links"。
"""
    try:
        res = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(profiles_list, ensure_ascii=False)}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(res.choices[0].message.content)
    except Exception:
        return profiles_list[0]

def extract_papers_from_page(md_content: str, name: str, limit: int = 10) -> list:
    prompt = f"请从以下属于 {name} 的 Publication 页面文本中，提取出最近的最多{limit}篇代表性论文的完整标题。只返回严格的 JSON 数组: {{\"papers\": [\"标题1\"]}}"
    try:
        res = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": md_content[:15000]}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(res.choices[0].message.content).get("papers", [])
    except Exception:
        return []

def search_openalex_by_title(title: str, email: str, retries: int = 3) -> dict:
    """ 用 OpenAlex API 搜索指定的论文标题以获取摘要和其他元数据 """
    safe_query = quote(title)
    url = f"https://api.openalex.org/works?filter=title.search:{safe_query}&per-page=1"
    headers = {"User-Agent": f"MentorSeeker/1.0 (mailto:{email})"}
    
    for attempt in range(retries):
        try:
            time.sleep(0.5) 
            response = httpx.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            if data.get('results') and len(data['results']) > 0:
                work = data['results'][0]
                abstract_inverted_index = work.get('abstract_inverted_index')
                abstract_text = "摘要未提供"
                
                if abstract_inverted_index:
                    max_idx = max([pos for positions in abstract_inverted_index.values() for pos in positions])
                    words = [""] * (max_idx + 1)
                    for word, positions in abstract_inverted_index.items():
                        for pos in positions: words[pos] = word
                    abstract_text = " ".join(words)

                return {
                    "title": work.get('title') or work.get('display_name'),
                    "abstract": abstract_text,
                    "url": work.get('doi') or work.get('id'), 
                    "year": work.get('publication_year'),
                }
            return {} 
        except Exception:
            if attempt < retries - 1: time.sleep(1)
            else: break 
    return {}

def summarize_papers(papers_context: str) -> str:
    prompt = """
仔细阅读以下关于某位导师的论文检索结果。
请生成一段简要的学术总结（300字以内），概括该导师近年来的主要研究兴趣、常用技术方法和学术贡献。如果信息太少，请直接说明。
"""
    try:
        res = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": papers_context[:10000]}
            ]
        )
        return res.choices[0].message.content
    except Exception:
        return ""

def generate_high_level_summary(mentor_info: dict) -> str:
    prompt = """
根据以下收集到的结构化导师信息，为该导师写一段综合评价（High-level Summary）。
综合评价应该包括：1. 学术地位与头衔。 2. 核心研究方向。 3. 教育背景与学术影响。
请输出自然流畅的段落描述。
"""
    try:
        res = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(mentor_info, ensure_ascii=False)}
            ]
        )
        return res.choices[0].message.content
    except Exception:
        return ""

def deduplicate_mentors_basic(mentors: list) -> list:
    print("使用基础 Name 包含启发式去重...")
    for m in mentors:
        if 'profile_url' in m and isinstance(m['profile_url'], str):
            val = m.pop('profile_url', '')
            m['profile_url'] = [val] if val else []

    res = []
    discarded = set()
    for i in range(len(mentors)):
        if i in discarded: continue
        item_i = mentors[i]
        name_i = item_i['name'].lower()
        
        for j in range(i + 1, len(mentors)):
            if j in discarded: continue
            item_j = mentors[j]
            name_j = item_j['name'].lower()
            
            if name_i in name_j or name_j in name_i:
                discarded.add(j)
                for url in item_j.get('profile_url', []):
                    if url not in item_i['profile_url']:
                        item_i['profile_url'].append(url)
                
        res.append(item_i)
    return res

# ==========================================
# 5. 主流程控制
# ==========================================

def run_enrichment(
    input_file: str,
    enrich_limit: int = 5,
    sleep_seconds: float = 1.0,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[list, str]:
    input_path = Path(input_file)

    match = re.search(r'mentor_search_result_(.*?)_', input_path.name)
    extracted_school = match.group(1) if match else "大学"

    print(f"--- 读取原始数据 {input_path} (推测学校: {extracted_school}) ---")

    if not input_path.exists():
        raise FileNotFoundError(f"文件 {input_path} 不存在，请检查！")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    unique_mentors = deduplicate_mentors_basic(data)
    print(f"去重后剩余 {len(unique_mentors)} 位导师。")

    mentors_to_enrich = unique_mentors[:enrich_limit]
    enriched_results = []

    for idx, mentor in enumerate(mentors_to_enrich):
        if should_stop and should_stop():
            print("🛑 收到中止请求，提前结束 enrichment。")
            break

        name = mentor.get('name', 'Unknown')
        print(f"\n[{idx+1}/{len(mentors_to_enrich)}] 🚀 正在 Enrichment: {name} ...")

        enriched_mentor = mentor.copy()
        profile_urls = mentor.get('profile_url', [])

        # 1. 尝试从个人官网 URL 提取信息
        all_profiles = []
        for profile_url in profile_urls:
            if profile_url and profile_url.startswith("http"):
                page_md = get_website_content(profile_url)
                if page_md:
                    p_info = extract_mentor_profile(page_md, name)
                    if p_info:
                        all_profiles.append(p_info)

        profile_info = merge_multiple_profiles(all_profiles) or {}
        enriched_mentor['structured_profile'] = profile_info

        # 2. 获取论文候选列表 (官网主页 -> 官网专门的 publication 页 -> Google Scholar Agent)
        papers_on_page = profile_info.get("recent_papers_mentioned_on_page", [])
        if not isinstance(papers_on_page, list):
            papers_on_page = []

        # 深度探测 Publication 链接
        if not papers_on_page:
            pub_links = profile_info.get("publication_page_links", [])
            if not isinstance(pub_links, list):
                pub_links = []
            extracted_all = []
            for link in pub_links:
                if link and isinstance(link, str) and link.startswith('http'):
                    print(f"   [Profile Navigator] 发现论文专页，深度抓取: {link}")
                    pub_md = get_website_content(link)
                    if pub_md:
                        extracted_titles = extract_papers_from_page(pub_md, name, limit=4)
                        if extracted_titles:
                            extracted_all.extend(extracted_titles)

            if extracted_all:
                unique_titles = list(dict.fromkeys([t.strip() for t in extracted_all if t.strip()]))
                papers_on_page.extend(unique_titles)
                profile_info['recent_papers_mentioned_on_page'] = papers_on_page

        # 如果通过官网还是找不到论文，唤醒 Google Scholar Agent 代理抓取
        if not papers_on_page:
            print(f"   [Scholar Agent] 官网未提供明确论文列表，启动 AI 代理检索 Google Scholar...")
            agent_found_titles = search_google_scholar_agent(name, extracted_school)
            if agent_found_titles:
                papers_on_page.extend(agent_found_titles)
                profile_info['recent_papers_mentioned_on_page'] = papers_on_page
                print(f"   [Scholar Agent] 成功代理抓取到 {len(agent_found_titles)} 篇论文标题！")

        # 3. 统一使用 OpenAlex 获取完整的摘要信息，并整理出统一的 publications 字段
        detailed_publications = []
        abstracts_lst = []

        if papers_on_page:
            print(f"   [OpenAlex API] 正在为 {len(papers_on_page)} 篇论文查证摘要和元数据...")
            for title_str in papers_on_page:
                paper_info = search_openalex_by_title(title_str, EMAIL)

                # 无论 API 查没查到，都保证结构统一
                abs_text = "摘要未提供"
                real_title = title_str
                url = ""
                year = ""

                if paper_info:
                    abs_text = paper_info.get('abstract') or "摘要未提供"
                    real_title = paper_info.get('title') or title_str
                    url = paper_info.get('url', "")
                    year = paper_info.get('year', "")

                # 统一的数据结构
                detailed_publications.append({
                    "title": real_title,
                    "abstract": abs_text,
                    "url": url,
                    "year": year
                })
                abstracts_lst.append(f"Title: {real_title}\nAbstract:\n{abs_text}\n")

        # 将统一格式的论文数据写入 enriched_mentor (替换旧的逻辑)
        enriched_mentor['publications'] = detailed_publications

        # 4. 论文总结
        papers_context = "提取的论文列表及摘要:\n" + "\n---\n".join(abstracts_lst) if abstracts_lst else ""
        if papers_context:
            print(f"   [Summarize] 正在根据获取的摘要总结近期论文...")
            paper_summary = summarize_papers(papers_context)
            enriched_mentor['papers_summary'] = paper_summary

        # 5. High-level Summary
        print(f"   [Summarize] 正在生成高维综合摘要...")
        high_level_summary = generate_high_level_summary(enriched_mentor)
        enriched_mentor['high_level_summary'] = high_level_summary

        enriched_results.append(enriched_mentor)
        time.sleep(sleep_seconds) # 稍作限流

    # 输出到新文件
    out_file = str(input_path.with_name(input_path.stem + "_enriched.json"))
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(enriched_results, f, ensure_ascii=False, indent=4)

    print(f"\n🎉 Enrichment 完成！结果已保存至 {out_file}")
    return enriched_results, out_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MentorSeeker enrichment pipeline")
    parser.add_argument("--input-file", default="mentor_search_result_HKUST_data_science.json", help="Raw mentor JSON file")
    parser.add_argument("--enrich-limit", type=int, default=5, help="How many mentors to enrich")
    parser.add_argument("--sleep-seconds", type=float, default=1.0, help="Sleep seconds between mentors")
    args = parser.parse_args()

    run_enrichment(
        input_file=args.input_file,
        enrich_limit=args.enrich_limit,
        sleep_seconds=args.sleep_seconds,
    )
