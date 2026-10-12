import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js";
import { Chart } from "react-chartjs-2";

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

// Least-squares line over (year, value) for the trend overlay.
function regressionLine(years, values) {
  const n = years.length;
  if (n < 2) return values.map(() => null);
  const xm = years.reduce((a, b) => a + b, 0) / n;
  const ym = values.reduce((a, b) => a + b, 0) / n;
  let sxx = 0;
  let sxy = 0;
  for (let i = 0; i < n; i++) {
    sxx += (years[i] - xm) ** 2;
    sxy += (years[i] - xm) * (values[i] - ym);
  }
  const slope = sxx ? sxy / sxx : 0;
  const intercept = ym - slope * xm;
  return years.map((y) => Math.max(0, slope * y + intercept));
}

export default function TrendChart({ series }) {
  const years = series.map((p) => p.year);
  const days = series.map((p) => p.heatwave_days);
  const rolling = series.map((p) => p.rolling_mean);
  const trend = regressionLine(years, days);

  const styles = getComputedStyle(document.documentElement);
  const accent = styles.getPropertyValue("--accent").trim() || "#1f6f54";
  const line = styles.getPropertyValue("--chart-line").trim() || "#e07a3c";
  const grid = styles.getPropertyValue("--grid").trim() || "rgba(128,128,128,0.2)";
  const text = styles.getPropertyValue("--text").trim() || "#222";

  const data = {
    labels: years,
    datasets: [
      {
        type: "bar",
        label: "Heatwave days / year",
        data: days,
        backgroundColor: accent + "cc",
        borderRadius: 3,
        order: 3,
      },
      {
        type: "line",
        label: "5-yr rolling average",
        data: rolling,
        borderColor: line,
        backgroundColor: line,
        borderWidth: 2,
        pointRadius: 0,
        spanGaps: true,
        tension: 0.3,
        order: 1,
      },
      {
        type: "line",
        label: "Linear trend",
        data: trend,
        borderColor: text,
        borderDash: [6, 4],
        borderWidth: 1.5,
        pointRadius: 0,
        order: 2,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { labels: { color: text, usePointStyle: true } },
      tooltip: {
        callbacks: {
          afterBody: (items) => {
            const i = items[0].dataIndex;
            const p = series[i];
            return [
              `Events: ${p.heatwave_events}`,
              `Mean duration: ${p.mean_duration} d`,
              p.max_intensity != null ? `Peak intensity: ${p.max_intensity} °C` : "",
              `Data coverage: ${Math.round(p.coverage * 100)}%`,
            ].filter(Boolean);
          },
        },
      },
    },
    scales: {
      x: { ticks: { color: text, maxRotation: 0, autoSkipPadding: 16 }, grid: { color: grid } },
      y: {
        beginAtZero: true,
        title: { display: true, text: "Days", color: text },
        ticks: { color: text },
        grid: { color: grid },
      },
    },
  };

  return (
    <div className="chart-box">
      <Chart type="bar" data={data} options={options} />
    </div>
  );
}
