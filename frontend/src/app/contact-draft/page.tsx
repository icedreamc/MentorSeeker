"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";
import { commitContactDraft, generateContactDraft, getMentor } from "@/lib/api";
import type { MentorDetail } from "@/lib/types";

function toLocalIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function ContactDraftClient() {
  const searchParams = useSearchParams();
  const mentorId = useMemo(() => Number(searchParams.get("mentor_id") || 0), [searchParams]);

  const [mentor, setMentor] = useState<MentorDetail | null>(null);
  const [loadingMentor, setLoadingMentor] = useState(false);

  const [language, setLanguage] = useState<"auto" | "zh" | "en">("auto");
  const [extraInstruction, setExtraInstruction] = useState("");
  const [eventDate, setEventDate] = useState(() => toLocalIsoDate(new Date()));

  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [fitPoints, setFitPoints] = useState<string[]>([]);

  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);

  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!mentorId) {
      return;
    }

    setLoadingMentor(true);
    setError("");
    (async () => {
      try {
        const detail = await getMentor(mentorId, 1);
        setMentor(detail);
      } catch (err) {
        setError(err instanceof Error ? err.message : "读取导师信息失败");
      } finally {
        setLoadingMentor(false);
      }
    })();
  }, [mentorId]);

  async function onGenerate(event: FormEvent) {
    event.preventDefault();
    if (!mentorId) {
      setError("缺少 mentor_id 参数。");
      return;
    }

    setGenerating(true);
    setError("");
    setMessage("");

    try {
      const result = await generateContactDraft({
        mentor_id: mentorId,
        language,
        extra_instruction: extraInstruction,
        user_id: 1,
      });
      setSubject(result.subject);
      setBody(result.body);
      setFitPoints(result.key_fit_points ?? []);
      setMessage(result.used_llm ? "已使用 LLM 生成套磁信草稿。" : "LLM 未可用，已使用本地模板生成草稿。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成草稿失败");
    } finally {
      setGenerating(false);
    }
  }

  async function onSaveDraft() {
    if (!mentorId) {
      setError("缺少 mentor_id 参数。");
      return;
    }
    if (!subject.trim() || !body.trim()) {
      setError("请先生成并完善主题与正文后再保存。");
      return;
    }

    setSaving(true);
    setError("");
    setMessage("");

    try {
      const result = await commitContactDraft({
        mentor_id: mentorId,
        event_date: eventDate,
        subject: subject.trim(),
        body: body.trim(),
        user_id: 1,
      });
      setMessage(`已保存到 Timeline 草稿（事件 #${result.id}）。`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存草稿失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h2 className="page-title">Contact 草稿确认</h2>
          <p className="page-desc">基于“我的资料 + 导师信息”生成套磁信草稿，确认后存入 Timeline（draft）。</p>
        </div>
        <div className="actions">
          <Link className="btn-secondary" href="/my-mentors">
            返回我的导师库
          </Link>
          <Link className="btn-secondary" href="/timeline">
            打开 Timeline
          </Link>
        </div>
      </header>

      {error ? <div className="status-pill status-failed">{error}</div> : null}
      {message ? <div className="status-pill status-success">{message}</div> : null}

      {!mentorId ? <div className="empty-box">缺少 mentor_id 参数，请从导师卡片上的 Contact 按钮进入。</div> : null}

      {mentorId ? (
        <section className="grid two contact-layout">
          <article className="card grid">
            <h3 className="section-title">导师信息</h3>
            {loadingMentor ? <p className="small">加载导师信息中...</p> : null}
            {!loadingMentor && mentor ? (
              <>
                <strong>{mentor.name}</strong>
                <div className="meta-row">
                  <span className="chip">{mentor.school}</span>
                  <span className="chip">{mentor.interested_field}</span>
                  {mentor.is_auto_enriched ? <span className="chip chip-enriched">Auto-enriched</span> : null}
                </div>
                <p className="small">{mentor.title}</p>
                <p className="small" style={{ whiteSpace: "pre-wrap" }}>
                  {mentor.high_level_summary?.trim() || mentor.research_direction || "暂无导师摘要"}
                </p>
                {(mentor.ai_keywords ?? []).length > 0 ? (
                  <div className="meta-row">
                    {mentor.ai_keywords.slice(0, 8).map((kw) => (
                      <span key={`${mentor.id}-${kw}`} className="chip">
                        {kw}
                      </span>
                    ))}
                  </div>
                ) : null}
              </>
            ) : null}
          </article>

          <form className="card grid" onSubmit={onGenerate}>
            <h3 className="section-title">生成参数</h3>

            <label className="field">
              <span className="field-label">语言</span>
              <select value={language} onChange={(e) => setLanguage(e.target.value as "auto" | "zh" | "en")}> 
                <option value="auto">自动（默认中文）</option>
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
            </label>

            <label className="field">
              <span className="field-label">附加要求（可选）</span>
              <textarea
                rows={4}
                value={extraInstruction}
                onChange={(e) => setExtraInstruction(e.target.value)}
                placeholder="例如：强调系统安全方向；语气简洁；希望询问组内博士生名额。"
              />
            </label>

            <label className="field">
              <span className="field-label">保存日期（Timeline）</span>
              <input type="date" value={eventDate} onChange={(e) => setEventDate(e.target.value)} />
            </label>

            <div className="actions">
              <button className="btn-primary" disabled={generating || !mentorId}>
                {generating ? "生成中..." : "生成草稿"}
              </button>
            </div>
          </form>
        </section>
      ) : null}

      {mentorId ? (
        <article className="card grid">
          <h3 className="section-title">草稿预览（可编辑后保存）</h3>

          {fitPoints.length > 0 ? (
            <div className="meta-row">
              {fitPoints.map((point, idx) => (
                <span key={`${idx}-${point}`} className="chip">
                  {point}
                </span>
              ))}
            </div>
          ) : null}

          <label className="field">
            <span className="field-label">邮件主题</span>
            <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="请先点击“生成草稿”" />
          </label>

          <label className="field">
            <span className="field-label">邮件正文</span>
            <textarea rows={14} value={body} onChange={(e) => setBody(e.target.value)} placeholder="草稿正文将显示在这里" />
          </label>

          <div className="actions">
            <button className="btn-primary" type="button" onClick={onSaveDraft} disabled={saving || !subject.trim() || !body.trim()}>
              {saving ? "保存中..." : "保存到 Timeline 草稿"}
            </button>
          </div>
        </article>
      ) : null}
    </section>
  );
}

export default function ContactDraftPage() {
  return (
    <Suspense fallback={<section className="page"><div className="empty-box">加载中...</div></section>}>
      <ContactDraftClient />
    </Suspense>
  );
}
