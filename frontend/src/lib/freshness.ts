import type { SourceHealth, SourceStatus } from "./types"

export interface Chip {
	key: string
	label: string
	text: string
	status: SourceStatus
	sources: string[]
	disruptedSince: string | null
	latestReport: string
}

export interface FreshnessModel {
	chips: Chip[]
	troubled: Chip[]
	notice: string | null
}

const LABELS: Record<string, string> = {
	needles: "Sharps",
	encampments: "Encampments",
	waste: "Human Waste",
}

/** Subject for the notice sentence ("Encampment reporting …"), singular where English needs it. */
const NOTICE_SUBJECT: Record<string, string> = {
	needles: "Sharps",
	encampments: "Encampment",
	waste: "Human waste",
}

const PLURAL_NOUNS: Record<string, string> = {
	needles: "sharps reports",
	encampments: "encampments",
	waste: "waste reports",
}

/** "Mon D, YYYY" via the local-noon trick, so UTC parsing never shifts the day. */
export const fmt = (d: string): string =>
	d
		? new Date(`${d}T12:00:00`).toLocaleDateString("en-US", {
				month: "short",
				day: "numeric",
				year: "numeric",
			})
		: "unknown"

/** "Mon D" (no year) — used for disrupted-since dates in chips, notice, and the map note. */
export const fmtShort = (d: string): string =>
	d
		? new Date(`${d}T12:00:00`).toLocaleDateString("en-US", {
				month: "short",
				day: "numeric",
			})
		: "unknown"

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/

function addDay(d: string): string {
	if (!ISO_DAY.test(d)) return ""
	const date = new Date(`${d}T12:00:00`)
	date.setDate(date.getDate() + 1)
	const y = date.getFullYear()
	const m = String(date.getMonth() + 1).padStart(2, "0")
	const day = String(date.getDate()).padStart(2, "0")
	return `${y}-${m}-${day}`
}

function okText(label: string, through: string): string {
	return `${label}: data through ${fmt(through)}`
}

function legacyText(label: string, through: string): string {
	return `${label}: data through ${fmt(through)}`
}

/** Degraded: reports still arrive at reduced volume, so keep the "data through" form. */
function degradedText(label: string, through: string): string {
	return `${okText(label, through)} · reporting volume down`
}

function notOkText(label: string, latestReport: string, disruptedSince: string | null): string {
	const base = `${label}: latest report ${fmt(latestReport)}`
	return disruptedSince ? `${base} · reporting disrupted since ${fmtShort(disruptedSince)}` : base
}

const LEGACY_NOTICE = (labels: string[]) =>
	`Boston moved its 311 system to a new platform in 2026. Some categories stopped appearing in the city's data during the switch (${labels.join(", ")}). We show those layers through their last complete date rather than guess.`

/**
 * Derive freshness chips + notice from a source_health.json (or frozen fallback dates when
 * health is unavailable). Handles schema_version < 2 / missing keys via `latest_report ??
 * through` and `disrupted_since ?? null`, per contract.md.
 */
export function freshnessModel(
	health: SourceHealth | null,
	frozen: Record<string, string>,
): FreshnessModel {
	const hasModernSchema = (health?.schema_version ?? 0) >= 2
	const layerEntries = Object.entries(health?.layers ?? {})

	let chips: Chip[]
	if (layerEntries.length > 0) {
		chips = layerEntries.map(([key, layer]) => {
			const label = LABELS[key] ?? key
			const status = layer.status ?? "stale"
			const through = layer.through ?? ""
			if (hasModernSchema) {
				const latestReport = layer.latest_report || through
				const disruptedSince = layer.disrupted_since ?? null
				const text =
					status === "ok"
						? okText(label, through)
						: status === "degraded"
							? degradedText(label, through)
							: notOkText(label, latestReport, disruptedSince)
				return {
					key,
					label,
					text,
					status,
					sources: layer.sources ?? [],
					disruptedSince,
					latestReport,
				}
			}
			return {
				key,
				label,
				text: legacyText(label, through),
				status,
				sources: layer.sources ?? [],
				disruptedSince: null,
				latestReport: through,
			}
		})
	} else {
		chips = Object.entries(frozen)
			.filter(([, d]) => ISO_DAY.test(d))
			.map(([key, d]) => {
				const label = LABELS[key] ?? key
				const disruptedSince = addDay(d) || null
				return {
					key,
					label,
					text: notOkText(label, d, disruptedSince),
					status: "stale" as SourceStatus,
					sources: [],
					disruptedSince,
					latestReport: d,
				}
			})
	}

	const troubled = chips.filter((c) => c.status !== "ok")

	let notice: string | null = null
	if (troubled.length > 0) {
		const sentences = troubled
			.filter((c) => c.disruptedSince || hasModernSchema)
			.map((c) => {
				const plural = PLURAL_NOUNS[c.key] ?? c.label.toLowerCase()
				const subject = NOTICE_SUBJECT[c.key] ?? c.label
				if (!c.disruptedSince) {
					return c.status === "degraded"
						? `${subject} reporting volume has dropped sharply since the switch; recent months may be incomplete.`
						: `${subject} reporting is disrupted; recent months may be incomplete.`
				}
				return `${subject} reporting has been disrupted since ${fmtShort(c.disruptedSince)}; reports that still arrive are shown, but low counts after that date reflect missing data, not fewer ${plural}.`
			})
		notice =
			sentences.length > 0
				? `Boston moved its 311 system to a new platform in 2026. ${sentences.join(" ")}`
				: LEGACY_NOTICE(troubled.map((c) => c.label))
	}

	return { chips, troubled, notice }
}

/** Layers currently disrupted, keyed by layer, per contract.md's HeatMap prop shape. */
export function disruptionsFromHealth(
	health: SourceHealth | null,
): Record<string, { since: string; latest: string }> {
	const result: Record<string, { since: string; latest: string }> = {}
	for (const [key, layer] of Object.entries(health?.layers ?? {})) {
		if (layer.status === "ok") continue
		const since = layer.disrupted_since ?? null
		if (!since) continue
		result[key] = { since, latest: layer.latest_report || layer.through || "" }
	}
	return result
}

/** True when (year, month) >= the (year, month) of `since` ("YYYY-MM-DD"). */
export function isDisruptedMonth(since: string, year: number, month: number): boolean {
	if (!ISO_DAY.test(since) || !Number.isFinite(year) || month < 1) return false
	const sinceYear = Number(since.slice(0, 4))
	const sinceMonth = Number(since.slice(5, 7))
	if (year !== sinceYear) return year > sinceYear
	return month >= sinceMonth
}

/**
 * Text for the map count line's disruption note ("May 28"), or null when the selected
 * year-month is "all" or before the disruption. `selMonth` is the map's 1-based month select
 * (0 = all months); `selYear` is a year string or "all".
 */
export function disruptionNote(
	disruptions: Record<string, { since: string; latest: string }>,
	layerKey: string,
	selYear: string,
	selMonth: number,
): string | null {
	if (selYear === "all" || selMonth === 0) return null
	const d = disruptions[layerKey]
	if (!d) return null
	if (!isDisruptedMonth(d.since, Number(selYear), selMonth)) return null
	return fmtShort(d.since)
}
