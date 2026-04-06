import type { APIRoute } from "astro"

const SITE = "https://www.urbanhazardmaps.com"

export const GET: APIRoute = () => {
	const xml = `<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>${SITE}/sitemap-0.xml</loc>
  </sitemap>
</sitemapindex>`
	return new Response(xml, {
		headers: { "Content-Type": "application/xml" },
	})
}
