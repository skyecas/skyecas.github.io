// --- Astronomical utilities ---
function raDeg(h, m, s) { return (h + m / 60 + s / 3600) * 15; }
function decDeg(d, m, s) {
  var sign = d < 0 ? -1 : 1;
  return sign * (Math.abs(d) + m / 60 + s / 3600);
}

// --- Spectral type to hex colour (computed, never stored) ---
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

function hexToRgba(hex, alpha) {
  var r = parseInt(hex.slice(1,3), 16);
  var g = parseInt(hex.slice(3,5), 16);
  var b = parseInt(hex.slice(5,7), 16);
  return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
}

function starSize(mag) { return Math.pow(2.512, (5 - mag) / 5) * 1.2; }

// --- Star class (colour always derived from spectral type) ---
function Star(config) {
  this.name = config.name || "?";
  this.ra = typeof config.ra === "number" ? config.ra : raDeg(config.ra[0], config.ra[1], config.ra[2] || 0);
  this.dec = typeof config.dec === "number" ? config.dec : decDeg(config.dec[0], config.dec[1], config.dec[2] || 0);
  this.mag = config.mag;
  this.spec = config.spec || "G2V";
}
Star.prototype.getColour = function() { return spectralToHex(this.spec); };
Star.prototype.getSize = function() { return Math.pow(2.512, (5 - this.mag) / 5) * 1.2; };

// --- Constellation class ---
function Constellation(config) {
  this.name = config.name;
  this.stars = config.stars.map(function(s) { return s instanceof Star ? s : new Star(s); });
  this.connections = config.connections || [];
  this.mainIndices = config.mainIndices || [];
  this.date = config.date || null;
  this.always = config.always || false;
}

Constellation.prototype.project = function(cx, cy, sc, rC, dC) {
  var cosFac = Math.cos(dC * Math.PI / 180);
  var pts = [];
  for (var i = 0; i < this.stars.length; i++) {
    var s = this.stars[i];
    pts.push({
      x: cx - sc * (s.ra - rC) * cosFac,
      y: cy - sc * (s.dec - dC),
      size: s.getSize(),
      colour: s.getColour(),
      name: s.name,
      mag: s.mag,
    });
  }
  return pts;
};

function getDateKey() {
  var d = new Date();
  return ("0" + d.getDate()).slice(-2) + "/" + ("0" + (d.getMonth() + 1)).slice(-2);
}

// --- All constellations (Wikipedia-verified data) ---
var consData = [
  { /* CASSIOPEIA */
    name: "Cassiopeia", always: true,
    stars: [
      { name:"Schedar", ra:[0,40,30.39], dec:[56,32,14.7], mag:2.24, spec:"K0II-IIIvar" },
      { name:"Caph", ra:[0,9,10.09], dec:[59,9,0.8], mag:2.28, spec:"F2III-IV" },
      { name:"Navi", ra:[0,56,42.5], dec:[60,43,0.3], mag:2.47, spec:"B0IV:evar" },
      { name:"Ruchbah", ra:[1,25,48.6], dec:[60,14,7.5], mag:2.68, spec:"A5Vv SB" },
      { name:"Segin", ra:[1,54,23.68], dec:[63,40,12.5], mag:3.35, spec:"B2pvar" },
      { name:"Achird", ra:[0,49,5.1], dec:[57,48,59.6], mag:3.46, spec:"G0V SB" },
      { name:"Fulu", ra:[0,36,58.27], dec:[53,53,49], mag:3.69, spec:"B2IV" },
      { name:"50 Cas", ra:[2,3,26.19], dec:[72,25,16.5], mag:3.95, spec:"A2V" },
      { name:"κ Cas", ra:[0,32,59.99], dec:[62,55,54.4], mag:4.17, spec:"B1Ia" },
      { name:"Marfak", ra:[1,11,5.93], dec:[55,8,59.8], mag:4.34, spec:"A7Vvar" },
      { name:"ι Cas", ra:[2,29,3.99], dec:[67,24,8.6], mag:4.46, spec:"A5p Sr" },
      { name:"ο Cas", ra:[0,44,43.5], dec:[48,17,3.8], mag:4.48, spec:"B5III" },
    ],
    connections: [[1,0],[0,2],[2,3],[3,4]],
    mainIndices: [0,1,2,3,4],
  },
  { /* ORION */
    name: "Orion", always: true,
    stars: [
      { name:"Betelgeuse", ra:[5,55,10.29], dec:[7,24,25.3], mag:0.42, spec:"M2Ib" },
      { name:"Bellatrix", ra:[5,25,7.87], dec:[6,20,59], mag:1.64, spec:"B2III" },
      { name:"Alnitak", ra:[5,40,45.53], dec:[-1,56,34.3], mag:1.77, spec:"O9.5I" },
      { name:"Alnilam", ra:[5,36,12.81], dec:[-1,12,6.9], mag:1.69, spec:"B0I" },
      { name:"Mintaka", ra:[5,32,0.40], dec:[-0,17,4.4], mag:2.25, spec:"O9.5II" },
      { name:"Saiph", ra:[5,47,45.34], dec:[-9,40,10.6], mag:2.06, spec:"B1.5I" },
      { name:"Rigel", ra:[5,14,32.28], dec:[-8,12,5.9], mag:0.13, spec:"B8I" },
      { name:"Meissa", ra:[5,35,8.28], dec:[9,56,3], mag:3.47, spec:"O8III" },
    ],
    connections: [[0,1],[2,3],[3,4],[2,5],[4,5],[2,6],[4,7],[6,7]],
    mainIndices: [0,1,2,3,4,5,6,7],
  },
  { /* LYRA */
    name: "Lyra", date: "27/07",
    stars: [
      { name:"Vega", ra:[18,36,56.19], dec:[38,46,58.8], mag:0.03, spec:"A0Vvar" },
      { name:"Sheliak", ra:[18,50,4.79], dec:[33,21,45.6], mag:3.52, spec:"A8:V comp SB" },
      { name:"Sulafat", ra:[18,58,56.62], dec:[32,41,22.4], mag:3.25, spec:"B9III" },
      { name:"δ² Lyr", ra:[18,54,30.29], dec:[36,53,55], mag:4.22, spec:"M4IIvar" },
    ],
    connections: [[0,3],[3,1],[3,2],[1,2]],
    mainIndices: [0,1,2,3],
  },
  { /* CYGNUS */
    name: "Cygnus", date: "12/08",
    stars: [
      { name:"Deneb", ra:[20,41,25.91], dec:[45,16,49.2], mag:1.25, spec:"A2Ia" },
      { name:"Sadr", ra:[20,22,13.7], dec:[40,15,24.1], mag:2.23, spec:"F8Ib" },
      { name:"Albireo", ra:[19,30,43.29], dec:[27,57,34.9], mag:3.05, spec:"K3II+..." },
      { name:"δ Cyg", ra:[19,44,58.44], dec:[45,7,50.5], mag:2.86, spec:"B9.5III" },
      { name:"ζ Cyg", ra:[21,12,56.18], dec:[30,13,37.5], mag:3.21, spec:"G8II SB" },
      { name:"ε Cyg", ra:[20,46,12.43], dec:[33,58,10], mag:2.48, spec:"K0III" },
    ],
    connections: [[0,1],[1,2],[3,1],[1,4]],
    mainIndices: [0,1,2,3,4],
  },
  { /* GEMINI */
    name: "Gemini", date: "04/09",
    stars: [
      { name:"Pollux", ra:[7,45,19.36], dec:[28,1,34.7], mag:1.16, spec:"K0III" },
      { name:"Castor", ra:[7,34,36], dec:[31,53,19.1], mag:1.90, spec:"A2Vm" },
      { name:"Alhena", ra:[6,37,42.7], dec:[16,23,57.9], mag:1.93, spec:"A0IV" },
      { name:"Wasat", ra:[7,20,7.39], dec:[21,58,56.4], mag:3.50, spec:"F0IV..." },
      { name:"Mebsuta", ra:[6,43,55.93], dec:[25,7,52.2], mag:3.06, spec:"G8Ib" },
      { name:"Propus", ra:[6,14,52.7], dec:[22,30,24.6], mag:3.31, spec:"M3III" },
    ],
    connections: [[0,3],[3,1],[2,3],[1,4],[4,3]],
    mainIndices: [0,1,2,3,4],
  },
  { /* SCORPIUS */
    name: "Scorpius", date: "26/10",
    stars: [
      { name:"Antares", ra:[16,29,24.46], dec:[-26,25,55.2], mag:0.96, spec:"M1.5I" },
      { name:"Shaula", ra:[17,33,36.52], dec:[-37,6,13.8], mag:1.63, spec:"B2IV" },
      { name:"Sargas", ra:[17,37,19.13], dec:[-43,0,9], mag:1.86, spec:"F2II" },
      { name:"Dschubba", ra:[16,0,20.01], dec:[-22,37,17.3], mag:2.29, spec:"B0.5IV" },
      { name:"Graffias", ra:[16,5,26.23], dec:[-19,48,19.4], mag:2.56, spec:"B1V" },
      { name:"Lesath", ra:[17,30,45.82], dec:[-37,17,44.9], mag:2.70, spec:"B2V" },
      { name:"τ Sco", ra:[16,35,52.95], dec:[-28,12,57.6], mag:2.82, spec:"B0.5V" },
      { name:"σ Sco", ra:[16,21,11.32], dec:[-25,35,34.5], mag:2.88, spec:"B2III" },
    ],
    connections: [[0,1],[1,2],[2,3],[3,4],[4,5],[5,6],[6,7]],
    mainIndices: [0,1,2,3,4,5,6,7],
  },
  { /* ANDROMEDA */
    name: "Andromeda", date: "31/03",
    stars: [
      { name:"Alpheratz", ra:[0,8,23.17], dec:[29,5,27], mag:2.07, spec:"B9p" },
      { name:"Mirach", ra:[1,9,43.8], dec:[35,37,15], mag:2.07, spec:"M0IIIvar" },
      { name:"Almach", ra:[2,3,53.92], dec:[42,19,47.5], mag:2.10, spec:"K3IIb" },
      { name:"δ And", ra:[0,39,19.6], dec:[30,51,40.4], mag:3.27, spec:"K3III..." },
      { name:"51 And", ra:[1,37,59.5], dec:[48,37,42.6], mag:3.59, spec:"K3III" },
      { name:"μ And", ra:[0,56,45.1], dec:[38,29,57.3], mag:3.86, spec:"A5V" },
      { name:"υ And", ra:[1,36,47.98], dec:[41,24,23], mag:4.10, spec:"F8V" },
      { name:"κ And", ra:[23,40,24.44], dec:[44,20,2.3], mag:4.15, spec:"B9IVn" },
      { name:"ι And", ra:[23,38,8.18], dec:[43,16,5.1], mag:4.29, spec:"B8V" },
    ],
    connections: [[0,1],[1,2],[2,4],[2,3],[3,5]],
    mainIndices: [0,1,2,3,4,5],
  },
];

var CONSTELLATIONS = {};
for (var i = 0; i < consData.length; i++) {
  CONSTELLATIONS[consData[i].name.toUpperCase()] = new Constellation(consData[i]);
}

// Backward-compatible aliases
var CASSIOPEIA_STARS = CONSTELLATIONS.CASSIOPEIA.stars;
var CASSIOPEIA_CONNECTIONS = CONSTELLATIONS.CASSIOPEIA.connections;
var ORION_STARS = CONSTELLATIONS.ORION.stars;
var ORION_CONNECTIONS = CONSTELLATIONS.ORION.connections;