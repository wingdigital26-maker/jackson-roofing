/* Jackson Roofing - motion: branded opening curtain, frosted shrink-nav,
   one restrained scroll-reveal pattern, hero-video keep-alive. All reduced-
   motion safe and failsafe (content never stays hidden). */
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches;

  /* ---- branded opening curtain (session-gated) ---- */
  var curtain = document.getElementById("curtain");
  if (curtain) {
    var seen = false;
    try { seen = sessionStorage.getItem("jr_seen") === "1"; } catch (e) {}
    if (seen || reduce) {
      curtain.parentNode.removeChild(curtain);
    } else {
      try { sessionStorage.setItem("jr_seen", "1"); } catch (e) {}
      var hide = function () {
        curtain.classList.add("gone");
        setTimeout(function () { if (curtain.parentNode) curtain.parentNode.removeChild(curtain); }, 900);
      };
      setTimeout(hide, 2100);
      // safety: never trap the page
      setTimeout(function () { if (curtain.parentNode) curtain.parentNode.removeChild(curtain); }, 3600);
    }
  }

  /* ---- frosted shrink-on-scroll nav ---- */
  var nav = document.querySelector("header.nav");
  if (nav) {
    var onScroll = function () { nav.classList.toggle("scrolled", window.scrollY > 24); };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    var toggle = nav.querySelector(".nav-toggle");
    var links = nav.querySelector("nav.links");
    if (toggle && links) {
      toggle.addEventListener("click", function () { links.classList.toggle("open"); });
      links.addEventListener("click", function (e) { if (e.target.tagName === "A") links.classList.remove("open"); });
    }
  }

  /* ---- scroll reveal (single pattern) ---- */
  var items = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && !reduce) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      });
    }, { threshold: 0.1, rootMargin: "0px 0px -5% 0px" });
    items.forEach(function (el) { io.observe(el); });
    // failsafe: reveal anything still hidden near the viewport, then everything
    setTimeout(function () {
      items.forEach(function (el) {
        if (!el.classList.contains("in") && el.getBoundingClientRect().top < window.innerHeight * 1.4) el.classList.add("in");
      });
    }, 1800);
    setTimeout(function () { items.forEach(function (el) { el.classList.add("in"); }); }, 4200);
  } else {
    items.forEach(function (el) { el.classList.add("in"); });
  }

  /* ---- keep the muted hero video playing ---- */
  var hv = document.querySelector(".hero-video");
  if (hv) {
    var play = function () { var p = hv.play(); if (p && p.catch) p.catch(function () {}); };
    play();
    hv.addEventListener("canplay", play);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) play(); });
    ["click", "touchstart", "scroll", "keydown"].forEach(function (ev) {
      window.addEventListener(ev, play, { once: true, passive: true });
    });
  }

  /* ---- footer year ---- */
  var y = document.getElementById("yr");
  if (y) y.textContent = new Date().getFullYear();
})();
