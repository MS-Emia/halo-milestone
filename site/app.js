// data.json を取得して描画する。外部由来の文字列は textContent / 属性設定のみで扱い、innerHTML は使わない。
"use strict";

(function () {
  const VIDEO_ID_RE = /^[A-Za-z0-9_-]{11}$/;
  const STALE_MS = 3 * 60 * 60 * 1000;
  const HISTORY_LIMIT = 20;
  const numberFormat = new Intl.NumberFormat("ja-JP");
  const jstFormat = new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });

  const $ = (id) => document.getElementById(id);
  let videos = [];
  let sortKey = "remaining";

  function videoUrl(id) {
    return "https://www.youtube.com/watch?v=" + id;
  }

  function formatJst(iso) {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? "" : jstFormat.format(d) + " JST";
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function showNotice(message, isError) {
    const notice = $("notice");
    notice.textContent = message;
    notice.classList.toggle("notice--error", Boolean(isError));
    notice.hidden = false;
  }

  function isValidVideo(v) {
    return v && typeof v.id === "string" && VIDEO_ID_RE.test(v.id) &&
      Number.isFinite(v.views) && Number.isFinite(v.remaining);
  }

  function buildCard(v, featured) {
    const card = $("card-template").content.firstElementChild.cloneNode(true);
    const url = videoUrl(v.id);
    const title = String(v.title || v.id);

    const thumb = card.querySelector(".thumb");
    thumb.href = url;
    thumb.setAttribute("aria-label", title + "(YouTubeで開く)");
    const img = thumb.querySelector("img");
    if (typeof v.thumbnail_url === "string" && v.thumbnail_url.startsWith("https://i.ytimg.com/")) {
      img.src = v.thumbnail_url;
    } else {
      img.remove();
    }

    const link = card.querySelector(".card-title a");
    link.href = url;
    link.textContent = title;
    link.title = title;

    card.querySelector(".views-num").textContent = numberFormat.format(v.views);

    const pct = Math.round(Math.min(Math.max(Number(v.progress) || 0, 0), 1) * 1000) / 10;
    const bar = card.querySelector(".progress");
    bar.setAttribute("aria-valuenow", String(pct));
    bar.setAttribute("aria-valuetext", v.next_label + "まで" + pct + "%");
    bar.setAttribute("aria-label", "次の節目(" + v.next_label + ")までの進捗");
    card.querySelector(".progress-fill").style.width = pct + "%";
    card.querySelector(".progress-pct").textContent = pct.toFixed(1) + "%";

    const remaining = card.querySelector(".remaining");
    remaining.append(v.next_label + "まで あと ");
    remaining.append(el("strong", "", numberFormat.format(v.remaining)));
    remaining.append(" 回");

    const last = card.querySelector(".last");
    if (v.last_milestone_label) {
      const when = v.last_reached_at ? "(" + formatJst(v.last_reached_at) + " に到達)" : "";
      last.textContent = "最後の節目: " + v.last_milestone_label + when;
    } else {
      last.textContent = "最後の節目: まだありません";
    }

    if (featured) {
      card.classList.add("card--feature");
      const badge = el("span", "badge");
      const halo = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      halo.setAttribute("class", "badge-halo");
      halo.setAttribute("aria-hidden", "true");
      const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
      use.setAttribute("href", "#halo");
      halo.append(use);
      badge.append(halo, "もうすぐ" + v.next_label);
      thumb.append(badge);
    }
    return card;
  }

  function renderApproaching() {
    const list = $("approaching-list");
    const items = videos.filter((v) => v.approaching).sort((a, b) => a.remaining - b.remaining);
    list.replaceChildren(...items.map((v) => buildCard(v, true)));
    $("approaching-section").hidden = items.length === 0;
  }

  function renderAll() {
    const list = $("all-list");
    $("video-count").textContent = videos.length ? "(" + videos.length + "本)" : "";
    if (!videos.length) {
      list.replaceChildren(el("p", "empty", "表示できる動画がまだありません。再生リストの設定を確認してください。"));
      return;
    }
    const sorted = videos.slice().sort(sortKey === "views"
      ? (a, b) => b.views - a.views
      : (a, b) => a.remaining - b.remaining);
    list.replaceChildren(...sorted.map((v) => buildCard(v, false)));
  }

  function renderHistory(events) {
    const list = $("history-list");
    const valid = (Array.isArray(events) ? events : [])
      .filter((e) => e && typeof e.id === "string" && VIDEO_ID_RE.test(e.id))
      .slice(0, HISTORY_LIMIT);
    if (!valid.length) {
      const li = el("li");
      li.append(el("span", "history-meta", "まだ到達履歴はありません。節目を越えるとここに記録されます。"));
      list.replaceChildren(li);
      return;
    }
    list.replaceChildren(...valid.map((e) => {
      const li = el("li");
      const title = el("a", "history-title", String(e.title || e.id));
      title.href = videoUrl(e.id);
      title.target = "_blank";
      title.rel = "noopener noreferrer";
      const meta = formatJst(e.reached_at) +
        (Number.isFinite(e.views_at_detection) ? " 検知(" + numberFormat.format(e.views_at_detection) + "回)" : "");
      li.append(el("span", "history-label", String(e.label || "")), title, el("span", "history-meta", meta));
      return li;
    }));
  }

  function renderUpdated(generatedAt) {
    const updated = new Date(generatedAt);
    if (Number.isNaN(updated.getTime())) {
      $("updated").textContent = "最終更新: 不明";
      return;
    }
    $("updated").textContent = "最終更新: " + formatJst(generatedAt);
    if (Date.now() - updated.getTime() >= STALE_MS) {
      showNotice("更新が止まっている可能性があります(最終更新から3時間以上経過しています)。");
    }
  }

  function setupSort() {
    document.querySelectorAll(".sort-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        sortKey = btn.dataset.sort;
        document.querySelectorAll(".sort-btn").forEach((b) => {
          b.setAttribute("aria-pressed", String(b === btn));
        });
        renderAll();
      });
    });
  }

  async function main() {
    setupSort();
    let data;
    try {
      const res = await fetch("data.json", { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      data = await res.json();
    } catch (err) {
      $("updated").textContent = "";
      showNotice("データを取得できませんでした。時間をおいて再読み込みしてください。", true);
      return;
    }
    videos = (Array.isArray(data.videos) ? data.videos : []).filter(isValidVideo);
    renderUpdated(data.generated_at);
    renderApproaching();
    renderAll();
    renderHistory(data.recent_events);
  }

  main();
})();
