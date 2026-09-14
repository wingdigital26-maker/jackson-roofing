/* =========================================================================
   Jackson Roofing — Social Command Center
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
  var PILLAR_COLORS = ["#0aa7e6", "#c9337d", "#0b7d5c", "#e0821b", "#7c5cff", "#c8452f", "#1a73e8"];

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
    feed:      document.getElementById("feed")
  };

  var state = { posts: [], schedule: null, pillars: [], pillarColor: {}, platform: "all", pillar: "all" };

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
    renderFilters();
    apply();
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

    // cadence text from schedule.json if present (flexible shape), else honest fallback
    var sched = state.schedule || {};
    var schedByKey = {};
    var schedList = Array.isArray(sched.platforms) ? sched.platforms : (Array.isArray(sched) ? sched : []);
    schedList.forEach(function (row) {
      if (!row) return;
      var pk = platMeta(row.platform || row.name || "").key;
      schedByKey[pk] = row.cadence || row.rhythm || row.frequency || row.note || "";
    });
    if (sched.note || sched.rhythm) els.stripNote.textContent = sched.note || sched.rhythm;

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
        pl.appendChild(segBtn(name, name, state.pillarColor[name], "pillar"));
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

  function renderCalendar(list) {
    // dow header
    if (!els.calDow.childElementCount) {
      ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].forEach(function (d) {
        var s = document.createElement("span"); s.textContent = d; els.calDow.appendChild(s);
      });
    }

    var grid = els.calGrid; grid.innerHTML = "";
    var start = calStart();

    // window is at least 30 days, expanding to cover the full post span so
    // every post always lands on the grid even across a month boundary.
    var span = 30;
    var allDates = state.posts.map(function (p) { return normDate(p.date); }).filter(Boolean);
    if (allDates.length) {
      var latest = allDates.reduce(function (a, b) { return a.key > b.key ? a : b; });
      var lastDt = new Date(latest.y, latest.m - 1, latest.day);
      var diff = Math.round((lastDt - start) / DAY_MS) + 1;
      span = Math.max(30, diff);
    }
    var last = new Date(start.getTime() + (span - 1) * DAY_MS);
    var opt = { month: "short", day: "numeric" };
    var range = start.toLocaleString("en-US", opt) + " – " + last.toLocaleString("en-US", opt) + ", " + last.getFullYear();
    els.calTitle.textContent = "Content calendar · " + range;

    // map posts by date key (filtered set drives placement)
    var byDate = {};
    list.forEach(function (p) {
      var d = normDate(p.date); if (!d) return;
      (byDate[d.key] = byDate[d.key] || []).push(p);
    });

    var todayKey = keyOf(new Date());

    // leading pad so the first day lands under its real weekday column
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
      // show month abbrev on day 1 or the very first cell for context
      var showMon = dt.getDate() === 1 || n === 0;
      var label = showMon ? dt.toLocaleString("en-US", { month: "short" }) + " " + dt.getDate() : String(dt.getDate());
      var head = '<div class="date">' + esc(label) + "</div>";
      var posts = byDate[key] || [];
      var body = "";
      if (posts.length) {
        cell.classList.add("has");
        body = '<div class="cell-posts">' + posts.slice(0, 3).map(function (p) {
          var pm = platMeta(p.platform);
          var time = p.time ? esc(p.time) : "";
          return '<button class="pdot" style="--acc:' + pm.meta.acc + '" data-id="' + esc(cardId(p)) + '" title="' + esc(pm.meta.label + (time ? " · " + p.time : "")) + '">' +
            (time ? '<span class="pd-time">' + time + "</span>" : "") +
            '<span class="pd-plat">' + esc(pm.meta.short) + "</span></button>";
        }).join("") + (posts.length > 3 ? '<span class="pdot" style="--acc:#6a7889">+' + (posts.length - 3) + " more</span>" : "") + "</div>";
      }
      cell.innerHTML = head + body;
      grid.appendChild(cell);
    }

    // day -> feed jump
    Array.prototype.forEach.call(grid.querySelectorAll(".pdot[data-id]"), function (btn) {
      btn.addEventListener("click", function () {
        var target = document.getElementById(btn.getAttribute("data-id"));
        if (!target) return;
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        target.classList.add("flash");
        setTimeout(function () { target.classList.remove("flash"); }, 1400);
      });
    });
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
    return '<span class="pc-pillar" style="--acc:' + (state.pillarColor[p.pillar] || "#6a7889") + '"><i></i>' + esc(p.pillar) + "</span>";
  }
  function geoBlock(p) {
    if (!p.geo) return "";
    return '<div class="pc-geo"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 12-9 12s-9-5-9-12a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>' + esc(p.geo) + "</div>";
  }
  function whenLabel(p) {
    var d = normDate(p.date);
    var ds = d ? new Date(d.y, d.m - 1, d.day).toLocaleString("en-US", { month: "short", day: "numeric" }) : "Draft";
    return ds + (p.time ? " · " + esc(p.time) : "");
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
    return card;
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
