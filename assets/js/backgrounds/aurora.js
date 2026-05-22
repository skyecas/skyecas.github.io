var requestAnimFrame = (function(){
  return window.requestAnimationFrame       ||
         window.webkitRequestAnimationFrame ||
         window.mozRequestAnimationFrame    ||
         window.oRequestAnimationFrame      ||
         window.msRequestAnimationFrame     ||
         function( callback ){
           window.setTimeout(callback, 1000 / 60);
         };
})();

var background = document.getElementById("bgCanvas"),
    bgCtx = background.getContext("2d"),
    rawWidth = window.innerWidth,
    rawHeight = window.innerHeight;

if (!isFinite(rawWidth) || rawWidth < 100) rawWidth = 1920;
if (!isFinite(rawHeight) || rawHeight < 100) rawHeight = 1080;
background.width = rawWidth;
background.height = rawHeight;

var width = rawWidth, height = rawHeight;
var sx = rawWidth / 1920, sy = rawHeight / 1080;
var mScale = Math.min(sx, sy);

var starColours = ["white", "aliceBlue", "powderBlue", "azure", "moccasin"];

function Star() {
  this.x = Math.random() * width;
  this.y = Math.random() * height * 0.8;
  this.size = Math.random() * 1.5 + 0.1;
  this.colour = starColours[Math.floor(Math.random() * starColours.length)];
  this.phase = Math.random() * Math.PI * 2;
  this.speed = 0.02 + Math.random() * 0.03;
}
Star.prototype.update = function(t) {
  var twinkle = Math.sin(t * this.speed + this.phase) * 0.5 + 0.5;
  bgCtx.globalAlpha = 0.5 + twinkle * 0.5;
  bgCtx.fillStyle = this.colour;
  bgCtx.fillRect(this.x, this.y, this.size, this.size);
  bgCtx.globalAlpha = 1;
};

function AuroraBand(yBase, height, colours, speed, phase) {
  this.yBase = yBase;
  this.height = height;
  this.colours = colours;
  this.speed = speed;
  this.phase = phase;
}
AuroraBand.prototype.update = function(t) {
  var grad = bgCtx.createLinearGradient(0, this.yBase - 30, 0, this.yBase + this.height + 30);
  for (var i = 0; i < this.colours.length; i++) {
    grad.addColorStop(i / (this.colours.length - 1), this.colours[i]);
  }
  bgCtx.save();
  bgCtx.globalAlpha = 0.18;
  bgCtx.fillStyle = grad;
  bgCtx.beginPath();
  bgCtx.moveTo(0, this.yBase);
  for (var x = 0; x <= width; x += 8) {
    var y = this.yBase
      + Math.sin(x * 0.008 + t * this.speed + this.phase) * 25
      + Math.sin(x * 0.015 + t * this.speed * 0.7 + this.phase * 1.3) * 15
      + Math.sin(x * 0.003 + t * this.speed * 1.3 + this.phase * 0.7) * 20;
    bgCtx.lineTo(x, y);
  }
  bgCtx.lineTo(width, this.yBase + this.height);
  bgCtx.lineTo(0, this.yBase + this.height);
  bgCtx.closePath();
  bgCtx.fill();
  bgCtx.restore();

  bgCtx.save();
  bgCtx.globalAlpha = 0.15;
  bgCtx.filter = "blur(20px)";
  bgCtx.fillStyle = grad;
  bgCtx.beginPath();
  bgCtx.moveTo(0, this.yBase);
  for (var x = 0; x <= width; x += 8) {
    var y = this.yBase
      + Math.sin(x * 0.008 + t * this.speed + this.phase) * 25
      + Math.sin(x * 0.015 + t * this.speed * 0.7 + this.phase * 1.3) * 15
      + Math.sin(x * 0.003 + t * this.speed * 1.3 + this.phase * 0.7) * 20;
    bgCtx.lineTo(x, y);
  }
  bgCtx.lineTo(width, this.yBase + this.height + 40);
  bgCtx.lineTo(0, this.yBase + this.height + 40);
  bgCtx.closePath();
  bgCtx.fill();
  bgCtx.restore();
  bgCtx.filter = "none";
};

var stars = [];
for (var i = 500; i > 0; i--) { stars.push(new Star()); }

var bands = [
  new AuroraBand(120 * sy, 250, [
    "rgba(0, 255, 100, 0.3)", "rgba(0, 200, 150, 0.2)", "rgba(100, 0, 200, 0.15)"
  ], 0.0008, 0),
  new AuroraBand(180 * sy, 200, [
    "rgba(0, 220, 120, 0.25)", "rgba(50, 255, 150, 0.2)", "rgba(150, 50, 255, 0.15)"
  ], 0.001, 2.1),
  new AuroraBand(80 * sy, 180, [
    "rgba(100, 255, 200, 0.2)", "rgba(200, 100, 255, 0.2)", "rgba(0, 255, 80, 0.15)"
  ], 0.0006, 4.3),
];

var time = 0;

var specialDates = {
  "27/07": "255, 215, 0", "12/08": "192, 192, 224",
  "23/08": "255, 127, 127", "04/09": "255, 105, 180",
  "26/10": "0, 229, 255", "31/03": "255, 143, 171"
};
function getDateRGB() {
  var d = new Date();
  var key = ("0" + d.getDate()).slice(-2) + "/" + ("0" + (d.getMonth() + 1)).slice(-2);
  return specialDates[key] || null;
}
function getDateKey() {
  var d = new Date();
  return ("0" + d.getDate()).slice(-2) + "/" + ("0" + (d.getMonth() + 1)).slice(-2);
}

// Cassiopeia stars with accurate coordinates and spectral classification
// Magnitudes and spectral types from SIMBAD / HR catalog
var cassBase = { x: 250 * sx, y: 1000 * sy };
var cassSX = -6.5 * sx;
var cassSY = -12 * sy;

// Brightness controls apparent size: mag 1 = ~2.3px, mag 6 = ~0.3px

var cassWCoords = [];
for (var i = 0; i < cassiopeiaStars.length; i++) {
  var s = cassiopeiaStars[i];
  cassWCoords.push({
    x: cassBase.x + cassSX * s.ra,
    y: cassBase.y + cassSY * s.dec,
    size: starSize(s.mag),
    colour: spectralToHex(s.spec),
    name: s.name,
    mag: s.mag,
  });
}

// Project star RA/Dec to screen for a constellation definition
function constPos(d, ra, dec) {
  var cosFac = Math.cos(d.dC * Math.PI / 180);
  return {
    x: d.cx - d.sc * (ra - d.rC) * cosFac,
    y: d.cy - d.sc * (dec - d.dC)
  };
}

// Additional constellations from shared data, projected to screen
function buildExtraCons() {
  var cons = [];
  var spec = [
    { key:"LYRA",      cx:200*sx,  cy:135*sy,  sc:16*mScale, rC:281.92, dC:35.61 },
    { key:"CYGNUS",    cx:1700*sx, cy:145*sy,  sc:9*mScale,  rC:304.64, dC:37.77 },
    { key:"GEMINI",    cx:180*sx,  cy:580*sy,  sc:10*mScale, rC:108.09, dC:24.69 },
    { key:"SCORPIUS",  cx:1730*sx, cy:640*sy,  sc:8*mScale,  rC:251.69, dC:-29.88 },
    { key:"ANDROMEDA", cx:960*sx,  cy:165*sy,  sc:13*mScale, rC:14.50,  dC:36.25 },
    { key:"ORION",     cx:1700*sx, cy:420*sy,  sc:10*mScale, rC:83.96,  dC:-1.62 },
  ];
  for (var i = 0; i < spec.length; i++) {
    var s = spec[i];
    var c = CONSTELLATIONS[s.key];
    if (!c) continue;
    cons.push({
      n: c.name,
      cx: s.cx, cy: s.cy, sc: s.sc, rC: s.rC, dC: s.dC,
      pts: c.project(s.cx, s.cy, s.sc, s.rC, s.dC),
      t: c.stars,
      m: c.mainIndices,
      c: c.connections,
      date: c.date,
      always: c.always,
    });
  }
  return cons;
}
var extraCons = buildExtraCons();

function drawConstellationDef(d, t) {
  var prom = d.always || d.date === getDateKey() ? 1.0 : 0.35;

  var pts = d.pts || (function() {
    var p = [];
    for (var i = 0; i < d.t.length; i++) {
      var si = d.t[i];
      p.push({
        x: d.cx - d.sc * (si.ra - d.rC) * Math.cos(d.dC * Math.PI / 180),
        y: d.cy - d.sc * (si.dec - d.dC),
        size: starSize(si.mag),
        colour: spectralToHex(si.spec),
        name: si.name,
        mag: si.mag,
      });
    }
    return p;
  })();

  var connAlpha = 0.04 + prom * 0.12;
  var glowMul = 0.15 + prom * 0.15;
  var starMul = 0.3 + prom * 0.5;

  for (var pi of pts) {
    var tw = Math.sin(t * 0.02 + pi.x * 0.005) * 0.3 + 0.7;
    var magFactor = pi.mag !== undefined ? Math.max(0.15, 1.15 - pi.mag * 0.2) : 1;
    var a = (starMul + tw * (1 - starMul)) * magFactor;
    var gs = pi.size * (2 + prom * 1.5);

    bgCtx.save();
    var gl = bgCtx.createRadialGradient(pi.x, pi.y, 0, pi.x, pi.y, gs);
    gl.addColorStop(0, hexToRgba(pi.colour, a * glowMul));
    gl.addColorStop(1, hexToRgba(pi.colour, 0));
    bgCtx.fillStyle = gl;
    bgCtx.beginPath();
    bgCtx.arc(pi.x, pi.y, gs, 0, Math.PI * 2);
    bgCtx.fill();
    bgCtx.restore();

    bgCtx.fillStyle = pi.colour;
    bgCtx.globalAlpha = a;
    bgCtx.beginPath();
    bgCtx.arc(pi.x, pi.y, pi.size, 0, Math.PI * 2);
    bgCtx.fill();
    bgCtx.globalAlpha = 1;
  }

  bgCtx.strokeStyle = "rgba(255, 255, 255, " + connAlpha + ")";
  bgCtx.lineWidth = 1;
  bgCtx.beginPath();
  for (var ci of d.c) {
    bgCtx.moveTo(pts[ci[0]].x, pts[ci[0]].y);
    bgCtx.lineTo(pts[ci[1]].x, pts[ci[1]].y);
  }
  bgCtx.stroke();

  bgCtx.font = "11px sans-serif";
  bgCtx.textAlign = "center";
  bgCtx.fillStyle = "rgba(255, 255, 255, " + (0.06 + prom * 0.12) + ")";
  var lx = 0, maxY = -Infinity;
  for (var mi of d.m) {
    lx += pts[mi].x;
    if (pts[mi].y > maxY) maxY = pts[mi].y;
  }
  bgCtx.fillText(d.n, lx / d.m.length, maxY + 18);
}

function drawConstellationStars(t) {
  for (var s of cassWCoords) {
    var twinkle = Math.sin(t * 0.02 + s.x * 0.005) * 0.3 + 0.7;
    var magFactor = Math.max(0.15, 1.15 - s.mag * 0.2);
    var alpha = (0.7 + twinkle * 0.3) * magFactor;
    var glowSize = s.size * 3.5;

    bgCtx.save();
    var glow = bgCtx.createRadialGradient(s.x, s.y, 0, s.x, s.y, glowSize);
    glow.addColorStop(0, hexToRgba(s.colour, alpha * 0.3));
    glow.addColorStop(1, hexToRgba(s.colour, 0));
    bgCtx.fillStyle = glow;
    bgCtx.beginPath();
    bgCtx.arc(s.x, s.y, glowSize, 0, Math.PI * 2);
    bgCtx.fill();
    bgCtx.restore();

    bgCtx.fillStyle = s.colour;
    bgCtx.globalAlpha = alpha;
    bgCtx.beginPath();
    bgCtx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
    bgCtx.fill();
    bgCtx.globalAlpha = 1;
  }

  bgCtx.strokeStyle = "rgba(255, 255, 255, 0.15)";
  bgCtx.lineWidth = 1;
  bgCtx.beginPath();
  for (var c of cassiopeiaConnections) {
    bgCtx.moveTo(cassWCoords[c[0]].x, cassWCoords[c[0]].y);
    bgCtx.lineTo(cassWCoords[c[1]].x, cassWCoords[c[1]].y);
  }
  bgCtx.stroke();

  bgCtx.font = "11px sans-serif";
  bgCtx.textAlign = "center";
  bgCtx.fillStyle = "rgba(255, 255, 255, 0.24)";
  var labelX = 0, minY = Infinity;
  for (var i = 0; i < 5; i++) { var s = cassWCoords[i]; labelX += s.x; if (s.y < minY) minY = s.y; }
  bgCtx.fillText("Cassiopeia", labelX / 5, minY - 20);
}

function drawLandscape() {
  bgCtx.fillStyle = "#060612";
  bgCtx.beginPath();
  bgCtx.moveTo(0, height * 0.85);
  for (var x = 0; x <= width; x += 15) {
    var h = Math.sin(x * 0.015) * 20 + Math.sin(x * 0.04) * 10 + Math.sin(x * 0.008) * 30 + 25;
    bgCtx.lineTo(x, height * 0.85 - h);
  }
  bgCtx.lineTo(width, height);
  bgCtx.lineTo(0, height);
  bgCtx.closePath();
  bgCtx.fill();
}

function animate() {
  time++;

  bgCtx.fillStyle = "#08081a";
  bgCtx.fillRect(0, 0, rawWidth, rawHeight);

  var skyGrad = bgCtx.createLinearGradient(0, 0, 0, height * 0.85);
  skyGrad.addColorStop(0, "#08081a");
  skyGrad.addColorStop(0.4, "#0a0a24");
  skyGrad.addColorStop(0.7, "#0d0d1e");
  skyGrad.addColorStop(1, "#0a0a14");
  bgCtx.fillStyle = skyGrad;
  bgCtx.fillRect(0, 0, width, height);

  for (var s of stars) { s.update(time); }

  drawConstellationStars(time);
  for (var ec of extraCons) { drawConstellationDef(ec, time); }

  var dc = getDateRGB();
  if (dc) {
    var pulse = Math.sin(time * 0.02) * 0.5 + 0.5;
    for (var b of bands) {
      var extra = "rgba(" + dc + ", " + pulse * 0.08 + ")";
      var colours = b.colours.slice();
      colours.push(extra);
      var grad = bgCtx.createLinearGradient(0, b.yBase - 30, 0, b.yBase + b.height + 30);
      for (var i = 0; i < colours.length; i++) {
        grad.addColorStop(i / (colours.length - 1), colours[i]);
      }
      bgCtx.save();
      bgCtx.globalAlpha = 0.3;
      bgCtx.fillStyle = grad;
      bgCtx.beginPath();
      bgCtx.moveTo(0, b.yBase);
      for (var x = 0; x <= width; x += 8) {
        var y = b.yBase
          + Math.sin(x * 0.008 + time * b.speed + b.phase) * 25
          + Math.sin(x * 0.015 + time * b.speed * 0.7 + b.phase * 1.3) * 15
          + Math.sin(x * 0.003 + time * b.speed * 1.3 + b.phase * 0.7) * 20;
        bgCtx.lineTo(x, y);
      }
      bgCtx.lineTo(width, b.yBase + b.height);
      bgCtx.lineTo(0, b.yBase + b.height);
      bgCtx.closePath();
      bgCtx.fill();
      bgCtx.restore();
    }
  } else {
    for (var b of bands) { b.update(time); }
  }

  drawLandscape();

  requestAnimFrame(animate);
}

animate();

window.addEventListener("resize", function() {
  var rw = window.innerWidth, rh = window.innerHeight;
  if (!isFinite(rw) || rw < 100) rw = 1920;
  if (!isFinite(rh) || rh < 100) rh = 1080;
  rawWidth = rw; rawHeight = rh;
  background.width = rawWidth; background.height = rawHeight;
  width = rawWidth; height = rawHeight;
  sx = rawWidth / 1920; sy = rawHeight / 1080;
  mScale = Math.min(sx, sy);
  cassBase = { x: 250 * sx, y: 1000 * sy };
  cassSX = -6.5 * sx;
  cassSY = -12 * sy;
  // recompute all Cassiopeia star coordinates
  for (var i = 0; i < cassiopeiaStars.length; i++) {
    var s = cassiopeiaStars[i];
    cassWCoords[i].x = cassBase.x + cassSX * s.ra;
    cassWCoords[i].y = cassBase.y + cassSY * s.dec;
  }
  // rebuild band definitions with new sy
  bands = [
    new AuroraBand(120 * sy, 250, [
      "rgba(0, 255, 100, 0.3)", "rgba(0, 200, 150, 0.2)", "rgba(100, 0, 200, 0.15)"
    ], 0.0008, 0),
    new AuroraBand(180 * sy, 200, [
      "rgba(0, 220, 120, 0.25)", "rgba(50, 255, 150, 0.2)", "rgba(150, 50, 255, 0.15)"
    ], 0.001, 2.1),
    new AuroraBand(80 * sy, 180, [
      "rgba(100, 255, 200, 0.2)", "rgba(200, 100, 255, 0.2)", "rgba(0, 255, 80, 0.15)"
    ], 0.0006, 4.3),
  ];
  // rebuild extra constellation positions from shared data
  extraCons = buildExtraCons();
});
