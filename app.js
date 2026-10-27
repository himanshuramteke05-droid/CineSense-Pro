"use strict";
const $ = (s, e = document) => e.querySelector(s), $$ = (s, e = document) => [...e.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const IMG = "https://image.tmdb.org/t/p/", SECTIONS = ["auth", "quiz", "rec", "diary", "watchlist", "taste", "search"];
const starsText = v => "★".repeat(Math.floor(v)) + (v % 1 ? "½" : "");
let marks = { watchlist: [], like: [] };
const marked = (k, id) => marks[k].some(x => x.id === id);
const EMO = { Funny: "😄", Emotional: "💔", Exciting: "⚡", Relaxing: "😌", "Thought-provoking": "🧠", "Surprise me": "🎲" };
let token = localStorage.getItem("token"), me = null, movies = {}, qa = {}, qi = 0;

async function api(path, body) {
  const res = await fetch("/api" + path, { method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const d = await res.json().catch(() => ({}));
  if (res.status === 401) { signOut(); throw new Error("Please log in again."); }
  if (!res.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Something went wrong.");
  return d;
}
function toast(t) { const el = $("#toast"); el.textContent = t; el.classList.add("show"); clearTimeout(toast.id); toast.id = setTimeout(() => el.classList.remove("show"), 2600); }
const say = (el, t) => { el.textContent = t || ""; };

function chips(box, options, { multi = false, selected = [] } = {}) {
  box.innerHTML = options.map(o => { const [v, l] = Array.isArray(o) ? o : [o, o];
    return `<button type="button" class="chip" data-v="${esc(v)}" aria-pressed="${selected.includes(v)}">${esc(l)}</button>`; }).join("");
  box.onclick = e => { const b = e.target.closest(".chip"); if (!b) return;
    if (multi) b.setAttribute("aria-pressed", b.getAttribute("aria-pressed") !== "true");
    else $$(".chip", box).forEach(c => c.setAttribute("aria-pressed", c === b)); };
}
const picked = box => $$('.chip[aria-pressed="true"]', box).map(b => b.dataset.v);

// ---------- navigation ----------
function show(name) {
  SECTIONS.forEach(s => { $("#" + s).hidden = s !== name; });
  $$("#nav button").forEach(b => b.setAttribute("aria-current", b.dataset.view === (name === "quiz" ? "rec" : name)));
  scrollTo(0, 0);
}
function go(view) {
  if (view === "rec") return me.has_quiz ? show("rec") : startQuiz();
  show(view); if (view === "diary") loadDiary(); if (view === "watchlist") loadWatch(); if (view === "taste") loadTaste(); if (view === "search") $("#q").focus();
}
$$("#nav button").forEach(b => { b.onclick = () => go(b.dataset.view); });
function signOut() { token = null; me = null; localStorage.removeItem("token"); $("#nav").hidden = $("#who").hidden = true; show("auth"); loadWall(); }
$("#logout").onclick = signOut;

// ---------- landing wall + auth ----------
async function loadWall() {
  try {
    const m = (await (await fetch("/api/showcase")).json()).movies.filter(x => x.poster_path), cols = [[], [], [], [], []];
    m.forEach((x, i) => cols[i % 5].push(`<img src="${IMG}w185${x.poster_path}" alt="">`));
    $("#wall").innerHTML = cols.map(c => `<div>${c.join("")}${c.join("")}</div>`).join("");
  } catch { /* wall is decoration only */ }
}
$$(".tab").forEach(t => { t.onclick = () => {
  $$(".tab").forEach(x => x.setAttribute("aria-selected", x === t));
  $("#login-form").hidden = t.dataset.tab !== "login"; $("#signup-form").hidden = t.dataset.tab !== "signup"; say($("#auth-msg"), ""); }; });
async function authenticate(path, payload) {
  try { token = (await api(path, payload)).token; localStorage.setItem("token", token); boot(); } catch (err) { say($("#auth-msg"), err.message); }
}
$("#login-form").onsubmit = e => { e.preventDefault(); authenticate("/login", { name: $("#l-name").value, password: $("#l-pass").value }); };
$("#signup-form").onsubmit = e => { e.preventDefault(); authenticate("/register", { name: $("#s-name").value, password: $("#s-pass").value, dob: $("#s-dob").value, email: $("#s-email").value }); };

// ---------- quiz wizard (one question per screen) ----------
const steps = () => [
  { k: "mood", t: "What are you usually in the mood for?", h: "Pick one.", o: me.moods.map(m => [m, EMO[m] + " " + m]), d: ["Exciting"] },
  { k: "interests", t: "Which of these sound interesting?", h: "Pick as many as you like.", o: me.genres, multi: 1 },
  { k: "time", t: "How much time do you usually have?", h: "We'll match the runtime.", o: me.times, d: ["No preference"] },
  { k: "langs", t: "Which languages do you watch in?", h: "Leave empty for all.", o: Object.entries(me.langs), multi: 1 },
  { k: "avoid", t: "Anything you'd rather skip?", h: "We'll never show these.", o: me.genres, multi: 1 }];
function startQuiz() { qa = {}; qi = 0; show("quiz"); drawStep(); }
function drawStep() {
  const S = steps(), s = S[qi];
  $("#qbar").style.width = ((qi + 1) / S.length * 100) + "%"; $("#qtitle").textContent = s.t; $("#qhint").textContent = s.h;
  chips($("#qopts"), s.o, { multi: !!s.multi, selected: qa[s.k] || s.d || [] });
  $("#qback").style.visibility = qi ? "visible" : "hidden"; $("#qnext").textContent = qi === S.length - 1 ? "Build my profile" : "Next";
}
$("#qback").onclick = () => { qa[steps()[qi].k] = picked($("#qopts")); qi--; drawStep(); };
$("#qnext").onclick = async () => {
  const S = steps(); qa[S[qi].k] = picked($("#qopts"));
  if (qi < S.length - 1) { qi++; return drawStep(); }
  try {
    await api("/quiz", { mood: qa.mood[0] || "Surprise me", interests: qa.interests, time: qa.time[0] || "No preference", langs: qa.langs, avoid: qa.avoid });
    me.has_quiz = true; toast("Profile created."); go("rec");
  } catch (err) { say($("#quiz-msg"), err.message); }
};

// ---------- cards ----------
function card(m, i, pct) {
  const meta = [m.year || "", m.runtime ? m.runtime + " min" : "", me.langs[m.original_language] || ""].filter(Boolean).join(" · ");
  return `<article class="mv" data-id="${m.id}" style="--i:${i}" tabindex="0"><div class="pz"><img src="${IMG}w342${esc(m.poster_path)}" alt="${esc(m.title)} poster" loading="lazy">
    ${pct != null ? `<span class="ring" style="--p:${pct}" title="Match score"><b>${pct}</b></span>` : ""}${m.vote_average ? `<span class="rt">★ ${Number(m.vote_average).toFixed(1)}</span>` : ""}</div>
    <div class="mb"><h3>${esc(m.title)}</h3><div class="meta">${esc(meta)}</div>${m.why ? `<p class="why">${esc(m.why)}</p>` : ""}</div></article>`;
}
function renderMovies(box, list, rec) {
  movies = Object.fromEntries(list.map(m => [m.id, m]));
  box.innerHTML = list.length ? list.map((m, i) => card(m, i, rec ? Math.round(m.strength * 100) : null)).join("") : '<p class="muted">No matches. Try another mood or description.</p>';
}
const skeleton = n => Array.from({ length: n }, () => '<div class="mv sk"><div class="pz"></div></div>').join("");
const open = e => { const el = e.target.closest(".mv"); if (el && movies[el.dataset.id]) openMovie(movies[el.dataset.id]); };
["#results", "#search-results"].forEach(s => { $(s).onclick = open; $(s).onkeydown = e => e.key === "Enter" && open(e); });

// ---------- For you: instant results, AI reasons stream in after ----------
$("#go").onclick = async () => {
  const btn = $("#go"), box = $("#results"); say($("#rec-msg"), ""); btn.disabled = true; box.innerHTML = skeleton(5);
  try {
    const d = await api("/recommend", { mood: picked($("#r-mood"))[0] || "Surprise me", with_: $("#r-with").value, k: 5, ai: false });
    renderMovies(box, d.movies, true); btn.disabled = false;
    const explainAll = async () => {
      say($("#rec-msg"), "");
      try {
        const r = (await api("/explain", { items: d.movies })).reasons;
        d.movies.forEach((m, i) => { const p = $(`.mv[data-id="${m.id}"] .why`), t = r[String(i + 1)];
          if (p && t) { p.textContent = t; p.className = "why ai fade"; m.why = t; } });
      } catch (err) {
        const busy = /503|UNAVAILABLE|429|demand|quota/i.test(err.message);
        $("#rec-msg").innerHTML = (busy ? "Gemini is busy right now (Google's side, your key is fine). " : "AI explanations unavailable: " + esc(err.message) + " ") + '<button class="ghost" id="retry-ai">Try again</button>';
        $("#retry-ai").onclick = explainAll;
      }
    };
    explainAll();
  } catch (err) { box.innerHTML = ""; say($("#rec-msg"), err.message); }
  btn.disabled = false;
};

// ---------- movie modal: cast, trailer, where to watch, rating ----------
async function openMovie(m) {
  const dlg = $("#modal"), tags = (m.genres || "").split(", ").filter(Boolean).map(g => `<span>${esc(g)}</span>`).join(""); let stars = 0;
  dlg.innerHTML = `<div class="mh" id="mh"><button class="x" aria-label="Close">✕</button><img src="${IMG}w342${esc(m.poster_path)}" alt="">
    <div><h1>${esc(m.title)}</h1><p class="muted">${esc([m.year, m.runtime && m.runtime + " min", m.vote_average && "★ " + Number(m.vote_average).toFixed(1)].filter(Boolean).join(" · "))}</p>
    <div class="tags">${tags}</div><p id="tg" class="muted"></p>${m.why ? `<p class="why ai">${esc(m.why)}</p>` : ""}</div></div>
    <div class="mbody"><p>${esc(m.overview)}</p><div id="extra"><p class="muted">Loading cast and streaming info…</p></div>
    <div class="acts"><button class="ghost" id="b-like">♥ Like</button><button class="ghost" id="b-wl">＋ Watchlist</button></div>
    <h3>Rate and review</h3><div class="stars" id="stars">${[1, 2, 3, 4, 5].map(v => `<button class="star" data-v="${v}" aria-label="${v} stars">★</button>`).join("")}</div>
    <textarea id="review" placeholder="Add a review… (optional)" rows="3"></textarea><p><button class="primary" id="save">Save to diary</button></p></div>`;
  dlg.showModal();
  $(".x", dlg).onclick = () => dlg.close();
  dlg.onclick = e => { if (e.target === dlg) dlg.close(); };
  const paint = () => $$(".star", dlg).forEach(x => { const v = +x.dataset.v; x.classList.toggle("on", v <= stars); x.classList.toggle("half", v - .5 === stars); });
  $$(".star", dlg).forEach(s => { s.onclick = e => { const r = s.getBoundingClientRect(); stars = +s.dataset.v - (e.clientX - r.left < r.width / 2 ? .5 : 0); paint(); }; });
  const flag = (id, kind, label) => { const b = $(id, dlg), on = () => marked(kind, m.id); const draw = () => { b.classList.toggle("act", on()); b.textContent = (on() ? "✓ " : "") + label; };
    draw(); b.onclick = async () => { try { await api("/mark", { kind, on: !on(), movie: m }); marks[kind] = on() ? marks[kind].filter(x => x.id !== m.id) : [m, ...marks[kind]]; draw(); } catch (err) { toast(err.message); } }; };
  flag("#b-like", "like", "♥ Liked".slice(0, 0) + "Like"); flag("#b-wl", "watchlist", "Watchlist");
  $("#save").onclick = async () => {
    if (!stars) return toast("Pick a star rating first.");
    try { await api("/rate", { id: m.id, title: m.title, genres: m.genres, runtime: m.runtime, rating: stars, review: $("#review").value, poster_path: m.poster_path || "" });
      dlg.close(); $$(`.mv[data-id="${m.id}"] .pz`).forEach(p => p.insertAdjacentHTML("beforeend", `<div class="done">Rated ${starsText(stars)}</div>`));
      toast("Added to your diary. Your taste profile updated."); } catch (err) { toast(err.message); }
  };
  try {
    const d = await api(`/movie/${m.id}?country=${$("#country").value}`), x = $("#extra");
    if (!d.configured) return (x.innerHTML = '<p class="muted">Add TMDB_API_KEY to the .env file to see cast, trailer and where to watch.</p>');
    if (d.backdrop) $("#mh").style.setProperty("--bd", `url(${IMG}w780${d.backdrop})`);
    $("#tg").textContent = [d.tagline, d.director && "Directed by " + d.director].filter(Boolean).join(" · ");
    const cast = d.cast.length ? `<h3>Cast</h3><div class="cast">${d.cast.map(c => `<figure>${c.img ? `<img src="${IMG}w185${c.img}" alt="${esc(c.name)}" loading="lazy">` : '<div class="ph">🎭</div>'}<figcaption><b>${esc(c.name)}</b><small>${esc(c.role)}</small></figcaption></figure>`).join("")}</div>` : "";
    const row = (k, l) => l.length ? `<div class="prov"><b>${k}</b>${l.map(p => p.logo ? `<img src="${IMG}w92${p.logo}" title="${esc(p.name)}" alt="${esc(p.name)}">` : `<span class="chip">${esc(p.name)}</span>`).join("")}</div>` : "";
    const any = d.stream.length || d.rent.length || d.buy.length;
    
    // Pro UI/UX Buttons
    let main_ott_btn = '';
    if (d.stream.length) {
       main_ott_btn = `<a class="btn primary-ott" target="_blank" rel="noopener" href="${esc(d.link)}">🍿 Watch on ${esc(d.stream[0].name)}</a>`;
    } else if (d.rent.length || d.buy.length) {
       main_ott_btn = `<a class="btn primary-ott" target="_blank" rel="noopener" href="${esc(d.link)}">🍿 Watch on OTT</a>`;
    }
    
    const trailer_btn = d.trailer ? `<a class="btn trailer-btn" target="_blank" rel="noopener" href="https://www.youtube.com/watch?v=${esc(d.trailer)}">▶ Watch Trailer</a>` : '';
    
    const action_bar = `<div class="pro-action-bar">${main_ott_btn}${trailer_btn}</div>`;

    x.innerHTML = action_bar + cast + `<h3>Where to watch</h3>` + (any ? row("Stream", d.stream) + row("Rent", d.rent) + row("Buy", d.buy) + (d.link ? `<p><a class="btn" target="_blank" rel="noopener" href="${esc(d.link)}">View all options on JustWatch</a></p>` : "") + "<small class='muted'>Availability from TMDB, powered by JustWatch.</small>" : '<p class="muted">Not listed for this country right now.</p>');
  } catch (err) { $("#extra").innerHTML = `<p class="msg">${esc(err.message)}</p>`; }
}

// ---------- My taste ----------
async function loadTaste() {
  const box = $("#taste-body"); box.innerHTML = '<p class="muted">Loading…</p>';
  try {
    const t = await api("/taste"), lvl = { Low: 1, Medium: 2, High: 3 }[t.confidence], top = t.profile[0];
    const bars = t.profile.map(p => `<div class="row"><span>${esc(p.genre)}</span><div class="track"><i style="width:0" data-w="${Math.round(p.score * 100)}"></i></div><b>${p.score.toFixed(2)}</b></div>`).join("");
    const hist = t.history.length ? `<h3>Watch history</h3><ul class="hist">${t.history.map(h => `<li><span>${esc(h.title)}</span><span class="muted">${esc(h.genres)}</span><span class="r">${starsText(h.rating)}</span><span class="muted">${new Date(h.ts * 1000).toLocaleDateString()}</span></li>`).join("")}</ul>` : '<p class="muted">Rate a few movies from For you and your profile starts to learn.</p>';
    box.innerHTML = `<h1 class="q">Your Movie DNA</h1><div class="stats"><div class="stat"><b>${t.count}</b>movies rated</div>
      <div class="stat"><b>${esc(t.confidence)}</b>confidence<div class="meter">${[1, 2, 3].map(i => `<i class="${i <= lvl ? "on" : ""}"></i>`).join("")}</div></div>
      <div class="stat"><b>${esc(top ? top.genre : "-")}</b>top genre</div></div><div class="dna">${bars}</div><h3>Email alerts</h3><p class="muted">We email you only when a new movie matches your Movie DNA.</p>
      <div class="searchbar"><input id="em" type="email" placeholder="you@example.com" value="${esc(me.email)}"><button id="em-save" class="ghost">Save</button><button id="em-test" class="ghost">Send test alert</button></div><p id="em-msg" class="msg"></p>${hist}<button id="retake" class="ghost">Retake the quiz</button>`;
    $("#em-save").onclick = async () => { try { await api("/email", { email: $("#em").value }); me.email = $("#em").value; say($("#em-msg"), ""); toast("Email saved."); } catch (e) { say($("#em-msg"), e.message); } };
    $("#em-test").onclick = async () => { const b = $("#em-test"); b.disabled = true; say($("#em-msg"), "Sending…"); try { await api("/email", { email: $("#em").value }); me.email = $("#em").value; const r = await api("/notify/test", {}); say($("#em-msg"), r.emails_sent ? "Sent! Check your inbox (and spam)." : "No movie matched your taste right now."); } catch (e) { say($("#em-msg"), e.message); } b.disabled = false; };
    requestAnimationFrame(() => $$(".track i", box).forEach(i => { i.style.width = i.dataset.w + "%"; }));
    $("#retake").onclick = async () => { await api("/quiz/reset", {}); me.has_quiz = false; go("rec"); };
  } catch (err) { box.innerHTML = `<p class="msg">${esc(err.message)}</p>`; }
}

// ---------- Diary + Watchlist (Letterboxd-style) ----------
async function loadDiary() {
  const box = $("#diary-body"); box.innerHTML = '<p class="muted">Loading…</p>';
  try {
    const e = (await api("/diary")).entries;
    box.innerHTML = '<h1 class="q">Your diary</h1>' + (e.length ? `<div class="diary">${e.map(x => { const d = new Date(x.ts * 1000);
      return `<div class="entry"><div class="dt"><b>${d.toLocaleString("en", { month: "short" })}</b><span>${d.getDate()}</span></div>
      ${x.poster ? `<img src="${IMG}w154${esc(x.poster)}" alt="">` : '<div class="nop"></div>'}
      <div><h3>${esc(x.title)}</h3><div class="r">${starsText(x.rating)}${marked("like", x.mid) ? ' <span class="heart">♥</span>' : ""}</div>${x.review ? `<p>${esc(x.review)}</p>` : ""}</div></div>`; }).join("")}</div>`
      : '<p class="muted">Nothing logged yet. Open a movie from For you and rate it.</p>');
  } catch (err) { box.innerHTML = `<p class="msg">${esc(err.message)}</p>`; }
}
async function loadWatch() {
  try { marks = await api("/marks"); } catch (err) { return toast(err.message); }
  const box = $("#wl-grid"); renderMovies(box, marks.watchlist, false);
  if (!marks.watchlist.length) box.innerHTML = '<p class="muted">Your watchlist is empty. Open any movie and tap Watchlist.</p>';
  box.onclick = open;
}

// ---------- Search ----------
$("#search-form").onsubmit = async e => {
  e.preventDefault(); const q = $("#q").value.trim(), box = $("#search-results"); if (!q) return;
  say($("#search-msg"), ""); box.innerHTML = skeleton(6);
  try { renderMovies(box, (await api("/search?q=" + encodeURIComponent(q))).movies, false); } catch (err) { box.innerHTML = ""; say($("#search-msg"), err.message); }
};

// ---------- start ----------
async function boot() {
  if (!token) { show("auth"); return loadWall(); }
  try { me = await api("/me"); } catch { return; }
  $("#nav").hidden = $("#who").hidden = false; $("#av").textContent = me.name[0].toUpperCase();
  try { marks = await api("/marks"); } catch { /* optional */ }
  chips($("#r-mood"), me.moods.map(m => [m, EMO[m] + " " + m]), { selected: ["Surprise me"] });
  $("#r-with").innerHTML = me.with.map(w => `<option>${esc(w)}</option>`).join(""); go("rec");
}
boot();
