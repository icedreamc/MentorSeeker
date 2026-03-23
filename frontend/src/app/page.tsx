import Link from "next/link";

export default function HomePage() {
  return (
    <section className="page">
      <article className="card hero">
        <h1>把导师信息收集变成一条可复用流水线</h1>
        <p>
          输入学校和方向，自动跑抓取与 enrichment；结果进入导师库，再通过收藏和 timeline 管理你的套磁节奏。
        </p>

        <div className="meta-row">
          <span className="chip" style={{ color: "#fff", background: "rgba(255,255,255,0.18)", borderColor: "rgba(255,255,255,0.35)" }}>
            Discover
          </span>
          <span className="chip" style={{ color: "#fff", background: "rgba(255,255,255,0.18)", borderColor: "rgba(255,255,255,0.35)" }}>
            Mentor Library
          </span>
          <span className="chip" style={{ color: "#fff", background: "rgba(255,255,255,0.18)", borderColor: "rgba(255,255,255,0.35)" }}>
            Timeline
          </span>
          <span className="chip" style={{ color: "#fff", background: "rgba(255,255,255,0.18)", borderColor: "rgba(255,255,255,0.35)" }}>
            AI Advisor
          </span>
        </div>

        <div className="quick-grid">
          <Link className="quick-card" href="/discover">
            <strong>开始探索</strong>
            <p className="small" style={{ color: "rgba(255,255,255,0.85)", marginTop: 6 }}>
              创建任务、查看抓取进度与输出文件
            </p>
          </Link>
          <Link className="quick-card" href="/mentors">
            <strong>浏览导师库</strong>
            <p className="small" style={{ color: "rgba(255,255,255,0.85)", marginTop: 6 }}>
              检索导师、查看详情、收藏并补充个人判断
            </p>
          </Link>
          <Link className="quick-card" href="/advisor-ai">
            <strong>AI 推荐助手</strong>
            <p className="small" style={{ color: "rgba(255,255,255,0.85)", marginTop: 6 }}>
              基于 RAG 给出导师推荐，沉淀会话与偏好记忆
            </p>
          </Link>
        </div>
      </article>

      <section className="grid three">
        <article className="card soft">
          <h3 className="section-title">1. Discover</h3>
          <p className="small">触发抓取任务，自动执行 discovery + enrichment。</p>
        </article>
        <article className="card soft">
          <h3 className="section-title">2. My Mentors</h3>
          <p className="small">收藏目标导师并维护人工备注，沉淀可行动名单。</p>
        </article>
        <article className="card soft">
          <h3 className="section-title">3. Timeline</h3>
          <p className="small">记录发信、回复、面试、offer/reject，避免错过窗口期。</p>
        </article>
      </section>
    </section>
  );
}
