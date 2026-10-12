// Labels, chart wording and units for each hazard, in one place so the
// dashboard stays consistent when a hazard is added.
export const HAZARDS = [
  {
    value: "heatwave",
    label: "Heatwave",
    metric: "Heatwave days",
    seriesLabel: "Heatwave days / year",
    thresholdLabel: "Threshold (95th pct)",
  },
  {
    value: "drought",
    label: "Drought",
    metric: "Drought days",
    seriesLabel: "Drought days / year",
    thresholdLabel: "Dry-day cutoff",
  },
  {
    value: "heavy_rainfall",
    label: "Heavy rainfall",
    metric: "Heavy-rainfall days",
    seriesLabel: "Heavy-rainfall days / year",
    thresholdLabel: "Threshold (95th pct, wet days)",
  },
];

export function hazardMeta(value) {
  return HAZARDS.find((h) => h.value === value) ?? HAZARDS[0];
}

export default function HazardSelect({ value, onChange }) {
  return (
    <label className="field">
      <span>Hazard type</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {HAZARDS.map((h) => (
          <option key={h.value} value={h.value}>
            {h.label}
          </option>
        ))}
      </select>
    </label>
  );
}
