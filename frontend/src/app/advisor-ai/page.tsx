"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  askAdvisor,
  createAdvisorSession,
  deleteAdvisorSession,
  getAdvisorMemory,
  getAdvisorSession,
  listAdvisorSessions,
  updateAdvisorMemory,
} from "@/lib/api";
import type { AdvisorMemory, AdvisorSessionDetail, AdvisorSessionSummary } from "@/lib/types";

const PERSONALIZED_BOOST_STORAGE_KEY = "advisor_personalized_boost";

export default function AdvisorAiPage() {
  const [sessions, setSessions] = useState<AdvisorSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [sessionDetail, setSessionDetail] = useState<AdvisorSessionDetail | null>(null);

  const [memory, setMemory] = useState<AdvisorMemory | null>(null);
  const [memoryDraft, setMemoryDraft] = useState("");
  const [showMemoryPanel, setShowMemoryPanel] = useState(false);

  const [query, setQuery] = useState("");
  const [personalizedBoost, setPersonalizedBoost] = useState(false);

  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [retrievalHint, setRetrievalHint] = useState("");

  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingSessionDetail, setLoadingSessionDetail] = useState(false);
  const [asking, setAsking] = useState(false);
  const [savingMemory, setSavingMemory] = useState(false);
  const [deletingSessionId, setDeletingSessionId] = useState<number | null>(null);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const activeSessionTitle = useMemo(() => {
    const row = sessions.find((item) => item.id === activeSessionId);
    return row?.title ?? "未选择会话";
  }, [activeSessionId, sessions]);

  async function refreshSessions() {
    setLoadingSessions(true);
    try {
      const rows = await listAdvisorSessions(1, 100);
      setSessions(rows);
      return rows;
    } finally {
      setLoadingSessions(false);
    }
  }

  async function refreshMemory() {
    const row = await getAdvisorMemory(1);
    setMemory(row);
    setMemoryDraft(row.memory_text || "");
    return row;
  }

  async function openSession(sessionId: number) {
    setLoadingSessionDetail(true);
    setError("");
    try {
      const detail = await getAdvisorSession(sessionId, 1);
      setActiveSessionId(sessionId);
      setSessionDetail(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取会话失败");
    } finally {
      setLoadingSessionDetail(false);
    }
  }

  useEffect(() => {
    const saved = window.localStorage.getItem(PERSONALIZED_BOOST_STORAGE_KEY);
    setPersonalizedBoost(saved === "1");

    (async () => {
      try {
        const [rows] = await Promise.all([refreshSessions(), refreshMemory()]);
        if (rows.length > 0) {
          await openSession(rows[0].id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "初始化 AI 推荐失败");
      }
    })();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [sessionDetail]);

  function onTogglePersonalizedBoost(next: boolean) {
    setPersonalizedBoost(next);
    window.localStorage.setItem(PERSONALIZED_BOOST_STORAGE_KEY, next ? "1" : "0");
  }

  async function onCreateSession() {
    setError("");
    setInfo("");
    setRetrievalHint("");
    try {
      const row = await createAdvisorSession({ user_id: 1, title: "新会话" });
      await refreshSessions();
      await openSession(row.id);
      setInfo("已创建新会话。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建会话失败");
    }
  }

  async function onDeleteSession(sessionId: number) {
    const confirmed = window.confirm("确定删除这个会话吗？删除后聊天记录不可恢复。");
    if (!confirmed) {
      return;
    }

    setDeletingSessionId(sessionId);
    setError("");
    setInfo("");
    setRetrievalHint("");

    try {
      await deleteAdvisorSession(sessionId, 1);
      const rows = await refreshSessions();

      if (rows.length === 0) {
        setActiveSessionId(null);
        setSessionDetail(null);
      } else {
        const nextId = rows.some((item) => item.id === activeSessionId) ? (activeSessionId as number) : rows[0].id;
        await openSession(nextId);
      }

      setInfo("会话已删除。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除会话失败");
    } finally {
      setDeletingSessionId(null);
    }
  }

  async function onSaveMemory(event: FormEvent) {
    event.preventDefault();
    setSavingMemory(true);
    setError("");
    setInfo("");

    try {
      const updated = await updateAdvisorMemory({ user_id: 1, memory_text: memoryDraft });
      setMemory(updated);
      setMemoryDraft(updated.memory_text);
      setInfo("动态记忆已更新。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存动态记忆失败");
    } finally {
      setSavingMemory(false);
    }
  }

  async function onAsk(event: FormEvent) {
    event.preventDefault();
    const cleanQuery = query.trim();

    if (!cleanQuery) {
      setError("请输入问题或筛选需求。\n例如：偏好机器学习与系统方向，优先近两年发文活跃的导师。 ");
      return;
    }

    setAsking(true);
    setError("");
    setInfo("");
    setRetrievalHint("");

    try {
      const result = await askAdvisor({
        user_id: 1,
        session_id: activeSessionId ?? undefined,
        query: cleanQuery,
        top_k: 8,
        personalized_boost: personalizedBoost,
      });

      setQuery("");
      setMemory((prev) =>
        prev
          ? { ...prev, memory_text: result.memory_text, updated_at: new Date().toISOString() }
          : { user_id: 1, memory_text: result.memory_text, updated_at: new Date().toISOString() },
      );
      setMemoryDraft(result.memory_text);

      await refreshSessions();
      await openSession(result.session_id);

      const llmInfo = result.used_llm
        ? "已使用 LLM + RAG 生成推荐。"
        : "LLM 未配置，已使用本地检索推荐。可在设置里配置 API Key。";
      const personalizationInfo = result.used_personalization ? " 个性化增强：已开启。" : " 个性化增强：未开启。";
      setInfo(`${llmInfo}${personalizationInfo}`);

      const primary = result.retrieval_debug?.primary_query ?? "";
      const secondary = result.retrieval_debug?.secondary_query ?? "";
      if (secondary) {
        setRetrievalHint(`检索重写：${primary} -> ${secondary}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "提问失败");
    } finally {
      setAsking(false);
    }
  }

  return (
    <section className="page advisor-v2-page">
      <header className="page-header">
        <div>
          <h2 className="page-title">AI 导师推荐助手</h2>
          <p className="page-desc">左侧管理会话与记忆，右侧对话和候选导师推荐。</p>
        </div>
        <div className="meta-row">
          <span className="chip">RAG</span>
          <span className="chip">Session</span>
          <span className="chip">Dynamic Memory</span>
        </div>
      </header>

      <section className="advisor-v2-layout">
        <aside className="card advisor-v2-sidebar">
          <div className="advisor-v2-actions">
            <button className="btn-primary" type="button" onClick={onCreateSession}>
              新会话
            </button>
            <button className="btn-secondary" type="button" onClick={() => setShowMemoryPanel((prev) => !prev)}>
              {showMemoryPanel ? "收起记忆" : "展开记忆"}
            </button>
          </div>

          <label className="field advisor-boost-toggle">
            <span className="field-label">个性化推荐增强</span>
            <div className="actions">
              <button
                className={personalizedBoost ? "btn-primary" : "btn-secondary"}
                type="button"
                onClick={() => onTogglePersonalizedBoost(!personalizedBoost)}
              >
                {personalizedBoost ? "已开启" : "已关闭"}
              </button>
              <span className="small">会记住你的上次选择</span>
            </div>
          </label>

          {showMemoryPanel ? (
            <form className="advisor-v2-memory-panel" onSubmit={onSaveMemory}>
              <div className="advisor-v2-memory-head">
                <strong>动态记忆</strong>
                <span className="small">{memory ? new Date(memory.updated_at).toLocaleString("zh-CN") : "未初始化"}</span>
              </div>
              <textarea
                rows={6}
                value={memoryDraft}
                onChange={(e) => setMemoryDraft(e.target.value)}
                placeholder="例如：偏好机器学习/数据系统；优先有工业合作经验；不考虑纯理论方向。"
              />
              <button className="btn-secondary" disabled={savingMemory}>
                {savingMemory ? "保存中..." : "保存记忆"}
              </button>
            </form>
          ) : null}

          <div className="advisor-v2-session-head">
            <h3 className="section-title">会话</h3>
            <span className="chip">{sessions.length}</span>
          </div>

          <div className="advisor-v2-session-list">
            {loadingSessions ? <div className="small">会话加载中...</div> : null}
            {!loadingSessions && sessions.length === 0 ? <div className="empty-box">还没有会话，点击“新会话”开始。</div> : null}

            {sessions.map((item) => (
              <article key={item.id} className={`advisor-v2-session-item${item.id === activeSessionId ? " active" : ""}`}>
                <button type="button" className="advisor-v2-session-open" onClick={() => openSession(item.id)}>
                  <strong>{item.title || `会话 #${item.id}`}</strong>
                  <span>
                    {item.message_count} 条消息 · {new Date(item.updated_at).toLocaleDateString("zh-CN")}
                  </span>
                </button>
                <button
                  type="button"
                  className="advisor-v2-session-delete btn-danger"
                  onClick={() => onDeleteSession(item.id)}
                  disabled={deletingSessionId === item.id}
                  aria-label={`删除会话 ${item.title || item.id}`}
                >
                  {deletingSessionId === item.id ? "删除中" : "删除"}
                </button>
              </article>
            ))}
          </div>
        </aside>

        <section className="card advisor-v2-chat">
          <div className="advisor-v2-chat-head">
            <div>
              <h3 className="section-title">聊天</h3>
              <p className="small">当前会话：{activeSessionTitle}</p>
            </div>
          </div>

          {info ? <div className="status-pill status-success">{info}</div> : null}
          {retrievalHint ? <div className="status-pill status-pending">{retrievalHint}</div> : null}
          {error ? <div className="status-pill status-failed">{error}</div> : null}

          <div className="advisor-v2-message-scroll">
            {loadingSessionDetail ? <p className="small">正在加载会话...</p> : null}

            {!loadingSessionDetail && !sessionDetail ? <div className="empty-box">先创建会话并发送你的第一个问题。</div> : null}

            {(sessionDetail?.messages ?? []).map((message) => (
              <section key={message.id} className={`advisor-message advisor-message-${message.role}`}>
                <div className="advisor-message-head">
                  <strong>{message.role === "user" ? "你" : "AI"}</strong>
                  <span>{new Date(message.created_at).toLocaleString("zh-CN")}</span>
                </div>
                <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{message.content}</p>

                {message.role === "assistant" && message.recommendations.length > 0 ? (
                  <div className="advisor-rec-grid">
                    {message.recommendations.map((rec) => (
                      <article key={`${message.id}-${rec.mentor_id}`} className="advisor-rec-card">
                        <div className="advisor-rec-head">
                          <strong>{rec.name}</strong>
                          <span className="chip">score {rec.match_score.toFixed(2)}</span>
                        </div>
                        <p className="small">{rec.school}</p>
                        <p className="small">{rec.title}</p>
                        <p className="small">{rec.reason}</p>
                        <div className="actions">
                          <Link className="btn-secondary" href={`/mentors/${rec.mentor_id}`}>
                            查看导师详情
                          </Link>
                          <Link className="btn-primary" href={`/contact-draft?mentor_id=${rec.mentor_id}`}>
                            Contact
                          </Link>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : null}
              </section>
            ))}
            <div ref={messagesEndRef} />
          </div>

          <form className="advisor-v2-composer" onSubmit={onAsk}>
            <label className="field" htmlFor="advisor-query">
              <span className="field-label">你的问题</span>
              <textarea
                id="advisor-query"
                rows={4}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="例如：我偏好 data-centric AI 和 NLP，目标是 2027 Fall PhD，请推荐 5 位导师并说明理由。"
              />
            </label>
            <div className="actions advisor-v2-composer-actions">
              <button className="btn-primary" disabled={asking}>
                {asking ? "分析中..." : "发送"}
              </button>
            </div>
          </form>
        </section>
      </section>
    </section>
  );
}
