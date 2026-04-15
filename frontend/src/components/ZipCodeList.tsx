import { useState } from "react"
import type { ZipStat } from "../lib/types"

interface DatasetZips {
	zipStats: ZipStat[]
	yearZips: Record<string, ZipStat[]>
	years: number[]
	label: string
}

interface ZipCodeListProps {
	datasets: Record<string, DatasetZips>
}

const TYPE_COLORS: Record<string, string> = {
	Sharps: "#76b7b2",
	Encampments: "#7b2d8e",
	"Human Waste": "#8B6914",
}

function formatNumber(n: number): string {
	return n.toLocaleString()
}

export default function ZipCodeList({ datasets }: ZipCodeListProps) {
	const types = Object.keys(datasets)
	const [activeType, setActiveType] = useState(types[0])
	const [activeYear, setActiveYear] = useState("all")

	const dataset = datasets[activeType]
	const zipStats =
		activeYear === "all" ? (dataset?.zipStats ?? []) : (dataset?.yearZips[activeYear] ?? [])
	const years = dataset?.years ?? []
	const maxCount = zipStats[0]?.count ?? 1
	const color = TYPE_COLORS[activeType] || "#76b7b2"

	return (
		<section className="section" aria-label="Top zip codes">
			<h2 style={sectionTitleStyle}>Top Zip Codes</h2>

			{types.length > 1 && (
				<div style={{ display: "flex", gap: "8px", flexWrap: "wrap", margin: "8px 0 12px" }}>
					{types.map((t) => (
						<button
							key={t}
							type="button"
							aria-label={`Show ${t} zip code data`}
							onClick={() => setActiveType(t)}
							style={{
								padding: "4px 12px",
								fontSize: "12px",
								border: `1px solid ${TYPE_COLORS[t] || "#999"}`,
								borderRadius: "14px",
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

			{years.length > 1 && (
				<div style={{ display: "flex", gap: "4px", flexWrap: "wrap", marginBottom: "12px" }}>
					<button
						type="button"
						aria-label="Show all years"
						onClick={() => setActiveYear("all")}
						style={{
							padding: "2px 8px",
							fontSize: "10px",
							border: "1px solid #ccc",
							borderRadius: "10px",
							background: activeYear === "all" ? "#555" : "transparent",
							color: activeYear === "all" ? "#fff" : "#666",
							cursor: "pointer",
							fontFamily: "inherit",
							fontWeight: activeYear === "all" ? 600 : 400,
						}}
					>
						All Years
					</button>
					{[...years].reverse().map((y) => (
						<button
							key={y}
							type="button"
							aria-label={`Show year ${y}`}
							onClick={() => setActiveYear(String(y))}
							style={{
								padding: "2px 8px",
								fontSize: "10px",
								border: "1px solid #ccc",
								borderRadius: "10px",
								background: activeYear === String(y) ? "#555" : "transparent",
								color: activeYear === String(y) ? "#fff" : "#666",
								cursor: "pointer",
								fontFamily: "inherit",
								fontWeight: activeYear === String(y) ? 600 : 400,
							}}
						>
							{y}
						</button>
					))}
				</div>
			)}

			{zipStats.length > 0 && (
				<p style={descStyle}>
					The most active zip codes for <strong>{activeType.toLowerCase()}</strong> requests, led by{" "}
					<strong>{zipStats[0].zip}</strong> with <strong>{formatNumber(zipStats[0].count)}</strong>{" "}
					reports.
				</p>
			)}

			<div className="card">
				<div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
					{zipStats.map((z) => {
						const barWidth = Math.max(2, Math.round((z.count / maxCount) * 100))
						return (
							<div key={z.zip} style={rowStyle}>
								<span style={labelStyle}>{z.zip}</span>
								<div style={barWrapStyle}>
									<div
										style={{
											height: 10,
											borderRadius: 5,
											background: color,
											width: `${barWidth}%`,
										}}
									/>
								</div>
								<span style={countStyle}>{formatNumber(z.count)}</span>
							</div>
						)
					})}
				</div>
			</div>
		</section>
	)
}

const sectionTitleStyle: React.CSSProperties = {
	fontSize: "var(--fs-xl, 20px)",
	fontWeight: 700,
	marginBottom: 4,
}

const descStyle: React.CSSProperties = {
	fontSize: "var(--fs-base, 14px)",
	color: "var(--color-text-muted, #666)",
	marginBottom: 16,
	maxWidth: 800,
	lineHeight: 1.6,
}

const rowStyle: React.CSSProperties = {
	display: "flex",
	alignItems: "center",
	gap: 10,
	fontSize: "var(--fs-sm, 13px)",
}

const labelStyle: React.CSSProperties = {
	width: 55,
	color: "var(--color-text-muted, #666)",
	fontWeight: 600,
	flexShrink: 0,
	fontVariantNumeric: "tabular-nums",
}

const barWrapStyle: React.CSSProperties = {
	flex: 1,
	background: "var(--color-border-light, #f0f0f0)",
	borderRadius: 5,
	overflow: "hidden",
}

const countStyle: React.CSSProperties = {
	width: 55,
	textAlign: "right",
	color: "var(--color-text, #1a1a1a)",
	fontWeight: 600,
	fontVariantNumeric: "tabular-nums",
}
