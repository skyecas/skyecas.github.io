var bg = initCanvas(function(w, h) {
	rawW = w; rawH = h;
	W = w; H = h;
	sx = w / 2; sy = h / 2;
	orScale = Math.min(w / baseW, h / baseH);
	if (!isFinite(orScale) || orScale < 0.05) orScale = 1;
	var maxA = 0;
	try { for (var p of planets) if (p.a > maxA) maxA = p.a; } catch(e) {}
	if (maxA < 50) maxA = 300;
	camScale = Math.min(w, h) / (maxA * 2.4);
	if (!isFinite(camScale) || camScale < 0.01) camScale = 1;
});
var c = bg.canvas, ctx = bg.ctx;
// W,H set by initCanvas callback
var W = rawW, H = rawH;

// --- Scene center ---
var sx = W / 2, sy = H / 2;
var baseW = 1920, baseH = 1080;
var orScale = Math.min(W / baseW, H / baseH);
if (!isFinite(orScale) || orScale < 0.05) orScale = 1;

// --- Camera (physics → screen transform) ---
var AU = 180;
var camScale = (function() {
  var maxA = 0;
  try { for (var p of planets) if (p.a > maxA) maxA = p.a; } catch(e) { maxA = 300; }
  if (maxA < 50) maxA = 300;
  var cs = Math.min(W, H) / (maxA * 2.4);
  if (!isFinite(cs) || cs < 0.01) cs = 1;
  return cs;
})();

// --- Constants ---
var MU = 120;

var stars = createBgStars(800, W, H, { parallax: true });

var scrollY = 0;
window.addEventListener("scroll", function() { scrollY = window.scrollY; }, { passive: true });

// --- Kepler utilities ---
function solveKepler(M, e) {
  M = M % (2*Math.PI); if (M < 0) M += 2*Math.PI;
  var E = M + e * Math.sin(M);
  for (var i = 0; i < 30; i++) {
    var f = E - e * Math.sin(E) - M;
    if (Math.abs(f) < 1e-10) break;
    var denom = 1 - e * Math.cos(E);
    if (Math.abs(denom) < 1e-12) { E += 0.01; continue; }
    E = E - f / denom;
  }
  if (!isFinite(E)) return M;
  return E;
}
function trueFromEccentric(E, e) {
  return 2 * Math.atan2(
    Math.sqrt(1 + e) * Math.sin(E / 2),
    Math.sqrt(1 - e) * Math.cos(E / 2)
  );
}
function kepToCart(a, e, w, M0, t) {
  var n = Math.sqrt(MU / (a*a*a));
  var M = M0 + n * t;
  var E = solveKepler(M, e);
  var th = trueFromEccentric(E, e);
  var r = a * (1 - e * Math.cos(E));
  var x = r * Math.cos(th), y = r * Math.sin(th);
  var cw = Math.cos(w), sw = Math.sin(w);
  return { rx: x*cw - y*sw, ry: x*sw + y*cw, r: r, th: th };
}
function kepVel(a, e, w, M0, t) {
  var n = Math.sqrt(MU / (a*a*a));
  var M = M0 + n * t;
  var E = solveKepler(M, e);
  var th = trueFromEccentric(E, e);
  var r = a * (1 - e * Math.cos(E));
  var p = a * (1 - e*e);
  var vr = Math.sqrt(MU/p) * e * Math.sin(th);
  var vt = Math.sqrt(MU/p) * (1 + e * Math.cos(th));
  var vx = vr*Math.cos(th) - vt*Math.sin(th);
  var vy = vr*Math.sin(th) + vt*Math.cos(th);
  var cw = Math.cos(w), sw = Math.sin(w);
  return { vx: vx*cw - vy*sw, vy: vx*sw + vy*cw };
}

// --- Planets with real orbital elements, initialized from current date ---
var planets = [];
try {
  (function() {
    var now = new Date();
    var j2000 = new Date(2000, 0, 1, 12, 0, 0);
    var days = (now - j2000) / 86400000;
    if (!isFinite(days)) days = 0;

    var raw = [
      { n:"Mercury", aAu:0.3871, e:0.20563, w:1.3520, M0j:174.795, ndpd:4.0923, r:5, col:"#b0a894", mu:0.2 },
      { n:"Venus",   aAu:0.7233, e:0.00677, w:2.2962, M0j:50.416,  ndpd:1.6021, r:9, col:"#e8c880", mu:0.8 },
      { n:"Earth",   aAu:1.0000, e:0.01671, w:1.7966, M0j:357.527, ndpd:0.9856, r:11, col:"#4a9bd7", mu:1.0 },
      { n:"Mars",    aAu:1.5237, e:0.09340, w:5.8655, M0j:19.393,  ndpd:0.5240, r:8, col:"#c05030", mu:0.5 },
    ];
    planets = raw.map(function(p) {
      var M0real = (p.M0j + p.ndpd * days) % 360;
      if (M0real < 0) M0real += 360;
      var aPx = p.aAu * AU;
      return {
        n: p.n, a: aPx, e: p.e, w: p.w, M0: M0real * Math.PI / 180,
        r: p.r * orScale, col: p.col, so: p.r * 3 * orScale, mu: p.mu
      };
    });
  })();
} catch (e) { planets = []; }

function pPos(p, t) { return kepToCart(p.a, p.e, p.w, p.M0, t); }
function pVel(p, t) { return kepVel(p.a, p.e, p.w, p.M0, t); }

// --- Lambert solver (2D p-iteration) ---
function lambert(r1x, r1y, r2x, r2y, dt) {
  var r1m = Math.sqrt(r1x*r1x + r1y*r1y);
  var r2m = Math.sqrt(r2x*r2x + r2y*r2y);
  if (r1m < 1 || r2m < 1 || dt < 1) return null;
  var c = Math.sqrt((r2x-r1x)*(r2x-r1x)+(r2y-r1y)*(r2y-r1y));
  var s = (r1m + r2m + c) / 2;
  var cosDt = (r1x*r2x + r1y*r2y) / (r1m*r2m);
  cosDt = Math.max(-1, Math.min(1, cosDt));
  var dTheta = Math.acos(cosDt);
  if (dTheta > Math.PI) dTheta = 2*Math.PI - dTheta;
  var sinDt = Math.sin(dTheta);
  if (Math.abs(sinDt) < 0.001) return null;
  var A = Math.sqrt(r1m*r2m) * Math.sin(dTheta) / Math.abs(Math.sin(dTheta));
  if (Math.abs(A) < 0.001) return null;
  var pMin = (r1m + r2m - c) / 2; if (pMin < 1) pMin = 1;
  var p = Math.max(pMin + 5, 10);
  for (var it = 0; it < 80; it++) {
    var x = p/r1m - 1;
    var y = (x*cosDt - (p/r2m - 1)) / sinDt;
    var e = Math.sqrt(x*x + y*y);
    if (e >= 1) { p *= 1.4; continue; }
    var a = p / (1 - e*e); if (a <= 0) { p *= 1.3; continue; }
    var cosDE = 1 - r1m/a * (1 - cosDt);
    cosDE = Math.max(-1, Math.min(1, cosDE));
    var dE = Math.acos(cosDE);
    var sinDE = r1m*r2m*Math.sin(dTheta) / Math.sqrt(a*p);
    sinDE = Math.max(-1, Math.min(1, sinDE));
    var tof = Math.sqrt(a*a*a/MU) * (dE - sinDE);
    if (tof < 0) { p *= 1.2; continue; }
    if (Math.abs(tof - dt) < 0.5) {
      var fL = 1 - r2m/p * (1 - cosDt);
      var gL = r1m*r2m*sinDt / Math.sqrt(MU*p);
      if (Math.abs(gL) < 1) return null;
      return { vx: (r2x - fL*r1x)/gL, vy: (r2y - fL*r1y)/gL };
    }
    var dp = Math.max(p*0.001, 0.001);
    var p2 = p + dp;
    var x2 = p2/r1m - 1, y2 = (x2*cosDt - (p2/r2m - 1))/sinDt;
    var e2 = Math.sqrt(x2*x2 + y2*y2); if (e2 >= 1) { p = p2; continue; }
    var a2 = p2/(1-e2*e2); if (a2 <= 0) { p = p2; continue; }
    var cosDE2 = 1 - r1m/a2*(1-cosDt); cosDE2 = Math.max(-1,Math.min(1,cosDE2));
    var dE2 = Math.acos(cosDE2);
    var tof2 = Math.sqrt(a2*a2*a2/MU) * (dE2 - r1m*r2m*Math.sin(dTheta)/Math.sqrt(a2*p2));
    var dfdp = (tof2 - tof) / dp;
    if (Math.abs(dfdp) < 1e-10) { p += 10; continue; }
    var pn = p - (tof-dt)/dfdp;
    if (pn < pMin) pn = pMin + 0.1;
    if (pn > p*10) pn = p*10;
    if (Math.abs(pn - p) < 0.001) {
      var fL = 1 - r2m/p*(1-cosDt);
      var gL = r1m*r2m*sinDt / Math.sqrt(MU*p);
      if (Math.abs(gL) < 1) return null;
      return { vx: (r2x-fL*r1x)/gL, vy: (r2y-fL*r1y)/gL };
    }
    p = pn;
  }
  return null;
}

// --- Spacecraft state (sun-relative) ---
var sc = { rx: 0, ry: 0, vx: 0, vy: 0 };
var totalDV = 0;

// --- Finite burn model ---
var burn = { active: false, dvx: 0, dvy: 0, rate: 0, remaining: 0 };
var burnRate = 0.003;

// --- Orbit elements from state ---
function orbitalElements(rx, ry, vx, vy, mu) {
  var r = Math.sqrt(rx*rx + ry*ry);
  var v2 = vx*vx + vy*vy;
  var h = rx*vy - ry*vx; // angular momentum
  var eps = v2/2 - mu/r; // specific energy
  var a = eps < 0 ? -mu/(2*eps) : Infinity;
  var e = 1, aStr = "∞", eStr = "0", T = Infinity, rp = 0, ra = 0;
  if (eps < 0) {
    aStr = a.toFixed(1);
    var eCompX = (v2 - mu/r)*rx - (rx*vx + ry*vy)*vx;
    var eCompY = (v2 - mu/r)*ry - (rx*vx + ry*vy)*vy;
    e = Math.sqrt(eCompX*eCompX + eCompY*eCompY) / mu;
    eStr = e.toFixed(4);
    T = 2 * Math.PI * Math.sqrt(a*a*a/mu);
    rp = a * (1 - e);
    ra = a * (1 + e);
  }
  return { v: Math.sqrt(v2), a: aStr, e: eStr, T: T, rp: rp, ra: ra, r: r, h: h, eps: eps };
}

// --- Event log ---
var eventLog = [];
function logEvent(type, msg) {
  eventLog.push({ t: eventLog.length === 0 ? 0 : time, type: type, msg: msg });
  if (eventLog.length > 50) eventLog.shift();
}

// --- Mission state ---
var mission = {
  target: -1, phase: "idle", legStart: 0, legDur: 3000,
  correctionsLeft: 2, prevPlanet: -1, visited: [],
  inSOI: -1, soiTime: 0, lastCCtime: 0, flybyCooldown: 0,
};

function pickTarget(idx, visited, t) {
  var best = -1, bestScore = Infinity;
  for (var i = 0; i < planets.length; i++) {
    if (i === idx) continue;
    var skip = false;
    for (var v of visited) if (v === i) { skip = true; break; }
    if (skip) continue;
    var pp = pPos(planets[i], t);
    var cp = pPos(planets[idx], t);
    var dx = pp.rx - cp.rx, dy = pp.ry - cp.ry;
    var dist = Math.sqrt(dx*dx+dy*dy);
    var score = dist + Math.abs(planets[i].a - planets[idx].a) * 0.5;
    if (score < bestScore) { bestScore = score; best = i; }
  }
  return best;
}

function findBestTransfer(fromIdx, toIdx, t) {
  var ep = pPos(planets[fromIdx], t);
  var ev = pVel(planets[fromIdx], t);
  var targetPeriod = Math.min(10000, 2 * Math.PI * Math.sqrt(planets[toIdx].a * planets[toIdx].a * planets[toIdx].a / MU) * 1.5);
  var minDT = Math.max(500, targetPeriod * 0.3);
  var bestLam = null, bestDV = Infinity, bestDt = minDT;
  for (var rev = 0; rev <= 5; rev++) {
    var dt = minDT + rev * targetPeriod;
    var tp = pPos(planets[toIdx], t + dt);
    var lam = lambert(ep.rx, ep.ry, tp.rx, tp.ry, dt);
    if (!lam) continue;
    var dvx = lam.vx - ev.vx, dvy = lam.vy - ev.vy;
    var vInf = Math.sqrt(dvx*dvx + dvy*dvy);
    var dv = Math.sqrt(vInf * vInf + 2 / 15);
    if (dv < bestDV) { bestDV = dv; bestLam = lam; bestDt = dt; }
  }
  return { lam: bestLam, dv: bestDV, dt: bestDt };
}

function launch(t) {
  var ep = pPos(planets[2], t);
  var ev = pVel(planets[2], t);
  // Find best target by trying Lambert transfers to each planet
  var bestTarget = -1, bestDV = Infinity, bestTrans = null;
  for (var i = 0; i < planets.length; i++) {
    if (i === 2) continue;
    var trans = findBestTransfer(2, i, t);
    if (trans.lam && trans.dv < bestDV && trans.dv < 0.40) {
      bestDV = trans.dv; bestTarget = i; bestTrans = trans;
    }
  }
  // Fallback: if Lambert fails, use a fixed prograde burn toward the nearest planet
  if (bestTarget < 0 || !bestTrans || !bestTrans.lam) {
    for (var i = 0; i < planets.length; i++) {
      if (i === 2) continue;
      var tp = pPos(planets[i], t);
      var dx = tp.rx - ep.rx, dy = tp.ry - ep.ry;
      var dist = Math.sqrt(dx*dx + dy*dy);
      if (bestTarget < 0 || dist < bestDV) {
        bestDV = dist; bestTarget = i;
      }
    }
    var tp = pPos(planets[bestTarget], t);
    // Use prograde/retrograde burn based on target orbit vs Earth orbit
    var dvx = ev.vx, dvy = ev.vy;
    var spd = Math.sqrt(dvx*dvx + dvy*dvy);
    if (spd < 0.01) { dvx = 1; dvy = 0; spd = 1; }
    // Retrograde for inner planets, prograde for outer
    var dir = planets[bestTarget].a > planets[2].a ? 1 : -1;
    dvx = dvx / spd * dir; dvy = dvy / spd * dir;
    var vInf = 1;
    var dvm = 0.37;
    sc.rx = ep.rx + 15 * dvx / vInf;
    sc.ry = ep.ry + 15 * dvy / vInf;
    sc.vx = ev.vx; sc.vy = ev.vy;
    totalDV = 0;
    mission.phase = "burning"; mission.legStart = t; mission.prevPlanet = 2;
    mission.visited = [2]; mission.correctionsLeft = 2; mission.inSOI = -1;
    mission.flybyCooldown = 0;
    mission.target = bestTarget;
    mission.legDur = 5000;
    logEvent('launch', "Launch from Earth → " + planets[bestTarget].n + " (fallback)");
    burn.active = true; burn.dvx = dvx / vInf * dvm; burn.dvy = dvy / vInf * dvm;
    burn.rate = burnRate; burn.remaining = dvm;
    return;
  }
  var dvx = bestTrans.lam.vx - ev.vx, dvy = bestTrans.lam.vy - ev.vy;
  var vInf = Math.sqrt(dvx*dvx + dvy*dvy);
  var dvm = bestTrans.dv;
  sc.rx = ep.rx + 15 * dvx / vInf;
  sc.ry = ep.ry + 15 * dvy / vInf;
  sc.vx = ev.vx; sc.vy = ev.vy;
  totalDV = 0;
  mission.phase = "burning"; mission.legStart = t; mission.prevPlanet = 2;
  mission.visited = [2]; mission.correctionsLeft = 2; mission.inSOI = -1;
  mission.flybyCooldown = 0;
  mission.target = bestTarget;
  mission.legDur = bestTrans.dt;
  logEvent('launch', "Launch from Earth → " + planets[bestTarget].n + " (Δv=" + dvm.toFixed(3) + ")");
  burn.active = true; burn.dvx = dvx / vInf * dvm; burn.dvy = dvy / vInf * dvm;
  burn.rate = burnRate; burn.remaining = dvm;
}

// --- Verlet integration (patched conic) ---
function integrate(t, dt) {
  // Check SOI
  var soiIdx = -1;
  for (var i = 0; i < planets.length; i++) {
    var pp = pPos(planets[i], t);
    var dx = sc.rx - pp.rx, dy = sc.ry - pp.ry;
    var d = Math.sqrt(dx*dx + dy*dy);
    if (d < planets[i].so) { soiIdx = i; break; }
  }

  // SOI entry/exit events
  if (soiIdx >= 0 && mission.inSOI < 0) {
    mission.inSOI = soiIdx;
    mission.soiTime = t;
    logEvent('soi', "== " + planets[soiIdx].n + " SOI entry ==");
  } else if (soiIdx < 0 && mission.inSOI >= 0) {
    logEvent('soi', "== " + planets[mission.inSOI].n + " SOI exit ==");
    mission.inSOI = -1;
    mission.legStart = t;
    if (mission.target >= 0 && mission.target < planets.length) {
      var tp = pPos(planets[mission.target], t);
      var dx = tp.rx - sc.rx, dy = tp.ry - sc.ry;
      mission.legDur = Math.max(1000, Math.min(15000, Math.sqrt(dx*dx+dy*dy) * 5));
    }
    mission.correctionsLeft = 2;
    mission.lastCCtime = t;
  }

  var mu = mission.inSOI >= 0 ? planets[mission.inSOI].mu : MU;
  var rx = sc.rx, ry = sc.ry;

  if (mission.inSOI >= 0) {
    // Planet-centered integration
    var pp = pPos(planets[mission.inSOI], t);
    var prx = sc.rx - pp.rx, pry = sc.ry - pp.ry;
    var r2 = prx*prx + pry*pry;
    var r3 = Math.max(1, r2 * Math.sqrt(r2));
    var ax = -mu * prx / r3, ay = -mu * pry / r3;
    sc.vx += ax*dt/2; sc.vy += ay*dt/2;
    sc.rx += sc.vx*dt; sc.ry += sc.vy*dt;
    if (t % 2 < 1) pushTrail(sx + sc.rx * camScale, sy + sc.ry * camScale);
    prx = sc.rx - pp.rx; pry = sc.ry - pp.ry;
    r2 = prx*prx + pry*pry; r3 = Math.max(1, r2*Math.sqrt(r2));
    ax = -mu*prx/r3; ay = -mu*pry/r3;
    sc.vx += ax*dt/2; sc.vy += ay*dt/2;
  } else {
    // Sun-centered integration
    var r2 = rx*rx + ry*ry;
    var r3 = Math.max(1, r2 * Math.sqrt(r2));
    var ax = -MU*rx/r3, ay = -MU*ry/r3;
    sc.vx += ax*dt/2; sc.vy += ay*dt/2;
    sc.rx += sc.vx*dt; sc.ry += sc.vy*dt;
    if (t % 2 < 1) pushTrail(sx + sc.rx * camScale, sy + sc.ry * camScale);
    r2 = sc.rx*sc.rx + sc.ry*sc.ry; r3 = Math.max(1, r2*Math.sqrt(r2));
    ax = -MU*sc.rx/r3; ay = -MU*sc.ry/r3;
    sc.vx += ax*dt/2; sc.vy += ay*dt/2;
  }
}

// --- Trail ---
var trail = [];
function pushTrail(x, y) { trail.push({x:x,y:y}); if (trail.length > 400) trail.splice(0, trail.length - 400); }

// --- Particles ---
var particles = [];
function emit(x, y, n, hue, spd) {
  for (var i = 0; i < n; i++) {
    var a = Math.random()*Math.PI*2, s = 0.5+Math.random()*spd;
    particles.push({x:x,y:y,vx:Math.cos(a)*s,vy:Math.sin(a)*s,
      life:20+Math.random()*30,ml:20+Math.random()*30,sz:0.5+Math.random()*1.5,
      hue:hue+(Math.random()-0.5)*30});
  }
}

// --- Drawing ---
function drawSun() {
  if (!isFinite(camScale) || camScale === 0) return;
  var r1 = 45 / camScale, r2 = 14 / camScale;
  var g = ctx.createRadialGradient(0,0,0,0,0,r1);
  g.addColorStop(0,"rgba(255,240,200,0.6)"); g.addColorStop(0.15,"rgba(255,220,150,0.3)");
  g.addColorStop(0.4,"rgba(255,180,80,0.08)"); g.addColorStop(1,"rgba(255,150,50,0)");
  ctx.fillStyle = g; ctx.beginPath(); ctx.arc(0,0,r1,0,Math.PI*2); ctx.fill();
  var g2 = ctx.createRadialGradient(0,0,0,0,0,r2);
  g2.addColorStop(0,"#fff8e0"); g2.addColorStop(0.5,"#ffdd66"); g2.addColorStop(1,"#ff8800");
  ctx.fillStyle = g2; ctx.beginPath(); ctx.arc(0,0,r2,0,Math.PI*2); ctx.fill();
}

function drawOrbits() {
  if (!planets || planets.length === 0) return;
  for (var p of planets) {
    ctx.strokeStyle = "rgba(60,100,180,0.2)"; ctx.lineWidth = 1; ctx.setLineDash([4,8]);
    ctx.beginPath();
    for (var th = 0; th <= Math.PI*2; th += 0.03) {
      var pos = kepToCart(p.a, p.e, p.w, 0, th / Math.sqrt(MU/(p.a*p.a*p.a)));
      if (th === 0) ctx.moveTo(pos.rx, pos.ry); else ctx.lineTo(pos.rx, pos.ry);
    }
    ctx.stroke(); ctx.setLineDash([]);
  }
}

function drawPlanet(p, t) {
  var pos = pPos(p, t);
  if (!isFinite(pos.rx) || !isFinite(pos.ry) || !isFinite(p.r)) return;
  var cs = 1 / camScale;
  var rv = p.r * cs;

  // Atmosphere glow
  ctx.fillStyle = p.col + "25";
  ctx.beginPath(); ctx.arc(pos.rx, pos.ry, rv * 2.5, 0, Math.PI * 2); ctx.fill();

  // Planet disk — shaded sphere
  var grd = ctx.createRadialGradient(pos.rx - rv * 0.15, pos.ry - rv * 0.15, rv * 0.1, pos.rx, pos.ry, rv);
  grd.addColorStop(0, p.col);
  grd.addColorStop(0.7, p.col);
  grd.addColorStop(1, "#000");
  ctx.fillStyle = grd;
  ctx.beginPath(); ctx.arc(pos.rx, pos.ry, rv, 0, Math.PI * 2); ctx.fill();

  // Terminator shadow — darken the hemisphere facing away from the sun
  var sunAng = Math.atan2(-pos.ry, -pos.rx);
  ctx.save();
  ctx.beginPath();
  ctx.arc(pos.rx, pos.ry, rv, sunAng + Math.PI / 2, sunAng - Math.PI / 2);
  ctx.lineTo(pos.rx, pos.ry);
  ctx.closePath();
  ctx.fillStyle = "rgba(0,0,0,0.35)";
  ctx.fill();
  ctx.restore();

  // Label
  ctx.font = (11 * cs) + "px sans-serif";
  ctx.textAlign = "center";
  ctx.fillStyle = "rgba(255,255,255,0.3)";
  ctx.fillText(p.n, pos.rx, pos.ry + rv + 14 * cs);
}

function drawSOI() {
  if (mission.inSOI < 0) return;
  var p = planets[mission.inSOI];
  var pos = pPos(p, time);
  ctx.strokeStyle = "rgba(100,255,200,0.12)"; ctx.lineWidth = 1; ctx.setLineDash([2,6]);
  ctx.beginPath(); ctx.arc(pos.rx, pos.ry, p.so, 0, Math.PI*2); ctx.stroke(); ctx.setLineDash([]);
}

function drawTrail() {
  for (var i = 1; i < trail.length; i++) {
    var a = (i/trail.length)*0.35;
    ctx.strokeStyle = "rgba(255,200,120,"+a+")";
    ctx.lineWidth = (i/trail.length)*1.5;
    ctx.beginPath(); ctx.moveTo(trail[i-1].x,trail[i-1].y); ctx.lineTo(trail[i].x,trail[i].y); ctx.stroke();
  }
}

function drawFutureArc(t) {
  if (mission.target < 0 || mission.target >= planets.length) return;
  if (mission.legDur < 100) return;
  ctx.strokeStyle = "rgba(255,200,100,0.08)"; ctx.lineWidth = 0.5; ctx.setLineDash([3,8]);
  ctx.beginPath();
  var first = true;
  for (var s = 0.1; s <= 1; s += 0.05) {
    var tp = pPos(planets[mission.target], t + s*mission.legDur);
    var lam = lambert(sc.rx, sc.ry, tp.rx, tp.ry, s*mission.legDur);
    if (!lam) continue;
    var tx = sc.rx, ty = sc.ry, vx = lam.vx, vy = lam.vy;
    for (var ins = 0; ins < 10; ins++) {
      var r2 = tx*tx+ty*ty, r3 = Math.max(1,r2*Math.sqrt(r2));
      var ax = -MU*tx/r3, ay = -MU*ty/r3;
      tx += vx*(s*mission.legDur/10); ty += vy*(s*mission.legDur/10);
      vx += ax*(s*mission.legDur/10); vy += ay*(s*mission.legDur/10);
    }
    if (first) { ctx.moveTo(tx, ty); first = false; }
    else ctx.lineTo(tx, ty);
  }
  ctx.stroke(); ctx.setLineDash([]);
}

function drawSC() {
  if (!isFinite(sc.rx) || !isFinite(sc.ry)) return;
  var cx = sc.rx, cy = sc.ry;
  var cs = 1 / camScale;
  var sr = 12 * cs;
  ctx.fillStyle = "rgba(100,200,255,0.15)";
  ctx.beginPath(); ctx.arc(cx,cy,sr,0,Math.PI*2); ctx.fill();
  ctx.save(); ctx.translate(cx,cy);
  var ang = Math.atan2(sc.vy, sc.vx);
  ctx.rotate(ang);
  var fl = (4+Math.random()*3) * cs;
  var fg = ctx.createLinearGradient(0,0,0,fl);
  fg.addColorStop(0,"rgba(255,255,200,0.9)"); fg.addColorStop(0.3,"rgba(255,180,50,0.7)");
  fg.addColorStop(0.6,"rgba(255,80,20,0.4)"); fg.addColorStop(1,"rgba(255,50,0,0)");
  ctx.fillStyle = fg;
  ctx.beginPath(); ctx.moveTo(-2*cs, 2*cs); ctx.quadraticCurveTo(-1*cs, fl*0.5, 0, fl);
  ctx.quadraticCurveTo(1*cs, fl*0.5, 2*cs, 2*cs); ctx.closePath(); ctx.fill();
  ctx.fillStyle = "#d0d8e0";
  ctx.beginPath(); ctx.moveTo(0, -6*cs); ctx.lineTo(-3*cs, 4*cs); ctx.lineTo(3*cs, 4*cs); ctx.closePath(); ctx.fill();
  ctx.fillStyle = "#6699cc";
  ctx.beginPath(); ctx.arc(0, 0, 2*cs, 0, Math.PI*2); ctx.fill();
  ctx.restore();
}

function drawTargetRing(t) {
  if (mission.target < 0 || mission.target >= planets.length) return;
  var tp = pPos(planets[mission.target], t);
  var cs = 1 / camScale;
  ctx.strokeStyle = "rgba(255,200,100,0.2)"; ctx.lineWidth = 0.5; ctx.setLineDash([3,5]);
  ctx.beginPath(); ctx.arc(tp.rx, tp.ry, planets[mission.target].r * cs * 3, 0, Math.PI*2); ctx.stroke();
  ctx.setLineDash([]);
  var dx = sc.rx - tp.rx, dy = sc.ry - tp.ry;
  var dist = Math.sqrt(dx*dx+dy*dy);
  if (dist > 30 * orScale / camScale) {
    ctx.font = (9 / camScale) + "px sans-serif"; ctx.fillStyle = "rgba(255,200,100,0.25)";
    ctx.textAlign = "center";
    ctx.fillText("→ " + planets[mission.target].n, tp.rx, tp.ry - planets[mission.target].r / camScale * 1.5);
  }
}

// --- HUD: Mission Control Panel ---
function fmtTime(tt) {
  var s = Math.floor(tt/60);
  var m = Math.floor(s/60);
  s = s % 60;
  var f = Math.floor(tt % 60);
  return ("0"+m).slice(-2)+":"+("0"+s).slice(-2)+"."+("0"+f).slice(-2);
}

function drawHUD(t) {
  var pw = 520, px = W - pw;
  ctx.fillStyle = "rgba(0,6,18,0.82)";
  ctx.fillRect(px, 0, pw, H);
  ctx.strokeStyle = "rgba(0,80,180,0.25)";
  ctx.lineWidth = 1;
  ctx.strokeRect(px, 0, pw, H);

  var col = px + 20;
  var row = 22;

  // Header
  ctx.font = "bold 16px 'Courier New',monospace";
  ctx.textAlign = "left";
  ctx.fillStyle = "rgba(80,180,255,0.7)";
  ctx.fillText("MISSION CONTROL", col, row); row += 22;
  ctx.font = "14px 'Courier New',monospace";
  ctx.textAlign = "left";
  ctx.fillStyle = "rgba(120,200,255,0.5)";
  ctx.fillText("T+" + fmtTime(t), col, row); row += 4;

  ctx.strokeStyle = "rgba(0,80,180,0.2)";
  ctx.beginPath(); ctx.moveTo(px + 10, row); ctx.lineTo(px + pw - 10, row); ctx.stroke(); row += 10;

  var oe = orbitalElements(sc.rx, sc.ry, sc.vx, sc.vy, mission.inSOI >= 0 ? planets[mission.inSOI].mu : MU);
  var inSOI = mission.inSOI >= 0;

  ctx.font = "15px 'Courier New',monospace";

  // Navigation
  ctx.fillStyle = "rgba(120,200,255,0.5)"; ctx.fillText("NAVIGATION", col, row); row += 20;
  ctx.fillStyle = "rgba(180,255,180,0.8)";
  ctx.fillText("VEL " + oe.v.toFixed(3) + " px/f", col, row); row += 20;
  ctx.fillText("Vx  " + sc.vx.toFixed(3), col, row); row += 20;
  ctx.fillText("Vy  " + sc.vy.toFixed(3), col, row); row += 20;
  ctx.fillText("RNG " + oe.r.toFixed(1) + " px", col, row); row += 20;
  if (inSOI) {
    var pp = pPos(planets[mission.inSOI], t);
    var dx = sc.rx - pp.rx, dy = sc.ry - pp.ry;
    var sd = Math.sqrt(dx*dx + dy*dy);
    ctx.fillText("SOI " + sd.toFixed(1) + "/" + planets[mission.inSOI].so, col, row); row += 20;
}

// --- Patched-conic prediction engine ---
var prediction = { encounters: [], trajectory: [], valid: false };
var predTimer = 0;

function predictEncounters() {
  var rx = sc.rx, ry = sc.ry, vx = sc.vx, vy = sc.vy;
  var soi = mission.inSOI;
  var t = time;
  var dt = 20;
  var maxSteps = 12000;
  var encounters = [];
  var trajectory = [];
  var maxEnc = 5;

  for (var step = 0; step < maxSteps; step++) {
    t += dt;

    // Find current SOI
    var newSOI = -1;
    for (var i = 0; i < planets.length; i++) {
      var pp = pPos(planets[i], t);
      var dx = rx - pp.rx, dy = ry - pp.ry;
      if (Math.sqrt(dx*dx + dy*dy) < planets[i].so) { newSOI = i; break; }
    }

    // SOI change detection
    if (newSOI !== soi) {
      if (newSOI >= 0) {
        var pp = pPos(planets[newSOI], t);
        var dx = rx - pp.rx, dy = ry - pp.ry;
        var dist = Math.sqrt(dx*dx + dy*dy);
        encounters.push({ type: "enter", planet: newSOI, time: t, dist: dist });
      } else {
        encounters.push({ type: "exit", planet: soi, time: t });
      }
      soi = newSOI;
      if (encounters.length >= maxEnc) break;
    }

    // Predict close approach within SOI
    if (soi >= 0) {
      var pp = pPos(planets[soi], t);
      var dx = rx - pp.rx, dy = ry - pp.ry;
      var dist = Math.sqrt(dx*dx + dy*dy);
      if (dist < planets[soi].r * 3 && encounters.length > 0 &&
          encounters[encounters.length-1].type !== "flyby") {
        encounters.push({ type: "flyby", planet: soi, time: t, dist: dist });
        if (encounters.length >= maxEnc) break;
      }
    }

    // Integration step
    var mu = soi >= 0 ? planets[soi].mu : MU;
    if (soi >= 0) {
      var pp = pPos(planets[soi], t);
      var prx = rx - pp.rx, pry = ry - pp.ry;
      var pr2 = prx*prx + pry*pry;
      var pr3 = Math.max(1, pr2 * Math.sqrt(pr2));
      var ax = -mu * prx / pr3, ay = -mu * pry / pr3;
      vx += ax * dt / 2; vy += ay * dt / 2;
      rx += vx * dt; ry += vy * dt;
      pp = pPos(planets[soi], t);
      prx = rx - pp.rx; pry = ry - pp.ry;
      pr2 = prx*prx + pry*pry; pr3 = Math.max(1, pr2 * Math.sqrt(pr2));
      ax = -mu * prx / pr3; ay = -mu * pry / pr3;
      vx += ax * dt / 2; vy += ay * dt / 2;
    } else {
      var r2 = rx*rx + ry*ry;
      var r3 = Math.max(1, r2 * Math.sqrt(r2));
      var ax = -MU * rx / r3, ay = -MU * ry / r3;
      vx += ax * dt / 2; vy += ay * dt / 2;
      rx += vx * dt; ry += vy * dt;
      r2 = rx*rx + ry*ry; r3 = Math.max(1, r2 * Math.sqrt(r2));
      ax = -MU * rx / r3; ay = -MU * ry / r3;
      vx += ax * dt / 2; vy += ay * dt / 2;
    }

    if (step % 40 === 0) {
      trajectory.push({ x: sx + rx * camScale, y: sy + ry * camScale });
    }

    if (Math.sqrt(rx*rx + ry*ry) > 5000) break;
  }

  return { encounters: encounters, trajectory: trajectory };
}

function drawPrediction() {
  if (!prediction.valid || prediction.trajectory.length < 2) return;
  ctx.save();
  ctx.setLineDash([3, 6]);
  ctx.strokeStyle = "rgba(255, 200, 100, 0.12)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(prediction.trajectory[0].x, prediction.trajectory[0].y);
  for (var i = 1; i < prediction.trajectory.length; i++) {
    ctx.lineTo(prediction.trajectory[i].x, prediction.trajectory[i].y);
  }
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();

  // Mark encounter waypoints
  for (var e of prediction.encounters) {
    var idx = Math.min(Math.floor((e.time - time) / 80 / 10), prediction.trajectory.length - 1);
    if (idx >= 0 && idx < prediction.trajectory.length) {
      var pt = prediction.trajectory[idx];
      ctx.fillStyle = e.type === "enter" ? "rgba(100,255,200,0.3)" :
                      e.type === "flyby" ? "rgba(255,200,100,0.4)" :
                      "rgba(255,100,100,0.2)";
      ctx.beginPath(); ctx.arc(pt.x, pt.y, 5, 0, Math.PI * 2); ctx.fill();
    }
  }
}

function drawOffscreenIndicator(t) {
  var scx = sx + sc.rx * camScale;
  var scy = sy + sc.ry * camScale;
  var hudLeft = W - 460;
  var margin = 30;
  var left = margin, right = hudLeft - margin, top = margin, bottom = H - margin;

  var onScreen = scx >= left && scx <= right && scy >= top && scy <= bottom;
  if (onScreen) return;

  // Clamp to edge
  var ex = Math.max(left, Math.min(right, scx));
  var ey = Math.max(top, Math.min(bottom, scy));
  var pulse = Math.sin(t * 0.05) * 0.3 + 0.7;

  // Arrow toward SC
  var dx = scx - ex, dy = scy - ey;
  var ang = Math.atan2(dy, dx);

  ctx.save();
  ctx.translate(ex, ey);
  ctx.rotate(ang);

  // Glow ring
  var gr = 26 + 6 * pulse;
  var glow = ctx.createRadialGradient(0, 0, 0, 0, 0, gr);
  glow.addColorStop(0, "rgba(100,200,255,0.15)");
  glow.addColorStop(1, "rgba(100,200,255,0)");
  ctx.fillStyle = glow;
  ctx.beginPath(); ctx.arc(0, 0, gr, 0, Math.PI * 2); ctx.fill();

  // Outer ring
  ctx.strokeStyle = "rgba(100,200,255," + (0.3 + 0.3 * pulse) + ")";
  ctx.lineWidth = 2;
  ctx.beginPath(); ctx.arc(0, 0, 22, 0, Math.PI * 2); ctx.stroke();

  // Arrow head pointing toward SC
  ctx.fillStyle = "rgba(100,200,255,0.7)";
  ctx.beginPath();
  ctx.moveTo(28, 0);
  ctx.lineTo(18, -7);
  ctx.lineTo(18, 7);
  ctx.closePath();
  ctx.fill();

  // Tiny spacecraft preview inside the ring
  ctx.rotate(-ang); // cancel rotation for SC preview so it shows correct orientation
  var scAng = Math.atan2(sc.vy, sc.vx);
  ctx.rotate(scAng);
  ctx.fillStyle = "rgba(180,220,255,0.6)";
  ctx.beginPath();
  ctx.moveTo(8, 0);
  ctx.lineTo(-5, -5);
  ctx.lineTo(-5, 5);
  ctx.closePath();
  ctx.fill();

  ctx.restore();
}

// --- Animation ---
var time = 0;
var launched = false;
var lastFrameTime = 0;

var orb = {};
orb.animate = function(timestamp) {
  if (lastFrameTime === 0) lastFrameTime = timestamp;
  var deltaMs = timestamp - lastFrameTime;
  if (lastFrameTime === 0) lastFrameTime = timestamp;
  var deltaMs = timestamp - lastFrameTime;
  lastFrameTime = timestamp;
  time += Math.min(deltaMs / 16.667, 3);

  ctx.fillStyle = "#03040c";
  ctx.fillRect(0,0,W,H);

  // Parallax stars (fixed-position canvas formula: ty = y - scrollY * depth)
  for (var si = 0; si < stars.length; si++) {
    var s = stars[si];
    if (s.depth === undefined) { s.depth = 0.3 + Math.random() * 0.4; }
    var paraY = s.y - scrollY * s.depth;
    if (paraY < -10 || paraY > H + 10) continue;
    var twinkle = 0.5 + 0.5 * Math.sin(time * s.speed + s.phase);
    var a = 0.3 + 0.7 * twinkle;
    ctx.fillStyle = hexToRgba(s.colour, a);
    ctx.beginPath();
    ctx.arc(s.x, paraY, s.size * (0.5 + 0.5 * twinkle), 0, Math.PI * 2);
    ctx.fill();
  }

  // Launch
  if (!launched) { launch(time); launched = true; }

  // Physics
  if (mission.phase !== "idle") {
    // Adjust dt for SOI accuracy
    var dt = 1;
    if (mission.inSOI >= 0) dt = 0.3;
    else if (mission.target >= 0) {
      var tp = pPos(planets[mission.target], time);
      var dx = tp.rx - sc.rx, dy = tp.ry - sc.ry;
      if (Math.sqrt(dx*dx+dy*dy) < 80 / camScale) dt = 0.5;
    }
    integrate(time, dt);

    // Finite burn application
    if (burn.active) {
      var applyDV = Math.min(burn.rate, burn.remaining);
      sc.vx += burn.dvx / burn.remaining * applyDV;
      sc.vy += burn.dvy / burn.remaining * applyDV;
      totalDV += applyDV;
      burn.remaining -= applyDV;
      emit(sx + sc.rx * camScale + (Math.random()-0.5)*4, sy + sc.ry * camScale + (Math.random()-0.5)*4, 1, 30, 0.5);
      if (burn.remaining <= 0.001) {
        burn.active = false;
        mission.phase = "coast";
        logEvent('burn', "Burn complete (Δv=" + totalDV.toFixed(3) + ")");
      }
    }

    // Course corrections — tiny nudges based on predicted encounters
    if (mission.inSOI < 0 && time > mission.lastCCtime + 500) {
      if (prediction.valid && prediction.encounters.length > 0) {
        var enc = prediction.encounters[0];
        if (enc.type === "enter" || enc.type === "flyby") {
          mission.lastCCtime = time;
          var spd = Math.sqrt(sc.vx*sc.vx + sc.vy*sc.vy);
          if (spd > 0.01) {
            var nudge = 0.015;
            sc.vx += sc.vx / spd * nudge;
            sc.vy += sc.vy / spd * nudge;
            totalDV += nudge;
            logEvent('correction', "Nudge +" + nudge.toFixed(3) + " → " + planets[enc.planet].n);
          }
        }
      } else {
        // No encounters predicted — ultra-low-energy Lambert from current position
        var bestDV = 0.03, bestTarget = -1, bestLam = null;
        for (var i = 0; i < planets.length; i++) {
          if (i === mission.prevPlanet) continue;
          var tp = pPos(planets[i], time + 5000);
          var lam = lambert(sc.rx, sc.ry, tp.rx, tp.ry, 5000);
          if (!lam) {
            tp = pPos(planets[i], time + 15000);
            lam = lambert(sc.rx, sc.ry, tp.rx, tp.ry, 15000);
          }
          if (!lam) continue;
          var dvx = lam.vx - sc.vx, dvy = lam.vy - sc.vy;
          var dv = Math.sqrt(dvx*dvx + dvy*dvy);
          if (dv < bestDV) { bestDV = dv; bestTarget = i; bestLam = lam; }
        }
        if (bestLam) {
          mission.lastCCtime = time;
          var dvx = bestLam.vx - sc.vx, dvy = bestLam.vy - sc.vy;
          var dvm = Math.sqrt(dvx*dvx + dvy*dvy);
          if (dvm > 0.03) { dvx = dvx/dvm*0.03; dvy = dvy/dvm*0.03; dvm = 0.03; }
          sc.vx += dvx; sc.vy += dvy;
          totalDV += dvm;
          mission.target = bestTarget;
          logEvent('correction', "Weak capture → " + planets[bestTarget].n + " (Δv=" + dvm.toFixed(3) + ")");
        }
      }
    }
    }

    // Flyby detection (inside SOI, close approach)
    if (mission.inSOI >= 0 && time > mission.flybyCooldown + 300) {
      var pp = pPos(planets[mission.inSOI], time);
      var dx = sc.rx - pp.rx, dy = sc.ry - pp.ry;
      var pd = Math.sqrt(dx*dx + dy*dy);
      var pv = pVel(planets[mission.inSOI], time);
      var rvx = sc.vx - pv.vx, rvy = sc.vy - pv.vy;
      var vInf = Math.sqrt(rvx*rvx + rvy*rvy);

      if (pd < planets[mission.inSOI].r * 4) {
        logEvent('flyby', "✦ " + planets[mission.inSOI].n + " flyby (v∞=" + vInf.toFixed(2) + ")");
        emit(sx + sc.rx * camScale, sy + sc.ry * camScale, 25, 40, 4);
        emit(sx + sc.rx * camScale, sy + sc.ry * camScale, 15, 200, 3);
        mission.visited.push(mission.inSOI);
        mission.prevPlanet = mission.inSOI;
        mission.target = pickTarget(mission.inSOI, mission.visited, time);
        mission.flybyCooldown = time;
        if (mission.visited.length >= planets.length) {
          mission.visited = [mission.prevPlanet];
        }
      }
    }
  }

  // --- Drawing ---
  if (isFinite(sx) && isFinite(sy) && isFinite(camScale)) {
    ctx.save();
    ctx.setTransform(camScale, 0, 0, camScale, sx, sy);
    drawOrbits(); drawSOI(); drawSun();
    for (var p of planets) drawPlanet(p, time);
    if (mission.phase !== "idle") {
      drawFutureArc(time);
      drawTargetRing(time);
      drawSC();
    }
    ctx.restore();
  }

  // Screen-space elements
  drawOffscreenIndicator(time);
  drawTrail();
  drawPrediction();

  // Particles
  particles = particles.filter(function(p){ return p.life > 0; });
  for (var p of particles) {
    p.x += p.vx; p.y += p.vy; p.vx *= 0.96; p.vy *= 0.96; p.life--;
    var a = Math.max(0, p.life/p.ml);
    ctx.fillStyle = "hsla("+p.hue+",100%,60%,"+a+")";
    ctx.beginPath(); ctx.arc(p.x, p.y, Math.max(0.5, p.sz*a), 0, Math.PI*2); ctx.fill();
  }

  drawHUD(time);

  // Periodic prediction update (every 30 frames)
  predTimer++;
  if (predTimer % 30 === 0 && mission.phase !== "idle") {
    prediction = predictEncounters();
    prediction.valid = true;
  }

  // Special date overlay
  var todayStr = getDateKey();
  var isSpecial = false;
  for (var i = 0; i < consData.length; i++) {
    if (consData[i].date === todayStr) { isSpecial = true; break; }
  }
  if (isSpecial) {
    var pu = Math.sin(time*0.02)*0.5+0.5;
    var g = ctx.createRadialGradient(sx,sy,0,sx,sy,500);
    g.addColorStop(0,"rgba(192,192,224,0)");
    g.addColorStop(0.7,"rgba(192,192,224,"+pu*0.04+")");
    g.addColorStop(1,"rgba(192,192,224,0)");
    ctx.fillStyle = g; ctx.fillRect(0,0,W,H);
  }

  requestAnimFrame(orb.animate);
}

try { requestAnimFrame(orb.animate); }
catch(e) { console.error("orbital startup:", e.message); }
