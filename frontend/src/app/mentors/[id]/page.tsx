"use client";

import { FormEvent, use, useEffect, useMemo, useState } from "react";
import { createTimeline, deleteMentorPermanently, getMentor, saveNote, toggleFavorite } from "@/lib/api";
import type { MentorDetail } from "@/lib/types";

type Props = {
  params: Promise<{ id: string }>;
};

export default function MentorDetailPage({ params }: Props) {
  const { id } = use(params);
  const mentorId = Number(id);

  const [detail, setDetail] = useState<MentorDetail | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const [note, setNote] = useState("");
  const [tags, setTags] = useState("");
  const [eventType, setEventType] = useState("emailed");
  const [eventDate, setEventDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [eventContent, setEventContent] = useState("");

  const publications = useMemo(() => detail?.publications ?? [], [detail]);

  async function load() {
    try {
      const data = await getMentor(mentorId);
      setDetail(data);
      setNote(data.user_note || "");
      setTags((data.user_tags || []).join(", "));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载导师详情失败");
    }
  }

  useEffect(() => {
    if (Number.isNaN(mentorId)) {
      setError("无效的导师 ID");
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mentorId]);

  async function onFavorite() {
    if (!detail) return;
    try {
      await toggleFavorite(detail.id, !detail.is_favorite);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "收藏操作失败");
    }
  }

  async function onDeleteMentor() {
    if (!detail) return;
    const confirmed = window.confirm(`确定要从导师库永久删除 ${detail.name} 吗？\n\n这会移除该导师及其关联的收藏、备注和 timeline 数据。`);
    if (!confirmed) {
      return;
    }

    try {
      await deleteMentorPermanently(detail.id);
      window.location.href = "/mentors";
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除导师失败");
    }
  }

  async function onSaveNote(event: FormEvent) {
    event.preventDefault();
    if (!detail) return;

    setSaving(true);
    try {
      const tagList = tags
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      await saveNote(detail.id, note, tagList);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存备注失败");
    } finally {
      setSaving(false);
    }
  }

  async function onAddTimeline(event: FormEvent) {
    event.preventDefault();
    if (!detail) return;

    try {
      await createTimeline({
        mentor_id: detail.id,
        event_type: eventType,
        event_date: eventDate,
        content: eventContent,
      });
      setEventContent("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "新增 timeline 事件失败");
    }
  }

  if (!detail) {
    return <section className="card">{error || "加载中..."}</section>;
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h2 className="page-title">{detail.name}</h2>
          <p className="page-desc">
            {detail.school} · {detail.interested_field}
          </p>
        </div>
        <div className="actions">
          <button className="btn-secondary" onClick={onFavorite}>
            {detail.is_favorite ? "取消收藏" : "收藏"}
          </button>
          <button className="btn-danger" onClick={onDeleteMentor}>
            永久删除
          </button>
        </div>
      </header>

      <article className="card grid">
        <h3 className="section-title">导师信息</h3>
        <p style={{ margin: 0 }}>{detail.title}</p>
        <p className="small" style={{ whiteSpace: "pre-wrap" }}>{detail.research_direction || "暂无研究方向描述"}</p>
        <div className="meta-row">
          {(detail.ai_keywords ?? []).map((keyword) => (
            <span key={`kw-${keyword}`} className="chip">
              {keyword}
            </span>
          ))}
        </div>
        <div className="meta-row">
          {(detail.profile_urls ?? []).map((url) => (
            <a key={url} className="chip" href={url} target="_blank" rel="noreferrer">
              主页链接
            </a>
          ))}
        </div>
      </article>

      <article className="card grid">
        <h3 className="section-title">High-level Summary</h3>
        <p className="small" style={{ whiteSpace: "pre-wrap" }}>
          {detail.high_level_summary?.trim() || "暂无综合摘要"}
        </p>
      </article>

      <article className="card grid">
        <h3 className="section-title">代表论文</h3>
        {publications.length === 0 ? <div className="empty-box">暂无论文数据。</div> : null}
        {publications.map((paper, idx) => (
          <div key={`${String(paper.title)}-${idx}`} className="card soft">
            <strong>{String(paper.title ?? "Untitled")}</strong>
            <p className="small" style={{ marginTop: 8 }}>
              {String(paper.abstract ?? "")}
            </p>
          </div>
        ))}
        {detail.papers_summary ? (
          <div className="card soft">
            <strong>论文总结</strong>
            <p className="small" style={{ whiteSpace: "pre-wrap", marginTop: 8 }}>
              {detail.papers_summary}
            </p>
          </div>
        ) : null}
      </article>

      <section className="grid two">
        <form className="card grid" onSubmit={onSaveNote}>
          <h3 className="section-title">个人备注</h3>
          <label className="field">
            <span className="field-label">备注内容</span>
            <textarea rows={5} value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">标签（逗号分隔）</span>
            <input value={tags} onChange={(e) => setTags(e.target.value)} />
          </label>
          <div className="actions">
            <button className="btn-primary" disabled={saving}>
              {saving ? "保存中..." : "保存备注"}
            </button>
          </div>
        </form>

        <form className="card grid" onSubmit={onAddTimeline}>
          <h3 className="section-title">新增 Timeline 事件</h3>
          <label className="field">
            <span className="field-label">事件类型</span>
            <select value={eventType} onChange={(e) => setEventType(e.target.value)}>
              <option value="emailed">emailed</option>
              <option value="replied">replied</option>
              <option value="interview">interview</option>
              <option value="offer">offer</option>
              <option value="reject">reject</option>
              <option value="note">note</option>
            </select>
          </label>
          <label className="field">
            <span className="field-label">日期</span>
            <input type="date" value={eventDate} onChange={(e) => setEventDate(e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">内容</span>
            <textarea rows={4} value={eventContent} onChange={(e) => setEventContent(e.target.value)} />
          </label>
          <div className="actions">
            <button className="btn-primary">新增事件</button>
          </div>
        </form>
      </section>

      {error ? <div className="status-pill status-failed">{error}</div> : null}
    </section>
  );
}
