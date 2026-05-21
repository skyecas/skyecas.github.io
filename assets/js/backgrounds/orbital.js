var requestAnimFrame = (function(){
  return window.requestAnimationFrame       ||
         window.webkitRequestAnimationFrame ||
         window.mozRequestAnimationFrame    ||
         window.oRequestAnimationFrame      ||
         window.msRequestAnimationFrame     ||
         function(cb){ window.setTimeout(cb, 1000 / 60); };
})();

var c = document.getElementById("bgCanvas"),
    ctx = c.getContext("2d"),
    W = window.innerWidth, H = window.innerHeight;
c.width = W; c.height = H;

// --- Scene center ---
var sx = W / 2, sy = H / 2;
var baseW = 1920, baseH = 1080;
var orScale = Math.min(W / baseW, H / baseH);

// --- Constants ---
var MU = 120;

// --- Stars ---
var starCols = ["white","aliceBlue","powderBlue","azure","moccasin","sandyBrown","coral"];
function Star(){
  this.x = Math.random()*W; this.y = Math.random()*H;
  this.s = Math.random()*1.5+0.1;
  this.col = starCols[Math.floor(Math.random()*starCols.length)];
  this.ph = Math.random()*Math.PI*2; this.sp = 0.01+Math.random()*0.02;
}
Star.prototype.draw = function(t){
  var tw = Math.sin(t*this.sp+this.ph)*0.3+0.7;
  ctx.globalAlpha = 0.4+tw*0.6; ctx.fillStyle = this.col;
  ctx.fillRect(this.x,this.y,this.s,this.s); ctx.globalAlpha = 1;
};
var stars = [];
for(var i=600;i>0;i--) stars.push(new Star());

// --- Kepler utilities ---
function solveKepler(M, e) {
  M = M % (2*Math.PI); if (M < 0) M += 2*Math.PI;
  var E = M + e * Math.sin(M);
  for (var i = 0; i < 30; i++) {
    var f = E - e * Math.sin(E) - M;
    if (Math.abs(f) < 1e-10) break;
    E = E - f / (1 - e * Math.cos(E));
  }
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

// --- Planets (sun-relative coords) ---
var planets = [
  { n:"Mercury", a:100, e:0.2056, w:1.35, M0:4.0, r:5*orScale,  col:"#b0a894", so:15*orScale, mu:0.2 },
  { n:"Venus",   a:170, e:0.0068, w:2.30, M0:1.2, r:9*orScale,  col:"#e8c880", so:25*orScale, mu:0.8 },
  { n:"Earth",   a:240, e:0.0167, w:3.12, M0:0.5, r:11*orScale, col:"#4a9bd7", so:30*orScale, mu:1.0 },
  { n:"Mars",    a:330, e:0.0934, w:0.87, M0:3.8, r:8*orScale,  col:"#c05030", so:20*orScale, mu:0.5 },
  { n:"Jupiter", a:520, e:0.0484, w:4.52, M0:2.1, r:21*orScale, col:"#d4a06a", so:60*orScale, mu:5.0 },
];

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

function launch(t) {
  var ep = pPos(planets[2], t);
  var ev = pVel(planets[2], t);
  sc.rx = ep.rx; sc.ry = ep.ry;
  sc.vx = ev.vx + 0.3; sc.vy = ev.vy - 0.2;
  totalDV = 0.36;
  mission.phase = "coast"; mission.legStart = t; mission.prevPlanet = 2;
  mission.visited = [2]; mission.correctionsLeft = 2; mission.inSOI = -1;
  mission.flybyCooldown = 0;
  mission.target = pickTarget(2, mission.visited, t);
  if (mission.target >= 0) {
    var tp = pPos(planets[mission.target], t);
    var dx = tp.rx - sc.rx, dy = tp.ry - sc.ry;
    mission.legDur = Math.max(1000, Math.min(15000, Math.sqrt(dx*dx+dy*dy) * 5));
    logEvent('launch', "Launch from Earth → " + planets[mission.target].n);
  } else logEvent('launch', "Launch from Earth");
}

function doCorrection(t) {
  if (mission.target < 0 || mission.target >= planets.length) return false;
  var tp = pPos(planets[mission.target], t + mission.legDur * 0.3);
  var dt = mission.legDur * 0.5;
  var lam = lambert(sc.rx, sc.ry, tp.rx, tp.ry, dt);
  if (lam) {
    var dvx = lam.vx - sc.vx, dvy = lam.vy - sc.vy;
    var dvm = Math.sqrt(dvx*dvx + dvy*dvy);
    if (dvm > 2) { dvx = dvx/dvm*2; dvy = dvy/dvm*2; dvm = 2; }
    sc.vx += dvx; sc.vy += dvy;
    totalDV += dvm;
    mission.correctionsLeft--;
    mission.lastCCtime = t;
    logEvent('correction', "Maneuvre (Δv=" + dvm.toFixed(3) + ") → " + planets[mission.target].n);
    emit(sc.rx + sx, sc.ry + sy, 8, 200, 1.5);
    return true;
  }
  return false;
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
    logEvent('soi', "≈≈ " + planets[soiIdx].n + " SOI entry ≈≈");
  } else if (soiIdx < 0 && mission.inSOI >= 0) {
    logEvent('soi', "≈≈ " + planets[mission.inSOI].n + " SOI exit ≈≈");
    mission.inSOI = -1;
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
    if (t % 2 < 1) pushTrail(sc.rx + sx, sc.ry + sy);
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
    if (t % 2 < 1) pushTrail(sc.rx + sx, sc.ry + sy);
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
  var r1 = 100 * orScale, r2 = 30 * orScale;
  var g = ctx.createRadialGradient(sx,sy,0,sx,sy,r1);
  g.addColorStop(0,"rgba(255,240,200,0.6)"); g.addColorStop(0.15,"rgba(255,220,150,0.3)");
  g.addColorStop(0.4,"rgba(255,180,80,0.08)"); g.addColorStop(1,"rgba(255,150,50,0)");
  ctx.fillStyle = g; ctx.beginPath(); ctx.arc(sx,sy,r1,0,Math.PI*2); ctx.fill();
  var g2 = ctx.createRadialGradient(sx-8*orScale,sy-8*orScale,0,sx,sy,r2);
  g2.addColorStop(0,"#fff8e0"); g2.addColorStop(0.5,"#ffdd66"); g2.addColorStop(1,"#ff8800");
  ctx.fillStyle = g2; ctx.beginPath(); ctx.arc(sx,sy,r2,0,Math.PI*2); ctx.fill();
}

function drawOrbits() {
  for (var p of planets) {
    ctx.strokeStyle = "rgba(60,100,180,0.2)"; ctx.lineWidth = 1; ctx.setLineDash([4,8]);
    ctx.beginPath();
    for (var th = 0; th <= Math.PI*2; th += 0.03) {
      var pos = kepToCart(p.a, p.e, p.w, 0, th / Math.sqrt(MU/(p.a*p.a*p.a)));
      var x = sx+pos.rx, y = sy+pos.ry;
      if (th === 0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
    }
    ctx.stroke(); ctx.setLineDash([]);
  }
}

function drawPlanet(p, t) {
  var pos = pPos(p, t);
  var cx = sx+pos.rx, cy = sy+pos.ry;
  ctx.fillStyle = p.col + "40";
  ctx.beginPath(); ctx.arc(cx,cy,p.r*2.5,0,Math.PI*2); ctx.fill();
  var g2 = ctx.createRadialGradient(cx-p.r*0.3,cy-p.r*0.3,0,cx,cy,p.r);
  g2.addColorStop(0,"#fff"); g2.addColorStop(0.2,p.col); g2.addColorStop(1,"#222");
  ctx.fillStyle = g2; ctx.beginPath(); ctx.arc(cx,cy,p.r,0,Math.PI*2); ctx.fill();
  ctx.font = "9px sans-serif"; ctx.textAlign = "center"; ctx.fillStyle = "rgba(255,255,255,0.3)";
  ctx.fillText(p.n, cx, cy+p.r+14);
}

function drawSOI() {
  if (mission.inSOI < 0) return;
  var p = planets[mission.inSOI];
  var pos = pPos(p, time);
  var cx = sx+pos.rx, cy = sy+pos.ry;
  ctx.strokeStyle = "rgba(100,255,200,0.12)"; ctx.lineWidth = 1; ctx.setLineDash([2,6]);
  ctx.beginPath(); ctx.arc(cx,cy,p.so,0,Math.PI*2); ctx.stroke(); ctx.setLineDash([]);
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
    if (first) { ctx.moveTo(sx+tx,sy+ty); first = false; }
    else ctx.lineTo(sx+tx,sy+ty);
  }
  ctx.stroke(); ctx.setLineDash([]);
}

function drawSC() {
  var cx = sx+sc.rx, cy = sy+sc.ry;
  var sr = 18 * orScale;
  ctx.fillStyle = "rgba(100,200,255,0.15)";
  ctx.beginPath(); ctx.arc(cx,cy,sr,0,Math.PI*2); ctx.fill();
  ctx.save(); ctx.translate(cx,cy);
  var ang = Math.atan2(sc.vy, sc.vx);
  ctx.rotate(ang);
  var fl = 12+Math.random()*8;
  var fg = ctx.createLinearGradient(0,0,0,fl);
  fg.addColorStop(0,"rgba(255,255,200,0.9)"); fg.addColorStop(0.3,"rgba(255,180,50,0.7)");
  fg.addColorStop(0.6,"rgba(255,80,20,0.4)"); fg.addColorStop(1,"rgba(255,50,0,0)");
  ctx.fillStyle = fg;
  ctx.beginPath(); ctx.moveTo(-4,3); ctx.quadraticCurveTo(-1.5,fl*0.5,0,fl);
  ctx.quadraticCurveTo(1.5,fl*0.5,4,3); ctx.closePath(); ctx.fill();
  ctx.fillStyle = "#d0d8e0";
  ctx.beginPath(); ctx.moveTo(0,-12); ctx.lineTo(-5,8); ctx.lineTo(5,8); ctx.closePath(); ctx.fill();
  ctx.fillStyle = "#6699cc";
  ctx.beginPath(); ctx.arc(0,0,3,0,Math.PI*2); ctx.fill();
  ctx.restore();
}

function drawTargetRing(t) {
  if (mission.target < 0 || mission.target >= planets.length) return;
  var tp = pPos(planets[mission.target], t);
  var tcx = sx+tp.rx, tcy = sy+tp.ry;
  ctx.strokeStyle = "rgba(255,200,100,0.2)"; ctx.lineWidth = 0.5; ctx.setLineDash([3,5]);
  ctx.beginPath(); ctx.arc(tcx,tcy,planets[mission.target].r*3,0,Math.PI*2); ctx.stroke();
  ctx.setLineDash([]);
  var dx = sc.rx - tp.rx, dy = sc.ry - tp.ry;
  var dist = Math.sqrt(dx*dx+dy*dy);
  if (dist > 30) {
    ctx.font = "9px sans-serif"; ctx.fillStyle = "rgba(255,200,100,0.25)";
    ctx.textAlign = "center";
    ctx.fillText("→ " + planets[mission.target].n, tcx, tcy-planets[mission.target].r-15);
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
  var ph = H - 130, pw = W, phh = 130;
  // Panel background
  ctx.fillStyle = "rgba(0,6,18,0.75)";
  ctx.fillRect(0, ph, pw, phh);
  ctx.strokeStyle = "rgba(0,80,180,0.3)";
  ctx.lineWidth = 1;
  ctx.strokeRect(0, ph, pw, phh);

  // Header line
  ctx.font = "bold 11px 'Courier New',monospace";
  ctx.fillStyle = "rgba(80,180,255,0.7)";
  ctx.textAlign = "left";
  ctx.fillText("MISSION CONTROL  •  KSP-1", 15, ph+16);
  ctx.textAlign = "right";
  ctx.fillText("T+" + fmtTime(t), pw-15, ph+16);

  // Divider
  ctx.strokeStyle = "rgba(0,80,180,0.2)";
  ctx.beginPath(); ctx.moveTo(0,ph+22); ctx.lineTo(pw,ph+22); ctx.stroke();

  var oe = orbitalElements(sc.rx, sc.ry, sc.vx, sc.vy, mission.inSOI >= 0 ? planets[mission.inSOI].mu : MU);
  var inSOI = mission.inSOI >= 0;

  // --- Telemetry columns ---
  ctx.font = "9px 'Courier New',monospace";
  var colX = [15, 210, 400, 590, 780];
  var rowY = [ph+30, ph+44, ph+58, ph+72, ph+86, ph+100, ph+114];

  // Col 0: Velocity & Navigation
  ctx.fillStyle = "rgba(120,200,255,0.5)";
  ctx.fillText("NAVIGATION", colX[0], rowY[0]);
  ctx.fillStyle = "rgba(180,255,180,0.8)";
  ctx.fillText("VEL  " + oe.v.toFixed(3) + " px/f", colX[0], rowY[1]);
  ctx.fillText("Vx   " + sc.vx.toFixed(3), colX[0], rowY[2]);
  ctx.fillText("Vy   " + sc.vy.toFixed(3), colX[0], rowY[3]);
  ctx.fillText("RNG  " + oe.r.toFixed(1) + " px", colX[0], rowY[4]);

  // Col 1: Orbital Elements
  ctx.fillStyle = "rgba(120,200,255,0.5)";
  ctx.fillText("ORBIT" + (inSOI ? " (SOI)" : ""), colX[1], rowY[0]);
  ctx.fillStyle = "rgba(180,255,180,0.8)";
  ctx.fillText("a    " + oe.a, colX[1], rowY[1]);
  ctx.fillText("e    " + oe.e, colX[1], rowY[2]);
  if (oe.T < Infinity) {
    ctx.fillText("T    " + fmtTime(oe.T), colX[1], rowY[3]);
  } else {
    ctx.fillText("T    ∞", colX[1], rowY[3]);
  }
  if (oe.eps < 0) {
    ctx.fillText("rp   " + oe.rp.toFixed(1), colX[1], rowY[4]);
    ctx.fillText("ra   " + oe.ra.toFixed(1), colX[1], rowY[5]);
  }

  // Col 2: Mission Status
  ctx.fillStyle = "rgba(120,200,255,0.5)";
  ctx.fillText("MISSION", colX[2], rowY[0]);
  ctx.fillStyle = "rgba(180,255,180,0.8)";
  var phaseStr = mission.phase.toUpperCase();
  if (inSOI) phaseStr += " [SOI:" + planets[mission.inSOI].n + "]";
  ctx.fillText("PHASE " + phaseStr, colX[2], rowY[1]);
  ctx.fillText("ΔV   " + totalDV.toFixed(3) + " px/f", colX[2], rowY[2]);
  if (mission.target >= 0 && mission.target < planets.length) {
    ctx.fillText("TGT  " + planets[mission.target].n, colX[2], rowY[3]);
    var tp = pPos(planets[mission.target], t);
    var dx = tp.rx - sc.rx, dy = tp.ry - sc.ry;
    ctx.fillText("RNG  " + Math.round(Math.sqrt(dx*dx+dy*dy)) + " px", colX[2], rowY[4]);
  }
  ctx.fillText("CRR  " + mission.correctionsLeft + " left", colX[2], rowY[5]);
  ctx.fillText("FRP  " + mission.visited.length + "/" + planets.length, colX[2], rowY[6]);

  // Col 3: Energy / Angular momentum
  ctx.fillStyle = "rgba(120,200,255,0.5)";
  ctx.fillText("DYNAMICS", colX[3], rowY[0]);
  ctx.fillStyle = "rgba(180,255,180,0.8)";
  ctx.fillText("ε    " + oe.eps.toFixed(4), colX[3], rowY[1]);
  ctx.fillText("h    " + oe.h.toFixed(2), colX[3], rowY[2]);
  ctx.fillText("μ    " + (inSOI ? planets[mission.inSOI].mu.toFixed(2) : MU.toFixed(0)), colX[3], rowY[3]);

  // SOI info
  if (inSOI) {
    var pp = pPos(planets[mission.inSOI], t);
    var dx = sc.rx - pp.rx, dy = sc.ry - pp.ry;
    var sd = Math.sqrt(dx*dx + dy*dy);
    ctx.fillText("SOI  " + sd.toFixed(1) + "/" + planets[mission.inSOI].so, colX[3], rowY[4]);
  }

  // --- Event log (right side) ---
  var logX = 1000, logW = pw - logX - 15;
  ctx.fillStyle = "rgba(120,200,255,0.5)";
  ctx.textAlign = "left";
  ctx.font = "9px 'Courier New',monospace";
  ctx.fillText("EVENT LOG", logX, rowY[0]);

  ctx.save();
  ctx.beginPath();
  ctx.rect(logX, rowY[1] - 2, logW, phh - (rowY[1] - ph + 2) - 4);
  ctx.clip();

  var logStart = Math.max(0, eventLog.length - 8);
  for (var i = logStart; i < eventLog.length; i++) {
    var ev = eventLog[i];
    var yOff = rowY[1] + (i - logStart) * 13;
    var col;
    switch (ev.type) {
      case 'launch': col = "#80ff80"; break;
      case 'target': col = "#80d0ff"; break;
      case 'correction': col = "#ffc060"; break;
      case 'soi': col = "#60ffc0"; break;
      case 'flyby': col = "#ffd080"; break;
      default: col = "#c0c0d0";
    }
    ctx.fillStyle = col;
    ctx.fillText("T+" + fmtTime(ev.t), logX, yOff);
    ctx.fillText(ev.msg, logX + 60, yOff);
  }
  ctx.restore();

  // --- Quick status bar ---
  ctx.fillStyle = "rgba(0,80,180,0.2)";
  ctx.fillRect(0, ph-16, pw, 16);
  ctx.font = "8px 'Courier New',monospace";
  ctx.fillStyle = "rgba(120,200,255,0.4)";
  ctx.textAlign = "left";
  var status = inSOI ? ("≈ " + planets[mission.inSOI].n + " SOI ≈") : "● SOLAR COAST";
  ctx.fillText(status, 15, ph-4);
  ctx.textAlign = "center";
  ctx.fillText("FLYBY COUNT: " + mission.visited.length + "  |  ΔV: " + totalDV.toFixed(2) + "  |  TGT: " +
    (mission.target >= 0 ? planets[mission.target].n : "NONE"), pw/2, ph-4);
  ctx.textAlign = "right";
  var corrStatus = mission.correctionsLeft > 0 ? "CRR AVL" : "CRR DONE";
  ctx.fillText(corrStatus, pw-15, ph-4);
}

// --- Special dates ---
var specialDates = {
  "27/07":"#FFD700","12/08":"#C0C0E0","23/08":"#FF7F7F",
  "04/09":"#FF69B4","26/10":"#00E5FF","31/03":"#FF8FAB"
};
function getDateHex() {
  var d = new Date();
  var key = ("0"+d.getDate()).slice(-2)+"/"+("0"+(d.getMonth()+1)).slice(-2);
  return specialDates[key] || null;
}

// --- Animation ---
var time = 0;
var launched = false;

function animate() {
  time++;

  ctx.fillStyle = "#03040c";
  ctx.fillRect(0,0,W,H);
  for (var s of stars) s.draw(time);

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
      if (Math.sqrt(dx*dx+dy*dy) < 80) dt = 0.5;
    }
    integrate(time, dt);

    // Course corrections
    var elapsed = time - mission.legStart;
    if (mission.correctionsLeft > 0 && mission.inSOI < 0) {
      if ((mission.correctionsLeft > 1 && elapsed > mission.legDur*0.3 && time > mission.lastCCtime + 200) ||
          (mission.correctionsLeft > 0 && elapsed > mission.legDur*0.7 && time > mission.lastCCtime + 200)) {
        doCorrection(time);
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
        // Close approach - the hyperbolic flyby is done by the patched conic,
        // but we log it and update the target
        logEvent('flyby', "✦ " + planets[mission.inSOI].n + " flyby (v∞=" + vInf.toFixed(2) + ")");
        emit(sx+sc.rx, sy+sc.ry, 25, 40, 4);
        emit(sx+sc.rx, sy+sc.ry, 15, 200, 3);

        mission.visited.push(mission.inSOI);
        mission.prevPlanet = mission.inSOI;

        var newT = pickTarget(mission.inSOI, mission.visited, time);
        if (newT >= 0) {
          mission.target = newT;
          mission.legStart = time;
          mission.correctionsLeft = 2;
          var np = pPos(planets[newT], time);
          var ndx = np.rx - sc.rx, ndy = np.ry - sc.ry;
          mission.legDur = Math.max(1000, Math.min(15000, Math.sqrt(ndx*ndx+ndy*ndy) * 5));
          logEvent('target', "New target: " + planets[newT].n);
          if (mission.visited.length >= planets.length) {
            mission.visited = [mission.prevPlanet];
          }
        } else {
          // All visited, reset
          mission.visited = [mission.prevPlanet];
          var rt = pickTarget(mission.prevPlanet, visited, time);
          if (rt >= 0) {
            mission.target = rt;
            mission.legStart = time;
            mission.correctionsLeft = 2;
            var np = pPos(planets[rt], time);
            var ndx = np.rx - sc.rx, ndy = np.ry - sc.ry;
            mission.legDur = Math.max(1000, Math.min(15000, Math.sqrt(ndx*ndx+ndy*ndy) * 5));
            logEvent('target', "New target: " + planets[rt].n);
            if (visited) {} // suppress unused
          }
        }
        mission.flybyCooldown = time;
      }
    }
  }

  // --- Drawing ---
  drawOrbits(); drawSOI(); drawSun();
  for (var p of planets) drawPlanet(p, time);
  drawTrail();
  if (mission.phase !== "idle") {
    drawFutureArc(time);
    drawTargetRing(time);
    drawSC();
  }

  // Particles
  particles = particles.filter(function(p){ return p.life > 0; });
  for (var p of particles) {
    p.x += p.vx; p.y += p.vy; p.vx *= 0.96; p.vy *= 0.96; p.life--;
    var a = Math.max(0, p.life/p.ml);
    ctx.fillStyle = "hsla("+p.hue+",100%,60%,"+a+")";
    ctx.beginPath(); ctx.arc(p.x, p.y, Math.max(0.5, p.sz*a), 0, Math.PI*2); ctx.fill();
  }

  drawHUD(time);

  // Special date overlay
  var dc = getDateHex();
  if (dc) {
    var pu = Math.sin(time*0.02)*0.5+0.5;
    var g = ctx.createRadialGradient(sx,sy,0,sx,sy,500);
    var r = parseInt(dc.slice(1,3),16), gr = parseInt(dc.slice(3,5),16), b = parseInt(dc.slice(5,7),16);
    g.addColorStop(0,"rgba("+r+","+gr+","+b+",0)");
    g.addColorStop(0.7,"rgba("+r+","+gr+","+b+","+pu*0.04+")");
    g.addColorStop(1,"rgba("+r+","+gr+","+b+",0)");
    ctx.fillStyle = g; ctx.fillRect(0,0,W,H);
  }

  requestAnimFrame(animate);
}

animate();
