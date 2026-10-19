import type { MetadataRoute } from "next";

// Indexing is opt-in (ROBOTS_INDEX=true on the public deployment); everything else is disallowed.
export default function robots(): MetadataRoute.Robots {
  const base = process.env.PUBLIC_APP_URL ?? "http://localhost:3000";
  if (process.env.ROBOTS_INDEX !== "true") return { rules: { userAgent: "*", disallow: "/" } };
  return {
    rules: { userAgent: "*", allow: ["/", "/help"], disallow: ["/api/", "/dashboard", "/projects", "/insights", "/backtest", "/settings", "/profile", "/admin"] },
    sitemap: `${base}/sitemap.xml`,
  };
}
