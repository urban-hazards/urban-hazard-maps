export type HeatCurve = "linear" | "logarithmic" | "exponential"

export function linear(t: number): number {
	const clamped = Math.max(0, Math.min(1, t))
	return clamped
}

export function logarithmic(t: number): number {
	const clamped = Math.max(0, Math.min(1, t))
	return Math.log10(1 + 9 * clamped)
}

export function exponential(t: number): number {
	const clamped = Math.max(0, Math.min(1, t))
	return (Math.exp(clamped) - 1) / (Math.E - 1)
}

export const HEAT_CURVES: Record<HeatCurve, (t: number) => number> = {
	linear,
	logarithmic,
	exponential,
}
