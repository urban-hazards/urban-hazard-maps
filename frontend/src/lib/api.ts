import type { HeatmapResponse, NeighborhoodStat, PageStats } from "./types"

const API_BASE = process.env.API_URL || "http://localhost:8000"

async function apiFetch<T>(path: string): Promise<T> {
	const res = await fetch(`${API_BASE}${path}`)
	if (!res.ok) {
		throw new Error(`API error ${res.status}: ${path}`)
	}
	return res.json() as Promise<T>
}

export function fetchPageStats(): Promise<PageStats> {
	return apiFetch<PageStats>("/api/stats/page")
}

export function fetchEncampmentStats(): Promise<PageStats> {
	return apiFetch<PageStats>("/api/encampments/stats/page")
}

export function fetchNeighborhoods(): Promise<NeighborhoodStat[]> {
	return apiFetch<NeighborhoodStat[]>("/api/neighborhoods")
}

export function fetchNeighborhood(slug: string): Promise<NeighborhoodStat> {
	return apiFetch<NeighborhoodStat>(`/api/neighborhoods/${slug}`)
}

export function fetchEncampmentHeatmap(year: string, month: number): Promise<HeatmapResponse> {
	return apiFetch<HeatmapResponse>(`/api/encampments/heatmap?year=${year}&month=${month}`)
}
