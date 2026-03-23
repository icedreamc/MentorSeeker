"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { batchDeleteMentors, batchEnrichMentors, createMentor, deleteMentorPermanently, listMentors, toggleFavorite } from "@/lib/api";
import type { MentorList } from "@/lib/types";

export default function MentorsPage() {
  const [q, setQ] = useState("");
  const [school, setSchool] = useState("");
  const [field, setField] = useState("");
  const [favoriteOnly, setFavoriteOnly] = useState(false);
  const [page, setPage] = useState(1);

  const [showCreatePanel, setShowCreatePanel] = useState(false);
  const [newName, setNewName] = useState("");
  const [newSchool, setNewSchool] = useState("");
  const [newField, setNewField] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newDirection, setNewDirection] = useState("");
  const [newProfileUrls, setNewProfileUrls] = useState("");

  const [selectedMentorIds, setSelectedMentorIds] = useState<number[]>([]);

  const [data, setData] = useState<MentorList | null>(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [deletingBatch, setDeletingBatch] = useState(false);

  const [error, setError] = useState("");
  const [createMessage, setCreateMessage] = useState("");
  const [enrichMessage, setEnrichMessage] = useState("");
  const [deleteMessage, setDeleteMessage] = useState("");

  const visibleMentors = data?.items ?? [];
  const visibleMentorIds = useMemo(() => visibleMentors.map((item) => item.id), [visibleMentors]);

  async function load(pageValue: number = page) {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ page: String(pageValue), page_size: "20" });
      if (q) params.set("q", q);
      if (school) params.set("school", school);
      if (field) params.set("interested_field", field);
      if (favoriteOnly) params.set("favorite_only", "true");

      const res = await listMentors(params);
      setData(res);
      setSelectedMentorIds((prev) => prev.filter((id) => res.items.some((item) => item.id === id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载导师失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    await load(1);
  }

  async function onCreateMentor(event: FormEvent) {
    event.preventDefault();
    setCreateMessage("");
    setError("");

    const payload = {
      school: newSchool.trim(),
      interested_field: newField.trim(),
      name: newName.trim(),
      title: newTitle.trim(),
      research_direction: newDirection.trim(),
      profile_urls: newProfileUrls
        .split(/[\n,]/)
        .map((item) => item.trim())
        .filter(Boolean),
    };

    if (!payload.school || !payload.interested_field || !payload.name) {
      setError("请至少填写：导师姓名、学校、研究方向。");
      return;
    }

    setCreating(true);
    try {
      await createMentor(payload);
      setCreateMessage("导师已加入导师库。");
      setShowCreatePanel(false);

      setNewName("");
      setNewSchool("");
      setNewField("");
      setNewTitle("");
      setNewDirection("");
      setNewProfileUrls("");

      if (!school) setSchool(payload.school);
      if (!field) setField(payload.interested_field);

      setPage(1);
      await load(1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "新增导师失败");
    } finally {
      setCreating(false);
    }
  }

  function toggleMentorSelection(mentorId: number) {
    setSelectedMentorIds((prev) => (prev.includes(mentorId) ? prev.filter((id) => id !== mentorId) : [...prev, mentorId]));
  }

  function toggleSelectAllVisible() {
    const allVisibleSelected = visibleMentorIds.length > 0 && visibleMentorIds.every((id) => selectedMentorIds.includes(id));
    if (allVisibleSelected) {
      setSelectedMentorIds((prev) => prev.filter((id) => !visibleMentorIds.includes(id)));
      return;
    }
    setSelectedMentorIds((prev) => {
      const merged = new Set([...prev, ...visibleMentorIds]);
      return [...merged];
    });
  }

  async function onBatchEnrich() {
    if (selectedMentorIds.length === 0) {
      setError("请先勾选要 enrich 的导师。");
      return;
    }

    const confirmed = window.confirm(`将对 ${selectedMentorIds.length} 位导师执行 enrich，并补充 AI 关键词，是否继续？`);
    if (!confirmed) return;

    setEnriching(true);
    setEnrichMessage("");
    setDeleteMessage("");
    setError("");

    try {
      const result = await batchEnrichMentors({ mentor_ids: selectedMentorIds, sleep_seconds: 0.2 });
      setEnrichMessage(`Batch enrich 已完成：请求 ${result.requested_count}，成功 ${result.enriched_count}，跳过 ${result.skipped_count}。`);
      setSelectedMentorIds([]);
      await load(page);
    } catch (err) {
      setError(err instanceof Error ? err.message : "批量 enrich 失败");
    } finally {
      setEnriching(false);
    }
  }

  async function onBatchDelete() {
    if (selectedMentorIds.length === 0) {
      setError("请先勾选要删除的导师。");
      return;
    }

    const confirmed = window.confirm(
      `确定要永久删除这 ${selectedMentorIds.length} 位导师吗？\n\n删除后将清理相关收藏、备注、timeline 记录，且不可恢复。`,
    );
    if (!confirmed) return;

    setDeletingBatch(true);
    setDeleteMessage("");
    setEnrichMessage("");
    setError("");

    try {
      const result = await batchDeleteMentors({ mentor_ids: selectedMentorIds });
      setDeleteMessage(`批量删除完成：请求 ${result.requested_count}，删除 ${result.deleted_count}，未找到 ${result.not_found_count}。`);
      setSelectedMentorIds([]);
      await load(page);
    } catch (err) {
      setError(err instanceof Error ? err.message : "批量删除失败");
    } finally {
      setDeletingBatch(false);
    }
  }

  async function onToggleFavorite(id: number, isFavorite: boolean) {
    try {
      await toggleFavorite(id, !isFavorite);
      await load(page);
    } catch (err) {
      setError(err instanceof Error ? err.message : "收藏操作失败");
    }
  }

  async function onDeleteMentor(id: number, name: string) {
    const confirmed = window.confirm(`确定要从导师库永久删除 ${name} 吗？\n\n删除后将不可恢复。`);
    if (!confirmed) return;

    try {
      await deleteMentorPermanently(id);
      await load(page);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除导师失败");
    }
  }

  const allVisibleSelected = visibleMentorIds.length > 0 && visibleMentorIds.every((id) => selectedMentorIds.includes(id));

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h2 className="page-title">导师库</h2>
          <p className="page-desc">支持手动新增、批量 enrich、批量删除、收藏与详情管理。</p>
        </div>
        <p className="small">共 {data?.total ?? 0} 位导师</p>
      </header>

      <section className="card grid mentor-toolbar-card">
        <div className="mentor-toolbar-row">
          <button className="btn-secondary" type="button" onClick={() => setShowCreatePanel((prev) => !prev)}>
            {showCreatePanel ? "收起手动新增" : "手动新增导师"}
          </button>

          <div className="actions">
            <button className="btn-secondary" type="button" onClick={toggleSelectAllVisible} disabled={visibleMentorIds.length === 0}>
              {allVisibleSelected ? "取消全选本页" : "全选本页"}
            </button>
            <button className="btn-primary" type="button" onClick={onBatchEnrich} disabled={enriching || selectedMentorIds.length === 0}>
              {enriching ? "Enrich 中..." : `批量 Enrich（${selectedMentorIds.length}）`}
            </button>
            <button className="btn-danger" type="button" onClick={onBatchDelete} disabled={deletingBatch || selectedMentorIds.length === 0}>
              {deletingBatch ? "删除中..." : `批量删除（${selectedMentorIds.length}）`}
            </button>
          </div>
        </div>

        {showCreatePanel ? (
          <form className="grid mentor-create-panel" onSubmit={onCreateMentor}>
            <h3 className="section-title">手动新增导师</h3>

            <div className="grid two">
              <label className="field">
                <span className="field-label">导师姓名 *</span>
                <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="例如：李华" />
              </label>
              <label className="field">
                <span className="field-label">学校 *</span>
                <input value={newSchool} onChange={(e) => setNewSchool(e.target.value)} placeholder="例如：武汉大学" />
              </label>
            </div>

            <div className="grid two">
              <label className="field">
                <span className="field-label">研究方向 *</span>
                <input value={newField} onChange={(e) => setNewField(e.target.value)} placeholder="例如：LLM" />
              </label>
              <label className="field">
                <span className="field-label">头衔</span>
                <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="例如：助理教授" />
              </label>
            </div>

            <label className="field">
              <span className="field-label">研究简介</span>
              <textarea rows={3} value={newDirection} onChange={(e) => setNewDirection(e.target.value)} />
            </label>

            <label className="field">
              <span className="field-label">主页链接（逗号或换行分隔）</span>
              <textarea rows={2} value={newProfileUrls} onChange={(e) => setNewProfileUrls(e.target.value)} />
            </label>

            <div className="actions">
              <button className="btn-primary" disabled={creating}>{creating ? "创建中..." : "新增导师"}</button>
            </div>
          </form>
        ) : null}

        {createMessage ? <div className="status-pill status-success">{createMessage}</div> : null}
        {enrichMessage ? <div className="status-pill status-success">{enrichMessage}</div> : null}
        {deleteMessage ? <div className="status-pill status-success">{deleteMessage}</div> : null}
      </section>

      <form className="card grid" onSubmit={onSearch}>
        <div className="grid two">
          <label className="field">
            <span className="field-label">关键词</span>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="姓名 / 头衔 / 方向 / summary" />
          </label>
          <label className="field">
            <span className="field-label">学校</span>
            <input value={school} onChange={(e) => setSchool(e.target.value)} />
          </label>
        </div>

        <div className="grid two">
          <label className="field">
            <span className="field-label">研究方向</span>
            <input value={field} onChange={(e) => setField(e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">筛选</span>
            <select value={favoriteOnly ? "fav" : "all"} onChange={(e) => setFavoriteOnly(e.target.value === "fav")}>
              <option value="all">全部导师</option>
              <option value="fav">只看收藏</option>
            </select>
          </label>
        </div>

        <div className="actions">
          <button className="btn-primary" disabled={loading}>{loading ? "加载中..." : "搜索"}</button>
        </div>
      </form>

      {error ? <div className="status-pill status-failed">{error}</div> : null}

      {!loading && visibleMentors.length === 0 ? <div className="empty-box">没有匹配导师。</div> : null}

      <div className="mentor-grid">
        {visibleMentors.map((item) => {
          const summaryText = item.high_level_summary?.trim() || item.research_direction?.trim() || "暂无导师简介";
          const keywords = item.ai_keywords ?? [];

          return (
            <article key={item.id} className="card mentor-card">
              <div className="mentor-head">
                <label className="mentor-select">
                  <input
                    type="checkbox"
                    checked={selectedMentorIds.includes(item.id)}
                    onChange={() => toggleMentorSelection(item.id)}
                  />
                  <span className="small">选择</span>
                </label>

                <button className="btn-secondary" onClick={() => onToggleFavorite(item.id, item.is_favorite)}>
                  {item.is_favorite ? "取消收藏" : "收藏"}
                </button>
              </div>

              <div>
                <strong>{item.name}</strong>
                <div className="meta-row" style={{ marginTop: 6 }}>
                  <span className="chip">{item.school}</span>
                  <span className="chip">{item.interested_field}</span>
                  {item.is_auto_enriched ? <span className="chip chip-enriched">Auto-enriched</span> : null}
                </div>
              </div>

              <p style={{ margin: 0 }}>{item.title}</p>
              <p className="small" style={{ whiteSpace: "pre-wrap" }}>{summaryText}</p>

              {keywords.length > 0 ? (
                <div className="meta-row">
                  {keywords.slice(0, 6).map((keyword) => (
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
                <button className="btn-danger" onClick={() => onDeleteMentor(item.id, item.name)}>
                  永久删除
                </button>
              </div>
            </article>
          );
        })}
      </div>

      <div className="actions">
        <button className="btn-secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          上一页
        </button>
        <button
          className="btn-secondary"
          disabled={!data || page * data.page_size >= data.total}
          onClick={() => setPage((p) => p + 1)}
        >
          下一页
        </button>
      </div>
    </section>
  );
}
