import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  FiUpload,
  FiPlay,
  FiArrowRight,
  FiCheck,
  FiFileText,
  FiX,
  FiZap,
  FiFolder,
  FiCpu,
  FiCrosshair,
  FiBarChart2,
  FiUsers,
  FiEye,
  FiSliders,
} from "react-icons/fi";
import AnalysisLoadingScreen from "../components/AnalysisLoadingScreen";
import api from "../services/api";

const previewCandidates = [
  { name: "Alexandra Chen", score: 94 },
  { name: "Marcus Williams", score: 88 },
  { name: "Priya Kapoor", score: 81 },
  { name: "James Liu", score: 74 },
  { name: "Sarah O'Brien", score: 67 },
];

const Landing = () => {
  const navigate = useNavigate();
  const jdInputRef = useRef(null);

  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [uploadStatus, setUploadStatus] = useState({ jd: false });
  const [jdFile, setJdFile] = useState(null);
  const [jdFileName, setJdFileName] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [statusDetail, setStatusDetail] = useState("");
  const [statusProgress, setStatusProgress] = useState(null);

  const handleJDUploadClick = () => jdInputRef.current?.click();

  const handleJDFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setJdFile(file);
    setJdFileName(file.name);
    setUploadStatus({ jd: true });
  };

  const clearJD = (e) => {
    e.stopPropagation();
    setJdFile(null);
    setJdFileName("");
    setUploadStatus({ jd: false });
    if (jdInputRef.current) jdInputRef.current.value = "";
  };

  // Maps backend stage keys → human-readable status messages
  const STAGE_LABELS = {
    jd_input:      "JD input received",
    jd_parsed:     "JSON response received",
    starting:      "Starting analysis…",
    stage1:        "Stage 1 operation started — Skill scoring",
    stage1_done:   "Stage 1 complete — Top candidates shortlisted",
    stage2_3:      "Stage 2 & 3 operation started — Behavioral & platform evaluation",
    insights:      "Assigning AI reasoning insights…",
    complete:      "Process complete",
  };

  const handleStartAnalysis = async () => {
    if (!jdFile) {
      alert("Upload a .docx job description first.");
      return;
    }
    setIsAnalyzing(true);
    setStatusMessage("JD input received");
    setStatusDetail("Uploading and parsing job description…");
    setStatusProgress(2);

    try {
      const result = await api.runAIAnalysis(
        jdFile,
        (jobId) => {
          // Called as soon as job_id is generated (before ranking starts)
          setStatusMessage("JSON response received");
          setStatusDetail("Job description parsed successfully");
          setStatusProgress(5);
        },
        (snap) => {
          // Called on each SSE progress update from the background ranking
          const label = STAGE_LABELS[snap.stage] || snap.stage || "Processing…";
          setStatusMessage(label);
          setStatusDetail(snap.detail || "");
          setStatusProgress(snap.pct ?? null);
        }
      );

      if (result.success && result.session_id) {
        setStatusMessage("Process complete");
        setStatusProgress(100);

        // Brief pause so user sees "Process complete"
        await new Promise((r) => setTimeout(r, 800));

        navigate(`/dashboard?session=${result.session_id}`, {
          state: {
            rankings: result.rankings,
            analyzedCount: result.analyzedCount,
          },
        });
      } else {
        setIsAnalyzing(false);
        alert("Analysis failed — no session ID returned.");
      }
    } catch (err) {
      setIsAnalyzing(false);
      setStatusMessage("");
      setStatusDetail("");
      setStatusProgress(null);
      alert("Error: " + err.message);
    }
  };

  return (
    <>
      <AnalysisLoadingScreen
        isActive={isAnalyzing}
        statusMessage={statusMessage}
        statusDetail={statusDetail}
        progress={statusProgress}
      />

      <div className="landing-page">
        {/* ── Hero ── */}
        <section className="hero-section">
          <div className="hero-content">
            <div className="hero-badge">
              <FiZap className="badge-icon" />
              AI-Powered Recruitment
            </div>

            <h1 className="hero-title">
              Hire better with
              <br />
              <span className="gradient-text">AI that understands context</span>
            </h1>

            <p className="hero-subtitle">
              Traditional ATS systems miss 75% of qualified candidates. RedRob
              evaluates resumes across skills, behaviour, and domain fit — not
              just keywords.
            </p>

            <div className="hero-stats">
              <div className="stat-item">
                <span className="stat-value">94%</span>
                <span className="stat-label">Accuracy</span>
              </div>
              <div className="stat-divider" />
              <div className="stat-item">
                <span className="stat-value">3×</span>
                <span className="stat-label">Faster hiring</span>
              </div>
              <div className="stat-divider" />
              <div className="stat-item">
                <span className="stat-value">+29</span>
                <span className="stat-label">Avg score boost</span>
              </div>
            </div>
          </div>

          {/* Static ranked output preview */}
          <div className="hero-visual">
            <div className="hero-preview-card">
              <div className="preview-card-header">
                <span className="preview-card-title">
                  AI Rankings — Software Engineers
                </span>
                <span className="preview-card-badge">Live</span>
              </div>

              <div className="preview-card-rows">
                {previewCandidates.map((c, i) => (
                  <div key={i} className="preview-card-row">
                    <span className="preview-rank">#{i + 1}</span>
                    <span className="preview-name">{c.name}</span>
                    <div className="preview-bar-wrap">
                      <div
                        className="preview-bar-fill"
                        style={{ width: `${c.score}%` }}
                      />
                    </div>
                    <span className="preview-score">{c.score}%</span>
                  </div>
                ))}
              </div>

              <div className="preview-card-footer">
                5 candidates · Evaluated across 3 AI dimensions
              </div>
            </div>
          </div>
        </section>

        {/* ── How it works ── */}
        <section className="how-it-works">
          <h2 className="section-title">How it works</h2>
          <div className="steps-grid">
            <div className="step-card">
              <div className="step-number">01</div>
              <FiFileText className="step-icon" />
              <h3>Upload Job Description</h3>
              <p>
                Share your role requirements. We parse what makes a candidate
                succeed here.
              </p>
            </div>
            <div className="step-card">
              <div className="step-number">02</div>
              <FiFolder className="step-icon" />
              <h3>Upload Resumes</h3>
              <p>
                Submit candidate resumes. Our AI parses every profile with full
                context.
              </p>
            </div>
            <div className="step-card">
              <div className="step-number">03</div>
              <FiCpu className="step-icon" />
              <h3>AI Analysis</h3>
              <p>
                Candidates are evaluated across semantic match, skills,
                behaviour, and domain expertise.
              </p>
            </div>
            <div className="step-card">
              <div className="step-number">04</div>
              <FiCrosshair className="step-icon" />
              <h3>Ranked Results</h3>
              <p>
                Get an intelligently ranked shortlist with full score
                breakdowns.
              </p>
            </div>
          </div>
        </section>

        {/* ── Upload ── */}
        <section className="upload-section">
          <h2 className="section-title">Get started</h2>

          <div className="upload-container">
            {/* JD upload */}
            <div className="upload-card">
              <div className="upload-header">
                <FiUpload className="upload-icon" />
                <h3>Job Description</h3>
              </div>

              <div
                className={`upload-area${uploadStatus.jd ? " uploaded" : ""}`}
                onClick={handleJDUploadClick}
              >
                {uploadStatus.jd ? (
                  <>
                    <FiCheck className="check-icon" />
                    <span>Job description ready</span>
                    <span className="upload-hint">{jdFileName}</span>
                  </>
                ) : (
                  <>
                    <FiFileText className="upload-big-icon" />
                    <span>Click to upload</span>
                    <span className="upload-hint">.docx supported</span>
                  </>
                )}
              </div>

              <input
                ref={jdInputRef}
                type="file"
                accept=".docx,.doc"
                onChange={handleJDFileChange}
                style={{ display: "none" }}
              />

              {uploadStatus.jd && (
                <div className="jd-preview">
                  <div className="jd-preview-header">
                    <FiFileText className="jd-preview-icon" />
                    <span className="jd-preview-filename">{jdFileName}</span>
                    <button
                      className="jd-clear-btn"
                      onClick={clearJD}
                      title="Remove"
                    >
                      <FiX />
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Resume — server-side */}
            <div className="upload-card">
              <div className="upload-header">
                <FiUpload className="upload-icon" />
                <h3>Candidate Resumes</h3>
              </div>
              <div className="upload-area" style={{ cursor: "default" }}>
                <FiUsers className="upload-big-icon" />
                <span>Server-side candidates</span>
                <span className="upload-hint">
                  Resumes are loaded automatically from the backend
                </span>
              </div>
            </div>
          </div>

          <button
            className={`start-analysis-btn${!uploadStatus.jd ? " disabled" : ""}`}
            onClick={handleStartAnalysis}
            disabled={!uploadStatus.jd || isAnalyzing}
          >
            {isAnalyzing ? (
              <>
                <span className="loading-spinner" />
                Analyzing…
              </>
            ) : (
              <>
                <FiPlay className="btn-icon" />
                Run AI Analysis
                <FiArrowRight className="btn-icon" />
              </>
            )}
          </button>
        </section>

        {/* ── Features ── */}
        <section className="features-section">
          <h2 className="section-title">Why RedRob</h2>
          <div className="features-grid">
            <div className="feature-card">
              <FiCpu className="feature-icon" />
              <h3>Semantic understanding</h3>
              <p>Evaluates context and meaning, not keyword frequency.</p>
            </div>
            <div className="feature-card">
              <FiUsers className="feature-icon" />
              <h3>Fair evaluation</h3>
              <p>Focuses on skills and potential, reducing pedigree bias.</p>
            </div>
            <div className="feature-card">
              <FiBarChart2 className="feature-icon" />
              <h3>Score breakdowns</h3>
              <p>Detailed per-dimension analysis for every candidate.</p>
            </div>
            <div className="feature-card">
              <FiSliders className="feature-icon" />
              <h3>Adjustable weights</h3>
              <p>Tune scoring criteria to your hiring priorities.</p>
            </div>
            <div className="feature-card">
              <FiUsers className="feature-icon" />
              <h3>Side-by-side compare</h3>
              <p>Compare any two candidates across all dimensions.</p>
            </div>
            <div className="feature-card">
              <FiEye className="feature-icon" />
              <h3>ATS blindspot detection</h3>
              <p>
                Surfaces qualified candidates that keyword-ATS systems reject.
              </p>
            </div>
          </div>
        </section>

        {/* ── CTA ── */}
        <section className="cta-section">
          <h2>Ready to hire smarter?</h2>
          <p>
            Join teams making better decisions with AI-powered candidate
            evaluation.
          </p>
          <button className="cta-button" onClick={() => navigate("/dashboard")}>
            Open Dashboard
            <FiArrowRight className="btn-icon" />
          </button>
        </section>
      </div>
    </>
  );
};

export default Landing;
