import { hazardMeta } from "./HazardSelect.jsx";

function Stat({ label, value, hint, muted }) {
  return (
    <div className={`stat${muted ? " stat-muted" : ""}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export default function InsightCard({ data }) {
  const meta = hazardMeta(data.hazard);
  const t = data.trend;
  const totalEvents = data.series.reduce((a, p) => a + p.events, 0);
  const totalDays = data.series.reduce((a, p) => a + p.hazard_days, 0);
  const avgCoverage =
    data.series.reduce((a, p) => a + p.coverage, 0) / (data.series.length || 1);

  const trendBadge = t.significant
    ? { text: `${t.mann_kendall_trend} · significant`, cls: "badge-sig" }
    : { text: t.mann_kendall_trend, cls: "badge-neutral" };

  // A percent change that isn't statistically significant is noise, not a
  // finding. Show it, but never style it as a headline result.
  const hasChange = t.percent_change != null;
  const changeText = hasChange
    ? `${t.percent_change > 0 ? "+" : ""}${t.percent_change}%`
    : "—";

  return (
    <div className="insight-card">
      <div className="insight-head">
        <h2>{data.region_name || `${data.lat}, ${data.lon}`}</h2>
        <span className={`badge ${trendBadge.cls}`}>{trendBadge.text}</span>
      </div>
      <p className="insight-text">{data.insight}</p>

      <div className="stats-row">
        <Stat label="Events" value={totalEvents} />
        <Stat label={`Total ${meta.metric.toLowerCase()}`} value={totalDays} />
        <Stat
          label={meta.thresholdLabel}
          value={`${data.threshold} ${data.threshold_unit}`}
          hint={
            data.baseline_fallback
              ? `⚠ fallback baseline ${data.baseline}`
              : `baseline ${data.baseline}`
          }
          muted={data.baseline_fallback}
        />
        <Stat
          label={t.significant ? "Trend" : "Trend (not significant)"}
          value={changeText}
          hint={
            t.significant
              ? `${t.slope_per_year}/yr · R²=${t.r_squared}`
              : `${t.slope_per_year}/yr · R²=${t.r_squared} · within noise`
          }
          muted={!t.significant}
        />
        <Stat
          label="Mann-Kendall p"
          value={t.mann_kendall_p}
          hint={t.significant ? "p < 0.05" : "not significant"}
          muted={!t.significant}
        />
      </div>

      {data.baseline_fallback && (
        <p className="coverage-note">
          The configured climatological baseline wasn’t available here, so the
          threshold came from the record itself ({data.baseline}) — it isn’t
          comparable with other regions or time ranges.
        </p>
      )}

      {avgCoverage < 0.9 && (
        <p className="coverage-note">
          Avg data coverage {Math.round(avgCoverage * 100)}% — some years have gaps.
        </p>
      )}

      {data.warnings?.length > 0 && (
        <details className="warnings">
          <summary>{data.warnings.length} data note(s)</summary>
          <ul>
            {data.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
