import { exportUrl } from "../api/client.js";

export default function ExportButtons({ params }) {
  return (
    <div className="export-row">
      <span>Export:</span>
      <a className="btn-ghost" href={exportUrl(params, "csv")} target="_blank" rel="noreferrer">
        CSV
      </a>
      <a className="btn-ghost" href={exportUrl(params, "pdf")} target="_blank" rel="noreferrer">
        PDF
      </a>
    </div>
  );
}
