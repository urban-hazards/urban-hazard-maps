import { atom } from "nanostores"

export type DataLayer = "Sharps" | "Encampments" | "Human Waste"

// "all" is shared across components — a numeric 0 sentinel would leak HeatMap's
// historical convention into the table components.
export type YearFilter = number | "all"
export type MonthFilter = number | "all"

export const $dataLayer = atom<DataLayer>("Sharps")
export const $year = atom<YearFilter>("all")
export const $month = atom<MonthFilter>("all")

export function setDataLayer(layer: DataLayer): void {
	$dataLayer.set(layer)
}

export function setYear(year: YearFilter): void {
	$year.set(year)
}

export function setMonth(month: MonthFilter): void {
	$month.set(month)
}
