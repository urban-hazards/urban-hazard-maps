import { useState } from "react"
import data from "../data/personnel-availability.json"

export default function PersonnelAvailabilityChip() {
	const [enabled, setEnabled] = useState(false)

	const toggle = () => setEnabled((prev) => !prev)

	const count = data.ranges.length

	const activeClasses = enabled ? "bg-slate-700 text-white" : "bg-white text-slate-700"

	return (
		<button
			type="button"
			onClick={toggle}
			className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${activeClasses}`}
		>
			Personnel availability ({count} ranges)
		</button>
	)
}
