import { BarController, BarElement, CategoryScale, Chart, LinearScale, Tooltip } from "chart.js"
import { useEffect, useRef, useState } from "react"

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip)
Chart.defaults.font.family = '"Source Sans 3", system-ui, sans-serif'

interface DatasetInfo {
	hourly: number[]
	yearHourly: Record<string, number[]>
	hoodHourly: Record<string, number[]>
	zipHourly: Record<string, number[]>
	years: number[]
	hoods: string[]
	zips: string[]
}

interface HourlyChartProps {
	datasets: Record<string, DatasetInfo>
}

const HOUR_LABELS = Array.from({ length: 24 }, (_, i) => {
	if (i === 0) return "12a"
	if (i < 12) return `${i}a`
	if (i === 12) return "12p"
	return `${i - 12}p`
})

const TYPE_COLORS: Record<string, string> = {
	Sharps: "#4e79a7",
	Encampments: "#e15759",
	"Human Waste": "#76b7b2",
}

type FilterMode = "year" | "hood" | "zip"

export default function HourlyChart({ datasets }: HourlyChartProps) {
	const canvasRef = useRef<HTMLCanvasElement>(null)
	const chartRef = useRef<Chart | null>(null)
	const [activeType, setActiveType] = useState("Sharps")
	const [filterMode, setFilterMode] = useState<FilterMode>("year")
	const [activeYear, setActiveYear] = useState("all")
	const [activeHood, setActiveHood] = useState("all")
	const [activeZip, setActiveZip] = useState("all")

	const datasetInfo = datasets[activeType]
	const yearHourly = datasetInfo.yearHourly ?? {}
	const hoodHourly = datasetInfo.hoodHourly ?? {}
	const zipHourly = datasetInfo.zipHourly ?? {}

	let hourly: number[]
	if (filterMode === "year") {
		hourly =
			activeYear === "all"
				? (datasetInfo.hourly ?? Array(24).fill(0))
				: (yearHourly[activeYear] ?? Array(24).fill(0))
	} else if (filterMode === "hood") {
		hourly =
			activeHood === "all"
				? (datasetInfo.hourly ?? Array(24).fill(0))
				: (hoodHourly[activeHood] ?? Array(24).fill(0))
	} else {
		hourly =
			activeZip === "all"
				? (datasetInfo.hourly ?? Array(24).fill(0))
				: (zipHourly[activeZip] ?? Array(24).fill(0))
	}

	useEffect(() => {
		if (!canvasRef.current) return

		const maxVal = Math.max(...hourly)
		const baseColor = TYPE_COLORS[activeType] || "#4e79a7"
		const colors = hourly.map((v) => {
			const t = maxVal > 0 ? v / maxVal : 0
			if (t > 0.7) return "#cc0000"
			if (t > 0.4) return "#ff8800"
			return baseColor
		})

		chartRef.current = new Chart(canvasRef.current, {
			type: "bar",
			data: {
				labels: HOUR_LABELS,
				datasets: [
					{
						data: hourly,
						backgroundColor: colors,
						borderWidth: 0,
						borderRadius: 2,
					},
				],
			},
			options: {
				responsive: true,
				plugins: { legend: { display: false } },
				scales: {
					x: { ticks: { font: { size: 9 }, maxRotation: 0 }, grid: { display: false } },
					y: { ticks: { font: { size: 10 } }, grid: { color: "rgba(0,0,0,0.05)" } },
				},
			},
		})

		return () => {
			chartRef.current?.destroy()
		}
	}, [hourly, activeType])

	const types = Object.keys(datasets)
	const years = datasetInfo.years ?? []
	const hoods = datasetInfo.hoods ?? []
	const zips = datasetInfo.zips ?? []

	return (
		<div className="card" style={{ padding: "20px 20px 16px" }}>
			<div className="card-title">Requests by Hour of Day</div>

			{/* Type toggle */}
			<div style={{ display: "flex", gap: "8px", flexWrap: "wrap", margin: "8px 0" }}>
				{types.map((t) => (
					<button
						key={t}
						type="button"
						aria-label={`Show ${t} hourly data`}
						onClick={() => {
							setActiveType(t)
							setActiveYear("all")
							setActiveHood("all")
							setActiveZip("all")
						}}
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

			{/* Filter mode tabs */}
			<div
				style={{
					display: "flex",
					gap: "4px",
					marginBottom: "6px",
					borderBottom: "1px solid #e0e0e0",
					paddingBottom: "6px",
				}}
			>
				{(
					[
						["year", "By Year"],
						["hood", "By Neighborhood"],
						["zip", "By Zip"],
					] as const
				).map(([mode, label]) => (
					<button
						key={mode}
						type="button"
						onClick={() => setFilterMode(mode)}
						style={{
							padding: "3px 10px",
							fontSize: "11px",
							border: "none",
							borderBottom: filterMode === mode ? "2px solid #555" : "2px solid transparent",
							background: "none",
							color: filterMode === mode ? "#333" : "#999",
							cursor: "pointer",
							fontFamily: "inherit",
							fontWeight: filterMode === mode ? 600 : 400,
						}}
					>
						{label}
					</button>
				))}
			</div>

			{/* Filter options */}
			{filterMode === "year" && (
				<div style={{ display: "flex", gap: "4px", flexWrap: "wrap", marginBottom: "8px" }}>
					<PillButton
						active={activeYear === "all"}
						onClick={() => setActiveYear("all")}
						label="All"
					/>
					{years.map((y) => (
						<PillButton
							key={y}
							active={activeYear === String(y)}
							onClick={() => setActiveYear(String(y))}
							label={String(y)}
						/>
					))}
				</div>
			)}

			{filterMode === "hood" && (
				<div style={{ marginBottom: "8px" }}>
					<select
						value={activeHood}
						onChange={(e) => setActiveHood(e.target.value)}
						style={selectStyle}
					>
						<option value="all">All Neighborhoods</option>
						{hoods.map((h) => (
							<option key={h} value={h}>
								{h}
							</option>
						))}
					</select>
				</div>
			)}

			{filterMode === "zip" && (
				<div style={{ marginBottom: "8px" }}>
					<select
						value={activeZip}
						onChange={(e) => setActiveZip(e.target.value)}
						style={selectStyle}
					>
						<option value="all">All Zip Codes</option>
						{zips.map((z) => (
							<option key={z} value={z}>
								{z}
							</option>
						))}
					</select>
				</div>
			)}

			<div style={{ padding: "4px 0" }}>
				<canvas ref={canvasRef} height={120} aria-label="Requests by hour of day bar chart" />
			</div>
		</div>
	)
}

function PillButton({
	active,
	onClick,
	label,
}: {
	active: boolean
	onClick: () => void
	label: string
}) {
	return (
		<button
			type="button"
			aria-label={`Show ${label}`}
			onClick={onClick}
			style={{
				padding: "3px 10px",
				fontSize: "11px",
				border: "1px solid #ccc",
				borderRadius: "10px",
				background: active ? "#555" : "transparent",
				color: active ? "#fff" : "#555",
				cursor: "pointer",
				fontFamily: "inherit",
				fontWeight: active ? 600 : 400,
			}}
		>
			{label}
		</button>
	)
}

const selectStyle: React.CSSProperties = {
	padding: "4px 8px",
	fontSize: "12px",
	border: "1px solid #ccc",
	borderRadius: "6px",
	background: "#fff",
	color: "#333",
	fontFamily: "inherit",
	cursor: "pointer",
	width: "100%",
	maxWidth: 220,
}
