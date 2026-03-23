"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { cancelJob, createJob, getJob, listJobs, runJob } from "@/lib/api";
import type { DiscoveryJob } from "@/lib/types";

const STATUS_TEXT: Record<string, string> = {
  pending: "排队中",
  running: "执行中",
  cancelling: "取消中",
  success: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const DISCOVERY_LAST_JOB_KEY = "mentorseeker:discover:last_job_id";

function parsePositiveInt(value: string): number | null {
  const n = Number.parseInt(value, 10);
  if (!Number.isFinite(n) || n <= 0) {
    return null;
  }
  return n;
}

function loadLastJobId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(DISCOVERY_LAST_JOB_KEY);
  return raw?.trim() || null;
}

function saveLastJobId(jobId: string | null) {
  if (typeof window === "undefined") {
    return;
  }
  if (!jobId) {
    window.localStorage.removeItem(DISCOVERY_LAST_JOB_KEY);
    return;
  }
  window.localStorage.setItem(DISCOVERY_LAST_JOB_KEY, jobId);
}

function isJobNotFoundError(err: unknown): boolean {
  if (!(err instanceof Error)) {
    return false;
  }
  return err.message.includes("Job not found") || err.message.includes("404");
}

export default function DiscoverPage() {
  const [school, setSchool] = useState("");
  const [interestedField, setInterestedField] = useState("");
  const [maxStepsInput, setMaxStepsInput] = useState("");
  const [targetMentorsInput, setTargetMentorsInput] = useState("");
  const [enrichLimitInput, setEnrichLimitInput] = useState("");

  const [job, setJob] = useState<DiscoveryJob | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const [restoring, setRestoring] = useState(true);

  const isCancellationRequested = useMemo(() => {
    if (!job) {
      return false;
    }
    if (job.status === "cancelling") {
      return true;
    }
    return job.status === "running" && job.progress_message.toLowerCase().includes("cancellation requested");
  }, [job]);

  const isRunning = useMemo(() => {
    if (!job) {
      return false;
    }
    if (job.status === "pending") {
      return true;
    }
    if (job.status === "running" && !isCancellationRequested) {
      return true;
    }
    return false;
  }, [job, isCancellationRequested]);

  const shouldPoll = useMemo(() => {
    if (!job) {
      return false;
    }
    return job.status === "pending" || job.status === "running" || job.status === "cancelling";
  }, [job]);

  useEffect(() => {
    let cancelled = false;

    async function restoreJobState() {
      setRestoring(true);
      try {
        let recovered: DiscoveryJob | null = null;

        const rememberedId = loadLastJobId();
        if (rememberedId) {
          try {
            recovered = await getJob(rememberedId);
          } catch (err) {
            if (isJobNotFoundError(err)) {
              saveLastJobId(null);
            }
          }
        }

        if (!recovered) {
          const recent = await listJobs(1);
          recovered = recent[0] ?? null;
          saveLastJobId(recovered?.id ?? null);
        }

        if (!cancelled) {
          setJob(recovered);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "恢复最近任务失败");
        }
      } finally {
        if (!cancelled) {
          setRestoring(false);
        }
      }
    }

    void restoreJobState();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    saveLastJobId(job?.id ?? null);
  }, [job?.id]);

  useEffect(() => {
    if (!job || !shouldPoll) {
      return;
    }

    const interval = isCancellationRequested ? 5000 : 2500;

    const id = setInterval(async () => {
      try {
        const latest = await getJob(job.id);
        setJob(latest);
      } catch (err) {
        if (isJobNotFoundError(err)) {
          saveLastJobId(null);
          setJob(null);
        }
        setError(err instanceof Error ? err.message : "轮询任务失败");
      }
    }, interval);

    return () => clearInterval(id);
  }, [job, shouldPoll, isCancellationRequested]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");

    const maxSteps = parsePositiveInt(maxStepsInput);
    const targetMentorCount = parsePositiveInt(targetMentorsInput);
    const enrichLimit = parsePositiveInt(enrichLimitInput);

    if (!school.trim() || !interestedField.trim() || maxSteps === null || targetMentorCount === null || enrichLimit === null) {
      setError("请完整填写学校、研究方向和三个正整数参数。\n示例：max_steps=10，target=40，enrich=5");
      setLoading(false);
      return;
    }

    try {
      const created = await createJob({
        school: school.trim(),
        interested_field: interestedField.trim(),
        max_steps: maxSteps,
        target_mentor_count: targetMentorCount,
        enrich_limit: enrichLimit,
        run_immediately: false,
      });
      const started = await runJob(created.id);
      setJob(started);
      saveLastJobId(started.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建任务失败");
    } finally {
      setLoading(false);
    }
  }

  async function onCancel() {
    if (!job || isCancellationRequested) {
      return;
    }

    setCanceling(true);
    setError("");
    try {
      const cancelled = await cancelJob(job.id);
      setJob(cancelled);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取消任务失败");
    } finally {
      setCanceling(false);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h2 className="page-title">探索导师</h2>
          <p className="page-desc">创建抓取任务并追踪执行状态，产出 enriched 导师数据。</p>
        </div>
        <div className="meta-row">
          <span className="chip">AI Discovery</span>
          <span className="chip">OpenAlex Enrichment</span>
          <span className="chip">Structured Output</span>
        </div>
      </header>

      <section className="grid two">
        <form className="card grid" onSubmit={onSubmit}>
          <h3 className="section-title">任务配置</h3>

          <label className="field">
            <span className="field-label">学校</span>
            <input value={school} onChange={(e) => setSchool(e.target.value)} placeholder="例如：WHU" required />
          </label>

          <label className="field">
            <span className="field-label">Interested Field</span>
            <input
              value={interestedField}
              onChange={(e) => setInterestedField(e.target.value)}
              placeholder="例如：AI security"
              required
            />
          </label>

          <div className="grid two">
            <label className="field">
              <span className="field-label">最大抓取步数</span>
              <input
                type="number"
                min={1}
                value={maxStepsInput}
                onChange={(e) => setMaxStepsInput(e.target.value)}
                placeholder="例如：10"
                required
              />
            </label>
            <label className="field">
              <span className="field-label">目标导师数</span>
              <input
                type="number"
                min={1}
                value={targetMentorsInput}
                onChange={(e) => setTargetMentorsInput(e.target.value)}
                placeholder="例如：40"
                required
              />
            </label>
          </div>

          <label className="field">
            <span className="field-label">Enrich 数量</span>
            <input
              type="number"
              min={1}
              value={enrichLimitInput}
              onChange={(e) => setEnrichLimitInput(e.target.value)}
              placeholder="例如：5"
              required
            />
          </label>

          <div className="actions">
            <button className="btn-primary" disabled={loading || isRunning}>
              {loading
                ? "提交中..."
                : isRunning
                  ? "任务执行中"
                  : isCancellationRequested
                    ? "取消中，可新建任务"
                    : "创建并执行任务"}
            </button>
          </div>
        </form>

        <article className="card grid">
          <h3 className="section-title">任务状态</h3>
          {restoring ? <div className="small">正在恢复最近任务...</div> : null}
          {!restoring && !job ? <div className="empty-box">还没有任务，提交左侧表单即可开始。</div> : null}

          {job ? (
            <>
              <div className={`status-pill status-${job.status}`}>{STATUS_TEXT[job.status] ?? job.status}</div>
              <p className="small">Job ID: {job.id}</p>
              <p className="small">进度：{job.progress_message || "-"}</p>
              <p className="small">新增导师：{job.mentor_count}</p>
              {job.raw_output_file ? <p className="small">Raw：{job.raw_output_file}</p> : null}
              {job.enriched_output_file ? <p className="small">Enriched：{job.enriched_output_file}</p> : null}
              {job.error_message ? <pre className="code-block">{job.error_message}</pre> : null}

              {job.status === "running" || job.status === "cancelling" ? (
                <div className="actions">
                  <button type="button" className="btn-danger" onClick={onCancel} disabled={canceling || isCancellationRequested}>
                    {isCancellationRequested ? "已请求中止" : canceling ? "中止中..." : "中止任务"}
                  </button>
                </div>
              ) : null}
            </>
          ) : null}

          {error ? <div className="status-pill status-failed">{error}</div> : null}
        </article>
      </section>
    </section>
  );
}
