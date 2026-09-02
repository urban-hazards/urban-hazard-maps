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

type Monthly = Record<string, number>

export interface MattressData {
	generated: string
	ckan_through: string
	open311_through: string
	open311_last_full_month: string
	mattress_pickup: {
		monthly: Monthly
		first_month: string | null
		last_month: string | null
		total: number
		automation_closures: number
		by_source: Record<string, number>
	}
	ckan_types_monthly: Record<string, Monthly>
	closure_mentions_monthly: Monthly
	open311: Record<string, { total: Monthly; mattress: Monthly; samples: string[] }>
}

interface Props {
	data: MattressData
	/** YYYY-MM 311 began logging Mattress_Pickup cases. */
	buttonMonth: string
	/** YYYY-MM of the last Mattress_Pickup cases (self-service scheduler replaced 311 intake). */
	cutoffMonth: string
}

// Validated categorical order (dataviz validator, light surface): blue, orange, aqua, yellow.
const SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
const QUEUE_LABELS: Record<string, string> = {
	"illegal-trash": "Improper Storage of Trash",
	"street-cleaning": "Requests for Street Cleaning",
	other: "General Request (“Other”)",
}
const QUEUE_ORDER = ["illegal-trash", "street-cleaning", "other"]

function monthRange(from: string, to: string): string[] {
	const out: string[] = []
	let [y, m] = from.split("-").map(Number)
	const [ty, tm] = to.split("-").map(Number)
	while (y < ty || (y === ty && m <= tm)) {
		out.push(`${y}-${String(m).padStart(2, "0")}`)
		m += 1
		if (m > 12) {
			m = 1
			y += 1
		}
	}
	return out
}

function shiftMonth(ym: string, delta: number): string {
	const [y, m] = ym.split("-").map(Number)
	const idx = y * 12 + (m - 1) + delta
	return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2, "0")}`
}

function shortLabel(ym: string): string {
	const [y, m] = ym.split("-")
	const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
	return m === "01" ? `${names[0]} ${y}` : names[Number(m) - 1]
}

/** Vertical rule at a labelled month — drawn as a chart.js inline plugin. */
function markerPlugin(months: string[], marks: { month: string; label: string }[]) {
	return {
		id: "monthMarkers",
		afterDraw(chart: Chart) {
			const { ctx, chartArea, scales } = chart
			const x = scales.x
			if (!x || !chartArea) return
			ctx.save()
			for (const mark of marks) {
				const i = months.indexOf(mark.month)
				if (i < 0) continue
				const px = x.getPixelForValue(i)
				ctx.strokeStyle = "#6b6b66"
				ctx.setLineDash([4, 4])
				ctx.lineWidth = 1
				ctx.beginPath()
				ctx.moveTo(px, chartArea.top)
				ctx.lineTo(px, chartArea.bottom)
				ctx.stroke()
				ctx.setLineDash([])
				ctx.fillStyle = "#4a4a46"
				ctx.font = "600 11px system-ui, sans-serif"
				ctx.textAlign = "left"
				ctx.fillText(mark.label, px + 4, chartArea.top + 12)
			}
			ctx.restore()
		},
	}
}

function useLineChart(
	canvasRef: React.RefObject<HTMLCanvasElement | null>,
	months: string[],
	series: { label: string; data: (number | null)[]; color: string }[],
	marks: { month: string; label: string }[],
	yTitle: string,
) {
	useEffect(() => {
		if (!canvasRef.current) return
		const chart = new Chart(canvasRef.current, {
			type: "line",
			data: {
				labels: months,
				datasets: series.map((s) => ({
					label: s.label,
					data: s.data,
					borderColor: s.color,
					backgroundColor: s.color,
					borderWidth: 2,
					pointRadius: 0,
					pointHoverRadius: 5,
					pointHitRadius: 12,
					tension: 0.25,
					spanGaps: false,
				})),
			},
			plugins: [markerPlugin(months, marks)],
			options: {
				responsive: true,
				maintainAspectRatio: false,
				interaction: { mode: "index", intersect: false },
				plugins: {
					legend: {
						display: series.length > 1,
						labels: { boxWidth: 14, padding: 12, font: { size: 12, weight: "bold" } },
					},
					tooltip: {
						callbacks: {
							title: (items) => months[items[0].dataIndex],
						},
					},
				},
				scales: {
					x: {
						grid: { display: false },
						ticks: {
							maxRotation: 0,
							autoSkip: false,
							font: { size: 11 },
							// Always label January (with year); label every 3rd month otherwise.
							callback: (_v, i) => {
								const ym = months[i]
								if (ym.endsWith("-01")) return shortLabel(ym)
								return (i - months.findIndex((m) => m.endsWith("-01"))) % 3 === 0
									? shortLabel(ym)
									: ""
							},
						},
					},
					y: {
						beginAtZero: true,
						title: { display: true, text: yTitle, font: { size: 11 } },
						grid: { color: "#e6e6e2" },
						ticks: { font: { size: 11 } },
					},
				},
			},
		})
		return () => chart.destroy()
	}, [canvasRef, months, series, marks, yTitle])
}

function sumWindow(
	m: Monthly,
	from: string,
	count: number,
	lastMonth: string,
): { total: number; months: number } {
	let total = 0
	let months = 0
	for (const ym of monthRange(from, shiftMonth(from, count - 1))) {
		if (ym > lastMonth) break
		total += m[ym] ?? 0
		months += 1
	}
	return { total, months }
}

function pct(a: number, b: number): string {
	if (!a) return "—"
	const d = ((b - a) / a) * 100
	return `${d > 0 ? "+" : ""}${d.toFixed(0)}%`
}

export default function MattressCharts({ data, buttonMonth, cutoffMonth }: Props) {
	const pickupRef = useRef<HTMLCanvasElement>(null)
	const mentionsRef = useRef<HTMLCanvasElement>(null)
	const [showTable, setShowTable] = useState(false)

	// --- Chart 1: the Mattress_Pickup case type, birth to cliff ---------------
	const mp = data.mattress_pickup.monthly
	const pickupMonths = monthRange(shiftMonth(buttonMonth, -3), shiftMonth(cutoffMonth, 3))
	const pickupSeries = [
		{
			label: "Mattress_Pickup cases",
			data: pickupMonths.map((ym) => mp[ym] ?? 0),
			color: SERIES_COLORS[0],
		},
	]
	useLineChart(
		pickupRef,
		pickupMonths,
		pickupSeries,
		[
			{ month: buttonMonth, label: "311 starts taking mattress calls" },
			{ month: cutoffMonth, label: "Self-service scheduler launches" },
		],
		"Cases per month",
	)

	// --- Chart 2: citizen mattress complaints in the queues that never had a button
	const lastFull = data.open311_last_full_month
	const mentionMonths = monthRange("2023-01", lastFull)
	const mentionSeries = QUEUE_ORDER.map((slug, i) => ({
		label: QUEUE_LABELS[slug],
		data: mentionMonths.map((ym) => data.open311[slug]?.mattress[ym] ?? 0),
		color: SERIES_COLORS[i],
	}))
	useLineChart(
		mentionsRef,
		mentionMonths,
		mentionSeries,
		[{ month: cutoffMonth, label: "Self-service scheduler launches" }],
		"Complaints mentioning a mattress",
	)

	// --- Before/after table ---------------------------------------------------
	const years = Array.from(new Set(mentionMonths.map((ym) => ym.slice(0, 4))))
	const yearly = (m: Monthly, y: string) =>
		Object.entries(m)
			.filter(([ym]) => ym.startsWith(y))
			.reduce((a, [, v]) => a + v, 0)
	const rows = QUEUE_ORDER.map((slug) => ({
		label: QUEUE_LABELS[slug],
		values: years.map((y) => yearly(data.open311[slug]?.mattress ?? {}, y)),
	}))
	const totalRow = {
		label: "All three queues",
		values: years.map((_, i) => rows.reduce((a, r) => a + r.values[i], 0)),
	}

	const before = sumWindow(
		QUEUE_ORDER.reduce<Monthly>((acc, slug) => {
			for (const [ym, v] of Object.entries(data.open311[slug]?.mattress ?? {}))
				acc[ym] = (acc[ym] ?? 0) + v
			return acc
		}, {}),
		cutoffMonth === buttonMonth ? shiftMonth(buttonMonth, -12) : shiftMonth(cutoffMonth, -12),
		12,
		lastFull,
	)
	const after = sumWindow(
		QUEUE_ORDER.reduce<Monthly>((acc, slug) => {
			for (const [ym, v] of Object.entries(data.open311[slug]?.mattress ?? {}))
				acc[ym] = (acc[ym] ?? 0) + v
			return acc
		}, {}),
		shiftMonth(cutoffMonth, 1),
		12,
		lastFull,
	)

	return (
		<div className="mattress-charts">
			<figure className="chart-figure">
				<figcaption>
					<strong>Mattress pickup cases in Boston 311, by month.</strong> The case type appears in{" "}
					{shortLabel(buttonMonth)} and disappears after {cutoffMonth}. Source: data.boston.gov 311
					export.
				</figcaption>
				<div className="chart-box" style={{ height: 260 }}>
					<canvas ref={pickupRef} aria-label="Mattress pickup 311 cases per month" />
				</div>
			</figure>

			<figure className="chart-figure">
				<figcaption>
					<strong>Citizen reports mentioning a mattress, by month and queue.</strong> Counted from
					the free-text description on each report (the public bulk export strips this field).
					Source: Open311 API, through {data.open311_through}.
				</figcaption>
				<div className="chart-box" style={{ height: 300 }}>
					<canvas
						ref={mentionsRef}
						aria-label="Monthly citizen reports mentioning a mattress, by queue"
					/>
				</div>
			</figure>

			<div className="before-after">
				<div className="stat-item">
					<span className="stat-number">
						{Math.round(before.total / Math.max(before.months, 1))}
					</span>
					<span className="stat-desc">
						mattress complaints / month, 12 months before the scheduler launched
					</span>
				</div>
				<div className="stat-item">
					<span className="stat-number">{Math.round(after.total / Math.max(after.months, 1))}</span>
					<span className="stat-desc">mattress complaints / month, 12 months after</span>
				</div>
				<div className="stat-item">
					<span className="stat-number">
						{pct(
							before.total / Math.max(before.months, 1),
							after.total / Math.max(after.months, 1),
						)}
					</span>
					<span className="stat-desc">change</span>
				</div>
			</div>

			<button type="button" className="table-toggle" onClick={() => setShowTable((v) => !v)}>
				{showTable ? "Hide" : "Show"} yearly table
			</button>
			{showTable && (
				<div className="table-wrap">
					<table className="data-table">
						<thead>
							<tr>
								<th>Queue</th>
								{years.map((y) => (
									<th key={y}>
										{y}
										{y === lastFull.slice(0, 4) ? ` (thru ${lastFull.slice(5)})` : ""}
									</th>
								))}
							</tr>
						</thead>
						<tbody>
							{[...rows, totalRow].map((r) => (
								<tr key={r.label}>
									<td>{r.label}</td>
									{r.values.map((v, i) => (
										<td key={years[i]}>{v.toLocaleString()}</td>
									))}
								</tr>
							))}
						</tbody>
					</table>
				</div>
			)}
		</div>
	)
}
