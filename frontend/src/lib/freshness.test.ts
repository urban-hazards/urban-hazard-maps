import { describe, expect, it } from "vitest"
import { disruptionsFromHealth, freshnessModel, isDisruptedMonth } from "./freshness"
import type { SourceHealth } from "./types"

const baseSchema2Health = (): SourceHealth => ({
	generated: "2026-09-23T00:00:00Z",
	schema_version: 2,
	layers: {
		encampments: {
			status: "stale",
			through: "2026-05-27",
			sources: ["ckan_legacy:Encampments"],
			latest_report: "2026-06-22",
			disrupted_since: "2026-05-28",
			coverage_sources: ["ckan_legacy:Encampments"],
		},
		needles: {
			status: "ok",
			through: "2026-09-09",
			sources: ["ckan_legacy:Needles"],
			latest_report: "2026-09-09",
			disrupted_since: null,
			coverage_sources: ["ckan_legacy:Needles"],
		},
	},
})

describe("freshnessModel", () => {
	it("renders the disrupted-layer chip text and notice for schema 2", () => {
		const { chips, notice } = freshnessModel(baseSchema2Health(), {})
		const encampments = chips.find((c) => c.key === "encampments")
		expect(encampments?.text).toBe(
			"Encampments: latest report Jun 22, 2026 · reporting disrupted since May 28",
		)
		expect(notice).toBe(
			"Boston moved its 311 system to a new platform in 2026. Encampment reporting has been disrupted since May 28; reports that still arrive are shown, but low counts after that date reflect missing data, not fewer encampments.",
		)
	})

	it("renders the ok-layer chip text for schema 2", () => {
		const { chips } = freshnessModel(baseSchema2Health(), {})
		const needles = chips.find((c) => c.key === "needles")
		expect(needles?.text).toBe("Sharps: data through Sep 9, 2026")
	})

	it("renders a degraded layer with the data-through form and a volume sentence", () => {
		const health = {
			generated: "",
			schema_version: 2,
			layers: {
				needles: {
					status: "degraded" as const,
					through: "2026-09-09",
					latest_report: "2026-09-09",
					disrupted_since: null,
					sources: [],
				},
			},
		}
		const m = freshnessModel(health, {})
		expect(m.chips[0].text).toBe("Sharps: data through Sep 9, 2026 · reporting volume down")
		expect(m.notice).toBe(
			"Boston moved its 311 system to a new platform in 2026. Sharps reporting volume has dropped sharply since the switch; recent months may be incomplete.",
		)
	})

	it("falls back to the legacy chip + notice for schema 1 / missing keys", () => {
		const legacyHealth: SourceHealth = {
			generated: "2026-06-01T00:00:00Z",
			schema_version: 1,
			layers: {
				encampments: {
					status: "stale",
					through: "2026-05-27",
					sources: ["ckan_legacy:Encampments"],
				},
			},
		}
		const { chips, notice } = freshnessModel(legacyHealth, {})
		const encampments = chips.find((c) => c.key === "encampments")
		expect(encampments?.text).toBe("Encampments: data through May 27, 2026")
		expect(() => freshnessModel(legacyHealth, {})).not.toThrow()
		expect(notice).toBe(
			"Boston moved its 311 system to a new platform in 2026. Some categories stopped appearing in the city's data during the switch (Encampments). We show those layers through their last complete date rather than guess.",
		)
	})

	it("uses the frozen fallback date when health is null", () => {
		const { chips } = freshnessModel(null, { encampments: "2026-05-27" })
		const encampments = chips.find((c) => c.key === "encampments")
		expect(encampments?.status).toBe("stale")
		expect(encampments?.disruptedSince).toBe("2026-05-28")
		expect(encampments?.text).toBe(
			"Encampments: latest report May 27, 2026 · reporting disrupted since May 28",
		)
	})
})

describe("disruptionsFromHealth", () => {
	it("excludes ok layers and layers with a null disrupted_since", () => {
		const health = baseSchema2Health()
		// waste has no disrupted_since even though it's not ok
		health.layers.waste = {
			status: "degraded",
			through: "2026-06-30",
			sources: ["ckan_legacy:Waste"],
			latest_report: "2026-06-30",
			disrupted_since: null,
		}
		const disruptions = disruptionsFromHealth(health)
		expect(Object.keys(disruptions)).toEqual(["encampments"])
		expect(disruptions.encampments).toEqual({ since: "2026-05-28", latest: "2026-06-22" })
	})
})

describe("isDisruptedMonth", () => {
	it("compares (year, month) against the since date", () => {
		expect(isDisruptedMonth("2026-05-28", 2026, 4)).toBe(false)
		expect(isDisruptedMonth("2026-05-28", 2026, 5)).toBe(true)
		expect(isDisruptedMonth("2026-05-28", 2026, 6)).toBe(true)
		expect(isDisruptedMonth("2026-05-28", 2027, 1)).toBe(true)
	})
})
