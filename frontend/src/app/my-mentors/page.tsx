"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { deleteMentorPermanently, generateAdvisorLibrarySummary, listMentors, toggleFavorite } from "@/lib/api";
import type { MentorList } from "@/lib/types";

export default function MyMentorsPage() {
  const [data, setData] = useState<MentorList | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [generatingSummary, setGeneratingSummary] = useState(false);

  async function load() {
    try {
      const params = new URLSearchParams({
        favorite_only: "true",
        page: "1",
        page_size: "100",
      });
      const res = await listMentors(params);
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function removeFavorite(id: number) {
    try {
      setError("");
      await toggleFavorite(id, false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "取消收藏失败");
    }
  }

  async function deleteMentor(id: number, name: string) {
    const confirmed = window.confirm(
      `确定要从导师库永久删除 ${name} 吗？\n\n这会全局移除该导师，并清理关联的收藏、备注和 timeline 数据。`,
    );
    if (!confirmed) {
      return;
    }

    try {
      setError("");
      await deleteMentorPermanently(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除导师失败");
    }
  }

  async function onGenerateSummary() {
    setGeneratingSummary(true);
    setError("");
    setMessage("");
    try {
      const result = await generateAdvisorLibrarySummary({ user_id: 1, scope: "favorites" });
      setMessage(
        result.updated
          ? `已基于 ${result.source_count} 位收藏导师生成总结${result.used_llm ? "（LLM）" : "（本地规则）"}。你可以去“设置”页继续手动微调。`
          : result.summary_text,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成导师库总结失败");
    } finally {
      setGeneratingSummary(false);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h2 className="page-title">我的导师库</h2>
          <p className="page-desc">查看收藏导师，并进入详情、联系草稿与偏好总结。 </p>
        </div>
        <div className="actions">
          <button className="btn-primary" type="button" disabled={generatingSummary} onClick={onGenerateSummary}>
            {generatingSummary ? "生成中..." : "生成总结"}
          </button>
          <p className="small">收藏总数：{data?.total ?? 0}</p>
        </div>
      </header>

      {message ? <div className="status-pill status-success">{message}</div> : null}
      {error ? <div className="status-pill status-failed">{error}</div> : null}

      {(data?.items ?? []).length === 0 ? <div className="empty-box">还没有收藏导师。</div> : null}

      <section className="mentor-grid">
        {(data?.items ?? []).map((item) => {
          const summaryText = item.high_level_summary?.trim() || item.research_direction?.trim() || "暂无研究方向描述";
          return (
            <article key={item.id} className="card mentor-card">
              <strong>{item.name}</strong>
              <div className="meta-row">
                <span className="chip">{item.school}</span>
                <span className="chip">{item.interested_field}</span>
                {item.is_auto_enriched ? <span className="chip chip-enriched">Auto-enriched</span> : null}
              </div>
              <p className="small" style={{ whiteSpace: "pre-wrap" }}>
                {summaryText}
              </p>
              {(item.ai_keywords ?? []).length > 0 ? (
                <div className="meta-row">
                  {item.ai_keywords.slice(0, 6).map((keyword) => (
                    <span key={`${item.id}-${keyword}`} className="chip">
                      {keyword}
                    </span>
                  ))}
                </div>
              ) : null}
              <div className="actions">
                <Link className="btn-secondary" href={`/mentors/${item.id}`}>
                  查看详情
                </Link>
                <Link className="btn-primary" href={`/contact-draft?mentor_id=${item.id}`}>
                  Contact
                </Link>
                <button className="btn-secondary" onClick={() => removeFavorite(item.id)}>
                  取消收藏
                </button>
                <button className="btn-danger" onClick={() => deleteMentor(item.id, item.name)}>
                  永久删除
                </button>
              </div>
            </article>
          );
        })}
      </section>
    </section>
  );
}
