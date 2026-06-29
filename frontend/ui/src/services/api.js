// API Service for RedRob AI Recruiter
// VITE_API_URL is injected at build time via Docker build-arg / .env
// Falls back to localhost:8000 for local dev without Docker
const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Shape helper: map a ranked result from the backend into what the UI expects
// ---------------------------------------------------------------------------
const mapRankedToFrontend = (rank) => ({
  id:              rank.candidate_id,
  name:            `Candidate ${rank.candidate_id.slice(-6)}`,
  role:            'AI-Ranked Candidate',
  summary:         rank.reasoning || '',
  location:        '',
  experience:      '',
  experienceYears: 0,
  skills:          [],
  education:       [],
  experience_details: [],
  certifications:  [],
  atsScore:        0,
  overallScore:    rank.final_score,
  rank:            rank.rank,
  reasoning:       rank.reasoning,
  breakdown:       rank.breakdown || {
    stage_1_skills_semantic:  0,
    stage_2_behavioral_star:  0,
    stage_3_platform_signals: 0,
  },
  scoreBreakdown: {
    semanticMatch:     rank.breakdown?.stage_1_skills_semantic  ?? 0,
    behavioralMatch:   rank.breakdown?.stage_2_behavioral_star  ?? 0,
    domainExperience:  rank.breakdown?.stage_3_platform_signals ?? 0,
  },
});

// ---------------------------------------------------------------------------
// getCandidates — pull top-100 from a session stored on the backend
// ---------------------------------------------------------------------------
export const getCandidates = async (sessionId) => {
  if (!sessionId) return [];

  const response = await fetch(`${BASE_URL}/api/rank/leaderboard/${sessionId}`);
  if (!response.ok) throw new Error(`Failed to load session: ${response.statusText}`);

  const data = await response.json();
  return (data.rankings || []).map(mapRankedToFrontend);
};

// ---------------------------------------------------------------------------
// getCandidateById — lightweight placeholder (no full dataset in browser)
// ---------------------------------------------------------------------------
export const getCandidateById = async (id) => ({
  id,
  name:            `Candidate ${id.slice(-6)}`,
  role:            'AI-Ranked Candidate',
  summary:         'Full profile stored server-side.',
  location:        '',
  experience:      '',
  experienceYears: 0,
  skills:          [],
  education:       [],
  experience_details: [],
  certifications:  [],
  atsScore:        0,
  overallScore:    0,
  breakdown:       {},
  scoreBreakdown:  {},
});

// ---------------------------------------------------------------------------
// getJobDescription — stub
// ---------------------------------------------------------------------------
export const getJobDescription = async () => ({
  title: '', department: '', experience: '', skills: [], responsibilities: '',
});

// ---------------------------------------------------------------------------
// calculateWeightedScore
// ---------------------------------------------------------------------------
export const calculateWeightedScore = (candidate, weights) => {
  const bd = candidate.breakdown    || {};
  const sb = candidate.scoreBreakdown || {};

  const semantic   = bd.stage_1_skills_semantic  ?? sb.semanticMatch    ?? 0;
  const behavioral = bd.stage_2_behavioral_star  ?? sb.behavioralMatch  ?? 0;
  const platform   = bd.stage_3_platform_signals ?? sb.domainExperience ?? 0;

  const wSem  = (weights.semantic   ?? 60) / 100;
  const wBeh  = (weights.behavioral ?? 20) / 100;
  const wPlat = (weights.platform   ?? 20) / 100;
  const total  = wSem + wBeh + wPlat || 1;

  // Return the float value with full precision. This ensures that the position-based
  // tie-breaker offsets baked into the breakdown scores are preserved.
  const rawWeighted = ((semantic * wSem) + (behavioral * wBeh) + (platform * wPlat)) / total;
  return Number(rawWeighted.toFixed(4));
};

// ---------------------------------------------------------------------------
// compareCandidates — stub (requires session data, not implemented client-side)
// ---------------------------------------------------------------------------
export const compareCandidates = async () => {
  throw new Error('Run AI analysis first to compare ranked candidates.');
};

// ---------------------------------------------------------------------------
// Stubs
// ---------------------------------------------------------------------------
export const getAllSkills       = async () => [];
export const uploadJobDescription = async () => ({ success: true });
export const uploadResumes      = async (files) => ({
  success: true,
  message: `${files.length} file(s) noted (resume parsing is handled server-side).`,
  parsedCount: files.length,
});

// ---------------------------------------------------------------------------
// runAIAnalysis — the main pipeline
//
// Flow:
//   1. Generate a job_id for SSE progress tracking
//   2. POST jdFile to /api/jd/parse  → get parsed_jd JSON
//   3. POST { ...parsedJD, job_id } to /api/rank/start → backend runs the
//      cascade funnel against its pre-loaded candidate pool and returns top-100
//
// The candidate dataset NEVER touches the frontend.
// Call getProgressUrl(job_id) to get the SSE stream URL for live tracking.
// ---------------------------------------------------------------------------

export const getProgressUrl = (jobId) => `${BASE_URL}/api/progress/${jobId}`;

export const runAIAnalysis = async (jdFile, onJobId, onProgress) => {
  if (!jdFile) {
    throw new Error('Please upload a Job Description (.docx) file to begin analysis.');
  }

  // Generate a stable job_id before the request so the SSE stream can be
  // opened immediately — the backend will write progress to it.
  const jobId = crypto.randomUUID();
  if (onJobId) onJobId(jobId);

  // ── Step 1: Parse the .docx into structured JD JSON ──────────────────────
  const formData = new FormData();
  formData.append('file', jdFile);

  const parseRes = await fetch(`${BASE_URL}/api/jd/parse`, {
    method: 'POST',
    body: formData,
  });

  if (!parseRes.ok) {
    const err = await parseRes.text();
    throw new Error(`Failed to parse job description: ${err}`);
  }

  const { parsed_jd: parsedJD } = await parseRes.json();

  // ── Step 2: Fire ranking (returns immediately, runs in background) ───────
  const rankRes = await fetch(`${BASE_URL}/api/rank/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...parsedJD, job_id: jobId }),
  });

  if (!rankRes.ok) {
    const err = await rankRes.text();
    throw new Error(`Ranking failed to start: ${err}`);
  }

  // ── Step 3: Wait for SSE to report done + session_id ─────────────────────
  const sessionId = await new Promise((resolve, reject) => {
    const url = getProgressUrl(jobId);
    const es = new EventSource(url);

    es.onmessage = (e) => {
      try {
        const snap = JSON.parse(e.data);
        if (onProgress) onProgress(snap);

        if (snap.done) {
          es.close();
          if (snap.stage === 'error') {
            reject(new Error(snap.detail || 'Ranking pipeline failed.'));
          } else if (snap.session_id) {
            resolve(snap.session_id);
          } else {
            reject(new Error('Ranking completed but no session ID was returned.'));
          }
        }
      } catch (_) {}
    };

    es.onerror = () => {
      es.close();
      reject(new Error('Lost connection to progress stream.'));
    };
  });

  // ── Step 4: Fetch ranked results from leaderboard ────────────────────────
  const lbRes = await fetch(`${BASE_URL}/api/rank/leaderboard/${sessionId}`);
  if (!lbRes.ok) {
    const err = await lbRes.text();
    throw new Error(`Failed to load results: ${err}`);
  }

  const result = await lbRes.json();

  return {
    success:       true,
    job_id:        jobId,
    session_id:    sessionId,
    analyzedCount: result.total_processed,
    rankings:      result.rankings,
    parsedJD,
  };
};

export default {
  getCandidates,
  getCandidateById,
  getJobDescription,
  calculateWeightedScore,
  compareCandidates,
  getAllSkills,
  uploadJobDescription,
  uploadResumes,
  runAIAnalysis,
  getProgressUrl,
};

