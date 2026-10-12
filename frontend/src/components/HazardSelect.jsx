const HAZARDS = [
  { value: "heatwave", label: "Heatwave", available: true },
  { value: "drought", label: "Drought (coming soon)", available: false },
  { value: "heavy_rainfall", label: "Heavy rainfall (coming soon)", available: false },
];

export default function HazardSelect({ value, onChange }) {
  return (
    <label className="field">
      <span>Hazard type</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {HAZARDS.map((h) => (
          <option key={h.value} value={h.value} disabled={!h.available}>
            {h.label}
          </option>
        ))}
      </select>
    </label>
  );
}
