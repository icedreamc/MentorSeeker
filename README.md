# MentorSeeker

MentorSeeker 是一个本地优先的导师检索与套磁管理工作台，面向准备申请研究生、博士或科研机会的用户。

它希望帮你把这条常见但混乱的路径串起来：

**“我只有一个模糊方向” -> “我找到一批潜在导师” -> “我完成筛选与跟进” -> “我有 AI 辅助推荐和套磁草稿”**

## ✨ 为什么做 MentorSeeker

现实中的找导师流程通常是碎片化的：

- 导师信息散落在学校官网、学院页面、个人主页和论文页面
- 收藏名单常常存在表格、文档、浏览器书签甚至聊天记录里
- 套磁草稿和联系记录分散，很容易漏跟进
- 通用 AI 推荐工具不知道你的真实偏好是如何逐步形成的

MentorSeeker 想把这些环节收拢到一个本地工作空间里，让你可以在同一个系统中：

1. 探索导师
2. 丰富导师信息
3. 管理自己的导师库
4. 记录 Timeline
5. 询问 AI 推荐与匹配建议
6. 生成联系草稿并沉淀到工作流中

## 🚀 项目亮点

- 🏠 `Local-first` 设计：你的 API 配置、个人资料、Cookie、记忆与推荐上下文默认都保留在本机
- 🔄 端到端工作流：从导师发现、信息 enrich、收藏管理，到 Timeline 与 AI 推荐一体化完成
- 🧠 个性化 AI 推荐：不仅看查询词，也结合动态记忆、用户资料和导师库信号
- 🗂️ Timeline 不只是记录板：它是你真正的沟通工作区，支持草稿、事件流、细节查看
- ✍️ Contact 草稿能力：结合你的背景与导师信息，生成更具体的套磁信草稿
- 👤 保留人工主导权：支持手动新增、手动修订、批量操作、手动删除，而不是“全自动黑箱”

## 🧩 核心功能

### 1. 探索导师

- 按学校与研究方向创建探索任务
- 在界面中查看任务状态与执行进度
- 将原始结果与 enrich 后结果保存到本地系统
- 当输入错误时，可以中止长任务并重新发起

### 2. 管理导师库

- 浏览系统中已收集的导师
- 支持大小写不敏感、部分匹配的搜索
- 收藏导师到“我的导师库”
- 手动新增导师，或从库中彻底删除导师
- 对选中的导师进行批量 enrich
- 查看关键词、高层总结与详细资料

### 3. 管理 Timeline

- 按日期记录联系事件
- 按导师分组查看事件流
- 将草稿也纳入同一套工作流中
- 点开事件后查看更完整的详细内容，而不是只看压缩卡片

### 4. AI 推荐工作区

- 类似聊天式的推荐界面
- 支持 session 历史记录
- 支持动态偏好记忆
- 支持“个性化推荐增强”
- 推荐结果可以结合你的资料与已有导师库，而不是空泛回答

### 5. Contact 草稿工作流

- 为某位导师生成定制化联系草稿
- 草稿会结合你的资料文本与导师信息
- 支持生成后人工确认与编辑
- 保存后可作为 `draft` 事件写入 Timeline

## 🛠️ 技术栈

- Backend: FastAPI, SQLAlchemy, SQLite
- Frontend: Next.js, TypeScript
- AI 接入: OpenAI-compatible Embedding / LLM API
- 数据存储: 本地数据库 + 本地 `.env` 配置 + 本地生成 JSON 数据

## 📁 项目结构

```text
MentorSeeker/
|-- backend/                 # FastAPI 后端
|-- frontend/                # Next.js 前端
|-- scripts/                 # setup / start / stop / pipeline 脚本
|-- docs/                    # 归档文档与说明
|-- data/                    # 抓取与 enrich 输出
|-- 01-Setup-MentorSeeker.bat
|-- 02-Start-MentorSeeker.bat
|-- .gitignore
`-- README.md
```

## ⚡ 快速开始

### 推荐方式

在 Windows 上：

1. 运行 `01-Setup-MentorSeeker.bat`
2. 运行 `02-Start-MentorSeeker.bat`
3. 打开 [http://localhost:3000](http://localhost:3000)

### 环境要求

在手动启动前，请先确保本机已安装：

- Python 3.10+
- Node.js 20+
- npm

同时需要先完成依赖安装：

Backend:

python -m venv backend/venv
.\backend\venv\Scripts\python.exe -m pip install -r backend/requirements.txt

Frontend:

cd frontend
npm install

### 手动开发启动

Backend:

```powershell
.\backend\venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```powershell
cd frontend
$env:NEXT_PUBLIC_API_BASE="http://localhost:8000"
npm run dev
```

### 网络环境说明

- 本项目在导师信息丰富阶段会使用 OpenAlex 与 Google Scholar 等公开学术资源，以补充导师的论文、研究方向与相关背景信息。
- 为了尽量减少对目标服务的压力，我们在抓取与信息丰富过程中采取了较为保守的请求策略，不进行高并发访问。
- 因此，在批量处理较多导师时，整体速度可能会比较慢，这是有意为之的设计取向。
- 部分外部站点可能会因为访问频率、网络环境或会话状态而限制请求；如果你在大量使用时发现获取效果下降，可以尝试更新本地配置中的 cookie 后再继续使用。
- 我们也建议用户始终以克制、审慎的方式使用本项目，避免对外部学术服务造成不必要的负担。

## ⚙️ 配置说明

后端配置位于 `backend/.env`。

常见字段包括：

- `DATABASE_URL`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `PROVIDER_EMAIL`
- `BROWSER_COOKIE`
- `USER_PROFILE_TEXT_B64`
- `USER_LIBRARY_SUMMARY_B64`

前端本地配置位于 `frontend/.env.local`。

常见字段：

- `NEXT_PUBLIC_API_BASE=http://localhost:8000`

## 💾 本地数据模型

MentorSeeker 默认将数据保存在本地：

- SQLite 数据库：保存应用状态
- 本地 JSON 文件：保存探索与 enrich 输出
- 本地 `.env`：保存用户控制的 API 与配置项

这个仓库的默认设计目标是：**本地使用，而不是公网部署**。

## 🤖 AI 使用说明

MentorSeeker 当前仍处于**非常初级**的阶段。

这意味着：

- 检索结果可能不完整
- enrich 信息可能有遗漏、误判或过度总结
- AI 推荐可能存在偏差、幻觉或排序不稳定
- 自动生成的联系草稿不应被视为可直接发送的正式内容

尤其需要强调的是：

- **在给重要老师发送邮件前，一定要逐句人工审阅**
- **不要直接复制 AI 生成内容后无检查发送**
- **涉及研究方向、论文理解、导师匹配判断时，请务必结合你自己的核查**

这个项目更适合被理解为：

**“帮助你提效的辅助工作台”**  
而不是  
**“可以替你做最终判断的自动系统”**

## 🧭 它不只是“搜老师”

MentorSeeker 并不只是一个“抓教授姓名”的工具。

它更像一个决策支持工作台，让你可以：

- 广泛搜索
- 深度 enrich
- 逐步收敛 shortlist
- 清楚追踪沟通状态
- 在偏好不断演化的过程中，持续向 AI 追问更好的问题

这对以下场景尤其有价值：

- 同时申请多所学校的用户
- 想认真比较多个导师方向与风格的用户
- 联系周期较长、需要持续跟进的用户

## 📌 当前状态

这个项目已经可以作为本地工具使用，当前已具备：

- 导师探索任务
- 导师 enrich
- 导师库管理
- Timeline 跟踪
- AI 推荐会话
- Contact 草稿生成

它仍在持续迭代中，当前重点是：

- 提升稳定性
- 完善文档
- 提高开源可用性
- 加入更多有用的功能

## 🔒 安全提醒

- 不要提交真实 API Key、Cookie、个人资料文本
- 如果开发过程中曾暴露过密钥，请立即轮换
- 保证 `backend/.env`、`frontend/.env.local`、本地数据库与生成数据不进入 Git

## 🗺️ Roadmap

- 更好的跨语言检索与排序
- 更强的导师信息 enrich 质量
- 更透明的推荐理由解释
- 对非技术本地用户更友好的上手体验
- 更完整的自动化测试与发布流程

## 📄 License

本项目使用 `MIT License`。

你可以自由使用、修改、分发和二次开发，只需保留原始许可证声明。

## 🙏 Acknowledgement

To Codex, who makes this happen.
