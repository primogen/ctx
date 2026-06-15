(() => {
  const config = window.CTX_MONITOR_MANAGE || {};
  const MANAGE_MUTATIONS_ENABLED = Boolean(config.mutationsEnabled);
  const MANAGE_TOKEN = config.token || "";
  let manageResults = Array.isArray(config.initialResults) ? config.initialResults : [];

  const resultsEl = document.getElementById("manage-results");
  const statusEl = document.getElementById("manage-search-status");
  const form = document.getElementById("entity-editor-form");
  const editorStatus = document.getElementById("entity-editor-status");
  let selected = null;

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => (
      {"&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"}[ch]
    ));
  }

  function displaySlug(slug) {
    return String(slug || "").replace(/^skills-sh-/, "");
  }

  function entityLabel(row) {
    return row.type + ":" + displaySlug(row.slug);
  }

  function setStatus(text) {
    editorStatus.textContent = text || "";
  }

  function fillForm(detail) {
    selected = {slug: detail.slug, type: detail.type};
    const fm = detail.frontmatter || {};
    form.slug.value = detail.slug || "";
    form.entity_type.value = detail.type || "skill";
    form.title.value = fm.title || fm.name || detail.slug || "";
    form.description.value = fm.description || "";
    form.tags.value = Array.isArray(fm.tags) ? fm.tags.join(", ") : (fm.tags || "");
    form.source_url.value = fm.source_url || fm.repo_url || fm.github_url || fm.homepage_url || "";
    form.body.value = detail.body || "";
    setStatus("editing " + entityLabel(selected));
  }

  function renderResults(rows) {
    statusEl.textContent = rows.length + " result" + (rows.length === 1 ? "" : "s");
    if (!rows.length) {
      resultsEl.innerHTML = '<p class="muted">No entities found.</p>';
      return;
    }
    resultsEl.innerHTML = rows.map((row) => (
      '<button type="button" class="manage-result" data-slug="' + escapeHtml(row.slug)
      + '" data-type="' + escapeHtml(row.type)
      + '"><strong>' + escapeHtml(row.display_slug || displaySlug(row.slug))
      + '</strong><span class="pill entity-type-' + escapeHtml(row.type) + '">'
      + escapeHtml(row.type) + '</span><span class="muted">'
      + escapeHtml(row.description || row.title || "") + "</span></button>"
    )).join("");
    document.querySelectorAll(".manage-result").forEach((btn) => btn.addEventListener("click", async () => {
      const slug = btn.dataset.slug;
      const type = btn.dataset.type;
      const res = await fetch("/api/entity/" + encodeURIComponent(slug) + ".json?type=" + encodeURIComponent(type));
      if (!res.ok) {
        setStatus("load failed: " + res.statusText);
        return;
      }
      fillForm(await res.json());
    }));
  }

  let timer = null;

  async function searchNow() {
    const q = document.getElementById("manage-search").value.trim();
    const type = document.getElementById("manage-type").value;
    const url = "/api/entities/search.json?q=" + encodeURIComponent(q)
      + (type ? "&type=" + encodeURIComponent(type) : "");
    statusEl.textContent = "Searching...";
    const res = await fetch(url);
    if (!res.ok) {
      statusEl.textContent = "Search failed: " + res.statusText;
      return;
    }
    manageResults = (await res.json()).results || [];
    renderResults(manageResults);
  }

  function scheduleSearch() {
    clearTimeout(timer);
    timer = setTimeout(searchNow, 250);
  }

  async function post(url, payload) {
    if (!MANAGE_MUTATIONS_ENABLED) {
      return {ok: false, detail: "mutations disabled on non-loopback bind"};
    }
    const res = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-CTX-Monitor-Token": MANAGE_TOKEN},
      body: JSON.stringify(payload),
    });
    let data = {};
    try {
      data = await res.json();
    } catch (_) {
      // The API usually responds with JSON, but keep the UI resilient to empty errors.
    }
    data.ok = res.ok && data.ok !== false;
    return data;
  }

  document.getElementById("manage-search").addEventListener("input", scheduleSearch);
  document.getElementById("manage-type").addEventListener("change", searchNow);
  document.getElementById("entity-new-button").addEventListener("click", () => {
    selected = null;
    form.reset();
    setStatus("new entity");
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const payload = Object.fromEntries(new FormData(form).entries());
    const isUpdate = selected && selected.slug === payload.slug && selected.type === payload.entity_type;
    if (isUpdate) {
      const ok = confirm(
        "Update existing " + payload.entity_type + ":" + payload.slug + "?\n\n"
        + "Benefit: keeps the catalog current.\n"
        + "Risk: a lower-quality edit can degrade recommendations.",
      );
      if (!ok) {
        setStatus("update cancelled");
        return;
      }
      payload.confirm_update = "true";
    }
    setStatus("saving...");
    const data = await post("/api/entity/upsert", payload);
    setStatus(data.detail || (data.ok ? "saved" : "save failed"));
    if (data.ok) searchNow();
  });

  document.getElementById("entity-delete-button").addEventListener("click", async () => {
    const slug = form.slug.value.trim();
    const type = form.entity_type.value;
    if (!slug || !confirm("Delete " + type + ":" + slug + " from the wiki catalog?")) return;
    setStatus("deleting...");
    const data = await post("/api/entity/delete", {slug, entity_type: type});
    setStatus(data.detail || (data.ok ? "deleted" : "delete failed"));
    if (data.ok) {
      selected = null;
      form.reset();
      searchNow();
    }
  });

  renderResults(manageResults);
})();
