import { useEffect, useState } from "react";
import { getRegions } from "../api/client.js";

export default function RegionPicker({ value, onChange }) {
  const [presets, setPresets] = useState([]);

  useEffect(() => {
    getRegions()
      .then(setPresets)
      .catch(() => setPresets([]));
  }, []);

  const handlePreset = (e) => {
    const p = presets.find((r) => r.name === e.target.value);
    if (p) onChange({ lat: p.lat, lon: p.lon, region_name: p.name });
  };

  return (
    <div className="field-group">
      <label className="field">
        <span>Region preset</span>
        <select value={value.region_name || ""} onChange={handlePreset}>
          <option value="" disabled>
            Select a city…
          </option>
          {presets.map((r) => (
            <option key={r.name} value={r.name}>
              {r.name}
            </option>
          ))}
        </select>
      </label>

      <div className="latlon">
        <label className="field">
          <span>Latitude</span>
          <input
            type="number"
            step="0.0001"
            min="-90"
            max="90"
            value={value.lat}
            onChange={(e) =>
              onChange({ lat: parseFloat(e.target.value), region_name: null })
            }
          />
        </label>
        <label className="field">
          <span>Longitude</span>
          <input
            type="number"
            step="0.0001"
            min="-180"
            max="180"
            value={value.lon}
            onChange={(e) =>
              onChange({ lon: parseFloat(e.target.value), region_name: null })
            }
          />
        </label>
      </div>
    </div>
  );
}
