import {
	CategoryScale,
	Chart,
	Legend,
	LinearScale,
	LineController,
	LineElement,
	PointElement,
	Tooltip,
} from "chart.js"
import { useEffect, useRef } from "react"

Chart.register(
	LineController,
	LineElement,
	PointElement,
	CategoryScale,
	LinearScale,
	Tooltip,
	Legend,
)
Chart.defaults.font.family = '"Source Sans 3", system-ui, sans-serif'

interface MonthlyTrendProps {
	yearMonthly: Record<string, number[]>
}

const MONTHS_SHORT = [
	"Jan",
	"Feb",
	"Mar",
	"Apr",
	"May",
	"Jun",
	"Jul",
	"Aug",
	"Sep",
	"Oct",
	"Nov",
	"Dec",
]
const COLORS = [
	"#4e79a7",
	"#f28e2b",
	"#e15759",
	"#76b7b2",
	"#59a14f",
	"#edc949",
	"#af7aa1",
	"#ff9da7",
]

export default function MonthlyTrend({ yearMonthly }: MonthlyTrendProps) {
	const canvasRef = useRef<HTMLCanvasElement>(null)
	const chartRef = useRef<Chart | null>(null)

	useEffect(() => {
		if (!canvasRef.current) return

		const datasets = Object.entries(yearMonthly).map(([yr, vals], i) => ({
			label: yr,
			data: vals,
			borderColor: COLORS[i % COLORS.length],
			backgroundColor: `${COLORS[i % COLORS.length]}22`,
			borderWidth: 2,
			pointRadius: 3,
			tension: 0.3,
			fill: false,
		}))

		chartRef.current = new Chart(canvasRef.current, {
			type: "line",
			data: { labels: MONTHS_SHORT, datasets },
			options: {
				responsive: true,
				plugins: {
					legend: { labels: { font: { size: 11 }, boxWidth: 12 } },
				},
				scales: {
					x: { ticks: { font: { size: 10 } }, grid: { color: "rgba(0,0,0,0.05)" } },
					y: {
						ticks: { font: { size: 10 } },
						grid: { color: "rgba(0,0,0,0.05)" },
						title: { display: true, text: "Cases", font: { size: 10 } },
					},
				},
			},
		})

		return () => {
			chartRef.current?.destroy()
		}
	}, [yearMonthly])

	return (
		<div className="card" style={{ padding: "20px 20px 16px" }}>
			<div className="card-title">Monthly Trend by Year</div>
			<div style={{ padding: "4px 0" }}>
				<canvas ref={canvasRef} height={180} />
			</div>
		</div>
	)
}
