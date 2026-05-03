export type HeatCurve = "linear" | "logarithmic" | "exponential"

function clamp01(t: number): number {
	if (Number.isNaN(t)) return 0
	return Math.max(0, Math.min(1, t))
}

export function linear(t: number): number {
	return clamp01(t)
}

export function logarithmic(t: number): number {
	return Math.log10(1 + 9 * clamp01(t))
}

export function exponential(t: number): number {
	return (Math.exp(clamp01(t)) - 1) / (Math.E - 1)
}

export const HEAT_CURVES: Record<HeatCurve, (t: number) => number> = {
	linear,
	logarithmic,
	exponential,
}
