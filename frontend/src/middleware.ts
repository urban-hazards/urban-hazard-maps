import { defineMiddleware } from "astro:middleware"

export const onRequest = defineMiddleware(({ request, redirect }, next) => {
	const url = new URL(request.url)

	// Redirect non-www to www in production
	if (url.hostname === "urbanhazardmaps.com") {
		url.hostname = "www.urbanhazardmaps.com"
		return redirect(url.toString(), 301)
	}

	return next()
})
