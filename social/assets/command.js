/* =========================================================================
   Jackson Roofing · Social Command Center
   Wing-owned draft system. Loads posts.json + schedule.json at runtime.
   Renders empty states honestly when data is missing. Nothing posts live.
   ========================================================================= */
(function () {
  "use strict";

  // ---- platform + pillar config (accents match CSS custom props) ----
  var PLATFORMS = {
    gbp:       { label: "Google Business", short: "GBP",       acc: "#1a73e8", kind: "update" },
    facebook:  { label: "Facebook",        short: "Facebook",  acc: "#1877f2", kind: "post"   },
    instagram: { label: "Instagram",       short: "Instagram", acc: "#c9337d", kind: "post"   },
    nextdoor:  { label: "Nextdoor",         short: "Nextdoor",  acc: "#0b7d5c", kind: "post"   }
  };
  var PILLAR_COLORS = ["#0aa7e6", "#c9337d", "#0b7d5c", "#e0821b", "#7c5cff", "#c8452f", "#1a73e8", "#8e2ea8"];

  // Practical caption limits per platform. GBP/Instagram are hard caps; Facebook
  // and Nextdoor numbers are the "keep it concise" sweet spot, not a hard limit.
  var LIMITS = {
    gbp:       { max: 1500, hard: true,  note: "1500 character limit" },
    facebook:  { max: 500,  hard: false, note: "concise reads best (about 500)" },
    instagram: { max: 2200, hard: true,  note: "2200 character limit" },
    nextdoor:  { max: 500,  hard: false, note: "neighbors prefer short and concise" }
  };
  var WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  // localStorage view preference, fully guarded (private mode / blocked storage)
  function readPref(k, dflt) {
    try { var v = window.localStorage.getItem(k); return v == null ? dflt : v; } catch (e) { return dflt; }
  }
  function writePref(k, v) {
    try { window.localStorage.setItem(k, v); } catch (e) { /* ignore */ }
  }

  // human labels + one-line intent for known pillars; unknown keys prettify gracefully
  var PILLAR_META = {
    "storm-response": { label: "Storm Response", desc: "Fast, calm guidance right after hail or wind so neighbors know the first steps and who to call." },
    "before-after":   { label: "Before & After", desc: "Real project transformations that show workmanship and build trust at a glance." },
    "education":      { label: "Education",       desc: "Plain-language answers to the questions homeowners actually ask about roofs and claims." },
    "trust":          { label: "Trust & Credentials", desc: "Family-run since 2000, licensing, warranties, and the proof behind the promise." },
    "reviews":        { label: "Reviews & Proof", desc: "Homeowner reviews and social proof from the North Texas cities Jackson serves." },
    "community":      { label: "Community",       desc: "Local presence across Plano and the DFW suburbs, the neighborly side of the brand." },
    "seasonal":       { label: "Seasonal & Maintenance", desc: "Timely upkeep and season-specific reminders tied to the North Texas weather calendar." }
  };
  function pillarLabel(key) {
    if (PILLAR_META[key] && PILLAR_META[key].label) return PILLAR_META[key].label;
    return String(key || "").replace(/[-_]+/g, " ").replace(/\b\w/g, function (m) { return m.toUpperCase(); });
  }

  var els = {
    loading:   document.getElementById("loading"),
    heroScope: document.getElementById("heroScope"),
    cadence:   document.getElementById("cadenceGrid"),
    stripNote: document.getElementById("stripNote"),
    pfFilter:  document.getElementById("platformFilter"),
    plFilter:  document.getElementById("pillarFilter"),
    count:     document.getElementById("filterCount"),
    calTitle:  document.getElementById("calTitle"),
    calLegend: document.getElementById("calLegend"),
    calDow:    document.getElementById("calDow"),
    calGrid:   document.getElementById("calGrid"),
    feed:      document.getElementById("feed"),
    pillarPanel: document.getElementById("pillarLegendPanel"),
    pillarHint:  document.getElementById("pillarHint"),
    dlSchedule:  document.getElementById("dlSchedule"),
    calViews:  document.getElementById("calViews"),
    calNav:    document.getElementById("calNav"),
    calPrev:   document.getElementById("calPrev"),
    calNext:   document.getElementById("calNext"),
    calRange:  document.getElementById("calRangeLabel")
  };

  var state = {
    posts: [], schedule: null, pillars: [], pillarColor: {},
    platform: "all", pillar: "all",
    calView: (["month", "week", "list"].indexOf(readPref("jr_calview", "month")) >= 0 ? readPref("jr_calview", "month") : "month"),
    weekIndex: 0, weeks: []
  };

  // ---------- helpers ----------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function platMeta(p) {
    var key = String(p || "").toLowerCase().replace(/[^a-z]/g, "");
    if (key === "google" || key === "googlebusinessprofile" || key === "googlebusiness") key = "gbp";
    return PLATFORMS[key] ? { key: key, meta: PLATFORMS[key] } : { key: key, meta: { label: p || "Post", short: p || "Post", acc: "#6a7889", kind: "post" } };
  }
  function fetchJSON(url) {
    return fetch(url, { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .catch(function () { return null; });
  }
  function normDate(d) {
    // accept YYYY-MM-DD; return {y,m,day,key} or null
    if (!d) return null;
    var m = String(d).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return null;
    return { y: +m[1], m: +m[2], day: +m[3], key: m[1] + "-" + m[2] + "-" + m[3] };
  }

  function fmtTime(t) {
    // "16:00" -> "4:00 PM"; passes through anything that is not HH:MM
    var m = String(t || "").match(/^(\d{1,2}):(\d{2})$/);
    if (!m) return String(t || "");
    var h = +m[1], mm = m[2], ap = h >= 12 ? "PM" : "AM";
    h = h % 12; if (h === 0) h = 12;
    return h + ":" + mm + " " + ap;
  }

  // Build a real "Mon, Wed, Fri mornings" style rhythm per platform from the
  // schedule.json cadence[] slots. Honest: reads only what the plan declares.
  function cadenceByPlatform() {
    var out = {};
    var sched = state.schedule || {};
    var slots = Array.isArray(sched.cadence) ? sched.cadence : [];
    var byKey = {};
    slots.forEach(function (s) {
      if (!s || !s.platform) return;
      var k = platMeta(s.platform).key;
      (byKey[k] = byKey[k] || []).push(s);
    });
    Object.keys(byKey).forEach(function (k) {
      var rows = byKey[k];
      var days = [];
      rows.forEach(function (r) { if (r.weekday && days.indexOf(r.weekday) < 0) days.push(r.weekday); });
      // order weekdays Mon..Sun for readability
      var order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
      days.sort(function (a, b) { return order.indexOf(a) - order.indexOf(b); });
      var perWeek = rows.length;
      var label = days.join(", ");
      out[k] = label + " · " + perWeek + "x / week";
    });
    return out;
  }

  // ---------- load ----------
  Promise.all([fetchJSON("data/posts.json"), fetchJSON("data/schedule.json")]).then(function (res) {
    var rawPosts = res[0];
    state.schedule = res[1];

    // posts.json may be an array or {posts:[...]}
    var arr = Array.isArray(rawPosts) ? rawPosts : (rawPosts && Array.isArray(rawPosts.posts) ? rawPosts.posts : []);
    state.posts = arr.filter(function (p) { return p && p.platform; });

    // pillar palette
    var seen = [];
    state.posts.forEach(function (p) { if (p.pillar && seen.indexOf(p.pillar) < 0) seen.push(p.pillar); });
    state.pillars = seen;
    seen.forEach(function (name, i) { state.pillarColor[name] = PILLAR_COLORS[i % PILLAR_COLORS.length]; });

    render();
    hideLoader();
  });

  // ---------- schedule download (feature-detected; degrades if absent) ----------
  // The export CSV is produced by a separate lane. If it is not present we hide
  // the affordance rather than offer a link that 404s.
  (function detectDownload() {
    var a = els.dlSchedule;
    if (!a) return;
    var url = a.getAttribute("href");
    fetch(url, { method: "HEAD", cache: "no-store" })
      .then(function (r) {
        // some static servers reject HEAD; fall back to a lightweight GET probe
        if (r && r.ok) { a.hidden = false; return; }
        if (r && (r.status === 405 || r.status === 501)) {
          return fetch(url, { cache: "no-store" }).then(function (g) { if (g && g.ok) a.hidden = false; });
        }
      })
      .catch(function () { /* absent or blocked: leave hidden */ });
  })();

  function hideLoader() {
    if (!els.loading) return;
    els.loading.classList.add("gone");
    setTimeout(function () { els.loading.setAttribute("hidden", ""); }, 320);
  }

  // ---------- render orchestration ----------
  function render() {
    var n = state.posts.length;
    els.heroScope.textContent = n ? (n + " drafted post" + (n === 1 ? "" : "s") + " across " + platformsInPlay() + " channels") : "No drafts queued yet";
    renderCadence();
    renderStrategy();
    renderFilters();
    setupCalViews();
    apply();
  }

  // ---------- strategy / pillar legend ----------
  function renderStrategy() {
    var panel = els.pillarPanel;
    if (!panel) return;
    panel.innerHTML = "";
    if (!state.pillars.length) {
      if (els.pillarHint) els.pillarHint.textContent = "";
      panel.innerHTML = '<p class="muted" style="margin:0;grid-column:1/-1">Pillars appear here once drafts are tagged.</p>';
      return;
    }
    if (els.pillarHint) els.pillarHint.textContent = state.pillars.length + " pillars in play";
    var counts = {};
    state.posts.forEach(function (p) { if (p.pillar) counts[p.pillar] = (counts[p.pillar] || 0) + 1; });
    state.pillars.forEach(function (key) {
      var acc = state.pillarColor[key] || "#6a7889";
      var desc = (PILLAR_META[key] && PILLAR_META[key].desc) || "Drafts tagged to this theme.";
      var item = document.createElement("div");
      item.className = "pl-item";
      item.style.setProperty("--acc", acc);
      item.innerHTML =
        '<div class="pl-top"><span class="pl-name">' + esc(pillarLabel(key)) + "</span>" +
        '<span class="pl-count">' + (counts[key] || 0) + "</span></div>" +
        '<p class="pl-desc">' + esc(desc) + "</p>";
      panel.appendChild(item);
    });
  }

  function platformsInPlay() {
    var set = {};
    state.posts.forEach(function (p) { set[platMeta(p.platform).key] = 1; });
    return Object.keys(set).length || 0;
  }

  // ---------- cadence strip ----------
  function renderCadence() {
    var g = els.cadence;
    g.innerHTML = "";

    // build per-platform mix from real posts
    var counts = {};
    state.posts.forEach(function (p) { var k = platMeta(p.platform).key; counts[k] = (counts[k] || 0) + 1; });

    // cadence text: prefer a real per-platform rhythm derived from the
    // schedule.json cadence[] slots (weekday + time), else honest fallback.
    var sched = state.schedule || {};
    var schedByKey = cadenceByPlatform();
    // legacy flat shapes still supported if a future schedule uses them
    var schedList = Array.isArray(sched.platforms) ? sched.platforms : (Array.isArray(sched) ? sched : []);
    schedList.forEach(function (row) {
      if (!row) return;
      var pk = platMeta(row.platform || row.name || "").key;
      if (!schedByKey[pk]) schedByKey[pk] = row.cadence || row.rhythm || row.frequency || row.note || "";
    });
    if (sched.note || sched.rhythm) els.stripNote.textContent = "Best-time cadence pulled from the plan, per channel.";

    var order = ["gbp", "facebook", "instagram", "nextdoor"];
    // include any extra platforms actually present
    Object.keys(counts).forEach(function (k) { if (order.indexOf(k) < 0) order.push(k); });

    var any = false;
    order.forEach(function (k) {
      var meta = PLATFORMS[k] || { label: k, acc: "#6a7889" };
      var c = counts[k] || 0;
      var cadence = schedByKey[k] || (c ? "Drafted in this cycle" : "No drafts yet this cycle");
      if (!PLATFORMS[k] && !c) return;
      any = true;
      var card = document.createElement("div");
      card.className = "pf-card";
      card.style.setProperty("--acc", meta.acc);
      card.innerHTML =
        '<div class="pf-name"><span class="pf-dot"></span>' + esc(meta.label) + "</div>" +
        '<div class="pf-count">' + c + '</div>' +
        '<div class="pf-cadence">' + esc(cadence) + "</div>";
      g.appendChild(card);
    });

    if (!any) {
      g.innerHTML = '<p class="muted" style="margin:0">Platform mix appears here once the content engine drafts the first posts.</p>';
    }
  }

  // ---------- filters ----------
  function renderFilters() {
    // platform seg
    var pf = els.pfFilter; pf.innerHTML = "";
    pf.appendChild(segBtn("all", "All", null, "platform"));
    var present = {};
    state.posts.forEach(function (p) { present[platMeta(p.platform).key] = 1; });
    ["gbp", "facebook", "instagram", "nextdoor"].forEach(function (k) {
      if (present[k]) pf.appendChild(segBtn(k, PLATFORMS[k].label, PLATFORMS[k].acc, "platform"));
    });

    // pillar seg
    var pl = els.plFilter; pl.innerHTML = "";
    if (state.pillars.length) {
      pl.appendChild(segBtn("all", "All", null, "pillar"));
      state.pillars.forEach(function (name) {
        pl.appendChild(segBtn(name, pillarLabel(name), state.pillarColor[name], "pillar"));
      });
    } else {
      pl.innerHTML = '<span class="muted" style="font-size:.85rem">No pillars tagged</span>';
    }
  }

  function segBtn(val, label, acc, group) {
    var b = document.createElement("button");
    b.type = "button";
    b.setAttribute("aria-pressed", state[group] === val ? "true" : "false");
    if (acc) b.style.setProperty("--acc", acc);
    b.innerHTML = (acc ? '<span class="swatch"></span>' : "") + esc(label);
    b.addEventListener("click", function () {
      state[group] = val;
      // update pressed states in this group
      var parent = group === "platform" ? els.pfFilter : els.plFilter;
      Array.prototype.forEach.call(parent.querySelectorAll("button"), function (x) { x.setAttribute("aria-pressed", "false"); });
      b.setAttribute("aria-pressed", "true");
      apply();
    });
    return b;
  }

  function filtered() {
    return state.posts.filter(function (p) {
      if (state.platform !== "all" && platMeta(p.platform).key !== state.platform) return false;
      if (state.pillar !== "all" && p.pillar !== state.pillar) return false;
      return true;
    });
  }

  // ---------- apply (calendar + feed + count) ----------
  function apply() {
    var list = filtered();
    els.count.innerHTML = "Showing <b>" + list.length + "</b> of <b>" + state.posts.length + "</b>";
    renderLegend();
    renderCalendar(list);
    renderFeed(list);
  }

  function renderLegend() {
    var L = els.calLegend; L.innerHTML = "";
    var present = {};
    filtered().forEach(function (p) { present[platMeta(p.platform).key] = 1; });
    ["gbp", "facebook", "instagram", "nextdoor"].forEach(function (k) {
      if (!present[k]) return;
      var s = document.createElement("span"); s.className = "leg"; s.style.setProperty("--acc", PLATFORMS[k].acc);
      s.innerHTML = "<i></i>" + PLATFORMS[k].label;
      L.appendChild(s);
    });
  }

  // ---------- calendar ----------
  var DAY_MS = 86400000;
  function keyOf(dt) {
    return dt.getFullYear() + "-" + String(dt.getMonth() + 1).padStart(2, "0") + "-" + String(dt.getDate()).padStart(2, "0");
  }
  function calStart() {
    // anchor to the EARLIEST post date (day-level) if present, else today.
    // A rolling 30-day window is used so a queue that crosses a month
    // boundary (e.g. Sep 15 -> Oct 12) still places every post on the grid.
    var dates = state.posts.map(function (p) { return normDate(p.date); }).filter(Boolean);
    if (dates.length) {
      dates.sort(function (a, b) { return a.key < b.key ? -1 : 1; });
      return new Date(dates[0].y, dates[0].m - 1, dates[0].day);
    }
    var t = new Date(); return new Date(t.getFullYear(), t.getMonth(), t.getDate());
  }

  function ensureDow() {
    if (!els.calDow.childElementCount) {
      WEEKDAYS.forEach(function (d) {
        var s = document.createElement("span"); s.textContent = d; els.calDow.appendChild(s);
      });
    }
  }
  function groupByDate(list) {
    var byDate = {};
    list.forEach(function (p) {
      var d = normDate(p.date); if (!d) return;
      (byDate[d.key] = byDate[d.key] || []).push(p);
    });
    // stable per-day order by time
    Object.keys(byDate).forEach(function (k) {
      byDate[k].sort(function (a, b) { return (a.time || "") < (b.time || "") ? -1 : 1; });
    });
    return byDate;
  }
  // full span [start, last] covering all posts, min 30 days
  function calSpan() {
    var start = calStart();
    var span = 30;
    var allDates = state.posts.map(function (p) { return normDate(p.date); }).filter(Boolean);
    if (allDates.length) {
      var latest = allDates.reduce(function (a, b) { return a.key > b.key ? a : b; });
      var lastDt = new Date(latest.y, latest.m - 1, latest.day);
      var diff = Math.round((lastDt - start) / DAY_MS) + 1;
      span = Math.max(30, diff);
    }
    return { start: start, span: span, last: new Date(start.getTime() + (span - 1) * DAY_MS) };
  }
  // weeks (Sunday-aligned) spanning the full window; each is a Date for its Sunday
  function buildWeeks() {
    var sp = calSpan();
    var wkStart = new Date(sp.start.getTime() - sp.start.getDay() * DAY_MS);
    var weeks = [];
    var cur = wkStart;
    while (cur <= sp.last) { weeks.push(new Date(cur.getTime())); cur = new Date(cur.getTime() + 7 * DAY_MS); }
    return weeks;
  }

  function jumpToCard(btn) {
    var target = document.getElementById(btn.getAttribute("data-id"));
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.classList.add("flash");
    setTimeout(function () { target.classList.remove("flash"); }, 1400);
  }
  function wireJumps(scope) {
    Array.prototype.forEach.call(scope.querySelectorAll(".pdot[data-id],.li-row[data-id]"), function (btn) {
      btn.addEventListener("click", function () { jumpToCard(btn); });
    });
  }
  function dotHTML(p, withTime, use12) {
    var pm = platMeta(p.platform);
    // month cells are dense: keep the short 24h time so it never outgrows the
    // cell on mobile. Week/list have room for the friendlier 12h format.
    var shown = p.time ? esc(use12 ? fmtTime(p.time) : p.time) : "";
    return '<button class="pdot" style="--acc:' + pm.meta.acc + '" data-id="' + esc(cardId(p)) + '" title="' + esc(pm.meta.label + (p.time ? " · " + fmtTime(p.time) : "")) + '">' +
      (withTime && shown ? '<span class="pd-time">' + shown + "</span>" : "") +
      '<span class="pd-plat">' + esc(pm.meta.short) + "</span></button>";
  }

  function renderCalendar(list) {
    var byDate = groupByDate(list);
    els.calDow.hidden = (state.calView !== "month");
    if (els.calNav) els.calNav.hidden = (state.calView !== "week");
    if (state.calView === "week") return renderWeek(list, byDate);
    if (state.calView === "list") return renderList(list);
    return renderMonth(byDate);
  }

  function renderMonth(byDate) {
    ensureDow();
    var grid = els.calGrid; grid.className = "cal-grid"; grid.innerHTML = "";
    var sp = calSpan(), start = sp.start, span = sp.span;
    var opt = { month: "short", day: "numeric" };
    els.calTitle.textContent = "Content calendar · " + start.toLocaleString("en-US", opt) + " – " + sp.last.toLocaleString("en-US", opt) + ", " + sp.last.getFullYear();

    var todayKey = keyOf(new Date());
    var firstDow = start.getDay();
    for (var i = 0; i < firstDow; i++) {
      var pad = document.createElement("div"); pad.className = "cell pad"; grid.appendChild(pad);
    }
    for (var n = 0; n < span; n++) {
      var dt = new Date(start.getTime() + n * DAY_MS);
      var key = keyOf(dt);
      var cell = document.createElement("div");
      cell.className = "cell" + (todayKey === key ? " today" : "");
      cell.setAttribute("role", "listitem");
      var showMon = dt.getDate() === 1 || n === 0;
      var label = showMon ? dt.toLocaleString("en-US", { month: "short" }) + " " + dt.getDate() : String(dt.getDate());
      var head = '<div class="date">' + esc(label) + "</div>";
      var posts = byDate[key] || [];
      var body = "";
      if (posts.length) {
        cell.classList.add("has");
        body = '<div class="cell-posts">' + posts.slice(0, 3).map(function (p) { return dotHTML(p, true, false); }).join("") +
          (posts.length > 3 ? '<span class="pdot" style="--acc:#6a7889">+' + (posts.length - 3) + " more</span>" : "") + "</div>";
      }
      cell.innerHTML = head + body;
      grid.appendChild(cell);
    }
    wireJumps(grid);
  }

  function renderWeek(list, byDate) {
    ensureDow();
    state.weeks = buildWeeks();
    if (!state.weeks.length) { renderMonth(byDate); return; }
    if (state.weekIndex >= state.weeks.length) state.weekIndex = state.weeks.length - 1;
    if (state.weekIndex < 0) state.weekIndex = 0;

    var wkStart = state.weeks[state.weekIndex];
    var wkEnd = new Date(wkStart.getTime() + 6 * DAY_MS);
    var opt = { month: "short", day: "numeric" };
    els.calTitle.textContent = "Week of " + wkStart.toLocaleString("en-US", opt);
    if (els.calRange) els.calRange.textContent = "Week " + (state.weekIndex + 1) + " of " + state.weeks.length;
    if (els.calPrev) els.calPrev.disabled = state.weekIndex === 0;
    if (els.calNext) els.calNext.disabled = state.weekIndex === state.weeks.length - 1;

    var grid = els.calGrid; grid.className = "cal-grid week"; grid.innerHTML = "";
    var todayKey = keyOf(new Date());
    for (var d = 0; d < 7; d++) {
      var dt = new Date(wkStart.getTime() + d * DAY_MS);
      var key = keyOf(dt);
      var cell = document.createElement("div");
      cell.className = "wcell" + (todayKey === key ? " today" : "");
      cell.setAttribute("role", "listitem");
      var posts = byDate[key] || [];
      var head = '<div class="wcell-head"><span class="wcell-dow">' + WEEKDAYS[dt.getDay()] +
        '</span><span class="wcell-date">' + dt.toLocaleString("en-US", opt) + "</span></div>";
      var body;
      if (posts.length) {
        cell.classList.add("has");
        body = '<div class="wcell-posts">' + posts.map(function (p) { return dotHTML(p, true, true); }).join("") + "</div>";
      } else {
        body = '<div class="wcell-empty">No posts</div>';
      }
      cell.innerHTML = head + body;
      grid.appendChild(cell);
    }
    wireJumps(grid);
  }

  function renderList(list) {
    var grid = els.calGrid; grid.className = "cal-grid agenda"; grid.innerHTML = "";
    var sp = calSpan();
    var opt = { month: "short", day: "numeric" };
    els.calTitle.textContent = "Agenda · " + sp.start.toLocaleString("en-US", opt) + " – " + sp.last.toLocaleString("en-US", opt);

    if (!list.length) {
      grid.innerHTML = '<p class="muted" style="margin:0">No posts match this filter.</p>';
      return;
    }
    var byDate = groupByDate(list);
    var keys = Object.keys(byDate).sort();
    var todayKey = keyOf(new Date());
    keys.forEach(function (key) {
      var m = key.match(/^(\d{4})-(\d{2})-(\d{2})/);
      var dt = new Date(+m[1], +m[2] - 1, +m[3]);
      var day = document.createElement("div");
      day.className = "li-day" + (key === todayKey ? " today" : "");
      var head = '<div class="li-date">' + esc(WEEKDAYS[dt.getDay()] + ", " + dt.toLocaleString("en-US", opt)) +
        '<span class="li-n">' + byDate[key].length + " post" + (byDate[key].length === 1 ? "" : "s") + "</span></div>";
      var rows = byDate[key].map(function (p) {
        var pm = platMeta(p.platform);
        var cap = String(p.caption || "").slice(0, 96);
        return '<button class="li-row" style="--acc:' + pm.meta.acc + '" data-id="' + esc(cardId(p)) + '">' +
          '<span class="li-time">' + esc(p.time ? fmtTime(p.time) : "—") + '</span>' +
          '<span class="li-plat">' + esc(pm.meta.short) + '</span>' +
          '<span class="li-cap">' + esc(cap) + (String(p.caption || "").length > 96 ? "…" : "") + "</span></button>";
      }).join("");
      day.innerHTML = head + '<div class="li-rows">' + rows + "</div>";
      grid.appendChild(day);
    });
    wireJumps(grid);
  }

  // ---------- calendar view toggle (Month / Week / List) ----------
  function setupCalViews() {
    var host = els.calViews;
    if (!host || host.childElementCount) return; // build once
    [["month", "Month"], ["week", "Week"], ["list", "List"]].forEach(function (v) {
      var b = document.createElement("button");
      b.type = "button";
      b.setAttribute("data-view", v[0]);
      b.setAttribute("aria-pressed", state.calView === v[0] ? "true" : "false");
      b.textContent = v[1];
      b.addEventListener("click", function () {
        if (state.calView === v[0]) return;
        state.calView = v[0];
        writePref("jr_calview", v[0]);
        Array.prototype.forEach.call(host.querySelectorAll("button"), function (x) { x.setAttribute("aria-pressed", "false"); });
        b.setAttribute("aria-pressed", "true");
        apply();
      });
      host.appendChild(b);
    });
    if (els.calPrev) els.calPrev.addEventListener("click", function () { if (state.weekIndex > 0) { state.weekIndex--; apply(); } });
    if (els.calNext) els.calNext.addEventListener("click", function () { if (state.weekIndex < state.weeks.length - 1) { state.weekIndex++; apply(); } });
  }

  function cardId(p) {
    return "post-" + (normDate(p.date) ? normDate(p.date).key : "x") + "-" + platMeta(p.platform).key + "-" + (p.time || "").replace(/[^0-9a-z]/gi, "");
  }

  // ---------- feed / platform-native mockups ----------
  function renderFeed(list) {
    var f = els.feed; f.innerHTML = "";
    if (!state.posts.length) { f.appendChild(emptyState(true)); return; }
    if (!list.length) { f.appendChild(emptyState(false)); return; }

    // sort by date then time
    list.slice().sort(function (a, b) {
      var da = (normDate(a.date) || {}).key || "9999", db = (normDate(b.date) || {}).key || "9999";
      if (da !== db) return da < db ? -1 : 1;
      return (a.time || "") < (b.time || "") ? -1 : 1;
    }).forEach(function (p) { f.appendChild(buildCard(p)); });
  }

  function mediaBlock(img, wide) {
    var src = img && img.src ? String(img.src) : "";
    var alt = img && img.alt ? img.alt : "Jackson Roofing";
    // only trust http(s) or ../ relative asset paths; else placeholder
    var ok = src && /^(https?:\/\/|\.\.?\/|assets\/|img\/)/.test(src);
    // placeholder always rendered as the layer behind; a broken img removes
    // itself on error to reveal it (no fragile inline-HTML quote nesting).
    var imgTag = ok ? '<img class="pc-img" loading="lazy" src="' + esc(src) + '" alt="' + esc(alt) + '" onerror="this.remove()">' : "";
    return '<div class="pc-media' + (wide ? " wide" : "") + '">' + phMarkup(alt) + imgTag + "</div>";
  }
  function phMarkup(alt) {
    return '<div class="pc-ph"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.6"/><path d="M21 15l-5-5L5 21"/></svg><span>' + esc(alt) + "</span></div>";
  }

  function tagsBlock(tags) {
    if (!tags || !tags.length) return "";
    return '<div class="pc-tags">' + tags.map(function (t) {
      var tag = String(t).replace(/^#*/, "");
      return '<span class="pc-tag">#' + esc(tag) + "</span>";
    }).join(" ") + "</div>";
  }
  function pillarBlock(p) {
    if (!p.pillar) return "";
    return '<span class="pc-pillar" style="--acc:' + (state.pillarColor[p.pillar] || "#6a7889") + '"><i></i>' + esc(pillarLabel(p.pillar)) + "</span>";
  }
  function geoBlock(p) {
    if (!p.geo) return "";
    return '<div class="pc-geo"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 12-9 12s-9-5-9-12a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>' + esc(p.geo) + "</div>";
  }
  function whenLabel(p) {
    var d = normDate(p.date);
    var ds = "Draft";
    if (d) {
      var dt = new Date(d.y, d.m - 1, d.day);
      ds = WEEKDAYS[dt.getDay()] + ", " + dt.toLocaleString("en-US", { month: "short", day: "numeric" });
    }
    return ds + (p.time ? " · " + esc(fmtTime(p.time)) : "");
  }

  function buildCard(p) {
    var pm = platMeta(p.platform), acc = pm.meta.acc, key = pm.key;
    var card = document.createElement("article");
    card.className = "pcard"; card.id = cardId(p); card.setAttribute("role", "listitem");
    card.style.setProperty("--acc", acc);

    var caption = esc(p.caption || "");
    var cta = p.cta ? esc(p.cta) : "Contact us";
    var avatarImg = '<div class="pc-avatar"><img loading="lazy" src="../assets/img/logo.webp" alt="Jackson Roofing logo" onerror="this.parentNode.textContent=\'JR\'"></div>';

    if (key === "instagram") {
      card.innerHTML =
        '<div class="pc-top">' + avatarImg +
          '<div class="pc-id"><span class="pc-brand">jacksonroofing</span><span class="pc-sub">' + esc(p.geo || "Plano, TX") + "</span></div>" +
          '<span class="pc-badge">Instagram</span></div>' +
        mediaBlock(p.image, false) +
        '<div class="ig-actions">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20.8 4.6a5.5 5.5 0 00-7.8 0L12 5.7l-1-1a5.5 5.5 0 10-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 000-7.8z"/></svg>' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12a8 8 0 01-11.3 7.3L3 21l1.7-6.7A8 8 0 1121 12z"/></svg>' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/></svg>' +
          '<svg class="spacer" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/></svg>' +
        "</div>" +
        '<div class="pc-body">' +
          '<p class="pc-caption"><b>jacksonroofing</b> ' + caption + "</p>" +
          tagsBlock(p.hashtags) +
        "</div>" +
        '<div class="pc-cta"><span class="cta-meta">' + whenLabel(p) + "</span>" + pillarBlock(p) + "</div>";
    } else if (key === "gbp") {
      card.innerHTML =
        '<div class="pc-top">' + avatarImg +
          '<div class="pc-id"><span class="pc-brand">Jackson Roofing</span><span class="pc-sub gbp-kind">Google · What’s new</span></div>' +
          '<span class="pc-badge">Google</span></div>' +
        '<div class="pc-body">' + geoBlock(p) + '<p class="pc-caption">' + caption + "</p>" + tagsBlock(p.hashtags) + "</div>" +
        mediaBlock(p.image, true) +
        '<div class="pc-cta"><button class="cta-btn" type="button">' + cta + "</button>" +
          '<span class="cta-meta">' + whenLabel(p) + "</span></div>" +
        '<div class="pc-body" style="padding-top:.55rem">' + pillarBlock(p) + "</div>";
    } else if (key === "nextdoor") {
      card.innerHTML =
        '<div class="pc-top">' + avatarImg +
          '<div class="pc-id"><span class="pc-brand">Jackson Roofing</span><span class="pc-sub">Local business · ' + esc(p.geo || "Plano") + "</span></div>" +
          '<span class="pc-badge">Nextdoor</span></div>' +
        '<div class="pc-body"><p class="pc-caption">' + caption + "</p>" + tagsBlock(p.hashtags) + "</div>" +
        mediaBlock(p.image, true) +
        '<div class="pc-cta"><button class="cta-btn" type="button">' + cta + "</button>" +
          '<span class="cta-meta">' + whenLabel(p) + "</span></div>" +
        '<div class="pc-body" style="padding-top:.55rem">' + pillarBlock(p) + "</div>";
    } else {
      // facebook (default)
      card.innerHTML =
        '<div class="pc-top">' + avatarImg +
          '<div class="pc-id"><span class="pc-brand">Jackson Roofing</span><span class="pc-sub">' + whenLabel(p) + " · " + esc(p.geo || "Plano, TX") + "</span></div>" +
          '<span class="pc-badge">Facebook</span></div>' +
        '<div class="pc-body"><p class="pc-caption">' + caption + "</p>" + tagsBlock(p.hashtags) + "</div>" +
        mediaBlock(p.image, true) +
        '<div class="pc-cta"><button class="cta-btn" type="button">' + cta + "</button>" + pillarBlock(p) + "</div>";
    }
    card.appendChild(copyBar(p));
    return card;
  }

  // ---------- per-post copy caption ----------
  var ICON_COPY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 012-2h10"/></svg>';
  var ICON_CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M20 6L9 17l-5-5"/></svg>';

  function captionText(p) {
    var out = String(p.caption || "");
    if (p.hashtags && p.hashtags.length) {
      var tags = p.hashtags.map(function (t) { return "#" + String(t).replace(/^#+/, ""); }).join(" ");
      out += (out ? "\n\n" : "") + tags;
    }
    return out;
  }

  function copyBar(p) {
    var bar = document.createElement("div");
    bar.className = "pc-actions";
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pc-copy";
    btn.innerHTML = ICON_COPY + "<span>Copy caption</span>";
    var text = captionText(p);
    var timer = null;
    btn.addEventListener("click", function () {
      copyToClipboard(text).then(function (ok) {
        if (timer) clearTimeout(timer);
        btn.classList.add("done");
        btn.innerHTML = ICON_CHECK + "<span>" + (ok ? "Copied" : "Press Ctrl+C") + "</span>";
        timer = setTimeout(function () {
          btn.classList.remove("done");
          btn.innerHTML = ICON_COPY + "<span>Copy caption</span>";
        }, 1600);
      });
    });
    bar.appendChild(btn);
    bar.appendChild(metricChips(p));
    return bar;
  }

  // char-count vs platform limit + hashtag-count chip. Calm, no alarm dots.
  function metricChips(p) {
    var wrap = document.createElement("div");
    wrap.className = "pc-metrics";

    var lim = LIMITS[platMeta(p.platform).key];
    var len = String(p.caption || "").length;
    var chip = document.createElement("span");
    chip.className = "pc-metric";
    if (lim) {
      var ratio = len / lim.max;
      var over = len > lim.max;
      var near = ratio >= 0.85;
      if (over) chip.className += " over";
      else if (near) chip.className += " near";
      else chip.className += " ok";
      chip.textContent = len + " / " + lim.max;
      chip.title = "Caption length vs " + lim.note + (over ? " (over the sweet spot, consider trimming)" : "");
    } else {
      chip.className += " ok";
      chip.textContent = len + " chars";
      chip.title = "Caption length";
    }
    wrap.appendChild(chip);

    var tagCount = (p.hashtags && p.hashtags.length) || 0;
    var tag = document.createElement("span");
    tag.className = "pc-metric tag";
    tag.textContent = tagCount ? ("# " + tagCount) : "# 0";
    tag.title = tagCount ? (tagCount + " hashtag" + (tagCount === 1 ? "" : "s")) : "No hashtags (native for this channel)";
    wrap.appendChild(tag);
    return wrap;
  }

  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return legacyCopy(text); });
    }
    return Promise.resolve(legacyCopy(text));
  }
  function legacyCopy(text) {
    try {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "absolute"; ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      var ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (e) { return false; }
  }

  // ---------- empty states ----------
  function emptyState(noData) {
    var d = document.createElement("div");
    d.className = "empty";
    if (noData) {
      d.innerHTML =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="4" width="18" height="17" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>' +
        "<h3>No drafts queued yet</h3>" +
        "<p>The content engine has not staged any posts. Drafts will appear here as realistic previews once <code>data/posts.json</code> is populated. Nothing is posted live from this page.</p>";
    } else {
      d.innerHTML =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>' +
        "<h3>No posts match this filter</h3>" +
        "<p>Try a different platform or pillar to see the drafts in this cycle.</p>";
    }
    return d;
  }
})();
