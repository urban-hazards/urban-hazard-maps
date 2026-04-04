export function formatHour(hour: number): string {
	if (hour === 0) return "12 AM"
	if (hour < 12) return `${hour} AM`
	if (hour === 12) return "12 PM"
	return `${hour - 12} PM`
}

export function formatNumber(n: number): string {
	return n.toLocaleString("en-US")
}

export function neighborhoodSlug(name: string): string {
	return name
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, "-")
		.replace(/^-|-$/g, "")
}
