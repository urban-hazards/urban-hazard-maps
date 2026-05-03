import { useState } from "react"
import data from "../data/personnel-availability.json"

export default function PersonnelAvailabilityChip() {
	const [enabled, setEnabled] = useState(false)

	const toggle = () => setEnabled((prev) => !prev)

	const count = data.ranges.length

	return (
		<button
			type="button"
			onClick={toggle}
			aria-pressed={enabled}
			style={{
				display: "inline-flex",
				alignItems: "center",
				gap: "6px",
				padding: "4px 10px",
				fontSize: "12px",
				borderRadius: "999px",
				border: "1px solid var(--color-border, #d1d5db)",
				background: enabled ? "var(--color-text, #334155)" : "var(--color-surface, #ffffff)",
				color: enabled ? "#ffffff" : "var(--color-text, #334155)",
				cursor: "pointer",
			}}
		>
			Personnel availability ({count} ranges)
		</button>
	)
}
