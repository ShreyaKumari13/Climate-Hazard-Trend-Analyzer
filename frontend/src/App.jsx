import { useEffect, useState } from "react";
import RegionPicker from "./components/RegionPicker.jsx";
import MapPicker from "./components/MapPicker.jsx";
import TimeRange from "./components/TimeRange.jsx";
import HazardSelect, { hazardMeta } from "./components/HazardSelect.jsx";
import TrendChart from "./components/TrendChart.jsx";
import InsightCard from "./components/InsightCard.jsx";
import ExportButtons from "./components/ExportButtons.jsx";
import { useAnalysis } from "./hooks/useAnalysis.js";

const DEFAULTS = {
  lat: 33.4484,
  lon: -112.074,
  region_name: "Phoenix, USA",
  startYear: 1990,
  endYear: 2020,
  hazard: "heatwave",
};

export default function App() {
  const [form, setForm] = useState(DEFAULTS);
  const { data, loading, error, run } = useAnalysis();

  const update = (patch) => setForm((f) => ({ ...f, ...patch }));

  const toParams = (f) => ({
    lat: f.lat,
    lon: f.lon,
    start_year: f.startYear,
    end_year: f.endYear,
    hazard: f.hazard,
    region_name: f.region_name || undefined,
  });

  const submit = (e) => {
    e?.preventDefault();
    run(toParams(form));
  };

  // Run once on first load so the dashboard isn't empty.
  useEffect(() => {
    run(toParams(DEFAULTS));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const valid =
    Number.isFinite(form.lat) &&
    Number.isFinite(form.lon) &&
    form.endYear >= form.startYear;

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Climate Hazard Trend Analyzer</h1>
          <p className="subtitle">
            Historical heatwave trends from ERA5 reanalysis (Open-Meteo).
          </p>
        </div>
        <a
          className="theme-toggle"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            document.documentElement.classList.toggle("dark");
          }}
        >
          ◐ Theme
        </a>
      </header>

      <div className="layout">
        <form className="controls" onSubmit={submit}>
          <h3>Region</h3>
          <RegionPicker value={form} onChange={update} />
          <MapPicker value={form} onChange={update} />

          <h3>Parameters</h3>
          <HazardSelect value={form.hazard} onChange={(hazard) => update({ hazard })} />
          <TimeRange
            startYear={form.startYear}
            endYear={form.endYear}
            onChange={update}
          />

          <button type="submit" className="btn-primary" disabled={!valid || loading}>
            {loading ? "Analyzing…" : "Analyze"}
          </button>
          {!valid && <p className="form-error">Check coordinates and year range.</p>}
        </form>

        <main className="results">
          {error && <div className="error-box">⚠ {error}</div>}

          {loading && !data && <div className="skeleton">Fetching & computing…</div>}

          {data && (
            <>
              <InsightCard data={data} />
              <div className="chart-header">
                <h3>{hazardMeta(data.hazard).metric} per year</h3>
                <ExportButtons params={toParams(form)} />
              </div>
              <TrendChart series={data.series} hazard={data.hazard} />
              {data.cached && <p className="cache-note">⚡ Served from cache.</p>}
            </>
          )}

          {!data && !loading && !error && (
            <div className="empty">Pick a region and press Analyze.</div>
          )}
        </main>
      </div>

      <footer className="app-footer">
        Data: Open-Meteo ERA5 ·{" "}
        {data?.hazard_definition ||
          "Heatwave = 3+ consecutive days above the regional 95th percentile of daily max temperature."}
      </footer>
    </div>
  );
}
