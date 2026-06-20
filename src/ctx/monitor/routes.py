"""Route inventory for ctx-monitor."""

from __future__ import annotations

NAV_ROUTES: tuple[tuple[str, str, str], ...] = (
    ("home", "Home", "/"),
    ("loaded", "Loaded", "/loaded"),
    ("skills", "Skills", "/skills"),
    ("skillspector", "SkillSpector", "/skillspector"),
    ("wiki", "Wiki", "/wiki"),
    ("graph", "Graph", "/graph"),
    ("manage", "Manage", "/manage"),
    ("harness", "Harness Setup", "/harness"),
    ("docs", "Docs", "/docs"),
    ("config", "Config", "/config"),
    ("status", "Status", "/status"),
    ("kpi", "KPIs", "/kpi"),
    ("runtime", "Runtime", "/runtime"),
    ("sessions", "Sessions", "/sessions"),
    ("logs", "Logs", "/logs"),
    ("events", "Live", "/events"),
)

PAGE_ROUTES: frozenset[str] = frozenset(href for _key, _label, href in NAV_ROUTES) | {
    "/catalog",
    "/catalog/",
    "/live",
}

GET_API_ROUTES: frozenset[str] = frozenset({
    "/api/sessions.json",
    "/api/manifest.json",
    "/api/status.json",
    "/api/kpi.json",
    "/api/grades.json",
    "/api/sidecars.json",
    "/api/runtime.json",
    "/api/skillspector.json",
    "/api/config.json",
    "/api/entities/search.json",
    "/api/events.stream",
})

GET_API_PATTERNS: tuple[str, ...] = (
    "/api/entity/<slug>.json",
    "/api/skill/<slug>.json",
    "/api/graph/<slug>.json",
)

POST_API_ROUTES: frozenset[str] = frozenset({
    "/api/load",
    "/api/unload",
    "/api/config",
    "/api/entity/upsert",
    "/api/entity/delete",
})
