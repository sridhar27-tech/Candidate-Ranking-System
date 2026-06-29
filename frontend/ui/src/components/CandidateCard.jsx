import React from "react";
import { Link } from "react-router-dom";
import { FiMapPin, FiBriefcase, FiArrowRight, FiCpu } from "react-icons/fi";

const getScoreColor = (score) => {
  if (score >= 90) return "#22c55e";
  if (score >= 75) return "#6366f1";
  if (score >= 60) return "#f59e0b";
  return "#ef4444";
};

const getRankLabel = (r) => {
  if (r === 1) return "🥇 #1";
  if (r === 2) return "🥈 #2";
  if (r === 3) return "🥉 #3";
  return `#${r}`;
};

const CandidateCard = ({ candidate, rank, sessionId, onViewInsights }) => {
  const scoreColor = getScoreColor(candidate.overallScore);
  const detailPath = sessionId
    ? `/candidate/${sessionId}/${candidate.id}`
    : `/candidate/${candidate.id}`;

  return (
    <div className="candidate-card">
      {rank != null && <div className="rank-badge">{getRankLabel(rank)}</div>}

      <div className="score-badge">
        <span className="score-value" style={{ color: scoreColor }}>
          {Number(candidate.overallScore).toFixed(1)}
        </span>
        <span className="score-label">Match</span>
      </div>

      <div className="card-content">
        <div className="card-header">
          <div className="candidate-avatar">
            {candidate.name
              .split(" ")
              .map((n) => n[0])
              .join("")}
          </div>
          <div className="candidate-info">
            <h3 className="candidate-name">{candidate.name}</h3>
            <p className="candidate-role">{candidate.role}</p>
          </div>
        </div>

        <div className="card-details">
          {candidate.location && (
            <div className="detail-item">
              <FiMapPin className="detail-icon" />
              <span>{candidate.location}</span>
            </div>
          )}
          {candidate.experience && (
            <div className="detail-item">
              <FiBriefcase className="detail-icon" />
              <span>{candidate.experience}</span>
            </div>
          )}
        </div>

        {candidate.skills.length > 0 && (
          <div className="skills-preview">
            {candidate.skills.slice(0, 5).map((skill, i) => (
              <span key={i} className="skill-tag">
                {skill}
              </span>
            ))}
            {candidate.skills.length > 5 && (
              <span className="skill-tag more">
                +{candidate.skills.length - 5}
              </span>
            )}
          </div>
        )}

        <div
          className="card-actions"
          style={{ display: "flex", gap: "0.5rem", marginTop: "0.25rem" }}
        >
          <button
            onClick={onViewInsights}
            className="view-details-btn"
            style={{
              flex: 1,
              background: "var(--accent)",
              color: "#fff",
              border: "none",
              cursor: "pointer",
              borderRadius: "var(--radius-sm)",
              padding: "0.5rem 0.875rem",
              fontSize: "0.82rem",
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "0.35rem",
            }}
          >
            <FiCpu style={{ fontSize: "0.95rem" }} />
            Insights
          </button>
          <Link
            to={detailPath}
            className="view-details-btn"
            style={{
              flex: 1,
              background: "var(--elevated)",
              color: "var(--text-1)",
              border: "1px solid var(--border)",
              cursor: "pointer",
              borderRadius: "var(--radius-sm)",
              padding: "0.5rem 0.875rem",
              fontSize: "0.82rem",
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "0.35rem",
              textDecoration: "none",
            }}
          >
            Details
            <FiArrowRight style={{ fontSize: "0.875rem" }} />
          </Link>
        </div>
      </div>
    </div>
  );
};

export default CandidateCard;
