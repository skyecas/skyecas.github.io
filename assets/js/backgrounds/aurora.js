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

var sx = rawWidth / 1920, sy = rawHeight / 1080;
var width = 1920, height = 1080;
var scale = Math.min(sx, sy);
var ox = (rawWidth - 1920 * scale) / 2, oy = (rawHeight - 1080 * scale) / 2;

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
  new AuroraBand(120, 250, [
    "rgba(0, 255, 100, 0.3)", "rgba(0, 200, 150, 0.2)", "rgba(100, 0, 200, 0.15)"
  ], 0.0008, 0),
  new AuroraBand(180, 200, [
    "rgba(0, 220, 120, 0.25)", "rgba(50, 255, 150, 0.2)", "rgba(150, 50, 255, 0.15)"
  ], 0.001, 2.1),
  new AuroraBand(80, 180, [
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

function raDeg(h, m, s) { return (h + m / 60 + s / 3600) * 15; }
function decDeg(d, m, s) {
  var sign = d < 0 ? -1 : 1;
  return sign * (Math.abs(d) + m / 60 + s / 3600);
}

function spectralToHex(spec) {
  var m = spec.match(/^([OBAFGKMLT])(\d+(?:\.\d+)?)\s*((?:I[ab]?|II|III|IV|V)(?:[-\/](?:I[ab]?|II|III|IV|V))?)?/);
  if (!m) return "#ffffff";

  var cls = m[1], sub = parseFloat(m[2]), lum = m[3] || "V";

  var basePos = {O:0, B:1, A:2, F:3, G:4, K:5, M:6, L:7, T:8}[cls] + sub / 10;

  var lumAdjust = 0;
  if (/^I/.test(lum)) lumAdjust = 0.6;
  else if (/^II/.test(lum)) lumAdjust = 0.5;
  else if (/^III/.test(lum)) lumAdjust = 0.4;
  else if (/^IV/.test(lum)) lumAdjust = 0.2;
  if (/a$/.test(lum)) lumAdjust += 0.05;
  else if (/b$/.test(lum)) lumAdjust -= 0.05;
  var pos = basePos + lumAdjust;

  var refs = [
    { p: 0.0, r: [150, 170, 255] }, { p: 0.5, r: [155, 180, 255] },
    { p: 1.0, r: [170, 196, 255] }, { p: 1.5, r: [190, 210, 255] },
    { p: 2.0, r: [220, 220, 255] }, { p: 2.5, r: [240, 230, 240] },
    { p: 3.0, r: [255, 240, 220] }, { p: 3.5, r: [255, 235, 200] },
    { p: 4.0, r: [255, 230, 180] }, { p: 4.5, r: [255, 220, 160] },
    { p: 5.0, r: [255, 200, 130] }, { p: 5.5, r: [255, 170, 90] },
    { p: 6.0, r: [230, 140, 70] },  { p: 6.5, r: [200, 100, 50] },
  ];

  if (pos < refs[0].p) return rgbToHex(refs[0].r);
  if (pos > refs[refs.length - 1].p) return rgbToHex(refs[refs.length - 1].r);

  for (var i = 0; i < refs.length - 1; i++) {
    if (pos < refs[i + 1].p) {
      var t = (pos - refs[i].p) / (refs[i + 1].p - refs[i].p);
      return rgbToHex([
        Math.round(refs[i].r[0] + (refs[i + 1].r[0] - refs[i].r[0]) * t),
        Math.round(refs[i].r[1] + (refs[i + 1].r[1] - refs[i].r[1]) * t),
        Math.round(refs[i].r[2] + (refs[i + 1].r[2] - refs[i].r[2]) * t),
      ]);
    }
  }
  return "#ffffff";
}

function rgbToHex(rgb) {
  return "#" + ("0" + rgb[0].toString(16)).slice(-2) + ("0" + rgb[1].toString(16)).slice(-2) + ("0" + rgb[2].toString(16)).slice(-2);
}

// Cassiopeia stars with accurate coordinates and spectral classification
// Magnitudes and spectral types from SIMBAD / HR catalog
var cassBase = { x: 250, y: 1000 };
var cassSX = -6.5;
var cassSY = -12;

var cassiopeiaStars = [
  // Bright W asterism (hardcoded colours for accuracy)
  { name: "Schedar",  ra: raDeg(0, 40, 30.4411),  dec: decDeg(56, 32, 14.392), mag: 2.24, colour: "#FFB870",  spec: "K0IIIa"   },
  { name: "Caph",     ra: raDeg(0, 9, 10.68518),  dec: decDeg(59, 8, 59.2120), mag: 2.28, colour: "#F0DDB0",  spec: "F2III"    },
  { name: "Navi",     ra: raDeg(0, 56, 42.50108), dec: decDeg(60, 43, 0.2984), mag: 2.47, colour: "#A0B4FF",  spec: "B0.5IVe"  },
  { name: "Ruchbah",  ra: raDeg(1, 25, 48.95147), dec: decDeg(60, 14, 7.0225), mag: 2.66, colour: "#E8E0D0",  spec: "A5III-IV" },
  { name: "Segin",    ra: raDeg(1, 54, 23.73409), dec: decDeg(63, 40, 12.3602), mag: 3.35, colour: "#A8C0F0",  spec: "B3III"    },
  // Additional fainter stars (colours computed from spectral type)
  { name: "Marfak",   ra: raDeg(1, 11, 6.0),     dec: decDeg(55, 8, 59),    mag: 4.34, spec: "A7IV-V" },
  { name: "Fului",    ra: raDeg(0, 36, 58.3),    dec: decDeg(53, 53, 49),   mag: 3.67, spec: "B2IV"   },
  { name: "ι Cas",    ra: raDeg(2, 29, 4.0),     dec: decDeg(67, 24, 9),    mag: 4.53, spec: "A5p"    },
  { name: "χ Cas",    ra: raDeg(1, 33, 55.9),    dec: decDeg(59, 13, 42),   mag: 4.68, spec: "G9III"  },
  { name: "ψ Cas",    ra: raDeg(1, 25, 56.0),    dec: decDeg(68, 7, 48),    mag: 4.72, spec: "K0III"  },
  { name: "λ Cas",    ra: raDeg(0, 31, 46.3),    dec: decDeg(54, 31, 20),   mag: 4.74, spec: "B8Vn"   },
  { name: "κ Cas",    ra: raDeg(1, 33, 17.1),    dec: decDeg(62, 43, 40),   mag: 4.88, spec: "B1Ia"   },
  { name: "φ Cas",    ra: raDeg(1, 59, 2.0),     dec: decDeg(58, 17, 21),   mag: 4.95, spec: "F0III"  },
  { name: "1 Cas",    ra: raDeg(23, 6, 36.8),    dec: decDeg(59, 14, 28),   mag: 4.84, spec: "B0.5III"},
  { name: "υ2 Cas",   ra: raDeg(23, 43, 16.0),   dec: decDeg(58, 22, 22),   mag: 4.83, spec: "K0III"  },
  { name: "55 Cas",   ra: raDeg(2, 12, 41.7),    dec: decDeg(66, 9, 58),    mag: 5.04, spec: "B9IV-V" },
];

// Brightness controls apparent size: mag 1 = ~2.3px, mag 6 = ~0.3px
function starSize(mag) { return Math.pow(2.512, (5 - mag) / 5) * 1.2; }

var cassWCoords = [];
for (var i = 0; i < cassiopeiaStars.length; i++) {
  var s = cassiopeiaStars[i];
  cassWCoords.push({
    x: cassBase.x + cassSX * s.ra,
    y: cassBase.y + cassSY * s.dec,
    size: starSize(s.mag),
    colour: s.colour || spectralToHex(s.spec),
    name: s.name
  });
}

// Connections for the W: Caph→Schedar→Navi→Ruchbah→Segin
// Indices: 0=Schedar, 1=Caph, 2=Navi, 3=Ruchbah, 4=Segin
// Order along W: Caph(1)→Schedar(0)→Navi(2)→Ruchbah(3)→Segin(4)
var cassiopeiaConnections = [
  [1, 0], [0, 2], [2, 3], [3, 4]
];

// Project star RA/Dec to screen for a constellation definition
function constPos(d, ra, dec) {
  var cosFac = Math.cos(d.dC * Math.PI / 180);
  return {
    x: d.cx - d.sc * (ra - d.rC) * cosFac,
    y: d.cy - d.sc * (dec - d.dC)
  };
}

// Additional constellations with real RA/Dec coords
// cx,cy = screen position of reference point; sc = px per degree
// rC,dC = reference RA/Dec (center of constellation)
// t = stars {ra,dec,mag,spec,name}; m = main indices for label; c = connections
function defConst(name, cx, cy, sc, rC, dC, stars, main, connections) {
  return { n: name, cx: cx, cy: cy, sc: sc, rC: rC, dC: dC, t: stars, m: main, c: connections };
}

var extraCons = [
  defConst("Lyra", 200, 135, 16, 281.92, 35.61, [
    { ra: raDeg(18,36,56.34), dec: decDeg(38,47,1.3),  mag: 0.03, spec: "A0V",  name: "Vega" },
    { ra: raDeg(18,50,4.80),  dec: decDeg(33,21,45.6), mag: 3.52, spec: "A4V",  name: "Sheliak" },
    { ra: raDeg(18,58,56.62), dec: decDeg(32,41,22.4), mag: 3.25, spec: "B9V",  name: "Sulafat" },
    { ra: raDeg(18,44,31.4),  dec: decDeg(37,36,2.0),  mag: 4.34, spec: "A4V",  name: "ζ¹ Lyr" },
  ], [0,1,2,3], [[0,3],[3,1],[3,2],[1,2]]),
  defConst("Cygnus", 1700, 145, 9, 304.64, 37.77, [
    { ra: raDeg(20,41,25.91), dec: decDeg(45,16,49.2),  mag: 1.25, spec: "A2Ia",  name: "Deneb" },
    { ra: raDeg(20,22,13.70), dec: decDeg(40,15,24.0),  mag: 2.23, spec: "F8Iab", name: "Sadr" },
    { ra: raDeg(19,30,43.29), dec: decDeg(27,57,34.9),  mag: 3.08, spec: "K0III", name: "Albireo" },
    { ra: raDeg(19,44,58.44), dec: decDeg(45,7,50.5),   mag: 2.86, spec: "B9III", name: "δ Cyg" },
    { ra: raDeg(21,13,28.37), dec: decDeg(30,14,24.7),  mag: 3.21, spec: "G8III", name: "ζ Cyg" },
  ], [0,1,2,3,4], [[0,1],[1,2],[3,1],[1,4]]),
  defConst("Gemini", 180, 580, 10, 108.09, 24.69, [
    { ra: raDeg(7,34,36.00),  dec: decDeg(31,53,18.0),  mag: 1.58, spec: "A1V",  name: "Castor" },
    { ra: raDeg(7,45,18.95),  dec: decDeg(28,1,34.3),   mag: 1.14, spec: "K0III", name: "Pollux" },
    { ra: raDeg(6,37,42.71),  dec: decDeg(16,23,57.4),  mag: 1.93, spec: "A0IV",  name: "Alhena" },
    { ra: raDeg(7,20,7.39),   dec: decDeg(21,58,56.4),  mag: 3.53, spec: "A1V",  name: "Wasat" },
    { ra: raDeg(6,43,55.93),  dec: decDeg(25,7,52.2),   mag: 2.98, spec: "G5III", name: "Mebsuta" },
  ], [0,1,2,3,4], [[0,3],[3,1],[2,3],[1,4],[4,3]]),
  defConst("Scorpius", 1730, 640, 8, 251.69, -29.88, [
    { ra: raDeg(16,0,20.01),  dec: decDeg(-22,37,17.3), mag: 2.29, spec: "B0.5IV", name: "Dschubba" },
    { ra: raDeg(16,5,26.23),  dec: decDeg(-19,48,19.4), mag: 2.56, spec: "B1V",    name: "Graffias" },
    { ra: raDeg(16,29,24.46), dec: decDeg(-26,25,55.2), mag: 0.96, spec: "M1.5I",  name: "Antares" },
    { ra: raDeg(16,21,11.32), dec: decDeg(-25,35,34.5), mag: 2.88, spec: "B2III",  name: "σ Sco" },
    { ra: raDeg(16,35,52.95), dec: decDeg(-28,12,57.6), mag: 2.82, spec: "B0.5V",  name: "τ Sco" },
    { ra: raDeg(17,37,19.13), dec: decDeg(-43,0,9.0),   mag: 1.86, spec: "F2II",   name: "Sargas" },
    { ra: raDeg(17,33,36.52), dec: decDeg(-37,6,13.8),  mag: 1.63, spec: "B2IV",   name: "Shaula" },
    { ra: raDeg(17,30,45.82), dec: decDeg(-37,17,44.9), mag: 2.70, spec: "B2V",    name: "Lesath" },
  ], [0,1,2,3,4,5,6,7], [[0,1],[1,2],[2,3],[3,4],[4,5],[5,6],[6,7]]),
  defConst("Andromeda", 960, 165, 13, 14.50, 36.25, [
    { ra: raDeg(0,8,23.26),   dec: decDeg(29,5,25.6),   mag: 2.06, spec: "B9IV",  name: "Alpheratz" },
    { ra: raDeg(0,39,19.67),  dec: decDeg(30,51,39.7),  mag: 3.27, spec: "K1III", name: "δ And" },
    { ra: raDeg(1,9,43.92),   dec: decDeg(35,37,14.0),  mag: 2.05, spec: "M0III", name: "Mirach" },
    { ra: raDeg(0,49,48.85),  dec: decDeg(41,4,20.1),   mag: 4.53, spec: "B5V",   name: "ν And" },
    { ra: raDeg(2,3,53.95),   dec: decDeg(42,19,47.2),  mag: 2.10, spec: "K3III", name: "Almach" },
    { ra: raDeg(0,56,45.21),  dec: decDeg(38,29,57.6),  mag: 3.86, spec: "A0V",   name: "μ And" },
  ], [0,1,2,3,4,5], [[0,1],[1,2],[2,4],[2,3],[3,5]]),
  defConst("Orion", 1700, 420, 10, 83.96, -1.62, [
    { ra: raDeg(5,55,10.29),  dec: decDeg(7,24,25.4),   mag: 0.45, spec: "M2I",  name: "Betelgeuse" },
    { ra: raDeg(5,25,7.86),   dec: decDeg(6,20,58.9),   mag: 1.64, spec: "B2III", name: "Bellatrix" },
    { ra: raDeg(5,40,45.53),  dec: decDeg(-1,56,34.3),  mag: 1.77, spec: "O9.5I", name: "Alnitak" },
    { ra: raDeg(5,36,12.81),  dec: decDeg(-1,12,6.9),   mag: 1.69, spec: "B0I",   name: "Alnilam" },
    { ra: raDeg(5,32,0.40),   dec: decDeg(-0,17,4.4),   mag: 2.25, spec: "O9.5II",name: "Mintaka" },
    { ra: raDeg(5,35,16.48),  dec: decDeg(-5,23,23.2),  mag: 3.43, spec: "B3V",   name: "Sword" },
    { ra: raDeg(5,47,45.34),  dec: decDeg(-9,40,10.6),  mag: 2.06, spec: "B1.5I", name: "Saiph" },
    { ra: raDeg(5,14,32.28),  dec: decDeg(-8,12,5.9),   mag: 0.13, spec: "B8I",   name: "Rigel" },
  ], [0,1,2,3,4,5,6,7], [[0,2],[1,4],[2,3],[3,4],[2,5],[4,5],[2,6],[4,7],[6,7],[0,1]]),
];
// Date/always prominence assignments
extraCons[0].date = "27/07"; // Lyra - wedding
extraCons[1].date = "12/08"; // Cygnus - proposal
extraCons[2].date = "04/09"; // Gemini - dating
extraCons[3].date = "26/10"; // Scorpius - Skye's birthday
extraCons[4].date = "31/03"; // Andromeda - HRT
extraCons[5].always = true;  // Orion - spouse taught first

function drawConstellationDef(d, t) {
  var prom = d.always || d.date === getDateKey() ? 1.0 : 0.35;

  var pts = [];
  for (var i = 0; i < d.t.length; i++) {
    var si = d.t[i];
    pts.push({
      x: d.cx - d.sc * (si.ra - d.rC) * Math.cos(d.dC * Math.PI / 180),
      y: d.cy - d.sc * (si.dec - d.dC),
      size: starSize(si.mag),
      colour: spectralToHex(si.spec),
      name: si.name,
    });
  }

  var connAlpha = 0.04 + prom * 0.12;
  var glowMul = 0.15 + prom * 0.15;
  var starMul = 0.3 + prom * 0.5;

  for (var pi of pts) {
    var tw = Math.sin(t * 0.02 + pi.x * 0.005) * 0.3 + 0.7;
    var a = starMul + tw * (1 - starMul);
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

function hexToRgba(hex, alpha) {
  var r = parseInt(hex.slice(1,3), 16);
  var g = parseInt(hex.slice(3,5), 16);
  var b = parseInt(hex.slice(5,7), 16);
  return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
}

function drawConstellationStars(t) {
  for (var s of cassWCoords) {
    var twinkle = Math.sin(t * 0.02 + s.x * 0.005) * 0.3 + 0.7;
    var alpha = 0.7 + twinkle * 0.3;
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

  bgCtx.setTransform(scale, 0, 0, scale, ox, oy);

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
  sx = rawWidth / 1920; sy = rawHeight / 1080;
  scale = Math.min(sx, sy);
  ox = (rawWidth - 1920 * scale) / 2; oy = (rawHeight - 1080 * scale) / 2;
});
