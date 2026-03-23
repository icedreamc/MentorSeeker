"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { createTimeline, deleteTimeline, getTimelineDailyOverview, listMentors, listTimeline } from "@/lib/api";
import type { MentorList, MentorSummary, TimelineDailyOverview, TimelineEvent, TimelineList } from "@/lib/types";

type MentorGroup = {
  mentorId: number;
  mentorName: string;
  items: TimelineEvent[];
};

type CalendarCell = {
  isoDate: string;
  count: number;
  typeCounts: Record<string, number>;
  isOutsideRange: boolean;
  isToday: boolean;
};

const EVENT_TYPE_OPTIONS = [
  { value: "all", label: "全部事件" },
  { value: "emailed", label: "已发送邮件" },
  { value: "replied", label: "已回复" },
  { value: "interview", label: "面试" },
  { value: "offer", label: "Offer" },
  { value: "reject", label: "Reject" },
  { value: "note", label: "笔记" },
  { value: "draft", label: "草稿" },
] as const;

const OVERVIEW_DAYS_OPTIONS = [
  { value: 90, label: "近 90 天" },
  { value: 182, label: "近 6 个月" },
  { value: 365, label: "近 1 年" },
];

function parseDateKey(value: string): number {
  return new Date(`${value}T00:00:00`).getTime();
}

function toLocalIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(base: Date, days: number): Date {
  const next = new Date(base);
  next.setDate(next.getDate() + days);
  return next;
}

function startOfWeek(date: Date): Date {
  const normalized = new Date(date);
  normalized.setDate(normalized.getDate() - normalized.getDay());
  normalized.setHours(0, 0, 0, 0);
  return normalized;
}

function diffDays(start: Date, end: Date): number {
  const oneDay = 24 * 60 * 60 * 1000;
  return Math.floor((end.getTime() - start.getTime()) / oneDay);
}

function formatDateLabel(date: string): string {
  return date.replace(/-/g, "/");
}

function getEventTypeLabel(eventType: string): string {
  return EVENT_TYPE_OPTIONS.find((item) => item.value === eventType)?.label ?? eventType;
}

function getContributionLevel(count: number, maxCount: number): number {
  if (count <= 0 || maxCount <= 0) return 0;
  const ratio = count / maxCount;
  if (ratio < 0.25) return 1;
  if (ratio < 0.5) return 2;
  if (ratio < 0.8) return 3;
  return 4;
}

function normalizeText(value: string): string {
  return value.trim().toLowerCase();
}

function mentorLabel(mentor: MentorSummary): string {
  return `${mentor.name} (${mentor.school})`;
}

async function fetchAllMentors(): Promise<MentorList> {
  const merged: MentorSummary[] = [];
  let page = 1;
  const pageSize = 100;
  let total = 0;

  while (page <= 20) {
    const res = await listMentors(new URLSearchParams({ page: String(page), page_size: String(pageSize), user_id: "1" }));
    merged.push(...res.items);
    total = res.total;
    if (page * res.page_size >= res.total) {
      break;
    }
    page += 1;
  }

  return {
    items: merged,
    page: 1,
    page_size: Math.max(merged.length, pageSize),
    total,
  };
}

export default function TimelinePage() {
  const [timeline, setTimeline] = useState<TimelineList | null>(null);
  const [overview, setOverview] = useState<TimelineDailyOverview | null>(null);
  const [mentors, setMentors] = useState<MentorList | null>(null);

  const [loading, setLoading] = useState(false);
  const [loadingOverview, setLoadingOverview] = useState(false);
  const [error, setError] = useState("");

  const [mentorId, setMentorId] = useState<number>(0);
  const [mentorQuery, setMentorQuery] = useState("");
  const [showMentorSuggestions, setShowMentorSuggestions] = useState(false);

  const [eventType, setEventType] = useState("emailed");
  const [eventDate, setEventDate] = useState(() => toLocalIsoDate(new Date()));
  const [content, setContent] = useState("");

  const [page, setPage] = useState(1);
  const [pageSize] = useState(100);

  const [streamTypeFilter, setStreamTypeFilter] = useState("all");
  const [keyword, setKeyword] = useState("");
  const [overviewDays, setOverviewDays] = useState(182);
  const [hoverDate, setHoverDate] = useState(() => toLocalIsoDate(new Date()));
  const [activeEvent, setActiveEvent] = useState<TimelineEvent | null>(null);

  async function load(pageValue: number = page) {
    setLoading(true);
    setError("");
    try {
      const [timelineRes, mentorRes] = await Promise.all([
        listTimeline(new URLSearchParams({ page: String(pageValue), page_size: String(pageSize), user_id: "1" })),
        fetchAllMentors(),
      ]);
      setTimeline(timelineRes);
      setMentors(mentorRes);

      if (!mentorId && mentorRes.items.length > 0) {
        const firstMentor = mentorRes.items[0];
        setMentorId(firstMentor.id);
        setMentorQuery(mentorLabel(firstMentor));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载 Timeline 失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadOverview() {
    setLoadingOverview(true);
    setError("");
    try {
      const params = new URLSearchParams({ user_id: "1", days: String(overviewDays) });
      if (streamTypeFilter !== "all") {
        params.set("event_type", streamTypeFilter);
      }
      const res = await getTimelineDailyOverview(params);
      setOverview(res);
      setHoverDate(toLocalIsoDate(new Date()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载总览失败");
    } finally {
      setLoadingOverview(false);
    }
  }

  useEffect(() => {
    load(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  useEffect(() => {
    loadOverview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overviewDays, streamTypeFilter]);

  const selectedMentor = useMemo(() => {
    if (!mentorId) return null;
    return (mentors?.items ?? []).find((item) => item.id === mentorId) ?? null;
  }, [mentorId, mentors?.items]);

  const mentorSuggestions = useMemo(() => {
    const all = mentors?.items ?? [];
    const query = normalizeText(mentorQuery);
    const candidates = !query
      ? all
      : all.filter((item) => {
          const haystack = `${item.name} ${item.school} ${item.title} ${item.research_direction}`.toLowerCase();
          return haystack.includes(query);
        });
    return candidates.slice(0, 12);
  }, [mentorQuery, mentors?.items]);

  const sortedEvents = useMemo(() => {
    const items = [...(timeline?.items ?? [])];
    items.sort((a, b) => {
      const byDate = parseDateKey(b.event_date) - parseDateKey(a.event_date);
      return byDate !== 0 ? byDate : b.id - a.id;
    });
    return items;
  }, [timeline?.items]);

  const filteredEvents = useMemo(() => {
    const keywordLower = keyword.trim().toLowerCase();
    return sortedEvents.filter((item) => {
      if (streamTypeFilter !== "all" && item.event_type !== streamTypeFilter) {
        return false;
      }
      if (!keywordLower) {
        return true;
      }
      const haystack = `${item.mentor_name} ${item.event_type} ${item.content}`.toLowerCase();
      return haystack.includes(keywordLower);
    });
  }, [keyword, sortedEvents, streamTypeFilter]);

  const mentorGroups = useMemo<MentorGroup[]>(() => {
    const grouped = new Map<number, MentorGroup>();
    for (const event of filteredEvents) {
      if (!grouped.has(event.mentor_id)) {
        grouped.set(event.mentor_id, {
          mentorId: event.mentor_id,
          mentorName: event.mentor_name,
          items: [],
        });
      }
      grouped.get(event.mentor_id)?.items.push(event);
    }

    return [...grouped.values()].sort((a, b) => {
      const aDate = a.items[0]?.event_date ?? "1970-01-01";
      const bDate = b.items[0]?.event_date ?? "1970-01-01";
      return parseDateKey(bDate) - parseDateKey(aDate);
    });
  }, [filteredEvents]);

  const overviewTotalEvents = useMemo(() => (overview?.items ?? []).reduce((sum, item) => sum + item.count, 0), [overview?.items]);
  const overviewActiveDays = useMemo(() => (overview?.items ?? []).filter((item) => item.count > 0).length, [overview?.items]);
  const activeMentorCount = useMemo(() => new Set(filteredEvents.map((item) => item.mentor_id)).size, [filteredEvents]);
  const latestEventDate = filteredEvents[0]?.event_date ?? "-";

  const staleMentorCount = useMemo(() => {
    const threshold = Date.now() - 14 * 24 * 60 * 60 * 1000;
    let staleCount = 0;
    for (const group of mentorGroups) {
      const latest = group.items[0];
      if (latest && parseDateKey(latest.event_date) < threshold) {
        staleCount += 1;
      }
    }
    return staleCount;
  }, [mentorGroups]);

  const calendarData = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const todayIso = toLocalIsoDate(today);

    const startDate = addDays(today, -(overviewDays - 1));
    const gridStart = startOfWeek(startDate);

    let gridDays = diffDays(gridStart, today) + 1;
    if (gridDays % 7 !== 0) {
      gridDays += 7 - (gridDays % 7);
    }

    const countByDate = new Map<string, { count: number; typeCounts: Record<string, number> }>();
    for (const item of overview?.items ?? []) {
      countByDate.set(item.event_date, { count: item.count, typeCounts: item.type_counts ?? {} });
    }

    let maxCount = 0;
    for (const row of countByDate.values()) {
      maxCount = Math.max(maxCount, row.count);
    }

    const cells: CalendarCell[] = [];
    for (let i = 0; i < gridDays; i += 1) {
      const current = addDays(gridStart, i);
      const isoDate = toLocalIsoDate(current);
      const isOutsideRange = current.getTime() < startDate.getTime() || current.getTime() > today.getTime();
      const point = countByDate.get(isoDate);

      cells.push({
        isoDate,
        count: isOutsideRange ? 0 : (point?.count ?? 0),
        typeCounts: isOutsideRange ? {} : (point?.typeCounts ?? {}),
        isOutsideRange,
        isToday: isoDate === todayIso,
      });
    }

    const weeks: CalendarCell[][] = [];
    for (let i = 0; i < cells.length; i += 7) {
      weeks.push(cells.slice(i, i + 7));
    }

    const monthLabels: Array<{ label: string; index: number }> = [];
    let lastMonth = "";
    weeks.forEach((week, index) => {
      const anchor = week.find((cell) => !cell.isOutsideRange);
      if (!anchor) return;
      const month = anchor.isoDate.slice(5, 7);
      if (month !== lastMonth) {
        monthLabels.push({ label: `${Number(month)}月`, index });
        lastMonth = month;
      }
    });

    return { weeks, monthLabels, maxCount, todayIso };
  }, [overview?.items, overviewDays]);

  const calendarCellMap = useMemo(() => {
    const map = new Map<string, CalendarCell>();
    for (const week of calendarData.weeks) {
      for (const cell of week) {
        map.set(cell.isoDate, cell);
      }
    }
    return map;
  }, [calendarData.weeks]);

  const hoverCell = useMemo(() => calendarCellMap.get(hoverDate) ?? null, [calendarCellMap, hoverDate]);

  const hoverTypeRows = useMemo(() => {
    if (!hoverCell) return [] as Array<[string, number]>;
    return Object.entries(hoverCell.typeCounts).sort((a, b) => b[1] - a[1]);
  }, [hoverCell]);

  function selectMentor(mentor: MentorSummary) {
    setMentorId(mentor.id);
    setMentorQuery(mentorLabel(mentor));
    setShowMentorSuggestions(false);
  }

  function onMentorInputChange(value: string) {
    setMentorQuery(value);
    setShowMentorSuggestions(true);

    const exact = (mentors?.items ?? []).find((item) => normalizeText(mentorLabel(item)) === normalizeText(value));
    if (exact) {
      setMentorId(exact.id);
      return;
    }

    setMentorId(0);
  }

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    if (!mentorId) {
      setError("请选择导师后再创建事件。");
      return;
    }

    try {
      setError("");
      await createTimeline({ mentor_id: mentorId, event_type: eventType, event_date: eventDate, content });
      setContent("");
      await Promise.all([load(page), loadOverview()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建事件失败");
    }
  }

  async function onDelete(eventId: number) {
    try {
      setError("");
      await deleteTimeline(eventId);
      setActiveEvent((prev) => (prev?.id === eventId ? null : prev));
      await Promise.all([load(page), loadOverview()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "\u5220\u9664\u4e8b\u4ef6\u5931\u8d25");
    }
  }

  async function onDeleteFromModal(eventId: number) {
    await onDelete(eventId);
  }

  const canPrev = page > 1;
  const canNext = !!timeline && page * timeline.page_size < timeline.total;
  const totalPages = timeline ? Math.max(1, Math.ceil(timeline.total / timeline.page_size)) : 1;

  return (
    <section className="page timeline-page">
      <header className="page-header">
        <div>
          <h2 className="page-title">Timeline</h2>
          <p className="page-desc">统一记录套磁进度，支持按导师分组查看与日历总览。</p>
        </div>
      </header>

      <article className="card timeline-overview-card">
        <div className="timeline-overview-head">
          <h3 className="section-title">Overview Timeline（日历总览）</h3>
          <div className="actions">
            <label className="field" style={{ minWidth: 140 }}>
              <span className="field-label">时间范围</span>
              <select value={overviewDays} onChange={(e) => setOverviewDays(Number(e.target.value))}>
                {OVERVIEW_DAYS_OPTIONS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>

        <p className="small">总览按“事件类型筛选”实时更新，热力图精确到天。{loadingOverview ? " 加载中..." : ""}</p>

        <div className="timeline-kpi-grid">
          <div className="timeline-kpi-card">
            <span className="timeline-kpi-label">总事件数（范围内）</span>
            <strong className="timeline-kpi-value">{overviewTotalEvents}</strong>
          </div>
          <div className="timeline-kpi-card">
            <span className="timeline-kpi-label">活跃天数</span>
            <strong className="timeline-kpi-value">{overviewActiveDays}</strong>
          </div>
          <div className="timeline-kpi-card">
            <span className="timeline-kpi-label">涉及导师数（当前筛选）</span>
            <strong className="timeline-kpi-value">{activeMentorCount}</strong>
          </div>
          <div className="timeline-kpi-card">
            <span className="timeline-kpi-label">14 天未跟进导师数</span>
            <strong className="timeline-kpi-value">{staleMentorCount}</strong>
          </div>
        </div>

        <div className="calendar-shell">
          <div className="calendar-month-row" style={{ gridTemplateColumns: `repeat(${calendarData.weeks.length}, 12px)` }}>
            {calendarData.monthLabels.map((label) => (
              <span key={`${label.label}-${label.index}`} style={{ gridColumnStart: label.index + 1 }}>
                {label.label}
              </span>
            ))}
          </div>

          <div className="calendar-grid-wrap">
            <div className="calendar-weekday-col" aria-hidden="true">
              <span>日</span>
              <span />
              <span>二</span>
              <span />
              <span>四</span>
              <span />
              <span>六</span>
            </div>

            <div className="calendar-weeks-grid" style={{ gridTemplateColumns: `repeat(${calendarData.weeks.length}, 12px)` }}>
              {calendarData.weeks.map((week, weekIndex) => (
                <div key={`week-${weekIndex}`} className="calendar-week-col">
                  {week.map((cell) => {
                    const level = getContributionLevel(cell.count, calendarData.maxCount);
                    const className = `calendar-cell level-${level}${cell.isOutsideRange ? " future" : ""}${cell.isToday ? " today" : ""}`;
                    const tooltipDetails = Object.entries(cell.typeCounts)
                      .map(([type, count]) => `${getEventTypeLabel(type)}: ${count}`)
                      .join(" | ");
                    const title = `${formatDateLabel(cell.isoDate)} · ${cell.count} 条事件${tooltipDetails ? ` (${tooltipDetails})` : ""}`;

                    return (
                      <button
                        key={cell.isoDate}
                        type="button"
                        className={`calendar-cell-btn ${className}`}
                        title={title}
                        aria-label={title}
                        disabled={cell.isOutsideRange}
                        onMouseEnter={() => setHoverDate(cell.isoDate)}
                        onFocus={() => setHoverDate(cell.isoDate)}
                        onClick={() => setHoverDate(cell.isoDate)}
                      />
                    );
                  })}
                </div>
              ))}
            </div>
          </div>

          <div className="calendar-legend">
            <span>少</span>
            <span className="calendar-cell level-0" />
            <span className="calendar-cell level-1" />
            <span className="calendar-cell level-2" />
            <span className="calendar-cell level-3" />
            <span className="calendar-cell level-4" />
            <span>多</span>
          </div>

          <div className="calendar-hover-panel">
            <div className="calendar-hover-head">
              <strong>{formatDateLabel(hoverCell?.isoDate ?? calendarData.todayIso)}</strong>
              <span>{hoverCell?.count ?? 0} 条事件</span>
            </div>

            {hoverTypeRows.length === 0 ? <p className="small">该日暂无事件明细。</p> : null}

            {hoverTypeRows.length > 0 ? (
              <div className="calendar-hover-type-grid">
                {hoverTypeRows.map(([eventTypeKey, count]) => (
                  <div key={`${eventTypeKey}-${count}`} className="chip calendar-hover-chip">
                    <span>{getEventTypeLabel(eventTypeKey)}</span>
                    <strong>{count}</strong>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </article>

      <section className="timeline-workspace">
        <form className="card grid timeline-form-card" onSubmit={onCreate}>
          <h3 className="section-title">新增事件</h3>

          <label className="field mentor-combobox">
            <span className="field-label">导师</span>
            <input
              value={mentorQuery}
              onChange={(e) => onMentorInputChange(e.target.value)}
              onFocus={() => setShowMentorSuggestions(true)}
              onBlur={() => {
                window.setTimeout(() => setShowMentorSuggestions(false), 120);
              }}
              placeholder="输入导师姓名/学校，自动联想匹配"
            />

            {showMentorSuggestions ? (
              <div className="mentor-suggestion-list">
                {mentorSuggestions.length === 0 ? <div className="mentor-suggestion empty">没有匹配导师</div> : null}
                {mentorSuggestions.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="mentor-suggestion"
                    onMouseDown={(event) => {
                      event.preventDefault();
                      selectMentor(item);
                    }}
                  >
                    <strong>{item.name}</strong>
                    <span>{item.school}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </label>

          <p className="small mentor-selected-tip">{selectedMentor ? `已选择：${mentorLabel(selectedMentor)}` : "请选择导师"}</p>

          <label className="field">
            <span className="field-label">事件类型</span>
            <select value={eventType} onChange={(e) => setEventType(e.target.value)}>
              {EVENT_TYPE_OPTIONS.filter((item) => item.value !== "all").map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span className="field-label">日期</span>
            <input type="date" value={eventDate} onChange={(e) => setEventDate(e.target.value)} />
          </label>

          <label className="field">
            <span className="field-label">内容</span>
            <textarea rows={5} value={content} onChange={(e) => setContent(e.target.value)} />
          </label>

          <div className="actions">
            <button className="btn-primary">保存事件</button>
          </div>
        </form>

        <article className="card timeline-stream-card">
          <div className="timeline-stream-head">
            <h3 className="section-title">事件流（按导师分组）</h3>
            <p className="small">最新事件日期：{latestEventDate === "-" ? "-" : formatDateLabel(latestEventDate)}</p>
          </div>

          <div className="timeline-filter-row timeline-filter-row-compact">
            <label className="field">
              <span className="field-label">事件类型</span>
              <select value={streamTypeFilter} onChange={(e) => setStreamTypeFilter(e.target.value)}>
                {EVENT_TYPE_OPTIONS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span className="field-label">关键词</span>
              <input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="导师名 / 事件类型 / 内容" />
            </label>
          </div>

          <div className="timeline-scroll-area">
            {!loading && mentorGroups.length === 0 ? <div className="empty-box">当前筛选下没有 Timeline 记录。</div> : null}

            {mentorGroups.map((group) => (
              <section key={group.mentorId} className="timeline-group">
                <header className="timeline-group-head">
                  <strong>{group.mentorName}</strong>
                  <div className="meta-row">
                    <span className="chip">{group.items.length} 条事件</span>
                    <span className="chip">最近：{formatDateLabel(group.items[0].event_date)}</span>
                  </div>
                </header>

                <div className="timeline-list">
                  {group.items.map((item) => (
                    <article
                      key={item.id}
                      className="timeline-item card soft timeline-item-clickable"
                      role="button"
                      tabIndex={0}
                      onClick={() => setActiveEvent(item)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setActiveEvent(item);
                        }
                      }}
                    >
                      <strong>
                        {formatDateLabel(item.event_date)} - {getEventTypeLabel(item.event_type)}
                      </strong>
                      <p className="small">{item.content || "\u65e0\u8865\u5145\u5185\u5bb9"}</p>
                      <div className="actions">
                        <button
                          className="btn-danger"
                          onClick={(event) => {
                            event.stopPropagation();
                            void onDelete(item.id);
                          }}
                        >
                          {"\u5220\u9664"}
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </div>

          <div className="actions timeline-pager">
            <button className="btn-secondary" disabled={!canPrev} onClick={() => setPage((prev) => prev - 1)}>
              上一页
            </button>
            <span className="small">
              第 {page} / {totalPages} 页（每页 {pageSize} 条）
            </span>
            <button className="btn-secondary" disabled={!canNext} onClick={() => setPage((prev) => prev + 1)}>
              下一页
            </button>
          </div>
        </article>
      </section>

      {activeEvent ? (
        <div className="timeline-event-modal-backdrop" onClick={() => setActiveEvent(null)}>
          <article className="timeline-event-modal card" onClick={(event) => event.stopPropagation()}>
            <header className="timeline-event-modal-head">
              <div>
                <h3 className="section-title">{activeEvent.mentor_name}</h3>
                <p className="small">
                  {formatDateLabel(activeEvent.event_date)} - {getEventTypeLabel(activeEvent.event_type)}
                </p>
              </div>
              <button className="btn-secondary" type="button" onClick={() => setActiveEvent(null)}>
                {"\u5173\u95ed"}
              </button>
            </header>

            <div className="timeline-event-modal-content">{activeEvent.content || "\u65e0\u8865\u5145\u5185\u5bb9"}</div>

            <div className="actions" style={{ justifyContent: "space-between" }}>
              <span className="chip">{"\u4e8b\u4ef6 ID: "}{activeEvent.id}</span>
              <button
                className="btn-danger"
                type="button"
                onClick={() => {
                  void onDeleteFromModal(activeEvent.id);
                }}
              >
                {"\u5220\u9664\u8be5\u4e8b\u4ef6"}
              </button>
            </div>
          </article>
        </div>
      ) : null}

      {error ? <div className="status-pill status-failed">{error}</div> : null}
    </section>
  );
}
