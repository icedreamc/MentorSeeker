import type {
  AdvisorAskResult,
  AdvisorLibrarySummaryGenerateResult,
  AdvisorMemory,
  AdvisorSessionDetail,
  AdvisorSessionSummary,
  AdvisorVectorIndexRebuildResult,
  AdvisorVectorIndexStatus,
  ContactDraftCommitResult,
  ContactDraftGenerateResult,
  DiscoveryJob,
  LocalSecretsState,
  LocalSecretsUpdateResult,
  MentorBatchDeleteResult,
  MentorBatchEnrichResult,
  MentorDetail,
  MentorList,
  MentorSummary,
  ProfileSettingsState,
  ProfileSettingsUpdateResult,
  TimelineDailyOverview,
  TimelineEvent,
  TimelineList,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers ?? {});
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

export async function createJob(payload: {
  school: string;
  interested_field: string;
  max_steps: number;
  target_mentor_count: number;
  enrich_limit: number;
  run_immediately: boolean;
}): Promise<DiscoveryJob> {
  return req<DiscoveryJob>("/api/discovery/jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function runJob(jobId: string): Promise<DiscoveryJob> {
  return req<DiscoveryJob>(`/api/discovery/jobs/${jobId}/run`, { method: "POST" });
}

export async function cancelJob(jobId: string): Promise<DiscoveryJob> {
  return req<DiscoveryJob>(`/api/discovery/jobs/${jobId}/cancel`, { method: "POST" });
}

export async function getJob(jobId: string): Promise<DiscoveryJob> {
  return req<DiscoveryJob>(`/api/discovery/jobs/${jobId}`);
}

export async function listJobs(limit = 20): Promise<DiscoveryJob[]> {
  return req<DiscoveryJob[]>(`/api/discovery/jobs?limit=${limit}`);
}

export async function listMentors(params: URLSearchParams): Promise<MentorList> {
  return req<MentorList>(`/api/mentors?${params.toString()}`);
}

export async function createMentor(payload: {
  school: string;
  interested_field: string;
  name: string;
  title: string;
  research_direction: string;
  profile_urls?: string[];
}): Promise<MentorSummary> {
  return req<MentorSummary>("/api/mentors", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function batchEnrichMentors(payload: {
  mentor_ids: number[];
  sleep_seconds?: number;
}): Promise<MentorBatchEnrichResult> {
  return req<MentorBatchEnrichResult>("/api/mentors/enrich", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function batchDeleteMentors(payload: { mentor_ids: number[] }): Promise<MentorBatchDeleteResult> {
  return req<MentorBatchDeleteResult>("/api/mentors/batch-delete", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getMentor(id: number, userId = 1): Promise<MentorDetail> {
  return req<MentorDetail>(`/api/mentors/${id}?user_id=${userId}`);
}

export async function toggleFavorite(id: number, isFavorite: boolean, userId = 1): Promise<{ is_favorite: boolean }> {
  return req<{ is_favorite: boolean }>(`/api/mentors/${id}/favorite`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId, is_favorite: isFavorite }),
  });
}

export async function removeFromMyLibrary(id: number, userId = 1): Promise<void> {
  await req(`/api/mentors/${id}/library?user_id=${userId}`, {
    method: "DELETE",
  });
}

export async function deleteMentorPermanently(id: number): Promise<void> {
  await req(`/api/mentors/${id}`, {
    method: "DELETE",
  });
}

export async function saveNote(id: number, noteText: string, tags: string[], userId = 1): Promise<void> {
  await req(`/api/mentors/${id}/note`, {
    method: "PATCH",
    body: JSON.stringify({ user_id: userId, note_text: noteText, tags }),
  });
}

export async function listTimeline(params: URLSearchParams): Promise<TimelineList> {
  return req<TimelineList>(`/api/timeline?${params.toString()}`);
}

export async function getTimelineDailyOverview(params: URLSearchParams): Promise<TimelineDailyOverview> {
  return req<TimelineDailyOverview>(`/api/timeline/overview/daily?${params.toString()}`);
}

export async function createTimeline(payload: {
  mentor_id: number;
  event_type: string;
  event_date: string;
  content: string;
  user_id?: number;
}): Promise<TimelineEvent> {
  return req<TimelineEvent>("/api/timeline", {
    method: "POST",
    body: JSON.stringify({ user_id: 1, ...payload }),
  });
}

export async function updateTimeline(
  eventId: number,
  payload: { event_type?: string; event_date?: string; content?: string },
): Promise<TimelineEvent> {
  return req<TimelineEvent>(`/api/timeline/${eventId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteTimeline(eventId: number): Promise<void> {
  await req(`/api/timeline/${eventId}`, { method: "DELETE" });
}

export async function getLocalSecrets(): Promise<LocalSecretsState> {
  return req<LocalSecretsState>("/api/settings/local-secrets");
}

export async function updateLocalSecrets(payload: {
  llm_base_url?: string;
  llm_model?: string;
  provider_email?: string;
  llm_api_key?: string;
  browser_cookie?: string;
  clear_llm_api_key?: boolean;
  clear_browser_cookie?: boolean;
}): Promise<LocalSecretsUpdateResult> {
  return req<LocalSecretsUpdateResult>("/api/settings/local-secrets", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function getProfileSettings(): Promise<ProfileSettingsState> {
  return req<ProfileSettingsState>("/api/settings/profile");
}

export async function updateProfileSettings(payload: {
  profile_text?: string;
  library_summary_text?: string;
  clear_profile?: boolean;
  clear_library_summary?: boolean;
}): Promise<ProfileSettingsUpdateResult> {
  return req<ProfileSettingsUpdateResult>("/api/settings/profile", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function listAdvisorSessions(userId = 1, limit = 30): Promise<AdvisorSessionSummary[]> {
  return req<AdvisorSessionSummary[]>(`/api/advisor-ai/sessions?user_id=${userId}&limit=${limit}`);
}

export async function createAdvisorSession(payload?: { user_id?: number; title?: string }): Promise<AdvisorSessionSummary> {
  return req<AdvisorSessionSummary>("/api/advisor-ai/sessions", {
    method: "POST",
    body: JSON.stringify({ user_id: 1, ...(payload ?? {}) }),
  });
}

export async function getAdvisorSession(sessionId: number, userId = 1): Promise<AdvisorSessionDetail> {
  return req<AdvisorSessionDetail>(`/api/advisor-ai/sessions/${sessionId}?user_id=${userId}`);
}

export async function deleteAdvisorSession(sessionId: number, userId = 1): Promise<void> {
  await req(`/api/advisor-ai/sessions/${sessionId}?user_id=${userId}`, {
    method: "DELETE",
  });
}

export async function askAdvisor(payload: {
  query: string;
  top_k?: number;
  session_id?: number;
  user_id?: number;
  personalized_boost?: boolean;
}): Promise<AdvisorAskResult> {
  return req<AdvisorAskResult>("/api/advisor-ai/ask", {
    method: "POST",
    body: JSON.stringify({ user_id: 1, top_k: 8, personalized_boost: false, ...payload }),
  });
}

export async function getAdvisorMemory(userId = 1): Promise<AdvisorMemory> {
  return req<AdvisorMemory>(`/api/advisor-ai/memory?user_id=${userId}`);
}

export async function updateAdvisorMemory(payload: { memory_text: string; user_id?: number }): Promise<AdvisorMemory> {
  return req<AdvisorMemory>("/api/advisor-ai/memory", {
    method: "PATCH",
    body: JSON.stringify({ user_id: 1, ...payload }),
  });
}

export async function generateAdvisorLibrarySummary(payload?: {
  user_id?: number;
  scope?: "favorites";
}): Promise<AdvisorLibrarySummaryGenerateResult> {
  return req<AdvisorLibrarySummaryGenerateResult>("/api/advisor-ai/library-summary/generate", {
    method: "POST",
    body: JSON.stringify({ user_id: 1, scope: "favorites", ...(payload ?? {}) }),
  });
}

export async function getAdvisorVectorIndexStatus(): Promise<AdvisorVectorIndexStatus> {
  return req<AdvisorVectorIndexStatus>("/api/advisor-ai/vector-index/status");
}

export async function rebuildAdvisorVectorIndex(payload?: {
  force?: boolean;
  batch_size?: number;
}): Promise<AdvisorVectorIndexRebuildResult> {
  return req<AdvisorVectorIndexRebuildResult>("/api/advisor-ai/vector-index/rebuild", {
    method: "POST",
    body: JSON.stringify({ force: true, batch_size: 32, ...(payload ?? {}) }),
  });
}

export async function generateContactDraft(payload: {
  mentor_id: number;
  language?: "auto" | "zh" | "en";
  extra_instruction?: string;
  user_id?: number;
}): Promise<ContactDraftGenerateResult> {
  return req<ContactDraftGenerateResult>("/api/contact-draft/generate", {
    method: "POST",
    body: JSON.stringify({ user_id: 1, language: "auto", extra_instruction: "", ...payload }),
  });
}

export async function commitContactDraft(payload: {
  mentor_id: number;
  event_date: string;
  subject: string;
  body: string;
  user_id?: number;
}): Promise<ContactDraftCommitResult> {
  return req<ContactDraftCommitResult>("/api/contact-draft/commit", {
    method: "POST",
    body: JSON.stringify({ user_id: 1, ...payload }),
  });
}

