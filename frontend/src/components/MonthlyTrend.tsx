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
import { useEffect, useRef, useState } from "react"

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

interface DatasetMonthly {
	yearMonthly: Record<string, number[]>
	label: string
}

interface MonthlyTrendProps {
	datasets: Record<string, DatasetMonthly>
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

// Darker versions of COLORS for button text (ensures readability on white)
const BUTTON_COLORS = [
	"#3b5d82",
	"#c06e12",
	"#b8393b",
	"#4e8a85",
	"#3e7837",
	"#b09a1a",
	"#8a5c80",
	"#d06a74",
]

const TYPE_COLORS: Record<string, string> = {
	Sharps: "#e85a1b",
	Encampments: "#7b2d8e",
	"Human Waste": "#8B6914",
}

const VISIBLE_COUNT = 3

function trimPartialYear(vals: number[]): (number | null)[] {
	// Find last month with actual data (non-zero)
	let lastNonZero = -1
	for (let i = vals.length - 1; i >= 0; i--) {
		if (vals[i] > 0) {
			lastNonZero = i
			break
		}
	}
	if (lastNonZero === -1) return vals
	// If trailing zeros exist, the last non-zero month is partial (data
	// released monthly) — cut it off too so the line doesn't plunge
	if (lastNonZero < vals.length - 1) {
		const cutoff = lastNonZero - 1
		return vals.map((v, i) => (i > cutoff ? null : v))
	}
	return vals
}

export default function MonthlyTrend({ datasets }: MonthlyTrendProps) {
	const canvasRef = useRef<HTMLCanvasElement>(null)
	const chartRef = useRef<Chart | null>(null)
	const types = Object.keys(datasets)
	const [activeType, setActiveType] = useState(types[0])
	const [, setToggle] = useState(0)

	const rawYearMonthly = datasets[activeType]?.yearMonthly ?? {}
	// Filter out years with no data (all zeros)
	const yearMonthly = Object.fromEntries(
		Object.entries(rawYearMonthly).filter(([, vals]) => vals.some((v) => v > 0)),
	)

	useEffect(() => {
		if (!canvasRef.current) return

		const entries = Object.entries(yearMonthly)

		const datasets = entries.map(([yr, vals], i) => ({
			label: yr,
			data: trimPartialYear(vals),
			borderColor: COLORS[i % COLORS.length],
			backgroundColor: `${COLORS[i % COLORS.length]}22`,
			borderWidth: 2,
			pointRadius: 3,
			tension: 0.3,
			fill: false,
			hidden: i < entries.length - VISIBLE_COUNT,
			spanGaps: false,
		}))

		chartRef.current = new Chart(canvasRef.current, {
			type: "line",
			data: { labels: MONTHS_SHORT, datasets },
			options: {
				responsive: true,
				plugins: {
					legend: {
						labels: {
							font: { size: 12, weight: "bold" },
							boxWidth: 14,
							padding: 10,
							generateLabels(chart) {
								const original = Chart.defaults.plugins.legend.labels.generateLabels(chart)
								return original.map((label) => ({
									...label,
									fontColor: label.hidden ? "#aaa" : "#333",
								}))
							},
						},
					},
				},
				scales: {
					x: {
						ticks: { font: { size: 10 } },
						grid: { color: "rgba(0,0,0,0.05)" },
					},
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

	const hiddenCount = Object.keys(yearMonthly).length - VISIBLE_COUNT

	function showAll() {
		const chart = chartRef.current
		if (!chart) return
		for (const ds of chart.data.datasets) ds.hidden = false
		chart.update()
		setToggle((t) => t + 1)
	}

	function hideAll() {
		const chart = chartRef.current
		if (!chart) return
		for (const ds of chart.data.datasets) ds.hidden = true
		chart.update()
		setToggle((t) => t + 1)
	}

	function soloYear(index: number) {
		const chart = chartRef.current
		if (!chart) return
		for (let i = 0; i < chart.data.datasets.length; i++) {
			chart.data.datasets[i].hidden = i !== index
		}
		chart.update()
		setToggle((t) => t + 1)
	}

	return (
		<div className="card" style={{ padding: "20px 20px 16px" }}>
			<div
				style={{
					display: "flex",
					alignItems: "baseline",
					justifyContent: "space-between",
					flexWrap: "wrap",
					gap: 8,
					marginBottom: 4,
				}}
			>
				<div className="card-title" style={{ margin: 0 }}>
					Monthly Trend by Year
				</div>
				<div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
					<button type="button" aria-label="Show all years" onClick={showAll} style={btnStyle}>
						Show all
					</button>
					<button type="button" aria-label="Hide all years" onClick={hideAll} style={btnStyle}>
						Clear
					</button>
				</div>
			</div>
			{types.length > 1 && (
				<div style={{ display: "flex", gap: "8px", flexWrap: "wrap", margin: "8px 0 4px" }}>
					{types.map((t) => (
						<button
							key={t}
							type="button"
							aria-label={`Show ${t} monthly trend`}
							onClick={() => setActiveType(t)}
							style={{
								padding: "3px 10px",
								fontSize: "11px",
								border: `1px solid ${TYPE_COLORS[t] || "#999"}`,
								borderRadius: "12px",
								background: activeType === t ? TYPE_COLORS[t] || "#999" : "transparent",
								color: activeType === t ? "#fff" : TYPE_COLORS[t] || "#999",
								cursor: "pointer",
								fontFamily: "inherit",
								fontWeight: activeType === t ? 600 : 400,
							}}
						>
							{t}
							{t === "Human Waste" && (
								<span style={{ fontSize: "9px", opacity: 0.7, marginLeft: 2 }}> (beta)</span>
							)}
						</button>
					))}
				</div>
			)}
			{hiddenCount > 0 && (
				<div
					style={{
						fontSize: "11px",
						color: "#888",
						marginBottom: 4,
					}}
				>
					Click a year in the legend to toggle it. {hiddenCount} older years hidden by default.
				</div>
			)}
			<div style={{ padding: "4px 0" }}>
				<canvas ref={canvasRef} height={180} aria-label="Monthly trend line chart by year" />
			</div>
			<div
				style={{
					display: "flex",
					flexWrap: "wrap",
					gap: 4,
					marginTop: 6,
				}}
			>
				{Object.keys(yearMonthly).map((yr, i) => (
					<button
						type="button"
						key={yr}
						onClick={() => soloYear(i)}
						style={{
							...btnStyle,
							color: BUTTON_COLORS[i % BUTTON_COLORS.length],
							borderColor: COLORS[i % COLORS.length],
							fontSize: "10px",
							padding: "1px 6px",
						}}
					>
						Only {yr}
					</button>
				))}
			</div>
		</div>
	)
}

const btnStyle: React.CSSProperties = {
	background: "none",
	border: "1px solid #ccc",
	borderRadius: "4px",
	padding: "2px 8px",
	fontSize: "11px",
	color: "#555",
	cursor: "pointer",
	lineHeight: "1.6",
}
