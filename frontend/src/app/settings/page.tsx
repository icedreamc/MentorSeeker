"use client";

import { FormEvent, useEffect, useState } from "react";
import { getLocalSecrets, getProfileSettings, updateLocalSecrets, updateProfileSettings } from "@/lib/api";

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [savingSecrets, setSavingSecrets] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);

  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [providerEmail, setProviderEmail] = useState("");
  const [llmApiKeyInput, setLlmApiKeyInput] = useState("");
  const [browserCookieInput, setBrowserCookieInput] = useState("");
  const [hasApiKey, setHasApiKey] = useState(false);
  const [hasCookie, setHasCookie] = useState(false);

  const [profileText, setProfileText] = useState("");
  const [librarySummaryText, setLibrarySummaryText] = useState("");
  const [hasProfile, setHasProfile] = useState(false);
  const [hasLibrarySummary, setHasLibrarySummary] = useState(false);

  async function loadAll() {
    setLoading(true);
    setError("");

    try {
      const [secretsRes, profileRes] = await Promise.all([getLocalSecrets(), getProfileSettings()]);
      setLlmBaseUrl(secretsRes.llm_base_url);
      setLlmModel(secretsRes.llm_model);
      setProviderEmail(secretsRes.provider_email);
      setHasApiKey(secretsRes.has_llm_api_key);
      setHasCookie(secretsRes.has_browser_cookie);

      setProfileText(profileRes.profile_text);
      setLibrarySummaryText(profileRes.library_summary_text);
      setHasProfile(profileRes.has_profile);
      setHasLibrarySummary(profileRes.has_library_summary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "设置读取失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function onSaveSecrets(event: FormEvent) {
    event.preventDefault();
    setSavingSecrets(true);
    setError("");
    setMessage("");

    try {
      const payload: {
        llm_base_url?: string;
        llm_model?: string;
        provider_email?: string;
        llm_api_key?: string;
        browser_cookie?: string;
      } = {
        llm_base_url: llmBaseUrl,
        llm_model: llmModel,
        provider_email: providerEmail,
      };

      if (llmApiKeyInput.trim()) {
        payload.llm_api_key = llmApiKeyInput;
      }
      if (browserCookieInput.trim()) {
        payload.browser_cookie = browserCookieInput;
      }

      const res = await updateLocalSecrets(payload);
      setHasApiKey(res.has_llm_api_key);
      setHasCookie(res.has_browser_cookie);
      setLlmApiKeyInput("");
      setBrowserCookieInput("");
      setMessage("本地密钥设置已更新（仅保存到本地 backend/.env）。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存本地密钥失败");
    } finally {
      setSavingSecrets(false);
    }
  }

  async function onSaveProfile(event: FormEvent) {
    event.preventDefault();
    setSavingProfile(true);
    setError("");
    setMessage("");

    try {
      const res = await updateProfileSettings({
        profile_text: profileText,
        library_summary_text: librarySummaryText,
      });
      setProfileText(res.profile_text);
      setLibrarySummaryText(res.library_summary_text);
      setHasProfile(res.has_profile);
      setHasLibrarySummary(res.has_library_summary);
      setMessage("我的资料与导师库总结已保存到本地。 ");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存我的资料失败");
    } finally {
      setSavingProfile(false);
    }
  }

  async function onClearApiKey() {
    setSavingSecrets(true);
    setError("");
    setMessage("");
    try {
      const res = await updateLocalSecrets({ clear_llm_api_key: true });
      setHasApiKey(res.has_llm_api_key);
      setLlmApiKeyInput("");
      setMessage("LLM API Key 已清除。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "清除 API Key 失败");
    } finally {
      setSavingSecrets(false);
    }
  }

  async function onClearCookie() {
    setSavingSecrets(true);
    setError("");
    setMessage("");
    try {
      const res = await updateLocalSecrets({ clear_browser_cookie: true });
      setHasCookie(res.has_browser_cookie);
      setBrowserCookieInput("");
      setMessage("Browser Cookie 已清除。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "清除 Cookie 失败");
    } finally {
      setSavingSecrets(false);
    }
  }

  async function onClearProfile() {
    setSavingProfile(true);
    setError("");
    setMessage("");
    try {
      const res = await updateProfileSettings({ clear_profile: true });
      setProfileText(res.profile_text);
      setHasProfile(res.has_profile);
      setMessage("我的资料已清空。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "清空资料失败");
    } finally {
      setSavingProfile(false);
    }
  }

  async function onClearLibrarySummary() {
    setSavingProfile(true);
    setError("");
    setMessage("");
    try {
      const res = await updateProfileSettings({ clear_library_summary: true });
      setLibrarySummaryText(res.library_summary_text);
      setHasLibrarySummary(res.has_library_summary);
      setMessage("导师库总结已清空。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "清空导师库总结失败");
    } finally {
      setSavingProfile(false);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h2 className="page-title">设置</h2>
          <p className="page-desc">管理本地密钥、我的资料、导师库总结。所有内容仅保存在本机。</p>
        </div>
      </header>

      <form className="card grid settings-card" onSubmit={onSaveSecrets}>
        <h3 className="section-title">本地密钥设置</h3>

        <div className="grid two">
          <label className="field">
            <span className="field-label">LLM Base URL</span>
            <input value={llmBaseUrl} onChange={(e) => setLlmBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" />
          </label>
          <label className="field">
            <span className="field-label">LLM Model</span>
            <input value={llmModel} onChange={(e) => setLlmModel(e.target.value)} placeholder="gpt-5-mini" />
          </label>
        </div>

        <label className="field">
          <span className="field-label">Provider Email</span>
          <input value={providerEmail} onChange={(e) => setProviderEmail(e.target.value)} placeholder="you@example.com" />
        </label>

        <div className="grid two">
          <label className="field">
            <span className="field-label">LLM API Key（可留空表示不更新）</span>
            <input
              type="password"
              value={llmApiKeyInput}
              onChange={(e) => setLlmApiKeyInput(e.target.value)}
              placeholder="输入新的 API Key"
              autoComplete="new-password"
            />
          </label>
          <label className="field">
            <span className="field-label">Browser Cookie（可留空表示不更新）</span>
            <input
              type="password"
              value={browserCookieInput}
              onChange={(e) => setBrowserCookieInput(e.target.value)}
              placeholder="输入新的 Cookie"
              autoComplete="new-password"
            />
          </label>
        </div>

        <div className="meta-row">
          <span className={`status-pill ${hasApiKey ? "status-success" : "status-failed"}`}>API Key: {hasApiKey ? "已配置" : "未配置"}</span>
          <span className={`status-pill ${hasCookie ? "status-success" : "status-failed"}`}>Cookie: {hasCookie ? "已配置" : "未配置"}</span>
        </div>

        <p className="small">
          敏感信息只保存于 <code>backend/.env</code>，且项目已通过 <code>.gitignore</code> 避免提交。
        </p>

        <div className="actions">
          <button className="btn-primary" disabled={savingSecrets || loading}>
            {savingSecrets ? "保存中..." : "保存密钥设置"}
          </button>
          <button className="btn-secondary" type="button" disabled={savingSecrets} onClick={onClearApiKey}>
            清除 API Key
          </button>
          <button className="btn-secondary" type="button" disabled={savingSecrets} onClick={onClearCookie}>
            清除 Cookie
          </button>
          <button className="btn-secondary" type="button" disabled={savingSecrets || loading} onClick={loadAll}>
            刷新
          </button>
        </div>
      </form>

      <form className="card grid settings-card" onSubmit={onSaveProfile}>
        <h3 className="section-title">我的资料（个性化推荐输入）</h3>

        <label className="field">
          <span className="field-label">我的资料（简历文本、研究兴趣、成果等）</span>
          <textarea
            rows={8}
            value={profileText}
            onChange={(e) => setProfileText(e.target.value)}
            placeholder="可粘贴你的简历、研究方向、项目经历、技能、目标申请方向等。"
          />
        </label>

        <label className="field">
          <span className="field-label">导师库总结（可自动生成后手动微调）</span>
          <textarea
            rows={6}
            value={librarySummaryText}
            onChange={(e) => setLibrarySummaryText(e.target.value)}
            placeholder="这里会保存基于收藏导师生成的高维偏好总结。"
          />
        </label>

        <div className="meta-row">
          <span className={`status-pill ${hasProfile ? "status-success" : "status-failed"}`}>我的资料: {hasProfile ? "已配置" : "未配置"}</span>
          <span className={`status-pill ${hasLibrarySummary ? "status-success" : "status-failed"}`}>
            导师库总结: {hasLibrarySummary ? "已配置" : "未配置"}
          </span>
        </div>

        <div className="actions">
          <button className="btn-primary" disabled={savingProfile || loading}>
            {savingProfile ? "保存中..." : "保存我的资料"}
          </button>
          <button className="btn-secondary" type="button" disabled={savingProfile} onClick={onClearProfile}>
            清空我的资料
          </button>
          <button className="btn-secondary" type="button" disabled={savingProfile} onClick={onClearLibrarySummary}>
            清空导师库总结
          </button>
        </div>
      </form>

      {message ? <div className="status-pill status-success">{message}</div> : null}
      {error ? <div className="status-pill status-failed">{error}</div> : null}
    </section>
  );
}
