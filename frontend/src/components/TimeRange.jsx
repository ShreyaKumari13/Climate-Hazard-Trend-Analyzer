export default function TimeRange({ startYear, endYear, onChange }) {
  const currentYear = new Date().getFullYear();
  const years = [];
  for (let y = 1940; y <= currentYear; y++) years.push(y);

  return (
    <div className="latlon">
      <label className="field">
        <span>Start year</span>
        <select
          value={startYear}
          onChange={(e) => onChange({ startYear: parseInt(e.target.value, 10) })}
        >
          {years.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>End year</span>
        <select
          value={endYear}
          onChange={(e) => onChange({ endYear: parseInt(e.target.value, 10) })}
        >
          {years.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
