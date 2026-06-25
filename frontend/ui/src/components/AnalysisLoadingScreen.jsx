import React from "react";

const AnalysisLoadingScreen = ({ isActive, statusMessage, statusDetail, progress }) => {
  if (!isActive) return null;

  const pct = typeof progress === "number" ? Math.min(Math.max(progress, 0), 100) : null;

  return (
    <div
      className="ald-overlay"
      role="alertdialog"
      aria-modal="true"
      aria-label="Analysis in progress"
    >
      <div className="ald-panel">
        <div className="ald-spinner" />
        <span className="ald-title">
          {statusMessage || "Analyzing candidates"}
        </span>
        {statusDetail ? (
          <span className="ald-subtitle">{statusDetail}</span>
        ) : (
          <span className="ald-subtitle">This may take a moment…</span>
        )}
        {pct !== null && (
          <div className="ald-progress-wrap">
            <div className="ald-progress-bar" style={{ width: `${pct}%` }} />
          </div>
        )}
        {pct !== null && (
          <span className="ald-pct">{pct}%</span>
        )}
      </div>
    </div>
  );
};

export default AnalysisLoadingScreen;
