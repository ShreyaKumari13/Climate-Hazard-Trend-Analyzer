/**
 * Guards a failure mode that a production build cannot catch.
 *
 * TrendChart uses the generic <Chart type="bar"> component (needed for the
 * mixed bar + line chart). Unlike <Bar>/<Line>, it does not auto-register its
 * controller, so registering BarElement/LineElement alone compiles perfectly
 * and then throws at runtime:
 *     Error: "bar" is not a registered controller
 *
 * Run: npm run verify
 */
import {
  Chart as ChartJS, CategoryScale, LinearScale,
  BarElement, BarController, PointElement, LineElement, LineController,
  Title, Tooltip, Legend,
} from "chart.js";

ChartJS.register(
  CategoryScale, LinearScale, BarElement, BarController,
  PointElement, LineElement, LineController, Title, Tooltip, Legend
);

const REQUIRED_CONTROLLERS = ["bar", "line"];
const REQUIRED_SCALES = ["category", "linear"];

let failed = false;
for (const id of REQUIRED_CONTROLLERS) {
  try {
    ChartJS.registry.getController(id);
    console.log(`  ok   controller "${id}"`);
  } catch (e) {
    failed = true;
    console.error(`  FAIL controller "${id}": ${e.message}`);
  }
}
for (const id of REQUIRED_SCALES) {
  try {
    ChartJS.registry.getScale(id);
    console.log(`  ok   scale "${id}"`);
  } catch (e) {
    failed = true;
    console.error(`  FAIL scale "${id}": ${e.message}`);
  }
}

if (failed) {
  console.error("\nChart.js registry incomplete - the dashboard chart would not render.");
  process.exit(1);
}
console.log("\nChart.js registry complete.");
