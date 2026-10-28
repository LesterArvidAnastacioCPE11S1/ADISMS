/* ADISMS web client – talks to the Flask API. */
var app = document.getElementById("app");

/* ---------- small helpers ---------- */
function $(id) { return document.getElementById(id); }

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

function money(n) {
  return "\u20B1" + Number(n || 0).toLocaleString("en-PH", {
    minimumFractionDigits: 2, maximumFractionDigits: 2
  });
}

function moneyShort(n) {
  return "\u20B1" + Math.round(Number(n) || 0).toLocaleString("en-PH");
}

function whole(n) {
  return Number(n || 0).toLocaleString("en-PH");
}

function cap(s) {
  s = String(s || "");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

var MONTHS = ["January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"];
var DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

function iso(d) {
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" +
    String(d.getDate()).padStart(2, "0");
}
function todayISO() { return iso(new Date()); }
function parseDay(value) {
  var p = String(value || "").slice(0, 10).split("-");
  return new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
}
function longDate(d) {
  if (!(d instanceof Date) || isNaN(d.getTime())) return "";
  return DAYS[d.getDay()] + ", " + d.getDate() + " " + MONTHS[d.getMonth()] + " " + d.getFullYear();
}
function shortDate(d) {
  if (!(d instanceof Date) || isNaN(d.getTime())) return "";
  return d.getDate() + " " + MONTHS[d.getMonth()].slice(0, 3) + " " + d.getFullYear();
}
function timeOf(ts) {
  var d = new Date(String(ts || "").replace(" ", "T"));
  if (isNaN(d.getTime())) return String(ts || "").slice(11, 16);
  var h = d.getHours(), m = d.getMinutes();
  var ap = h >= 12 ? "PM" : "AM";
  h = h % 12 || 12;
  return h + ":" + String(m).padStart(2, "0") + " " + ap;
}
function relDay(ts) {
  var day = String(ts || "").slice(0, 10);
  if (day === todayISO()) return "Today";
  var y = new Date();
  y.setDate(y.getDate() - 1);
  if (day === iso(y)) return "Yesterday";
  return shortDate(parseDay(day));
}
function greeting() {
  var h = new Date().getHours();
  return h < 12 ? "Magandang umaga" : h < 18 ? "Magandang hapon" : "Magandang gabi";
}

function toast(message) {
  var el = document.createElement("div");
  el.className = "toast";
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(function () { el.remove(); }, 2800);
}

/* ---------- state ---------- */
var st = {
  user: null, role: null, email: null, phone: null,
  authMode: "login",
  cart: [], receipt: null,
  tab: "photo", engine: "auto", engines: [],
  identifyIntent: "detail", identifyBack: "dash", match: null, photoUrl: null,
  inv: { q: "", filter: "all", sort: "id" },
  saleQuery: "", saleBrowse: false, saleTimer: null, saleBack: "dash",
  reportDate: todayISO(),
  deliveryId: null, deliveryBack: "stock",
  detailId: null, detailEdit: false,
  pickIntent: null,
  prevView: null, view: null,
  stream: null, cache: []
};

/* ---------- API ---------- */
async function api(path, method, body) {
  var options = { method: method || "GET", headers: {} };
  if (body instanceof FormData) {
    options.body = body;
  } else if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  var response = await fetch(path, options);
  var data = await response.json().catch(function () { return {}; });
  if (response.status === 401 && path !== "/api/login" &&
      path !== "/api/me" && path !== "/api/register") {
    st.user = null;
    st.authMode = "login";
    go("login");
    throw new Error("Please log in.");
  }
  if (!response.ok) throw new Error(data.error || "Request failed.");
  return data;
}

function applyUser(data) {
  st.user = data.username;
  st.role = data.role;
  st.email = data.email || "";
  st.phone = data.phone || "";
}

function resetState() {
  stopCamera();
  if (st.photoUrl) { try { URL.revokeObjectURL(st.photoUrl); } catch (e) { /* ignore */ } }
  st.user = null; st.role = null; st.email = null; st.phone = null;
  st.cart = []; st.receipt = null; st.match = null; st.photoUrl = null;
  st.saleQuery = ""; st.saleBrowse = false; st.detailEdit = false;
  st.reportDate = todayISO(); st.deliveryId = null; st.pickIntent = null;
  st.authMode = "login"; st.prevView = null; st.view = null;
  st.cache = [];
}

/* ---------- icons ---------- */
var ICON = {
  home: '<path d="M4 10.6 12 4l8 6.6V20a1 1 0 0 1-1 1h-4.6v-6H9.6v6H5a1 1 0 0 1-1-1z"/>',
  box: '<path d="M20.5 8.3 12 3.5 3.5 8.3v7.4L12 20.5l8.5-4.8z"/><path d="m3.5 8.3 8.5 4.8 8.5-4.8M12 13.1v7.4"/>',
  boxplus: '<path d="M20.5 10.6V8.3L12 3.5 3.5 8.3v7.4l5 2.8"/><path d="m3.5 8.3 8.5 4.8 8.5-4.8"/><path d="M18 14.5v6M15 17.5h6"/>',
  receipt: '<rect x="5" y="3.5" width="14" height="17" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/>',
  chart: '<path d="M3 20h18"/><path d="M6 16.5 10 11l3.5 3.5L20 7"/><path d="M20 11V7h-4"/>',
  trend: '<path d="M4 16.5 9.5 11l3 3L20 6.5"/><path d="M15.5 6.5H20V11"/>',
  scan: '<path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16"/><path d="M7 12h10"/>',
  barcode: '<path d="M4 5v14M7 5v14M10 5v9M13 5v14M16.5 5v14M20 5v14"/>',
  camera: '<path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h2l1.2-2h6.6L16.5 7h2A1.5 1.5 0 0 1 20 8.5v9A1.5 1.5 0 0 1 18.5 19h-13A1.5 1.5 0 0 1 4 17.5z"/><circle cx="12" cy="13" r="3.4"/>',
  user: '<circle cx="12" cy="8" r="3.6"/><path d="M4.8 20c.9-3.6 3.7-5.4 7.2-5.4s6.3 1.8 7.2 5.4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  x: '<path d="m6 6 12 12M18 6 6 18"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7"/>',
  arrowleft: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  arrowright: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  chevleft: '<path d="m14 6-6 6 6 6"/>',
  chevright: '<path d="m10 6 6 6-6 6"/>',
  chevdown: '<path d="m6 9 6 6 6-6"/>',
  search: '<circle cx="11" cy="11" r="6.4"/><path d="m16 16 4.2 4.2"/>',
  image: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="m5 18 5-5 3.5 3.5L17 13l3 3"/>',
  calendar: '<rect x="4" y="5.5" width="16" height="15" rx="2"/><path d="M8 3.5v4M16 3.5v4M4 10h16"/>',
  clock: '<circle cx="12" cy="12" r="8"/><path d="M12 7.5V12l3 2"/>',
  doc: '<path d="M6 3.5h8l4 4V20H6z"/><path d="M14 3.5V8h4M9 12h6M9 15.5h4"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M18.7 5.3l-1.4 1.4M6.7 17.3l-1.4 1.4"/>',
  shield: '<path d="M12 3.5 5 6.2v5.4c0 4.4 3 7.5 7 8.9 4-1.4 7-4.5 7-8.9V6.2z"/><path d="m9 12 2 2 4-4"/>',
  info: '<circle cx="12" cy="12" r="8.4"/><path d="M12 11v5M12 8h.01"/>',
  alert: '<path d="M12 4 3 19h18z"/><path d="M12 9v5M12 17h.01"/>',
  lock: '<rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8.5 10V7.5a3.5 3.5 0 0 1 7 0V10"/>',
  edit: '<path d="M4 20h4L19.5 8.5a2.1 2.1 0 0 0-3-3L5 17z"/><path d="m14.5 6.5 3 3"/>',
  gear: '<circle cx="12" cy="12" r="3.2"/><path d="M12 3.5v2.2M12 18.3v2.2M20.5 12h-2.2M5.7 12H3.5M18 6l-1.6 1.6M7.6 16.4 6 18M18 18l-1.6-1.6M7.6 7.6 6 6"/>',
  logout: '<path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4"/><path d="m15 8 4 4-4 4M19 12H9"/>',
  eye: '<path d="M2.7 12S6.2 5.8 12 5.8 21.3 12 21.3 12 17.8 18.2 12 18.2 2.7 12 2.7 12z"/><circle cx="12" cy="12" r="3"/>',
  eyeoff: '<path d="M4 4l16 16"/><path d="M9.6 6.3A9.7 9.7 0 0 1 12 6c5.8 0 9.3 6 9.3 6a17 17 0 0 1-3 3.6M6.2 8.2A17.4 17.4 0 0 0 2.7 12s3.5 6 9.3 6a9.6 9.6 0 0 0 4-.9"/><path d="M10 10a2.8 2.8 0 0 0 4 4"/>',
  spin: '<path d="M12 3.5a8.5 8.5 0 1 1-8.5 8.5"/>',
  sort: '<path d="M4 6h9M4 12h6M4 18h3"/><path d="m15 9 3 3 3-3"/><path d="M18 12V4"/>',
  arrup: '<path d="M7 17 17 7M9 7h8v8"/>',
  arrdown: '<path d="m7 7 10 10M17 9v8H9"/>',
  store: '<path d="M4 10.4V9.2L5.5 4h13L20 9.2v1.2"/><path d="M4 10.4c0 1.5 1.2 2.6 2.7 2.6s2.6-1.1 2.6-2.6c0 1.5 1.2 2.6 2.7 2.6s2.6-1.1 2.6-2.6c0 1.5 1.2 2.6 2.7 2.6S20 11.9 20 10.4"/><path d="M5.6 13v7h12.8v-7"/><path d="M10 20v-4.2h4V20"/>',
  sparkle: '<path d="M12 3.5 13.6 8l4.4 1.6L13.6 11 12 15.5 10.4 11 6 9.6 10.4 8z"/><path d="M18.5 15.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>',
  trash: '<path d="M4.5 7h15"/><path d="M9.5 7V4.8h5V7"/><path d="m6.5 7 .9 12.2a1.2 1.2 0 0 0 1.2 1.1h6.8a1.2 1.2 0 0 0 1.2-1.1L17.5 7"/><path d="M10.2 11v5.5M13.8 11v5.5"/>'
};

function icon(name, cls) {
  return '<svg class="ic ' + (cls || "") + '" viewBox="0 0 24 24" fill="none" ' +
    'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" ' +
    'aria-hidden="true">' + (ICON[name] || ICON.box) + '</svg>';
}

function storeArt() {
  return '<svg viewBox="0 0 360 200" role="img" aria-label="Illustration of the Arvid DryGoods storefront">' +
    '<defs><linearGradient id="awningGrad" x1="0" y1="0" x2="0" y2="1">' +
    '<stop offset="0" stop-color="#2a7154"/><stop offset="1" stop-color="#1f5c43"/></linearGradient></defs>' +
    '<rect width="360" height="200" fill="#eaf2eb"/>' +
    '<ellipse cx="180" cy="187" rx="120" ry="11" fill="#dbe7dd"/>' +
    '<rect x="72" y="86" width="216" height="96" fill="#f3e7cf"/>' +
    '<rect x="86" y="102" width="82" height="56" rx="6" fill="#173f30"/>' +
    '<rect x="94" y="114" width="18" height="34" rx="3" fill="#d8a24a"/>' +
    '<rect x="118" y="110" width="18" height="38" rx="3" fill="#9ec2a8"/>' +
    '<rect x="142" y="118" width="16" height="30" rx="3" fill="#cf6a4f"/>' +
    '<rect x="180" y="102" width="38" height="80" rx="4" fill="#216247"/>' +
    '<circle cx="210" cy="144" r="2.6" fill="#d8e6dd"/>' +
    '<rect x="228" y="102" width="46" height="42" rx="5" fill="#e6d6b8"/>' +
    '<path d="M233 116h36M233 126h36" stroke="#d3bf9c" stroke-width="3" stroke-linecap="round"/>' +
    '<rect x="72" y="44" width="216" height="42" rx="10" fill="url(#awningGrad)"/>' +
    '<text x="180" y="71" text-anchor="middle" font-family="Inter, Segoe UI, Arial, sans-serif" ' +
    'font-size="13" font-weight="800" letter-spacing="1.4" fill="#ffffff">ARVID DRYGOODS</text>' +
    '<path d="M72 86h36v14a18 18 0 0 1-36 0z" fill="#f6eddb"/>' +
    '<path d="M108 86h36v14a18 18 0 0 1-36 0z" fill="#8fb89c"/>' +
    '<path d="M144 86h36v14a18 18 0 0 1-36 0z" fill="#f6eddb"/>' +
    '<path d="M180 86h36v14a18 18 0 0 1-36 0z" fill="#8fb89c"/>' +
    '<path d="M216 86h36v14a18 18 0 0 1-36 0z" fill="#f6eddb"/>' +
    '<path d="M252 86h36v14a18 18 0 0 1-36 0z" fill="#8fb89c"/>' +
    '<rect x="72" y="86" width="216" height="5" fill="#e6d8bd"/>' +
    '</svg>';
}

/* ---------- layout helpers ---------- */
function render(html, opts) {
  opts = opts || {};
  app.innerHTML = '<div class="phone ' + (opts.dark ? "dark " : "") + (opts.pad || "") + '">' +
    html + '</div>' + (opts.nav ? tabbar(opts.nav) : "");
}

function tabbar(active) {
  var tabs = [["dash", "home", "Home"], ["inventory", "box", "Inventory"],
              ["stock", "receipt", "Stock"], ["sales", "chart", "Sales"]];
  return '<nav class="tabbar">' + tabs.map(function (t) {
    return '<button data-go="' + t[0] + '" class="' + (active === t[0] ? "on" : "") + '">' +
      '<span class="tab-ic">' + icon(t[1]) + '</span>' + t[2] + '</button>';
  }).join("") + '</nav>';
}

function topbar(title, back, right, sub, backId) {
  return '<div class="topbar">' +
    '<button class="iconbtn" data-back="' + esc(back || "dash") + '"' +
    (backId ? ' data-back-id="' + esc(backId) + '"' : "") +
    ' aria-label="Back">' + icon("arrowleft") + '</button>' +
    '<div><div class="title">' + esc(title) + '</div>' +
    (sub ? '<div class="sub">' + esc(sub) + '</div>' : "") + '</div>' +
    (right || '<span></span>') + '</div>';
}

function thumb(p, cls) {
  if (p && p.image_url) {
    return '<img class="thumb ' + (cls || "") + '" src="' + esc(p.image_url) + '" alt="">';
  }
  return '<span class="thumb thumb-empty ' + (cls || "") + '">' + icon("box") + '</span>';
}

function stockClass(p) {
  return p.stock === 0 ? "out" : (p.stock <= p.reorder_level ? "low" : "");
}
function stockText(p) {
  if (p.stock === 0) return "Out of stock";
  if (p.stock <= p.reorder_level) return p.stock + " left \u00B7 Low";
  return p.stock + " in stock";
}
function stockPill(p) {
  var c = stockClass(p);
  return '<span class="pill ' + c + '">' +
    (c === "out" ? "Out of stock" : c === "low" ? "Low stock" : "In stock") + '</span>';
}

var BUCKET_ENDS = ["10 AM", "12 PM", "2 PM", "4 PM", "6 PM", "8 PM"];
function lastBucket(hourly) {
  var last = -1;
  (hourly || []).forEach(function (h, i) { if (h.total > 0) last = i; });
  return last;
}
function untilLabel(hourly, prefix) {
  var last = lastBucket(hourly);
  if (last < 0) return "No sales yet";
  return prefix + ", until " + BUCKET_ENDS[last];
}
function hourlyChart(hourly) {
  var last = lastBucket(hourly);
  if (last < 0) return '<div class="bars-empty">No sales recorded in this period yet.</div>';
  var list = (hourly || []).slice(0, last + 1);
  var max = 1;
  list.forEach(function (h) { if (h.total > max) max = h.total; });
  return '<div class="bars">' + list.map(function (h, i) {
    var height = Math.max(8, Math.round(h.total / max * 110));
    return '<div class="bar-col"><span class="bar-val">' + moneyShort(h.total) + '</span>' +
      '<div class="bar' + (i === last ? " on" : "") + '" style="height:' + height + 'px"></div>' +
      '<span class="bar-label">' + esc(h.label) + '</span></div>';
  }).join("") + '</div>';
}

function findProduct(id) {
  for (var i = 0; i < st.cache.length; i++) {
    if (st.cache[i].product_id === id) return st.cache[i];
  }
  return null;
}

/* ---------- cart ---------- */
function cartCount() {
  return st.cart.reduce(function (n, l) { return n + l.quantity; }, 0);
}
function cartTotal() {
  return Math.round(st.cart.reduce(function (n, l) { return n + l.quantity * l.price; }, 0) * 100) / 100;
}
function addToCart(p, qty, quiet) {
  if (!p) return false;
  qty = Math.max(1, parseInt(qty, 10) || 1);
  if (p.stock < 1) { toast(p.name + " is out of stock."); return false; }
  var line = null;
  st.cart.forEach(function (l) { if (l.product_id === p.product_id) line = l; });
  if (line) {
    if (line.quantity >= line.stock) {
      toast("Only " + line.stock + " in stock for " + p.name + ".");
      return false;
    }
    line.quantity = Math.min(line.stock, line.quantity + qty);
  } else {
    st.cart.push({
      product_id: p.product_id, name: p.name, price: p.price,
      stock: p.stock, image_url: p.image_url,
      quantity: Math.min(p.stock, qty)
    });
  }
  if (!quiet) toast(p.name + " added to cart");
  return true;
}
function changeQty(id, delta) {
  var line = null;
  st.cart.forEach(function (l) { if (l.product_id === id) line = l; });
  if (!line) return;
  var next = line.quantity + delta;
  if (next < 1) return;
  if (next > line.stock) { toast("Only " + line.stock + " available."); return; }
  line.quantity = next;
}

function cartCard(l) {
  return '<div class="cart-card"><div class="cart-top">' + thumb(l) +
    '<div class="item-main"><div class="item-name">' + esc(l.name) + '</div>' +
    '<div class="item-meta">' + esc(l.product_id) + ' \u00B7 ' + money(l.price) + ' each</div></div>' +
    '<button class="cart-x" data-x="' + esc(l.product_id) + '" aria-label="Remove ' + esc(l.name) + '">' +
    icon("x") + '</button></div>' +
    '<div class="cart-line"><div class="stepper">' +
    '<button data-step="-1" data-line="' + esc(l.product_id) + '" aria-label="Decrease quantity">' + icon("minus") + '</button>' +
    '<span>' + l.quantity + '</span>' +
    '<button data-step="1" data-line="' + esc(l.product_id) + '" aria-label="Increase quantity">' + icon("plus") + '</button>' +
    '</div><strong>' + money(l.quantity * l.price) + '</strong></div>' +
    '<div class="cart-avail">' + l.stock + ' available \u00B7 Maximum ' + l.stock + ' units</div></div>';
}

/* ---------- engines & camera ---------- */
async function loadEngines() {
  if (st.engines.length) return;
  try {
    var data = await api("/api/recognition/engines");
    st.engines = data.engines || [];
    if (data.default && st.engine === "auto") st.engine = data.default;
  } catch (e) { /* keep the fallback list */ }
}
function engineOptions() {
  var names = {
    template: "Template matching (A)",
    orb: "ORB features (B)",
    cnn: "CNN transfer learning (C)"
  };
  var list = st.engines.length ? st.engines :
    [{ name: "template", available: true }, { name: "orb", available: true }];
  var out = '<option value="auto"' + (st.engine === "auto" ? " selected" : "") +
    '>Auto \u00B7 best available</option>';
  return out + list.map(function (e) {
    return '<option value="' + esc(e.name) + '"' + (e.available ? "" : " disabled") +
      (st.engine === e.name ? " selected" : "") + '>' + esc(names[e.name] || e.name) +
      (e.available ? "" : " \u00B7 unavailable") + '</option>';
  }).join("");
}
function engineLabel(name) {
  return {
    template: "Template matching (A)",
    orb: "ORB features (B)",
    cnn: "CNN transfer learning (C)"
  }[name] || cap(name || "Auto");
}

function stopCamera() {
  if (st.stream) {
    st.stream.getTracks().forEach(function (track) { track.stop(); });
    st.stream = null;
  }
}

function captureFrame() {
  var vid = $("vid");
  if (!vid || !vid.videoWidth) { toast("Camera is not ready yet."); return; }
  var canvas = document.createElement("canvas");
  canvas.width = vid.videoWidth;
  canvas.height = vid.videoHeight;
  canvas.getContext("2d").drawImage(vid, 0, 0, canvas.width, canvas.height);
  canvas.toBlob(function (blob) {
    if (blob) sendIdentify(new File([blob], "capture.jpg", { type: "image/jpeg" }));
  }, "image/jpeg", 0.92);
}

async function sendIdentify(file) {
  stopCamera();
  if (st.photoUrl) { try { URL.revokeObjectURL(st.photoUrl); } catch (e) { /* ignore */ } }
  st.photoUrl = URL.createObjectURL(file);
  var img = $("preview");
  if (img) { img.src = st.photoUrl; img.hidden = false; }
  var status = $("scanStatus");
  if (status) status.hidden = false;
  var form = new FormData();
  form.append("image", file, file.name || "capture.jpg");
  form.append("engine", st.engine || "auto");
  try {
    st.match = await api("/api/recognize", "POST", form);
    st.match.mode = "photo";
    go("check");
  } catch (err) {
    if (status) status.hidden = true;
    toast(err.message);
  }
}

async function barcodeLookup(code) {
  code = String(code || "").trim();
  if (!code) { toast("Enter a barcode number."); return; }
  var started = performance.now();
  try {
    var p = await api("/api/barcode/" + encodeURIComponent(code));
    st.match = {
      accepted: true, product: p, mode: "barcode", engine: "Barcode",
      confidence: 100, elapsed_ms: performance.now() - started, candidates: []
    };
    st.photoUrl = null;
    go("check");
  } catch (err) {
    toast(err.message || "Product could not be identified.");
  }
}

function openManualSearch() {
  st.pickIntent = st.identifyIntent && st.identifyIntent !== "detail" ? st.identifyIntent : null;
  go("inventory", { keepPick: true });
}

/* ---------- views ---------- */
var V = {};

V.login = function () {
  var signup = st.authMode === "signup";
  if (signup) {
    render(
      '<div class="brand"><span class="logo">' + icon("store") + '</span>' +
      '<div><h1>Arvid DryGoods</h1><p>Mansalay, Oriental Mindoro</p></div></div>' +
      '<h2 class="login-title" style="font-size:34px">Create your account.</h2>' +
      '<p class="login-lead">Staff accounts can record sales and deliveries. Ask the store owner if you need help.</p>' +
      '<form id="signupForm" novalidate>' +
      '<label class="field"><span>Username</span><input id="ru" maxlength="32" autocomplete="username" placeholder="3-32 characters"></label>' +
      '<label class="field"><span>Email address</span><input id="re" type="email" autocomplete="email" placeholder="you@example.com">' +
      '<span class="hint">Required. You can sign in with your email or username.</span></label>' +
      '<label class="field"><span>Phone number (optional)</span><input id="rph" type="tel" autocomplete="tel" placeholder="e.g. 0917 123 4567"></label>' +
      '<label class="field"><span>Password</span><div class="inputwrap"><input id="rp" type="password" autocomplete="new-password" placeholder="At least 8 characters">' +
      '<button type="button" class="peek" id="peekSignup" aria-label="Show password">' + icon("eye") + '</button></div></label>' +
      '<label class="field"><span>Confirm password</span><input id="rc" type="password" autocomplete="new-password"></label>' +
      '<div class="err" id="e"></div>' +
      '<button class="btn" type="submit">' + icon("arrowright") + 'Create account</button>' +
      '</form>' +
      '<div class="login-contact">Already have an account?<br>' +
      '<button class="link" id="toLogin">Log in</button></div>' +
      '<p class="login-foot">ADISMS \u00B7 Inventory &amp; Sales Management</p>', {});
  } else {
    render(
      '<div class="brand"><span class="logo">' + icon("store") + '</span>' +
      '<div><h1>Arvid DryGoods</h1><p>Mansalay, Oriental Mindoro</p></div></div>' +
      '<div class="hero-ill">' + storeArt() + '</div>' +
      '<h2 class="login-title">Welcome back.</h2>' +
      '<p class="login-lead">Your store, in good order. Sign in to manage inventory and sales.</p>' +
      '<form id="loginForm" novalidate>' +
      '<label class="field"><span>Username or email</span><div class="inputwrap">' +
      '<input id="lu" autocomplete="username" placeholder="Enter your staff account">' +
      '<span class="peek">' + icon("user") + '</span></div></label>' +
      '<label class="field"><span>Password</span><div class="inputwrap">' +
      '<input id="lp" type="password" autocomplete="current-password" placeholder="Enter your password">' +
      '<button type="button" class="peek" id="peek" aria-label="Show password">' + icon("eye") + '</button></div></label>' +
      '<div class="forgot-row"><button type="button" class="link" id="forgot">Forgot password?</button></div>' +
      '<div class="err" id="e"></div>' +
      '<button class="btn" type="submit">' + icon("arrowright") + 'Sign in</button>' +
      '</form>' +
      '<div class="safety">' + icon("lock") +
      '<div>For authorized owners and employees only. Use your own staff account.</div></div>' +
      '<p class="login-foot">ADISMS \u00B7 Inventory &amp; Sales Management</p>' +
      '<div class="login-contact">Need an account or help signing in?<br>' +
      '<button class="link" id="toSignup">Create a staff account</button>' +
      '<span class="muted"> \u00B7 </span>' +
      '<button class="link" id="help">Contact the store owner</button></div>', {});
  }

  function bindPeek(btnId, inputId) {
    var btn = $(btnId);
    if (!btn) return;
    btn.onclick = function () {
      var input = $(inputId);
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.innerHTML = icon(show ? "eyeoff" : "eye");
    };
  }

  if (signup) {
    bindPeek("peekSignup", "rp");
    $("toLogin").onclick = function () { st.authMode = "login"; go("login"); };
    $("signupForm").onsubmit = async function (event) {
      event.preventDefault();
      var payload = {
        username: $("ru").value.trim(),
        email: $("re").value.trim(),
        phone: $("rph").value.trim(),
        password: $("rp").value,
        confirm_password: $("rc").value
      };
      if (!payload.username || !payload.email || !payload.password) {
        $("e").textContent = "Username, email and password are required.";
        return;
      }
      if (payload.password !== payload.confirm_password) {
        $("e").textContent = "Passwords do not match.";
        return;
      }
      var btn = $("signupForm").querySelector(".btn");
      btn.disabled = true;
      try {
        applyUser(await api("/api/register", "POST", payload));
        st.authMode = "login";
        toast("Account created");
        go("dash");
      } catch (err) {
        $("e").textContent = err.message;
        btn.disabled = false;
      }
    };
    return;
  }

  bindPeek("peek", "lp");
  $("toSignup").onclick = function () { st.authMode = "signup"; go("login"); };
  $("help").onclick = function () { toast("Ask the store owner to help with your account."); };
  $("forgot").onclick = function () { toast("Password resets are handled by the store owner."); };
  $("loginForm").onsubmit = async function (event) {
    event.preventDefault();
    var identifier = $("lu").value.trim();
    var password = $("lp").value;
    if (!identifier || !password) {
      $("e").textContent = "Enter your username or email and password.";
      return;
    }
    var btn = $("loginForm").querySelector(".btn");
    btn.disabled = true;
    try {
      applyUser(await api("/api/login", "POST", { username: identifier, password: password }));
      toast("Welcome back, " + cap(st.user));
      go("dash");
    } catch (err) {
      $("e").textContent = err.message;
      btn.disabled = false;
    }
  };
};

V.dash = async function () {
  var d = await api("/api/dashboard");
  st.email = d.email || "";
  st.phone = d.phone || "";
  var attention = (d.stock_checker || []).slice(0, 2);
  var attentionCount = d.out_of_stock_count + d.stock_low_count;

  var attentionHtml = attention.length ? '<div class="card">' + attention.map(function (p) {
    var out = p.stock === 0;
    return '<div class="attn"><span class="tile ' + (out ? "red" : "amber") + '">' + icon("box") + '</span>' +
      '<div class="item-main"><div class="item-name">' + esc(p.name) + '</div>' +
      '<div class="item-meta">' + (out ? "Out of stock" : "Low stock") +
      ' \u00B7 Reorder at ' + p.reorder_level + '</div></div>' +
      '<span class="num ' + (out ? "red" : "amber") + '">' + p.stock + '</span></div>';
  }).join("") + '</div>'
    : '<div class="notice">' + icon("check") + '<div>Every product is above its reorder level.</div></div>';

  render(
    '<header class="page-head"><div><h1 class="h-title">Arvid DryGoods</h1>' +
    '<p class="h-sub">' + longDate(new Date()) + '</p></div>' +
    '<button class="avatar" data-go="settings" aria-label="Account settings">' + icon("user") + '</button></header>' +
    '<div class="greet"><h2>' + greeting() + ', ' + esc(cap(d.user)) + '!</h2>' +
    '<span>' + esc(d.role) + '</span></div>' +
    '<section class="hero"><span class="corner">' + icon("trend") + '</span>' +
    '<div class="label">Today\u2019s sales</div>' +
    '<div class="amount">' + money(d.sales_today) + '</div>' +
    '<div class="hero-stats">' +
    '<div><b>' + whole(d.transactions_today) + '</b><span>Transactions</span></div>' +
    '<div><b>' + whole(d.items_sold_today) + '</b><span>Items sold</span></div>' +
    '<div><b>' + whole(d.products_count) + '</b><span>Products</span></div>' +
    '</div></section>' +
    '<div class="quick">' +
    '<button data-go="sale">' + icon("plus") + '<span>New sale</span></button>' +
    '<button data-go="identify" data-intent="detail">' + icon("scan") + '<span>Scan product</span></button>' +
    '<button data-go="delivery">' + icon("boxplus") + '<span>Receive stock</span></button>' +
    '</div>' +
    '<div class="card"><div class="sec" style="margin:0 0 14px"><h2>Sales today</h2>' +
    '<button class="link" data-go="sales">View report ' + icon("arrowright") + '</button></div>' +
    '<div class="charthead"><span>Sales in PHP</span><span>' +
    untilLabel(d.hourly_sales, "Today") + '</span></div>' +
    hourlyChart(d.hourly_sales) + '</div>' +
    '<div class="sec"><h2>Stock needs attention</h2>' +
    (attentionCount ? '<button class="link" data-go="stock">View all ' + attentionCount + ' ' +
      icon("arrowright") + '</button>' : "") + '</div>' +
    attentionHtml +
    '<p class="footnote">ADISMS \u00B7 Inventory &amp; Sales Management</p>',
    { nav: "dash", pad: "pb-tab" });
};

V.inventory = async function () {
  var all = await api("/api/products");
  st.cache = all;
  var picking = !!st.pickIntent;
  var pickText = st.pickIntent === "sale" ? "Choose a product to add to the sale."
    : st.pickIntent === "delivery" ? "Choose the product that arrived."
      : "Choose a product.";

  render(
    '<div class="page-head"><div><h1 class="h-title">Inventory</h1>' +
    '<p class="h-sub">Your centralized product catalog</p></div>' +
    '<button class="iconbtn" data-go="identify" data-intent="detail" aria-label="Scan product">' +
    icon("scan") + '</button></div>' +
    (picking ? '<div class="notice">' + icon("scan") + '<div class="stack"><b>' + pickText +
      '</b><button class="link" id="cancelPick">Cancel selection</button></div></div>' : "") +
    '<div class="search">' + icon("search") +
    '<input id="invQ" placeholder="Search name or Product ID" value="' + esc(st.inv.q) + '">' +
    '<button class="glyphbtn" data-go="identify" data-intent="detail" aria-label="Scan barcode">' +
    icon("barcode") + '</button></div>' +
    '<div class="filters">' +
    '<div class="select' + (st.inv.filter !== "all" ? " active" : "") + '"><select id="invFilter">' +
    '<option value="all"' + (st.inv.filter === "all" ? " selected" : "") + '>All stock</option>' +
    '<option value="in"' + (st.inv.filter === "in" ? " selected" : "") + '>In stock</option>' +
    '<option value="low"' + (st.inv.filter === "low" ? " selected" : "") + '>Low stock</option>' +
    '<option value="out"' + (st.inv.filter === "out" ? " selected" : "") + '>Out of stock</option>' +
    '</select>' + icon("chevdown") + '</div>' +
    '<div class="select"><select id="invSort">' +
    '<option value="id"' + (st.inv.sort === "id" ? " selected" : "") + '>Sort: Product ID</option>' +
    '<option value="name"' + (st.inv.sort === "name" ? " selected" : "") + '>Sort: Name</option>' +
    '<option value="low"' + (st.inv.sort === "low" ? " selected" : "") + '>Sort: Lowest stock</option>' +
    '<option value="price"' + (st.inv.sort === "price" ? " selected" : "") + '>Sort: Price</option>' +
    '</select>' + icon("chevdown") + '</div></div>' +
    '<div id="invList"></div>',
    { nav: "inventory", pad: "pb-tab" });

  function filtered() {
    var q = st.inv.q.trim().toLowerCase();
    var list = all.filter(function (p) {
      if (q && p.name.toLowerCase().indexOf(q) < 0 && p.product_id.toLowerCase().indexOf(q) < 0) return false;
      if (st.inv.filter === "in") return p.stock > 0;
      if (st.inv.filter === "low") return p.stock > 0 && p.stock <= p.reorder_level;
      if (st.inv.filter === "out") return p.stock === 0;
      return true;
    });
    list.sort(function (a, b) {
      if (st.inv.sort === "name") return a.name.localeCompare(b.name);
      if (st.inv.sort === "low") {
        var ra = a.reorder_level ? a.stock / a.reorder_level : 99;
        var rb = b.reorder_level ? b.stock / b.reorder_level : 99;
        return ra - rb;
      }
      if (st.inv.sort === "price") return a.price - b.price;
      return a.product_id.localeCompare(b.product_id);
    });
    return list;
  }

  function paint() {
    var list = filtered();
    var units = list.reduce(function (n, p) { return n + p.stock; }, 0);
    $("invList").innerHTML =
      '<div class="listmeta"><span>' + list.length + ' product' + (list.length === 1 ? "" : "s") +
      ' \u00B7 ' + whole(units) + ' unit' + (units === 1 ? "" : "s") + '</span>' +
      '<button class="link" data-go="register">' + icon("plus") + ' Add product</button></div>' +
      (list.length ? list.map(function (p) {
        var action = picking
          ? 'data-pick="' + esc(p.product_id) + '"'
          : 'data-go="detail" data-id="' + esc(p.product_id) + '"';
        return '<button class="item" ' + action + '>' + thumb(p) +
          '<div class="item-main"><div class="item-name">' + esc(p.name) + '</div>' +
          '<div class="item-meta">' + esc(p.product_id) + ' \u00B7 Reorder at ' + p.reorder_level + '</div></div>' +
          '<div class="item-right"><div class="item-price">' + money(p.price) + '</div>' +
          '<div class="item-stock ' + stockClass(p) + '">' + stockText(p) + '</div></div></button>';
      }).join("") :
        '<div class="empty"><span class="tile neutral">' + icon("search") + '</span>' +
        '<b>No products match</b>Try another search or add a new product.</div>');
  }

  $("invQ").oninput = function () { st.inv.q = this.value; paint(); };
  $("invFilter").onchange = function () {
    st.inv.filter = this.value;
    this.parentNode.className = "select" + (this.value !== "all" ? " active" : "");
    paint();
  };
  $("invSort").onchange = function () { st.inv.sort = this.value; paint(); };
  if (picking) {
    $("cancelPick").onclick = function () { st.pickIntent = null; go("inventory"); };
  }
  paint();
};

V.stock = async function () {
  var d = await api("/api/stock");
  st.cache = (d.attention || []).concat(d.above || []);
  var attention = d.attention || [];

  render(
    '<div class="page-head"><div><h1 class="h-title">Stock checker</h1>' +
    '<p class="h-sub">' + longDate(new Date()) + ' \u00B7 Live stock levels</p></div>' +
    '<button class="iconbtn" data-go="delivery" aria-label="Receive stock">' +
    icon("boxplus") + '</button></div>' +
    '<div class="summary2">' +
    '<div class="card red"><b>' + d.summary.out_of_stock + '</b><span>Out of stock</span></div>' +
    '<div class="card amber"><b>' + d.summary.low_stock + '</b><span>Low stock</span></div></div>' +
    '<div class="sortline">' + icon("sort") + ' Lowest quantities first</div>' +
    (attention.length ? attention.map(function (p) {
      var c = stockClass(p);
      return '<div class="stock-card-row"><div class="cart-top">' + thumb(p) +
        '<div class="item-main"><div class="item-name">' + esc(p.name) + '</div>' +
        '<div class="item-meta">' + esc(p.product_id) + ' \u00B7 Reorder at ' + p.reorder_level + ' units</div></div>' +
        '<div class="stocknum ' + (c === "out" ? "red" : "amber") + '"><b>' + p.stock + '</b><span>units</span></div></div>' +
        '<div class="stock-foot"><span class="pill ' + c + '">' +
        (c === "out" ? "Out of stock" : "Low stock") + '</span>' +
        '<button class="link" data-go="delivery" data-id="' + esc(p.product_id) + '">' +
        icon("boxplus") + ' Receive stock</button></div></div>';
    }).join("") : '<div class="notice">' + icon("check") +
      '<div>Every product is above its reorder level.</div></div>') +
    '<div class="notice">' + icon("info") +
    '<div>Record deliveries when goods arrive. Supplier orders are handled by store staff, not automatically.</div></div>' +
    '<p class="small muted" style="text-align:center">' +
    ((d.above || []).length
      ? (d.above.length + ' other product' + (d.above.length === 1 ? " is" : "s are") +
        ' above ' + (d.above.length === 1 ? "its" : "their") + ' reorder level' +
        (d.above.length === 1 ? "" : "s") + '.')
      : "No products are above their reorder levels.") + '</p>',
    { nav: "stock", pad: "pb-tab" });
};

V.sales = async function (params) {
  params = params || {};
  if (!params.keepDate) st.reportDate = todayISO();
  var d = await api("/api/reports/day?date=" + encodeURIComponent(st.reportDate));
  var isToday = d.date === todayISO();
  var dateObj = parseDay(d.date);
  var top = d.top_products || [];
  var shown = top.slice(0, 3);
  var rest = top.slice(3);
  var max = 1;
  shown.forEach(function (p) { if (p.quantity > max) max = p.quantity; });
  var prefix = isToday ? "Today" : shortDate(dateObj);

  render(
    '<h1 class="h-title" style="margin-bottom:2px">Daily sales</h1>' +
    '<div class="datenav">' +
    '<button id="prevDay" aria-label="Previous day">' + icon("chevleft") + '</button>' +
    '<button class="center" id="todayJump">' + icon("calendar") + esc(shortDate(dateObj)) +
    (isToday ? ' \u00B7 Today' : "") + '</button>' +
    '<button id="nextDay" aria-label="Next day"' + (isToday ? " disabled" : "") + '>' +
    icon("chevright") + '</button></div>' +
    '<div class="sales-total"><div><div class="cap">Total sales</div>' +
    '<div class="amount">' + money(d.summary.total) + '</div></div>' +
    '<div class="side"><b>' + d.summary.transactions + ' transaction' +
    (d.summary.transactions === 1 ? "" : "s") + '</b>' +
    '<span>' + d.summary.items + ' items sold</span></div></div>' +
    '<div class="card"><div class="charthead"><span>Sales in PHP</span><span>' +
    untilLabel(d.hourly, prefix) + '</span></div>' + hourlyChart(d.hourly) + '</div>' +
    '<div class="sec"><h2>Top selling products</h2><span class="muted small">By units sold</span></div>' +
    '<div class="card">' +
    (shown.length ? shown.map(function (p) {
      return '<div class="toprow"><div class="toprow-head"><span>' + esc(p.name) + '</span>' +
        '<span>' + p.quantity + ' \u00B7 ' + moneyShort(p.revenue) + '</span></div>' +
        '<div class="progress"><i style="width:' + Math.max(4, Math.round(p.quantity / max * 100)) + '%"></i></div></div>';
    }).join("") + (rest.length ? '<p class="otherline">Other: ' + rest.map(function (p) {
      return esc(p.name) + ' ' + p.quantity + ' \u00B7 ' + moneyShort(p.revenue);
    }).join("; ") + '</p>' : "")
      : '<div class="empty" style="padding:14px 6px"><b>No products sold</b>Nothing was sold on this date.</div>') +
    '</div>' +
    '<div class="sec"><h2>Recent sales</h2></div>' +
    '<div class="card">' +
    (d.recent.length ? d.recent.map(function (s) {
      return '<div class="sale-row"><span class="sale-ic">' + icon("receipt") + '</span>' +
        '<b>' + esc(s.sale_number) + '</b>' +
        '<span class="when">' + timeOf(s.created_at) + ' \u00B7 ' + s.items +
        ' item' + (s.items === 1 ? "" : "s") + '</span>' +
        '<span class="amt">' + money(s.total) + '</span></div>';
    }).join("") : '<div class="empty" style="padding:14px 6px"><b>No sales yet</b>' +
      'Sales recorded on this date will appear here.</div>') +
    '</div>',
    { nav: "sales", pad: "pb-tab" });

  $("prevDay").onclick = function () {
    var d2 = parseDay(st.reportDate);
    d2.setDate(d2.getDate() - 1);
    st.reportDate = iso(d2);
    go("sales", { keepDate: true });
  };
  $("nextDay").onclick = function () {
    var d2 = parseDay(st.reportDate);
    d2.setDate(d2.getDate() + 1);
    if (iso(d2) > todayISO()) return;
    st.reportDate = iso(d2);
    go("sales", { keepDate: true });
  };
  $("todayJump").onclick = function () {
    st.reportDate = todayISO();
    go("sales", { keepDate: true });
  };
};

V.detail = async function (params) {
  var id = params && params.id ? params.id : (st.detailId || "");
  if (!id) { go("inventory"); return; }
  st.detailId = id;
  var p = await api("/api/products/" + encodeURIComponent(id));
  st.cache = [p];
  var movements = p.movements || [];
  var last = movements[0];

  var lastLine = last
    ? '<div class="lastmove">' + icon("clock") + 'Last movement \u00B7 ' +
      esc(last.type === "SALE" ? "Sale " + last.reference :
        last.type === "DELIVERY" ? "Delivery" : "Initial stock") +
      ', ' + relDay(last.created_at) + ', ' + timeOf(last.created_at) + '</div>'
    : '<div class="lastmove">' + icon("clock") + 'No stock movements yet.</div>';

  var movementRows = movements.map(function (m) {
    var up = m.qty_change > 0;
    var label = m.type === "SALE" ? "Sale \u00B7 " + m.reference :
      m.type === "DELIVERY" ? "Delivery \u00B7 " + m.reference : "Initial stock";
    return '<div class="movement"><span class="tile green">' +
      icon(m.type === "SALE" ? "arrup" : m.type === "DELIVERY" ? "arrdown" : "box") + '</span>' +
      '<div class="item-main"><div class="item-name" style="font-size:14.5px">' + esc(label) + '</div>' +
      '<div class="item-meta">' + relDay(m.created_at) + ', ' + timeOf(m.created_at) +
      ' \u00B7 ' + m.qty_before + ' \u2192 ' + m.qty_after + ' units</div></div>' +
      '<span class="qty' + (up ? "" : " neg") + '">' + (up ? "+" : "\u2212") +
      Math.abs(m.qty_change) + '</span></div>';
  }).join("");

  var photoPanel = st.detailEdit
    ? '<div class="photo-panel"><div class="row">' +
      (p.image_url ? '<img class="thumb" src="' + esc(p.image_url) + '" alt="">'
        : '<span class="thumb thumb-empty">' + icon("camera") + '</span>') +
      '<div class="item-main"><h3>Recognition photos</h3>' +
      '<p>Used by template matching, ORB and CNN. Add clear, well-lit angles.</p>' +
      '<input type="file" id="photoFiles" accept="image/*" multiple></div></div>' +
      '<div class="err" id="photoErr"></div>' +
      '<button class="btn sm quiet" id="photoUpload">Upload photos</button></div>'
    : "";

  var removePanel = st.role === "Owner"
    ? '<div class="danger-zone"><div><b>Remove product</b>' +
      '<p>Deletes this catalog entry and its photos. Products with sales or ' +
      'delivery history are kept so past reports stay accurate.</p></div>' +
      '<button class="btn danger" id="deleteProduct">' + icon("trash") +
      ' Delete product</button></div>'
    : "";

  render(
    topbar("Product details", "inventory", '<button class="iconbtn" id="editPhoto" aria-label="Recognition photos">' +
      icon("edit") + '</button>') +
    '<div class="detail-hero">' +
    (p.image_url ? '<img src="' + esc(p.image_url) + '" alt="' + esc(p.name) + '">'
      : '<span class="thumb-empty">' + icon("box") + '</span>') + '</div>' +
    '<div class="detail-eyebrow"><span class="cap">Product \u00B7 ' + esc(p.product_id) + '</span>' +
    stockPill(p) + '</div>' +
    '<h1 class="detail-title">' + esc(p.name) + '</h1>' +
    '<p class="detail-sub">' + (p.barcode ? "Barcode " + esc(p.barcode) : "No barcode on file") + '</p>' +
    '<div class="card pricegrid">' +
    '<div><div class="cap">Selling price</div><b>' + money(p.price) + '</b></div>' +
    '<div><div class="cap">Available stock</div><b>' + p.stock + ' units</b></div>' +
    '<div class="divider"></div>' +
    '<div class="foot"><span>Reorder level</span><b>' + p.reorder_level + ' units</b></div></div>' +
    lastLine +
    '<div class="sec" style="margin-bottom:6px"><h2>Stock movement</h2></div>' +
    (movements.length ? '<div class="card">' + movementRows + '</div>'
      : '<div class="card"><p class="muted small">Sales and deliveries for this product will appear here.</p></div>') +
    photoPanel +
    removePanel +
    '<p class="footnote">Identifying a product never changes stock.</p>' +
    '<div class="actionbar"><div class="btn-row">' +
    '<button class="btn ghost" id="detailDeliver">' + icon("boxplus") + 'Receive stock</button>' +
    '<button class="btn" id="detailSale">' + icon("plus") + 'New sale</button>' +
    '</div></div>',
    { pad: "pb-action" });

  $("editPhoto").onclick = function () {
    st.detailEdit = !st.detailEdit;
    go("detail", { id: p.product_id });
  };
  $("detailDeliver").onclick = function () {
    st.pickIntent = null;
    go("delivery", { id: p.product_id });
  };
  $("detailSale").onclick = function () {
    if (addToCart(p, 1, true)) go("sale");
  };
  if ($("deleteProduct")) {
    $("deleteProduct").onclick = async function () {
      if (!window.confirm('Delete "' + p.name + '"? This cannot be undone.')) return;
      var btn = $("deleteProduct");
      btn.disabled = true;
      try {
        await api("/api/products/" + encodeURIComponent(p.product_id), "DELETE");
        toast(p.name + " deleted");
        go("inventory");
      } catch (err) {
        toast(err.message);
        btn.disabled = false;
      }
    };
  }
  if (st.detailEdit) {
    $("photoUpload").onclick = async function () {
      var files = $("photoFiles").files;
      if (!files || !files.length) { $("photoErr").textContent = "Choose at least one photo."; return; }
      var form = new FormData();
      for (var i = 0; i < files.length; i++) form.append("image", files[i]);
      try {
        var result = await api("/api/products/" + encodeURIComponent(p.product_id) + "/images", "POST", form);
        toast(result.images.length + " photo(s) uploaded");
        st.detailEdit = false;
        go("detail", { id: p.product_id });
      } catch (err) {
        $("photoErr").textContent = err.message;
      }
    };
  }
};

V.identify = async function (params) {
  params = params || {};
  await loadEngines();
  if (params.intent) st.identifyIntent = params.intent;
  if (params.tab) st.tab = params.tab;
  if (!st.tab) st.tab = "photo";
  var photoMode = st.tab !== "barcode";

  var photoPanel =
    '<div class="viewer" id="viewer">' +
    '<video id="vid" class="viewer-media" playsinline muted hidden></video>' +
    '<img id="preview" class="viewer-media" alt="" hidden>' +
    '<div class="frame"><i></i><i></i><i></i><i></i></div>' +
    '<div class="frame-hint">Keep one product inside the frame</div>' +
    '<div class="frame-hint" id="scanStatus" hidden style="top:18px;bottom:auto">Recognizing product\u2026</div>' +
    '</div>' +
    '<div class="hintline">' + icon("sun") + 'Use good lighting. Keep the label facing you.</div>' +
    '<div class="capture-ring"><button class="capture" id="capture" aria-label="Capture product photo"></button></div>' +
    '<button class="dark-link subtle" id="choosePhoto">' + icon("image") + ' Choose a photo instead</button>' +
    '<button class="dark-link" id="manualSearch">' + icon("search") + ' Search manually instead</button>' +
    '<input type="file" id="file" accept="image/*" hidden>';

  var barcodePanel =
    '<div class="viewer" id="barcodeViewer" style="min-height:250px">' +
    '<video id="bcamVideo" class="viewer-media" playsinline muted hidden></video>' +
    '<div class="frame"><i></i><i></i><i></i><i></i></div>' +
    '<div class="frame-hint">Point the camera at the barcode</div>' +
    '</div>' +
    '<label class="dark-label">Barcode number</label>' +
    '<div class="dark-field"><input id="bcode" class="input" inputmode="numeric" placeholder="Scan or type a barcode">' +
    '<button class="btn" id="blook">Look up</button></div>' +
    '<button class="dark-link subtle" id="bcam">' + icon("barcode") + ' Scan with camera</button>' +
    '<button class="dark-link" id="manualSearch">' + icon("search") + ' Search manually instead</button>';

  render(
    topbar("Identify product", st.identifyBack || "dash",
      '<button class="iconbtn" id="engineToggle" aria-label="Recognition settings">' + icon("sparkle") + '</button>') +
    '<p class="dark-sub">Scan a barcode or take a clear product photo.</p>' +
    '<div class="seg">' +
    '<button id="tabBarcode" class="' + (photoMode ? "" : "on") + '">' + icon("barcode") + ' Barcode</button>' +
    '<button id="tabPhoto" class="' + (photoMode ? "on" : "") + '">' + icon("camera") + ' Photo</button></div>' +
    '<div class="engine-panel" id="enginePanel" hidden><label for="engine">Recognition method</label>' +
    '<select id="engine">' + engineOptions() + '</select></div>' +
    (photoMode ? photoPanel : barcodePanel) +
    '<p class="dark-note">Identifying a product does not change stock.</p>',
    { dark: true });

  $("tabBarcode").onclick = function () { go("identify", { tab: "barcode", intent: st.identifyIntent }); };
  $("tabPhoto").onclick = function () { go("identify", { tab: "photo", intent: st.identifyIntent }); };
  $("engineToggle").onclick = function () { $("enginePanel").hidden = !$("enginePanel").hidden; };
  $("engine").onchange = function () { st.engine = this.value; };
  $("manualSearch").onclick = openManualSearch;

  if (photoMode) {
    $("choosePhoto").onclick = function () { $("file").click(); };
    $("file").onchange = function () {
      if (this.files && this.files[0]) sendIdentify(this.files[0]);
    };
    $("capture").onclick = async function () {
      if (st.stream) { captureFrame(); return; }
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { $("file").click(); return; }
      try {
        st.stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment" }
        });
        var vid = $("vid");
        vid.srcObject = st.stream;
        vid.hidden = false;
        var preview = $("preview");
        if (preview) preview.hidden = true;
        await vid.play();
        toast("Camera ready \u2014 tap again to capture.");
      } catch (err) {
        $("file").click();
      }
    };
    return;
  }

  $("blook").onclick = function () { barcodeLookup($("bcode").value); };
  $("bcode").onkeydown = function (event) {
    if (event.key === "Enter") { event.preventDefault(); barcodeLookup($("bcode").value); }
  };
  $("bcam").onclick = function () {
    if (!("BarcodeDetector" in window)) {
      toast("Camera barcode scanning isn't supported here. Type the number instead.");
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      toast("Camera is unavailable in this browser.");
      return;
    }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }).then(function (stream) {
      st.stream = stream;
      var vid = $("bcamVideo");
      if (!vid) return;
      vid.srcObject = stream;
      vid.hidden = false;
      vid.play().then(function () {
        var detector = new BarcodeDetector();
        function tick() {
          if (!st.stream) return;
          detector.detect(vid).then(function (codes) {
            if (codes && codes.length) {
              var code = codes[0].rawValue;
              stopCamera();
              var intent = st.identifyIntent;
              go("identify", { tab: "barcode", intent: intent }).then(function () {
                barcodeLookup(code);
              });
              return;
            }
          }).catch(function () { /* keep scanning */ }).then(function () {
            if (st.stream) setTimeout(tick, 300);
          });
        }
        tick();
      });
    }).catch(function (err) {
      toast("Camera unavailable: " + err.message);
    });
  };
};

V.check = function () {
  var m = st.match;
  if (!m || !m.product) { go("identify"); return; }
  var p = m.product;
  var barcode = m.mode === "barcode";
  var accepted = !!m.accepted;

  if (!accepted) {
    var candidates = (m.candidates || []).map(function (c) {
      return '<button class="cand" data-candidate="' + esc(c.product_id) + '">' +
        '<span><b>' + esc(c.name || c.product_id) + '</b>' +
        '<small>' + esc(c.product_id) + ' \u00B7 Select this product</small></span>' +
        '<span class="pct">' + c.confidence + '%</span></button>';
    }).join("");
    render(
      topbar("Check the product", "identify", null, barcode ? "Barcode lookup" : "Photo identification") +
      '<span class="pill">No confident match</span>' +
      '<h1 class="check-hero">Couldn&rsquo;t confirm this product.</h1>' +
      '<p class="check-lead">Nothing matched closely enough. Pick a closest match, search manually, or register the item.</p>' +
      '<div class="card">' + (candidates || '<p class="muted">No close matches were found.</p>') + '</div>' +
      '<div class="check-actions btn-row">' +
      '<button class="btn ghost" id="manual">' + icon("search") + 'Manual search</button>' +
      '<button class="btn ghost" data-go="register">' + icon("plus") + 'Register item</button></div>' +
      '<div class="notice amber">' + icon("alert") +
      '<div>Retry with a clearer photo, or check that the product has reference photos.</div></div>',
      {});
    $("manual").onclick = openManualSearch;
    return;
  }

  var img = p.image_url
    ? '<img src="' + esc(p.image_url) + '" alt="' + esc(p.name) + '">'
    : (st.photoUrl ? '<img src="' + esc(st.photoUrl) + '" alt="Captured product photo">'
      : '<span class="thumb-empty">' + icon("box") + '</span>');
  var recognition = (!barcode && m.engine)
    ? '<div class="item-meta" style="margin-top:6px">' + esc(engineLabel(m.engine)) +
      ' \u00B7 ' + m.confidence + '% confidence \u00B7 ' + Math.round(m.elapsed_ms) + ' ms</div>'
    : "";

  render(
    topbar("Check the product", "identify", null, barcode ? "Barcode lookup" : "Photo identification") +
    '<span class="pill">' + (barcode ? "Barcode match" : "Possible match") + '</span>' +
    '<h1 class="check-hero">Is this the right product?</h1>' +
    '<p class="check-lead">Compare the name and pack size before continuing.</p>' +
    '<div class="match-card"><div class="match-img">' + img + '</div>' +
    '<div class="match-body"><h3>' + esc(p.name) + '</h3>' +
    '<div class="meta">' + esc(p.product_id) + (p.barcode ? ' \u00B7 ' + esc(p.barcode) : "") + '</div>' +
    recognition +
    '<div class="match-foot"><span class="price">' + money(p.price) + '</span>' +
    '<span class="stock">' + p.stock + ' units \u00B7 Before sale</span></div></div></div>' +
    '<div class="check-actions"><button class="btn" id="accept">' + icon("check") +
    ' Yes, use this product</button>' +
    '<div class="btn-row" style="margin-top:10px">' +
    '<button class="btn ghost" id="retake">' + icon("refresh") +
    (barcode ? ' Scan again' : ' Retake photo') + '</button>' +
    '<button class="btn ghost" id="manual">' + icon("search") + ' Manual search</button>' +
    '</div></div>' +
    '<div class="notice">' + icon("shield") +
    '<div>Stock stays the same. A sale or delivery must be saved to update inventory.</div></div>' +
    '<div class="notice amber">' + icon("scan") +
    '<div class="stack"><b>Unsure or no product found?</b><br>' +
    'Retry with a clearer photo or search manually. If it is a new item, register it first.' +
    '<button class="link" id="regFromCheck">' + icon("plus") + ' Register new product</button></div></div>',
    {});

  $("accept").onclick = function () {
    if (st.identifyIntent === "sale") {
      if (addToCart(p, 1, true)) go("sale");
    } else if (st.identifyIntent === "delivery") {
      go("delivery", { id: p.product_id });
    } else {
      go("detail", { id: p.product_id });
    }
  };
  $("retake").onclick = function () {
    go("identify", { intent: st.identifyIntent, tab: barcode ? "barcode" : "photo" });
  };
  $("manual").onclick = openManualSearch;
  $("regFromCheck").onclick = function () { go("register"); };
};

V.sale = async function () {
  var all = await api("/api/products");
  st.cache = all;
  var q = st.saleQuery || "";
  var matches = q.trim() ? all.filter(function (p) {
    var needle = q.trim().toLowerCase();
    return p.name.toLowerCase().indexOf(needle) >= 0 ||
      p.product_id.toLowerCase().indexOf(needle) >= 0;
  }) : [];

  var results = q.trim()
    ? '<div class="result-list">' + (matches.length ? matches.slice(0, 6).map(function (p) {
      return '<div class="result-row">' + thumb(p) +
        '<div class="item-main"><div class="item-name">' + esc(p.name) + '</div>' +
        '<div class="item-meta">' + esc(p.product_id) + ' \u00B7 ' + money(p.price) +
        ' \u00B7 ' + stockText(p) + '</div></div>' +
        '<button class="add" data-add="' + esc(p.product_id) + '" aria-label="Add ' + esc(p.name) + '">' +
        icon("plus") + '</button></div>';
    }).join("") : '<p class="empty" style="padding:18px 6px">No products match that search.</p>') + '</div>'
    : "";

  var browse = st.saleBrowse ? '<div class="card" style="padding:6px 16px">' +
    all.map(function (p) {
      return '<div class="result-row">' + thumb(p) +
        '<div class="item-main"><div class="item-name">' + esc(p.name) + '</div>' +
        '<div class="item-meta">' + esc(p.product_id) + ' \u00B7 ' + stockText(p) + '</div></div>' +
        '<button class="add" data-add="' + esc(p.product_id) + '" aria-label="Add ' + esc(p.name) + '">' +
        icon("plus") + '</button></div>';
    }).join("") + '</div>' : "";

  var cart = st.cart.length
    ? st.cart.map(cartCard).join("") +
      '<div class="notice">' + icon("info") +
      '<div>Stock is deducted only after you record the sale. Check quantities before saving.</div></div>'
    : '<div class="empty" style="padding:24px 10px"><span class="tile neutral">' + icon("box") + '</span>' +
      '<b>Your cart is empty</b>Scan a product or search above to add items.</div>';

  render(
    topbar("New sale", st.saleBack || "dash", null,
      shortDate(new Date()) + ' \u00B7 Before saving') +
    '<div class="search">' + icon("search") +
    '<input id="saleQ" placeholder="Add by name or Product ID" autocomplete="off" value="' + esc(q) + '">' +
    '<button class="glyphbtn" data-go="identify" data-intent="sale" aria-label="Scan product">' +
    icon("scan") + '</button></div>' +
    '<div class="btn-row" style="margin-bottom:8px">' +
    '<button class="btn ghost" data-go="identify" data-intent="sale">' + icon("scan") + ' Scan product</button>' +
    '<button class="btn ghost" id="browseBtn">' + icon("box") + ' Browse items</button></div>' +
    results + browse +
    '<div class="cart-head"><h2>Cart</h2><span>' + st.cart.length + ' product' +
    (st.cart.length === 1 ? "" : "s") + '</span></div>' +
    cart +
    '<div class="actionbar"><div class="total"><span>Total \u00B7 ' + cartCount() +
    ' item' + (cartCount() === 1 ? "" : "s") + '</span><b>' + money(cartTotal()) + '</b></div>' +
    '<button class="btn" id="recordSale"' + (st.cart.length ? "" : " disabled") + '>' +
    icon("check") + ' Record sale \u00B7 ' + money(cartTotal()) + '</button></div>',
    { pad: "pb-action" });

  $("saleQ").oninput = function () {
    st.saleQuery = this.value;
    clearTimeout(st.saleTimer);
    st.saleTimer = setTimeout(function () {
      go("sale").then(function () {
        var field = $("saleQ");
        if (field) {
          field.focus();
          field.setSelectionRange(field.value.length, field.value.length);
        }
      });
    }, 260);
  };
  $("browseBtn").onclick = function () {
    st.saleBrowse = !st.saleBrowse;
    go("sale");
  };
  $("recordSale").onclick = async function () {
    if (!st.cart.length) return;
    var btn = $("recordSale");
    btn.disabled = true;
    try {
      st.receipt = await api("/api/sales/cart", "POST", {
        items: st.cart.map(function (l) {
          return { product_id: l.product_id, quantity: l.quantity };
        })
      });
      st.cart = [];
      st.saleQuery = "";
      st.saleBrowse = false;
      toast("Sale recorded");
      go("receipt");
    } catch (err) {
      toast(err.message);
      btn.disabled = false;
    }
  };
};

V.receipt = function () {
  var r = st.receipt;
  if (!r) { go("dash"); return; }
  var dt = new Date(String(r.created_at || "").replace(" ", "T"));
  render(
    topbar("Sale recorded", "dash") +
    '<div class="success-ic">' + icon("check") + '</div>' +
    '<h1 class="receipt-title">Sale saved!</h1>' +
    '<p class="receipt-lead">Your sale and stock changes are recorded.</p>' +
    '<div class="receipt-card">' +
    '<div class="store-name">Arvid DryGoods</div>' +
    '<div class="store-addr">Villa Celestial, Mansalay</div>' +
    '<div class="rule"></div>' +
    '<div class="kv"><span>Sale number</span><b>' + esc(r.sale_number) + '</b></div>' +
    '<p class="small muted" style="margin-top:6px">' +
    (isNaN(dt.getTime()) ? "" : longDate(dt) + ' \u00B7 ') + timeOf(r.created_at) +
    (r.username ? ' \u00B7 ' + esc(cap(r.username)) : "") + '</p>' +
    '<div class="rule"></div>' +
    r.lines.map(function (l) {
      return '<div class="rline"><div><b>' + esc(l.name) + '</b>' +
        '<small>' + l.quantity + ' \u00D7 ' + money(l.unit_price) + ' \u00B7 ' +
        esc(l.product_id) + '</small></div><b>' + money(l.line_total) + '</b></div>';
    }).join("") +
    '<div class="rule"></div>' +
    '<div class="total-line"><span>Total \u00B7 ' + r.item_count + ' item' +
    (r.item_count === 1 ? "" : "s") + '</span><b>' + money(r.total) + '</b></div>' +
    '</div>' +
    '<div class="stock-card"><h3>' + icon("box") + ' Stock updated</h3>' +
    r.lines.map(function (l) {
      return '<div class="stock-line"><span>' + esc(l.name) + ' \u00B7 \u2212' +
        l.quantity + ' unit' + (l.quantity === 1 ? "" : "s") + '</span><b>' +
        l.qty_before + ' \u2192 ' + l.qty_after + '</b></div>';
    }).join("") + '</div>' +
    '<div class="actionbar"><button class="btn" data-go="sale">' + icon("plus") +
    'Start a new sale</button><button class="btn ghost" data-go="dash">Back to home</button></div>',
    { pad: "pb-action-lg" });
};

V.delivery = async function (params) {
  params = params || {};
  if (params.clear) st.deliveryId = null;
  if (params.id) st.deliveryId = params.id;
  if (!st.deliveryId) return deliveryPicker();
  var p;
  try {
    p = await api("/api/products/" + encodeURIComponent(st.deliveryId));
  } catch (err) {
    st.deliveryId = null;
    return deliveryPicker();
  }
  st.cache = [p];
  if (params.id && st.prevView !== "delivery") {
    st.deliveryBack = (st.prevView === "detail" || st.prevView === "stock") ? st.prevView : "stock";
  }
  var back = st.deliveryBack || "stock";
  var backId = back === "detail" ? p.product_id : null;

  render(
    topbar("Receive delivery", back, null, "Add goods that have arrived at the store", backId) +
    '<label class="field-label">Product</label>' +
    '<div class="product-pick">' + thumb(p) +
    '<div class="item-main"><div class="item-name">' + esc(p.name) + '</div>' +
    '<div class="item-meta">' + esc(p.product_id) + ' \u00B7 ' + stockText(p) + '</div></div>' +
    '<button class="link" id="changeProduct">Change</button></div>' +
    '<label class="field" style="margin-top:20px"><span>Quantity received (units)</span>' +
    '<input id="delQty" type="number" min="1" step="1" inputmode="numeric" value="1">' +
    '<span class="hint">Enter the number of individual units, not boxes.</span></label>' +
    '<label class="field"><span>Date received</span>' +
    '<input id="delDate" type="date" value="' + todayISO() + '" max="' + todayISO() + '"></label>' +
    '<label class="field"><span>Delivery reference</span>' +
    '<input id="delRef" maxlength="60" placeholder="e.g. D-012 / DR-1028"></label>' +
    '<div class="after-card"><h3>Stock after saving</h3>' +
    '<div class="after-row">' +
    '<div class="cell"><span>Current</span><b>' + p.stock + '</b></div>' +
    '<div class="op">+</div>' +
    '<div class="cell"><span>Received</span><b id="addQty">1</b></div>' +
    '<div class="op">\u2192</div>' +
    '<div class="cell new"><span>New stock</span><b id="newQty">' + (p.stock + 1) + '</b></div>' +
    '</div><p class="after-note">Current stock includes all recorded sales and deliveries.</p></div>' +
    '<div class="notice">' + icon("info") + '<div id="saveNote">Saving this delivery adds 1 unit to inventory. ' +
    'Stock stays at ' + p.stock + ' until you save.</div></div>' +
    '<div class="actionbar"><button class="btn" id="saveDelivery">' + icon("boxplus") +
    '<span id="saveLabel">Save delivery \u00B7 Add 1 unit</span></button></div>',
    { pad: "pb-action" });

  function updateAfter() {
    var qty = parseInt($("delQty").value, 10);
    var ok = isFinite(qty) && qty >= 1;
    $("addQty").textContent = ok ? qty : "0";
    $("newQty").textContent = ok ? p.stock + qty : "\u2014";
    $("saveNote").textContent = ok
      ? "Saving this delivery adds " + qty + " unit" + (qty === 1 ? "" : "s") +
        " to inventory. Stock stays at " + p.stock + " until you save."
      : "Enter a quantity of at least 1 unit.";
    $("saveLabel").textContent = ok
      ? "Save delivery \u00B7 Add " + qty + " unit" + (qty === 1 ? "" : "s")
      : "Save delivery";
    $("saveDelivery").disabled = !ok;
  }

  $("delQty").oninput = updateAfter;
  $("changeProduct").onclick = function () {
    st.deliveryId = null;
    go("delivery", { clear: true });
  };
  $("saveDelivery").onclick = async function () {
    var qty = parseInt($("delQty").value, 10);
    if (!isFinite(qty) || qty < 1) { toast("Enter a valid quantity."); return; }
    var btn = $("saveDelivery");
    btn.disabled = true;
    try {
      await api("/api/deliveries", "POST", {
        product_id: p.product_id,
        quantity: qty,
        reference: $("delRef").value.trim(),
        received_on: $("delDate").value || null
      });
      st.deliveryId = null;
      toast("Delivery saved \u00B7 " + qty + " unit" + (qty === 1 ? "" : "s") + " added");
      go("detail", { id: p.product_id });
    } catch (err) {
      toast(err.message);
      btn.disabled = false;
    }
  };
};

async function deliveryPicker() {
  var all = await api("/api/products");
  st.cache = all;
  if (st.prevView === "detail" || st.prevView === "stock") {
    st.deliveryBack = st.prevView;
  }
  var back = st.deliveryBack || "stock";

  render(
    topbar("Receive delivery", back, null, "Choose the product that arrived") +
    '<div class="search">' + icon("search") +
    '<input id="pickQ" placeholder="Search name or Product ID"></div>' +
    '<div id="pickList"></div>' +
    '<div class="notice">' + icon("info") +
    '<div>Deliveries add stock only after you save them.</div></div>',
    {});

  function paint() {
    var q = $("pickQ").value.trim().toLowerCase();
    var list = all.filter(function (p) {
      return !q || p.name.toLowerCase().indexOf(q) >= 0 ||
        p.product_id.toLowerCase().indexOf(q) >= 0;
    });
    $("pickList").innerHTML = list.length
      ? '<div class="card" style="padding:6px 16px">' + list.map(function (p) {
        return '<button class="item" data-deliver="' + esc(p.product_id) + '">' + thumb(p) +
          '<div class="item-main"><div class="item-name">' + esc(p.name) + '</div>' +
          '<div class="item-meta">' + esc(p.product_id) + ' \u00B7 ' + p.stock + ' in stock</div></div>' +
          '<div class="item-right">' + icon("chevright") + '</div></button>';
      }).join("") + '</div>'
      : '<div class="empty"><b>No match</b>Try another search.</div>';
  }

  $("pickQ").oninput = paint;
  paint();
}

V.register = function () {
  var back = st.prevView && st.prevView !== "register" ? st.prevView : "dash";
  render(
    topbar("Register product", back, null, "Create a new product record") +
    '<label class="photo-upload" for="regPhoto">' +
    '<span class="thumb thumb-empty" id="regPreview">' + icon("camera") + '</span>' +
    '<span class="item-main"><b>Product photo</b>' +
    '<span>Keep the name and pack size clear.</span>' +
    '<span class="link">' + icon("camera") + ' Take or upload photo</span></span></label>' +
    '<input type="file" id="regPhoto" accept="image/*" hidden>' +
    '<label class="field"><span>Product name</span>' +
    '<input id="regName" maxlength="80" placeholder="e.g. Ariel Powder \u00B7 70 g"></label>' +
    '<label class="field"><span>Product ID</span>' +
    '<input id="regId" maxlength="32" placeholder="e.g. P-009">' +
    '<span class="hint">Unique ID used for product lookup. Letters, numbers, hyphens and underscores.</span></label>' +
    '<label class="field"><span>Selling price (PHP)</span>' +
    '<input id="regPrice" type="number" min="0" step="0.01" inputmode="decimal" placeholder="0.00"></label>' +
    '<div class="field-row">' +
    '<label class="field"><span>Initial stock (units)</span>' +
    '<input id="regStock" type="number" min="0" step="1" inputmode="numeric" value="0"></label>' +
    '<label class="field"><span>Reorder level</span>' +
    '<input id="regReorder" type="number" min="0" step="1" inputmode="numeric" value="10"></label></div>' +
    '<label class="field"><span>Barcode (optional)</span>' +
    '<input id="regBarcode" inputmode="numeric" maxlength="64" placeholder="Scan or enter a barcode"></label>' +
    '<div class="notice">' + icon("info") +
    '<div id="regNote">Saving creates the product with its initial stock. Low-stock alerts appear at the reorder level.</div></div>' +
    '<p class="small muted">Check the catalog first to avoid duplicate products.</p>' +
    '<div class="err" id="regErr"></div>' +
    '<div class="actionbar"><button class="btn" id="saveProduct">' + icon("check") +
    ' Save product</button></div>',
    { pad: "pb-action" });

  $("regPhoto").onchange = function () {
    var file = this.files && this.files[0];
    if (!file) return;
    var preview = $("regPreview");
    if (preview) {
      preview.outerHTML = '<img class="thumb" id="regPreview" src="' +
        URL.createObjectURL(file) + '" alt="Selected product photo">';
    }
  };

  $("saveProduct").onclick = async function () {
    var name = $("regName").value.trim();
    var pid = $("regId").value.trim();
    if (!name || !pid) {
      $("regErr").textContent = "Product name and a unique Product ID are required.";
      return;
    }
    var btn = $("saveProduct");
    btn.disabled = true;
    $("regErr").textContent = "";
    try {
      var product = await api("/api/products", "POST", {
        name: name,
        product_id: pid,
        barcode: $("regBarcode").value.trim(),
        price: $("regPrice").value === "" ? 0 : parseFloat($("regPrice").value),
        stock: $("regStock").value === "" ? 0 : parseInt($("regStock").value, 10),
        reorder_level: $("regReorder").value === "" ? 10 : parseInt($("regReorder").value, 10)
      });
      var file = $("regPhoto").files && $("regPhoto").files[0];
      if (file) {
        var form = new FormData();
        form.append("image", file);
        await api("/api/products/" + encodeURIComponent(product.product_id) + "/images", "POST", form);
      }
      toast("Product registered");
      go("detail", { id: product.product_id });
    } catch (err) {
      $("regErr").textContent = err.message;
      btn.disabled = false;
    }
  };
};

V.settings = async function () {
  var d = await api("/api/settings");
  applyUser(d);
  render(
    topbar("Settings", "dash") +
    '<div class="card account-card"><span class="account-avatar">' + icon("user") + '</span>' +
    '<div class="item-main"><b>' + esc(d.username) + '</b>' +
    '<span>' + esc(d.role) + ' \u00B7 Staff account</span></div></div>' +
    '<div class="settings-sec">Contact details</div>' +
    '<div class="card"><form id="contactForm" novalidate>' +
    '<label class="field"><span>Email address</span>' +
    '<input id="setEmail" type="email" autocomplete="email" value="' + esc(d.email || "") + '">' +
    '<span class="hint">Required. You can sign in with your email or username.</span></label>' +
    '<label class="field"><span>Phone number (optional)</span>' +
    '<input id="setPhone" type="tel" autocomplete="tel" value="' + esc(d.phone || "") + '" placeholder="e.g. 0917 123 4567"></label>' +
    '<div class="err" id="contactErr"></div>' +
    '<button class="btn" type="submit">Save contact details</button></form></div>' +
    '<div class="settings-sec">Password</div>' +
    '<div class="card"><form id="passwordForm" novalidate>' +
    '<label class="field"><span>Current password</span>' +
    '<input id="curPass" type="password" autocomplete="current-password"></label>' +
    '<label class="field"><span>New password</span>' +
    '<input id="newPass" type="password" autocomplete="new-password" placeholder="At least 8 characters"></label>' +
    '<label class="field"><span>Confirm new password</span>' +
    '<input id="confPass" type="password" autocomplete="new-password"></label>' +
    '<div class="err" id="passErr"></div>' +
    '<button class="btn ghost" type="submit">Change password</button></form></div>' +
    '<div class="settings-sec">Session</div>' +
    '<button class="btn danger" id="logout">' + icon("logout") + 'Log out</button>' +
    '<p class="footnote">ADISMS \u00B7 Arvid DryGoods</p>',
    {});

  $("contactForm").onsubmit = async function (event) {
    event.preventDefault();
    var btn = $("contactForm").querySelector(".btn");
    btn.disabled = true;
    try {
      applyUser(await api("/api/settings", "PATCH", {
        email: $("setEmail").value.trim(),
        phone: $("setPhone").value.trim()
      }));
      $("contactErr").textContent = "";
      toast("Contact details saved");
    } catch (err) {
      $("contactErr").textContent = err.message;
    }
    btn.disabled = false;
  };

  $("passwordForm").onsubmit = async function (event) {
    event.preventDefault();
    var current = $("curPass").value;
    var next = $("newPass").value;
    var confirm = $("confPass").value;
    if (!current || !next) {
      $("passErr").textContent = "Fill in your current and new password.";
      return;
    }
    if (next !== confirm) {
      $("passErr").textContent = "New passwords do not match.";
      return;
    }
    var btn = $("passwordForm").querySelector(".btn");
    btn.disabled = true;
    try {
      await api("/api/settings/password", "POST", {
        current_password: current,
        new_password: next,
        confirm_password: confirm
      });
      $("curPass").value = $("newPass").value = $("confPass").value = "";
      $("passErr").textContent = "";
      toast("Password updated");
    } catch (err) {
      $("passErr").textContent = err.message;
    }
    btn.disabled = false;
  };

  $("logout").onclick = async function () {
    try { await api("/api/logout", "POST"); } catch (e) { /* sign out locally anyway */ }
    resetState();
    toast("Signed out");
    go("login");
  };
};

/* ---------- navigation ---------- */
async function go(view, params) {
  params = params || {};
  stopCamera();
  if (st.saleTimer && view !== "sale") {
    clearTimeout(st.saleTimer);
    st.saleTimer = null;
  }
  var previous = st.view;
  if (["dash", "inventory", "stock", "sales", "settings"].indexOf(view) >= 0 && !params.keepPick) {
    st.pickIntent = null;
  }
  if (view === "identify" && previous && previous !== "identify" && previous !== "check") {
    st.identifyBack = previous;
  }
  if (view === "sale" && previous && previous !== "sale" &&
      previous !== "check" && previous !== "identify" && previous !== "receipt") {
    st.saleBack = previous;
  }
  st.prevView = previous;
  st.view = view;
  try {
    await V[view](params);
    window.scrollTo(0, 0);
  } catch (err) {
    if (view !== "login") toast(err.message || "Something went wrong.");
  }
}

document.addEventListener("click", function (event) {
  var back = event.target.closest("[data-back]");
  if (back) {
    go(back.dataset.back, { id: back.dataset.backId, keepPick: false });
    return;
  }

  var deliver = event.target.closest("[data-deliver]");
  if (deliver) {
    go("delivery", { id: deliver.dataset.deliver });
    return;
  }

  var goEl = event.target.closest("[data-go]");
  if (goEl) {
    go(goEl.dataset.go, { id: goEl.dataset.id, intent: goEl.dataset.intent });
    return;
  }

  var pick = event.target.closest("[data-pick]");
  if (pick) {
    var picked = findProduct(pick.dataset.pick);
    if (!picked) { toast("Product not found."); return; }
    var intent = st.pickIntent;
    st.pickIntent = null;
    if (intent === "sale") {
      if (addToCart(picked, 1, true)) go("sale");
    } else if (intent === "delivery") {
      go("delivery", { id: picked.product_id });
    } else {
      go("detail", { id: picked.product_id });
    }
    return;
  }

  var candidate = event.target.closest("[data-candidate]");
  if (candidate) {
    api("/api/products/" + encodeURIComponent(candidate.dataset.candidate)).then(function (product) {
      var base = st.match || {};
      st.match = {
        accepted: true, product: product, mode: base.mode || "photo",
        engine: base.engine, confidence: base.confidence || 0, candidates: base.candidates || []
      };
      go("check");
    }).catch(function (err) { toast(err.message); });
    return;
  }

  var add = event.target.closest("[data-add]");
  if (add) {
    var product = findProduct(add.dataset.add);
    if (product && addToCart(product, 1)) go("sale");
    return;
  }

  var step = event.target.closest("[data-step]");
  if (step) {
    changeQty(step.dataset.line, Number(step.dataset.step));
    go("sale");
    return;
  }

  var remove = event.target.closest("[data-x]");
  if (remove) {
    st.cart = st.cart.filter(function (l) { return l.product_id !== remove.dataset.x; });
    go("sale");
  }
});

api("/api/me").then(function (user) {
  applyUser(user);
  go("dash");
}).catch(function () {
  go("login");
});
