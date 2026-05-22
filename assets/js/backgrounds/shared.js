// --- Astronomical utilities ---
function raDeg(h, m, s) { return (h + m / 60 + s / 3600) * 15; }
function decDeg(d, m, s) {
  var sign = d < 0 ? -1 : 1;
  return sign * (Math.abs(d) + m / 60 + s / 3600);
}

// --- Spectral type to hex colour ---
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
    { p: 0.0, r: [144, 166, 255] }, { p: 0.5, r: [155, 176, 255] },
    { p: 1.0, r: [156, 178, 255] }, { p: 1.5, r: [170, 191, 255] },
    { p: 2.0, r: [185, 201, 255] }, { p: 2.5, r: [202, 215, 255] },
    { p: 3.0, r: [224, 229, 255] }, { p: 3.5, r: [248, 247, 255] },
    { p: 4.0, r: [255, 248, 252] }, { p: 4.5, r: [255, 244, 234] },
    { p: 5.0, r: [255, 238, 221] }, { p: 5.5, r: [255, 210, 161] },
    { p: 6.0, r: [255, 195, 139] }, { p: 6.5, r: [255, 204, 111] },
    { p: 7.0, r: [255, 198, 108] }, { p: 7.5, r: [255, 198, 108] },
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

function rgbToHex(rgb) { return "#" + ("0" + rgb[0].toString(16)).slice(-2) + ("0" + rgb[1].toString(16)).slice(-2) + ("0" + rgb[2].toString(16)).slice(-2); }

function hexToRgba(hex, alpha) {
  var r = parseInt(hex.slice(1,3), 16);
  var g = parseInt(hex.slice(3,5), 16);
  var b = parseInt(hex.slice(5,7), 16);
  return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
}

function starSize(mag) { return Math.pow(2.512, (5 - mag) / 5) * 1.2; }

// --- Star class (colour always from spectral type) ---
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
    pts.push({ x: cx - sc * (s.ra - rC) * cosFac, y: cy - sc * (s.dec - dC), size: s.getSize(), colour: s.getColour(), name: s.name, mag: s.mag });
  }
  return pts;
};

function getDateKey() {
  var d = new Date();
  return ("0" + d.getDate()).slice(-2) + "/" + ("0" + (d.getMonth() + 1)).slice(-2);
}

// --- All constellations (Wikipedia-verified, mag <= 5.5) ---
var consData = [
{ /* ORION */
    name: "Orion", always: true,
    stars: [
      { name:"Tabit", ra:[4.0, 49.0, 50.14], dec:[6.0, 57.0, 40.5], mag:3.19, spec:"F6V" },
      { name:"\u03c02 Ori", ra:[4.0, 50.0, 36.72], dec:[8.0, 54.0, 0.9], mag:4.35, spec:"A1V" },
      { name:"\u03c04 Ori", ra:[4.0, 51.0, 12.37], dec:[5.0, 36.0, 18.4], mag:3.68, spec:"B2III" },
      { name:"\u03c05 Ori", ra:[4.0, 54.0, 15.1], dec:[2.0, 26.0, 26.4], mag:3.71, spec:"B2III" },
      { name:"\u03c06 Ori", ra:[4.0, 58.0, 32.9], dec:[1.0, 42.0, 50.5], mag:4.47, spec:"K2II" },
      { name:"Rigel", ra:[5.0, 14.0, 32.27], dec:[-8.0, 12.0, 5.9], mag:0.18, spec:"B8Ia" },
      { name:"Bellatrix", ra:[5.0, 25.0, 7.87], dec:[6.0, 20.0, 59.0], mag:1.64, spec:"B2III" },
      { name:"Mintaka AB", ra:[5.0, 32.0, 0.4], dec:[-0.0, 17.0, 56.7], mag:2.20, spec:"B0III" },
      { name:"Meissa A", ra:[5.0, 35.0, 8.28], dec:[9.0, 56.0, 3.0], mag:3.47, spec:"O8III" },
      { name:"Alnilam", ra:[5.0, 36.0, 12.81], dec:[-1.0, 12.0, 6.9], mag:1.69, spec:"B0Ia" },
      { name:"Alnitak A", ra:[5.0, 40.0, 45.52], dec:[-1.0, 56.0, 33.3], mag:1.88, spec:"O9.7Ib" },
      { name:"Saiph", ra:[5.0, 47.0, 45.39], dec:[-9.0, 40.0, 10.6], mag:2.07, spec:"B0.5Ia" },
      { name:"\u03c71 Ori", ra:[5.0, 54.0, 23.08], dec:[20.0, 16.0, 35.1], mag:4.39, spec:"G0V" },
      { name:"Betelgeuse", ra:[5.0, 55.0, 10.29], dec:[7.0, 24.0, 25.3], mag:0.42, spec:"M2Ib" },
      { name:"\u03bc Ori", ra:[6.0, 2.0, 22.99], dec:[9.0, 38.0, 50.5], mag:4.12, spec:null },
      { name:"\u03bd Ori", ra:[6.0, 7.0, 34.32], dec:[14.0, 46.0, 6.7], mag:4.42, spec:"B3IV" },
      { name:"\u03be Ori", ra:[6.0, 11.0, 56.4], dec:[14.0, 12.0, 31.7], mag:4.45, spec:"B3IV" },
      { name:"\u03c72 Ori", ra:[6.0, 3.0, 55.18], dec:[20.0, 8.0, 18.5], mag:4.64, spec:"B2Ia" },
      { name:"\u03c01 Ori", ra:[4.0, 54.0, 53.7], dec:[10.0, 9.0, 4.1], mag:4.64, spec:"A0V" },
      { name:"69 Ori", ra:[6.0, 12.0, 3.28], dec:[16.0, 7.0, 49.6], mag:4.95, spec:"B5V" },
      { name:"5 Ori", ra:[4.0, 53.0, 22.76], dec:[2.0, 30.0, 29.8], mag:5.33, spec:"M1III" },
      { name:"Hatysa", ra:[5.0, 35.0, 25.98], dec:[-5.0, 54.0, 35.6], mag:2.75, spec:"O9III" },
      { name:"Saif al Jabbar", ra:[5.0, 24.0, 28.62], dec:[-2.0, 23.0, 49.7], mag:3.35, spec:"B1V" },
      { name:"\u03c4 Ori", ra:[5.0, 17.0, 36.4], dec:[-6.0, 50.0, 39.8], mag:3.59, spec:"B5III" },
      { name:"component of the \u03c3 Ori system", ra:[5.0, 38.0, 44.77], dec:[-2.0, 36.0, 0.2], mag:3.77, spec:"O9.5V" },
      { name:"\u03bf2 Ori", ra:[4.0, 56.0, 22.32], dec:[13.0, 30.0, 52.5], mag:4.06, spec:"K2III" },
      { name:"\u03c62 Ori", ra:[5.0, 36.0, 54.33], dec:[9.0, 17.0, 29.1], mag:4.09, spec:"G8III" },
      { name:"29 Ori", ra:[5.0, 23.0, 56.84], dec:[-7.0, 48.0, 28.6], mag:4.13, spec:"G8III" },
      { name:"32 Ori", ra:[5.0, 30.0, 47.05], dec:[5.0, 56.0, 53.6], mag:4.20, spec:"B5V" },
      { name:"\u03c61 Ori", ra:[5.0, 34.0, 49.24], dec:[9.0, 29.0, 22.5], mag:4.39, spec:"B0IV" },
      { name:"\u03c1 Ori", ra:[5.0, 13.0, 17.48], dec:[2.0, 51.0, 40.5], mag:4.46, spec:"K3III" },
      { name:"\u03c9 Ori", ra:[5.0, 39.0, 11.15], dec:[4.0, 7.0, 17.3], mag:4.50, spec:"B3III" },
      { name:"HD 40657", ra:[6.0, 0.0, 3.35], dec:[-3.0, 4.0, 26.7], mag:4.53, spec:"K2III" },
      { name:"42 Ori", ra:[5.0, 35.0, 23.16], dec:[-4.0, 50.0, 18.0], mag:4.58, spec:"B2III" },
      { name:"\u03c82 Ori", ra:[5.0, 26.0, 50.23], dec:[3.0, 5.0, 44.4], mag:4.59, spec:"B2IV" },
      { name:"Thabit", ra:[5.0, 31.0, 55.86], dec:[-7.0, 18.0, 5.5], mag:4.62, spec:"B0V" },
      { name:"11 Ori", ra:[5.0, 4.0, 34.14], dec:[15.0, 24.0, 15.1], mag:4.65, spec:"A0" },
      { name:"\u03bf1 Ori", ra:[4.0, 52.0, 31.96], dec:[14.0, 15.0, 2.8], mag:4.71, spec:"M3" },
      { name:"31 Ori", ra:[5.0, 29.0, 43.98], dec:[-1.0, 5.0, 31.8], mag:4.71, spec:"K5III" },
      { name:"22 Ori", ra:[5.0, 21.0, 45.75], dec:[-0.0, 22.0, 56.9], mag:4.72, spec:"B2IV" },
      { name:"56 Ori", ra:[5.0, 52.0, 26.44], dec:[1.0, 51.0, 18.6], mag:4.76, spec:"K2II" },
      { name:"49 Ori", ra:[5.0, 38.0, 53.09], dec:[-7.0, 12.0, 45.8], mag:4.77, spec:"A4V" },
      { name:"HD 36960", ra:[5.0, 35.0, 2.68], dec:[-6.0, 0.0, 7.3], mag:4.78, spec:"B0.5V" },
      { name:"15 Ori", ra:[5.0, 9.0, 41.96], dec:[15.0, 35.0, 50.2], mag:4.81, spec:"F2IV" },
      { name:"\u03c81 Ori", ra:[5.0, 24.0, 44.83], dec:[1.0, 50.0, 47.2], mag:4.89, spec:"B1V" },
      { name:"51 Ori", ra:[5.0, 42.0, 28.66], dec:[1.0, 28.0, 28.8], mag:4.90, spec:"K1III" },
      { name:"HD 44131", ra:[6.0, 19.0, 59.6], dec:[-2.0, 56.0, 40.2], mag:4.91, spec:"M1III" },
      { name:"HD 37756", ra:[5.0, 40.0, 50.72], dec:[-1.0, 7.0, 43.6], mag:4.95, spec:"B2IV" },
      { name:"component of the \u03b8  Ori system", ra:[5.0, 35.0, 22.9], dec:[-5.0, 24.0, 57.8], mag:4.98, spec:"O9.5V" },
      { name:"23 Ori", ra:[5.0, 22.0, 50.0], dec:[3.0, 32.0, 40.0], mag:5.00, spec:"B1V" },
      { name:"74 Ori", ra:[6.0, 16.0, 26.57], dec:[12.0, 16.0, 18.2], mag:5.04, spec:"F5IV" },
      { name:"27 Ori", ra:[5.0, 24.0, 28.91], dec:[-0.0, 53.0, 30.0], mag:5.07, spec:"K0III" },
      { name:"component of the  Trapezium", ra:[5.0, 35.0, 16.47], dec:[-5.0, 23.0, 22.9], mag:5.13, spec:"O6V" },
      { name:"64 Ori", ra:[6.0, 3.0, 27.36], dec:[19.0, 41.0, 26.2], mag:5.14, spec:"B8V" },
      { name:"6 Ori", ra:[4.0, 54.0, 46.91], dec:[11.0, 25.0, 33.5], mag:5.18, spec:"A3V" },
      { name:"HD 33554", ra:[5.0, 11.0, 41.56], dec:[16.0, 2.0, 44.4], mag:5.18, spec:"K5III" },
      { name:"71 Ori", ra:[6.0, 14.0, 50.94], dec:[19.0, 9.0, 24.8], mag:5.20, spec:"F6V" },
      { name:"60 Ori", ra:[5.0, 58.0, 49.58], dec:[0.0, 33.0, 10.7], mag:5.21, spec:"A1V" },
      { name:"45 Ori", ra:[5.0, 35.0, 39.49], dec:[-4.0, 51.0, 21.9], mag:5.24, spec:"F0III" },
      { name:"52 Ori", ra:[5.0, 48.0, 0.23], dec:[6.0, 27.0, 15.2], mag:5.26, spec:"A5V" },
      { name:"38 Ori", ra:[5.0, 34.0, 16.79], dec:[3.0, 46.0, 1.0], mag:5.32, spec:"A2V" },
      { name:"HD 31296", ra:[4.0, 54.0, 47.79], dec:[7.0, 46.0, 45.0], mag:5.33, spec:"K1III" },
      { name:"14 Ori", ra:[5.0, 7.0, 52.87], dec:[8.0, 29.0, 54.9], mag:5.33, spec:null },
      { name:"21 Ori", ra:[5.0, 19.0, 11.23], dec:[2.0, 35.0, 45.4], mag:5.34, spec:"F5II" },
      { name:"HD 36591", ra:[5.0, 32.0, 41.35], dec:[-1.0, 35.0, 30.6], mag:5.34, spec:"B1IV" },
      { name:"72 Ori", ra:[6.0, 15.0, 25.13], dec:[16.0, 8.0, 35.5], mag:5.34, spec:"B7V" },
      { name:"HD 30210", ra:[4.0, 46.0, 1.7], dec:[11.0, 42.0, 20.2], mag:5.35, spec:null },
      { name:"VV Ori", ra:[5.0, 33.0, 31.45], dec:[-1.0, 9.0, 21.9], mag:5.36, spec:"B1V" },
      { name:"55 Ori", ra:[5.0, 51.0, 21.98], dec:[-7.0, 31.0, 4.8], mag:5.36, spec:"B2IV" },
      { name:"HD 30034", ra:[4.0, 44.0, 25.77], dec:[11.0, 8.0, 46.2], mag:5.39, spec:"F0V" },
      { name:"75 Ori", ra:[6.0, 17.0, 6.62], dec:[9.0, 56.0, 33.1], mag:5.39, spec:"A2V" },
      { name:"U Ori", ra:[5.0, 55.0, 49.3], dec:[20.0, 10.0, 30.0], mag:5.40, spec:"M8III" },
      { name:"16 Ori", ra:[5.0, 9.0, 19.6], dec:[9.0, 49.0, 46.6], mag:5.43, spec:"A2" },
      { name:"73 Ori", ra:[6.0, 15.0, 44.97], dec:[12.0, 33.0, 3.9], mag:5.44, spec:"B9II" },
      { name:"33 Ori", ra:[5.0, 31.0, 14.53], dec:[3.0, 17.0, 31.7], mag:5.46, spec:"B1.5V" },
      { name:"HD 34043", ra:[5.0, 14.0, 44.05], dec:[5.0, 9.0, 22.1], mag:5.50, spec:"K4III" },
    ],
    connections: [[9, 7], [6, 0], [0, 1], [10, 9], [2, 3], [15, 14], [6, 8], [13, 10], [10, 11], [8, 13], [11, 5], [3, 4], [7, 6], [14, 13], [5, 7], [0, 2], [16, 14], [16, 15], [15, 12]],
    mainIndices: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
  },

{ /* CASSIOPEIA */
    name: "Cassiopeia", always: true,
    stars: [
      { name:"Caph", ra:[0.0, 9.0, 10.09], dec:[59.0, 9.0, 0.8], mag:2.28, spec:"F2III" },
      { name:"Schedar", ra:[0.0, 40.0, 30.39], dec:[56.0, 32.0, 14.7], mag:2.24, spec:"K0II" },
      { name:"Tiansi", ra:[0.0, 56.0, 42.5], dec:[60.0, 43.0, 0.3], mag:2.47, spec:"B0IV" },
      { name:"Ruchbah", ra:[1.0, 25.0, 48.6], dec:[60.0, 14.0, 7.5], mag:2.68, spec:"A5V" },
      { name:"Segin", ra:[1.0, 54.0, 23.68], dec:[63.0, 40.0, 12.5], mag:3.35, spec:"B2" },
      { name:"Achird", ra:[0.0, 49.0, 5.1], dec:[57.0, 48.0, 59.6], mag:3.46, spec:"G0V" },
      { name:"F\u00f9l\u00f9 (\u9644\u8def)", ra:[0.0, 36.0, 58.27], dec:[53.0, 53.0, 49.0], mag:3.69, spec:"B2IV" },
      { name:"50 Cas", ra:[2.0, 3.0, 26.19], dec:[72.0, 25.0, 16.5], mag:3.95, spec:"A2V" },
      { name:"Cexing", ra:[0.0, 32.0, 59.99], dec:[62.0, 55.0, 54.4], mag:4.17, spec:"B1Ia" },
      { name:"Marfak", ra:[1.0, 11.0, 5.93], dec:[55.0, 8.0, 59.8], mag:4.34, spec:"A7V" },
      { name:"Huagai", ra:[2.0, 29.0, 3.99], dec:[67.0, 24.0, 8.6], mag:4.46, spec:"A5" },
      { name:"\u03bf Cas", ra:[0.0, 44.0, 43.5], dec:[48.0, 17.0, 3.8], mag:4.48, spec:"B5III" },
      { name:"48 Cas", ra:[2.0, 1.0, 57.55], dec:[70.0, 54.0, 25.4], mag:4.49, spec:"A3IV" },
      { name:"yellow hypergiant", ra:[23.0, 54.0, 23.04], dec:[57.0, 29.0, 57.8], mag:4.51, spec:"F8Ia" },
      { name:"Castula", ra:[0.0, 56.0, 40.01], dec:[59.0, 10.0, 52.2], mag:4.62, spec:"G8III" },
      { name:"\u03c7 Cas", ra:[1.0, 33.0, 55.93], dec:[59.0, 13.0, 55.5], mag:4.68, spec:"K0III" },
      { name:"\u03c8 Cas", ra:[1.0, 25.0, 55.9], dec:[68.0, 7.0, 47.8], mag:4.72, spec:"K0III" },
      { name:"\u03bb Cas", ra:[0.0, 31.0, 46.32], dec:[54.0, 31.0, 20.4], mag:4.74, spec:"B8V" },
      { name:"\u03be Cas", ra:[0.0, 42.0, 3.88], dec:[50.0, 30.0, 45.1], mag:4.80, spec:"B2.5V" },
      { name:"HR 244", ra:[0.0, 53.0, 4.28], dec:[61.0, 7.0, 24.8], mag:4.80, spec:"F8V" },
      { name:"R Cas", ra:[23.0, 58.0, 24.8], dec:[51.0, 23.0, 19.0], mag:4.80, spec:"M6.5" },
      { name:"\u03c51 Cas", ra:[0.0, 55.0, 0.19], dec:[58.0, 58.0, 22.1], mag:4.83, spec:"K2III" },
      { name:"1 Cas", ra:[23.0, 6.0, 36.81], dec:[59.0, 25.0, 11.2], mag:4.84, spec:"B0.5IV" },
      { name:"HD 19275", ra:[3.0, 11.0, 56.24], dec:[74.0, 23.0, 37.9], mag:4.85, spec:"A2V" },
      { name:"\u03c4 Cas", ra:[23.0, 47.0, 3.39], dec:[58.0, 39.0, 6.7], mag:4.88, spec:"K1III" },
      { name:"\u03c3 Cas", ra:[23.0, 59.0, 0.53], dec:[55.0, 45.0, 17.8], mag:4.88, spec:"B1V" },
      { name:"AR Cas", ra:[23.0, 30.0, 1.92], dec:[58.0, 32.0, 56.1], mag:4.89, spec:"B3IV" },
      { name:"\u03bd Cas", ra:[0.0, 48.0, 49.99], dec:[50.0, 58.0, 5.5], mag:4.90, spec:"B9III" },
      { name:"\u03c0 Cas", ra:[0.0, 43.0, 28.09], dec:[47.0, 1.0, 28.7], mag:4.95, spec:"A5V" },
      { name:"\u03c6 Cas", ra:[1.0, 20.0, 4.92], dec:[58.0, 13.0, 53.8], mag:4.95, spec:"F0Ia" },
      { name:"4 Cas", ra:[23.0, 24.0, 50.25], dec:[62.0, 16.0, 58.2], mag:4.96, spec:"M1III" },
      { name:"\u03c9 Cas", ra:[1.0, 56.0, 0.0], dec:[68.0, 41.0, 7.0], mag:4.97, spec:"B8III" },
      { name:"HD 3240", ra:[0.0, 36.0, 8.29], dec:[54.0, 10.0, 6.4], mag:5.08, spec:"B7III" },
      { name:"V509 Cas", ra:[23.0, 0.0, 5.1], dec:[56.0, 56.0, 43.4], mag:5.10, spec:"F80" },
      { name:"Marfak", ra:[1.0, 8.0, 12.92], dec:[54.0, 55.0, 27.2], mag:5.17, spec:"G5VI" },
      { name:"HD 15920", ra:[2.0, 38.0, 2.09], dec:[72.0, 49.0, 5.6], mag:5.17, spec:"G8III" },
      { name:"42 Cas", ra:[1.0, 42.0, 55.73], dec:[70.0, 37.0, 21.2], mag:5.18, spec:"B9V" },
      { name:"49 Cas", ra:[2.0, 5.0, 31.58], dec:[76.0, 6.0, 54.4], mag:5.22, spec:"G8III" },
      { name:"47 Cas", ra:[2.0, 5.0, 7.05], dec:[77.0, 16.0, 53.2], mag:5.27, spec:"F0V" },
      { name:"40 Cas", ra:[1.0, 38.0, 30.94], dec:[73.0, 2.0, 24.3], mag:5.28, spec:"G8II" },
      { name:"HD 11946", ra:[1.0, 59.0, 37.99], dec:[64.0, 37.0, 17.9], mag:5.29, spec:"A0V" },
      { name:"31 Cas", ra:[1.0, 10.0, 39.27], dec:[68.0, 46.0, 43.3], mag:5.32, spec:"A0V" },
      { name:"HD 4775", ra:[0.0, 50.0, 43.57], dec:[64.0, 14.0, 51.3], mag:5.35, spec:"A4V" },
      { name:"12 Cas", ra:[0.0, 24.0, 47.49], dec:[61.0, 49.0, 51.8], mag:5.38, spec:"B9III" },
      { name:"HD 4222", ra:[0.0, 45.0, 17.2], dec:[55.0, 13.0, 17.1], mag:5.41, spec:"A2V" },
      { name:"23 Cas", ra:[0.0, 47.0, 46.02], dec:[74.0, 50.0, 51.3], mag:5.42, spec:"B8III" },
      { name:"6 Cas", ra:[23.0, 48.0, 50.17], dec:[62.0, 12.0, 52.3], mag:5.43, spec:"A3Ia" },
      { name:"HD 3474", ra:[0.0, 39.0, 9.89], dec:[49.0, 21.0, 16.5], mag:5.45, spec:"K5III" },
    ],
    connections: [[1, 0], [3, 2], [4, 3], [2, 1]],
    mainIndices: [0, 1, 2, 3, 4],
  },
{ /* LYRA */
    name: "Lyra", date: "27/07",
    stars: [
      { name:"Vega", ra:[18.0, 36.0, 56.19], dec:[38.0, 46.0, 58.8], mag:0.03, spec:"A0V" },
      { name:"\u03b61 Lyr", ra:[18.0, 44.0, 46.34], dec:[37.0, 36.0, 18.2], mag:4.34, spec:null },
      { name:"Sheliak", ra:[18.0, 50.0, 4.79], dec:[33.0, 21.0, 45.6], mag:3.52, spec:"A8" },
      { name:"\u03b42 Lyr", ra:[18.0, 54.0, 30.29], dec:[36.0, 53.0, 55.0], mag:4.22, spec:"M4II" },
      { name:"Sulafat", ra:[18.0, 58.0, 56.62], dec:[32.0, 41.0, 22.4], mag:3.25, spec:"B9III" },
      { name:"R Lyr", ra:[18.0, 55.0, 20.09], dec:[43.0, 56.0, 45.2], mag:4.08, spec:"M5III" },
      { name:"\u03ba Lyr", ra:[18.0, 19.0, 51.72], dec:[36.0, 3.0, 52.0], mag:4.33, spec:"K2III" },
      { name:"\u03b8 Lyr", ra:[19.0, 16.0, 22.1], dec:[38.0, 8.0, 1.4], mag:4.35, spec:"K0II" },
      { name:"Aladfar", ra:[19.0, 13.0, 45.49], dec:[39.0, 8.0, 45.5], mag:4.43, spec:"B2.5IV" },
      { name:"component of the \u03b5 Lyr system", ra:[18.0, 44.0, 22.78], dec:[39.0, 36.0, 45.3], mag:4.60, spec:"A8V" },
      { name:"component of the \u03b5 Lyr system", ra:[18.0, 44.0, 20.34], dec:[39.0, 40.0, 11.9], mag:4.67, spec:"F1V" },
      { name:"HD 173780", ra:[18.0, 46.0, 4.47], dec:[26.0, 39.0, 43.5], mag:4.83, spec:"K3III" },
      { name:"\u03bb Lyr", ra:[19.0, 0.0, 0.82], dec:[32.0, 8.0, 43.8], mag:4.94, spec:"K3III" },
      { name:"16 Lyr", ra:[19.0, 1.0, 26.36], dec:[46.0, 56.0, 6.1], mag:5.00, spec:"A7V" },
      { name:"Alathfar", ra:[18.0, 24.0, 13.8], dec:[39.0, 30.0, 26.1], mag:5.11, spec:"A3IV" },
      { name:"HD 176051", ra:[18.0, 57.0, 1.47], dec:[32.0, 54.0, 5.8], mag:5.20, spec:"G0V" },
      { name:"17 Lyr", ra:[19.0, 7.0, 25.5], dec:[32.0, 30.0, 6.0], mag:5.20, spec:"F0V" },
      { name:"\u03bd Lyr", ra:[18.0, 49.0, 52.92], dec:[32.0, 33.0, 3.9], mag:5.22, spec:"A3V" },
      { name:"\u03b9 Lyr", ra:[19.0, 7.0, 18.13], dec:[36.0, 6.0, 0.6], mag:5.25, spec:"B6IV" },
      { name:"HD 176527", ra:[18.0, 59.0, 45.43], dec:[26.0, 13.0, 49.6], mag:5.26, spec:"K2III" },
      { name:"HD 172044", ra:[18.0, 36.0, 37.35], dec:[33.0, 28.0, 8.5], mag:5.41, spec:"B8II" },
      { name:"HD 175740", ra:[18.0, 54.0, 52.18], dec:[41.0, 36.0, 9.8], mag:5.46, spec:"G8III" },
      { name:"HD 171301", ra:[18.0, 32.0, 49.95], dec:[30.0, 33.0, 15.1], mag:5.47, spec:"B8IV" },
    ],
    connections: [[0, 1], [2, 4], [1, 2], [3, 1], [4, 3]],
    mainIndices: [0, 1, 2, 3, 4],
  },

{ /* CYGNUS */
    name: "Cygnus", date: "12/08",
    stars: [
      { name:"\u03ba Cyg", ra:[19.0, 17.0, 6.11], dec:[53.0, 22.0, 5.4], mag:3.80, spec:"K0III" },
      { name:"\u03b9 Cyg", ra:[19.0, 29.0, 42.34], dec:[51.0, 43.0, 46.1], mag:3.76, spec:"A5V" },
      { name:"Albireo A", ra:[19.0, 30.0, 43.29], dec:[27.0, 57.0, 34.9], mag:3.05, spec:"K3II" },
      { name:"Fawaris", ra:[19.0, 44.0, 58.44], dec:[45.0, 7.0, 50.5], mag:2.86, spec:"B9.5III" },
      { name:"\u03b7 Cyg", ra:[19.0, 56.0, 18.4], dec:[35.0, 5.0, 0.6], mag:3.89, spec:"K0III" },
      { name:"Sadr", ra:[20.0, 22.0, 13.7], dec:[40.0, 15.0, 24.1], mag:2.23, spec:"F8Ib" },
      { name:"Deneb", ra:[20.0, 41.0, 25.91], dec:[45.0, 16.0, 49.2], mag:1.25, spec:"A2Ia" },
      { name:"Aljanah", ra:[20.0, 46.0, 12.43], dec:[33.0, 58.0, 10.0], mag:2.48, spec:"K0III" },
      { name:"\u03b6 Cyg", ra:[21.0, 12.0, 56.18], dec:[30.0, 13.0, 37.5], mag:3.21, spec:"G8II" },
      { name:"\u03bc1 Cyg", ra:[21.0, 44.0, 8.59], dec:[28.0, 44.0, 33.4], mag:4.69, spec:"F6V" },
      { name:"\u03be Cyg", ra:[21.0, 4.0, 55.86], dec:[43.0, 55.0, 40.3], mag:3.72, spec:"K5Ib" },
      { name:"\u03c4 Cyg", ra:[21.0, 14.0, 47.35], dec:[38.0, 2.0, 39.6], mag:3.74, spec:"F1IV" },
      { name:"\u03bf1 Cyg", ra:[20.0, 13.0, 37.9], dec:[46.0, 44.0, 28.8], mag:3.80, spec:"K2II" },
      { name:"\u03bd Cyg", ra:[20.0, 57.0, 10.41], dec:[41.0, 10.0, 1.9], mag:3.94, spec:"A1V" },
      { name:"\u03bf2 Cyg", ra:[20.0, 15.0, 28.32], dec:[47.0, 42.0, 51.1], mag:3.96, spec:"K3Ib" },
      { name:"\u03c1 Cyg", ra:[21.0, 33.0, 58.87], dec:[45.0, 35.0, 31.4], mag:3.98, spec:"G8III" },
      { name:"41 Cyg", ra:[20.0, 29.0, 23.73], dec:[30.0, 22.0, 6.8], mag:4.01, spec:"F5II" },
      { name:"52 Cyg", ra:[20.0, 45.0, 39.76], dec:[30.0, 43.0, 10.8], mag:4.22, spec:"K0III" },
      { name:"\u03c3 Cyg", ra:[21.0, 17.0, 24.95], dec:[39.0, 23.0, 40.9], mag:4.22, spec:"B9Ia" },
      { name:"Pennae Caudalis", ra:[21.0, 46.0, 47.61], dec:[49.0, 18.0, 34.5], mag:4.23, spec:"B3III" },
      { name:"33 Cyg", ra:[20.0, 13.0, 23.8], dec:[56.0, 34.0, 3.1], mag:4.28, spec:"A3IV" },
      { name:"\u03c5 Cyg", ra:[21.0, 17.0, 55.07], dec:[34.0, 53.0, 48.8], mag:4.41, spec:"B2V" },
      { name:"39 Cyg", ra:[20.0, 23.0, 51.6], dec:[32.0, 11.0, 24.7], mag:4.43, spec:"K3III" },
      { name:"\u03b8 Cyg", ra:[19.0, 36.0, 26.54], dec:[50.0, 13.0, 13.7], mag:4.49, spec:"F4V" },
      { name:"\u03bb Cyg", ra:[20.0, 47.0, 24.53], dec:[36.0, 29.0, 26.7], mag:4.53, spec:"B6IV" },
      { name:"63 Cyg", ra:[21.0, 6.0, 36.09], dec:[47.0, 38.0, 54.3], mag:4.56, spec:"K4II" },
      { name:"47 Cyg A", ra:[20.0, 33.0, 54.19], dec:[35.0, 15.0, 3.1], mag:4.61, spec:"K2Ib" },
      { name:"\u03c6 Cyg", ra:[19.0, 39.0, 22.6], dec:[30.0, 9.0, 11.6], mag:4.68, spec:"G8III" },
      { name:"Azelfafage", ra:[21.0, 42.0, 5.66], dec:[51.0, 11.0, 22.7], mag:4.69, spec:"B3IV" },
      { name:"8 Cyg", ra:[19.0, 31.0, 46.32], dec:[34.0, 27.0, 10.7], mag:4.74, spec:"B3IV" },
      { name:"59 Cyg", ra:[20.0, 59.0, 49.55], dec:[47.0, 31.0, 15.4], mag:4.74, spec:"B1" },
      { name:"P Cyg", ra:[20.0, 17.0, 47.2], dec:[38.0, 1.0, 58.6], mag:4.77, spec:"B2" },
      { name:"30 Cyg", ra:[20.0, 13.0, 18.04], dec:[46.0, 48.0, 56.4], mag:4.80, spec:"A5III" },
      { name:"57 Cyg", ra:[20.0, 53.0, 14.75], dec:[44.0, 23.0, 14.2], mag:4.80, spec:"B5V" },
      { name:"55 Cyg", ra:[20.0, 48.0, 56.29], dec:[46.0, 6.0, 50.9], mag:4.81, spec:"B3Ia" },
      { name:"72 Cyg", ra:[21.0, 34.0, 46.48], dec:[38.0, 32.0, 1.8], mag:4.87, spec:"K1III" },
      { name:"15 Cyg", ra:[19.0, 44.0, 16.55], dec:[37.0, 21.0, 15.4], mag:4.89, spec:"G8III" },
      { name:"\u03c8 Cyg", ra:[19.0, 55.0, 37.82], dec:[52.0, 26.0, 20.5], mag:4.91, spec:"A4V" },
      { name:"28 Cyg", ra:[20.0, 9.0, 25.62], dec:[36.0, 50.0, 22.5], mag:4.93, spec:"B2.5V" },
      { name:"29 Cyg", ra:[20.0, 14.0, 31.98], dec:[36.0, 48.0, 22.1], mag:4.93, spec:"A2V" },
      { name:"T Cyg", ra:[20.0, 47.0, 10.72], dec:[34.0, 22.0, 26.8], mag:4.93, spec:"K3III" },
      { name:"\u03c91 Cyg", ra:[20.0, 30.0, 3.53], dec:[48.0, 57.0, 5.6], mag:4.94, spec:"B2.5IV" },
      { name:"22 Cyg", ra:[19.0, 55.0, 51.76], dec:[38.0, 29.0, 12.1], mag:4.95, spec:"B5IV" },
      { name:"HD 189276", ra:[19.0, 55.0, 55.39], dec:[58.0, 50.0, 45.7], mag:4.98, spec:"K5II" },
      { name:"2 Cyg", ra:[19.0, 24.0, 7.57], dec:[29.0, 37.0, 16.7], mag:4.99, spec:"B3IV" },
      { name:"17 Cyg", ra:[19.0, 46.0, 25.58], dec:[33.0, 43.0, 43.3], mag:5.00, spec:"F5" },
      { name:"20 Cyg", ra:[19.0, 50.0, 37.73], dec:[52.0, 59.0, 17.4], mag:5.03, spec:"K3III" },
      { name:"68 Cyg", ra:[21.0, 18.0, 27.18], dec:[43.0, 56.0, 45.5], mag:5.04, spec:"O8" },
      { name:"74 Cyg", ra:[21.0, 36.0, 56.98], dec:[40.0, 24.0, 48.6], mag:5.04, spec:"A5V" },
      { name:"96825", ra:[19.0, 40.0, 50.11], dec:[45.0, 31.0, 28.7], mag:5.06, spec:"F5II" },
      { name:"26 Cyg", ra:[20.0, 1.0, 21.55], dec:[50.0, 6.0, 16.8], mag:5.06, spec:"K1II" },
      { name:"56 Cyg", ra:[20.0, 50.0, 4.83], dec:[44.0, 3.0, 32.3], mag:5.06, spec:"A4" },
      { name:"75 Cyg", ra:[21.0, 40.0, 11.06], dec:[43.0, 16.0, 25.7], mag:5.09, spec:"M1III" },
      { name:"Albireo B", ra:[19.0, 30.0, 45.4], dec:[27.0, 57.0, 55.0], mag:5.12, spec:"B8V" },
      { name:"23 Cyg", ra:[19.0, 53.0, 17.37], dec:[57.0, 31.0, 24.5], mag:5.14, spec:"B5V" },
      { name:"35 Cyg", ra:[20.0, 18.0, 39.07], dec:[34.0, 58.0, 58.0], mag:5.14, spec:"F5Ib" },
      { name:"25 Cyg", ra:[19.0, 59.0, 55.2], dec:[37.0, 2.0, 34.4], mag:5.15, spec:"B3IV" },
      { name:"4 Cyg", ra:[19.0, 26.0, 9.12], dec:[36.0, 19.0, 4.3], mag:5.17, spec:"B9" },
      { name:"96459", ra:[19.0, 36.0, 38.05], dec:[44.0, 41.0, 42.7], mag:5.17, spec:"K0III" },
      { name:"19 Cyg", ra:[19.0, 50.0, 33.99], dec:[38.0, 43.0, 19.8], mag:5.18, spec:"M2IIIa" },
      { name:"61 Cyg A", ra:[21.0, 6.0, 50.84], dec:[38.0, 44.0, 29.4], mag:5.20, spec:"K5V" },
      { name:"71 Cyg", ra:[21.0, 29.0, 26.91], dec:[46.0, 32.0, 25.2], mag:5.22, spec:"K0III" },
      { name:"99968", ra:[20.0, 16.0, 55.28], dec:[40.0, 21.0, 54.3], mag:5.27, spec:"K5II" },
      { name:"105898", ra:[21.0, 26.0, 51.57], dec:[48.0, 50.0, 6.4], mag:5.29, spec:"A6" },
      { name:"70 Cyg", ra:[21.0, 27.0, 21.36], dec:[37.0, 7.0, 0.5], mag:5.30, spec:"B3V" },
      { name:"96288", ra:[19.0, 34.0, 41.26], dec:[42.0, 24.0, 45.3], mag:5.34, spec:"A2V" },
      { name:"27 Cyg", ra:[20.0, 6.0, 21.93], dec:[35.0, 58.0, 24.7], mag:5.38, spec:"K0IV" },
      { name:"60 Cyg", ra:[21.0, 1.0, 10.92], dec:[46.0, 9.0, 20.8], mag:5.38, spec:"B1V" },
      { name:"9 Cyg", ra:[19.0, 34.0, 50.92], dec:[29.0, 27.0, 46.5], mag:5.39, spec:"A0V" },
      { name:"14 Cyg", ra:[19.0, 39.0, 26.47], dec:[42.0, 49.0, 5.6], mag:5.41, spec:"B9III" },
      { name:"51 Cyg", ra:[20.0, 42.0, 12.63], dec:[50.0, 20.0, 24.1], mag:5.41, spec:"B2V" },
      { name:"98194", ra:[19.0, 57.0, 13.86], dec:[40.0, 22.0, 4.2], mag:5.46, spec:"B5V" },
      { name:"103145", ra:[20.0, 53.0, 53.91], dec:[33.0, 26.0, 16.1], mag:5.47, spec:"K5III" },
      { name:"103094", ra:[20.0, 53.0, 18.56], dec:[45.0, 10.0, 54.1], mag:5.48, spec:"K0II" },
    ],
    connections: [[4, 2], [5, 7], [1, 3], [0, 1], [5, 4], [3, 5], [5, 6], [7, 8]],
    mainIndices: [0, 1, 2, 3, 4, 5, 6, 7, 8],
  },
{ /* GEMINI */
    name: "Gemini", date: "04/09",
    stars: [
      { name:"1 Gem", ra:[6.0, 4.0, 7.22], dec:[23.0, 15.0, 49.1], mag:4.16, spec:"G7III" },
      { name:"Propus", ra:[6.0, 14.0, 52.7], dec:[22.0, 30.0, 24.6], mag:3.31, spec:"M3III" },
      { name:"Tejat Posterior", ra:[6.0, 22.0, 57.59], dec:[22.0, 30.0, 49.9], mag:2.87, spec:"M3.0III" },
      { name:"Nucatai", ra:[6.0, 28.0, 57.79], dec:[20.0, 12.0, 43.8], mag:4.13, spec:"B6III" },
      { name:"Alhena", ra:[6.0, 37.0, 42.7], dec:[16.0, 23.0, 57.9], mag:1.93, spec:"A0IV" },
      { name:"Mebsuta", ra:[6.0, 43.0, 55.93], dec:[25.0, 7.0, 52.2], mag:3.06, spec:"G8Ib" },
      { name:"Alzir", ra:[6.0, 45.0, 17.43], dec:[12.0, 53.0, 45.8], mag:3.35, spec:"F5IV" },
      { name:"\u03b8 Gem", ra:[6.0, 52.0, 47.34], dec:[33.0, 57.0, 40.9], mag:3.60, spec:"A3III" },
      { name:"Mekbuda", ra:[7.0, 4.0, 6.54], dec:[20.0, 34.0, 13.1], mag:4.01, spec:"G1Ib" },
      { name:"\u03c4 Gem", ra:[7.0, 11.0, 8.39], dec:[30.0, 14.0, 43.0], mag:4.41, spec:"K2III" },
      { name:"\u03bb Gem", ra:[7.0, 18.0, 5.61], dec:[16.0, 32.0, 25.7], mag:3.58, spec:"A3V" },
      { name:"Wasat", ra:[7.0, 20.0, 7.39], dec:[21.0, 58.0, 56.4], mag:3.50, spec:"F0IV" },
      { name:"Propus", ra:[7.0, 25.0, 43.68], dec:[27.0, 47.0, 53.8], mag:3.78, spec:"G9III" },
      { name:"Castor A", ra:[7.0, 34.0, 36.0], dec:[31.0, 53.0, 19.1], mag:1.90, spec:"A2V" },
      { name:"\u03c5 Gem", ra:[7.0, 35.0, 55.37], dec:[26.0, 53.0, 45.6], mag:4.06, spec:"K5III" },
      { name:"J\u012bx\u012bn (\u7a4d\u85aa)", ra:[7.0, 44.0, 26.87], dec:[24.0, 23.0, 53.3], mag:3.57, spec:"G8III" },
      { name:"Pollux", ra:[7.0, 45.0, 19.36], dec:[28.0, 1.0, 34.7], mag:1.16, spec:"K0III" },
      { name:"\u03c1 Gem", ra:[7.0, 29.0, 6.61], dec:[31.0, 47.0, 2.7], mag:4.16, spec:"F0V" },
      { name:"\u03c3 Gem", ra:[7.0, 43.0, 18.69], dec:[28.0, 53.0, 2.7], mag:4.23, spec:"K1III" },
      { name:"30 Gem", ra:[6.0, 43.0, 59.29], dec:[13.0, 13.0, 41.3], mag:4.49, spec:"K1III" },
      { name:"38 Gem", ra:[6.0, 54.0, 38.59], dec:[13.0, 10.0, 40.9], mag:4.71, spec:"F0V" },
      { name:"Jishui", ra:[7.0, 39.0, 9.96], dec:[34.0, 35.0, 4.7], mag:4.89, spec:"F3III" },
      { name:"81 Gem", ra:[7.0, 46.0, 7.49], dec:[18.0, 30.0, 36.6], mag:4.89, spec:"K5III" },
      { name:"6 Cancri", ra:[8.0, 3.0, 31.1], dec:[27.0, 47.0, 39.9], mag:4.94, spec:"K2III" },
      { name:"\u03c6 Gem", ra:[7.0, 53.0, 29.84], dec:[26.0, 45.0, 57.1], mag:4.97, spec:"A3V" },
      { name:"65 Gem", ra:[7.0, 29.0, 48.78], dec:[27.0, 54.0, 58.3], mag:5.01, spec:"K2III" },
      { name:"57 Gem", ra:[7.0, 23.0, 28.55], dec:[25.0, 3.0, 2.2], mag:5.04, spec:"G8III" },
      { name:"74 Gem", ra:[7.0, 39.0, 28.59], dec:[17.0, 40.0, 28.3], mag:5.04, spec:"M0III" },
      { name:"51 Gem", ra:[7.0, 13.0, 22.27], dec:[16.0, 9.0, 32.6], mag:5.07, spec:"K3V" },
      { name:"64 Gem", ra:[7.0, 29.0, 20.46], dec:[28.0, 7.0, 6.3], mag:5.07, spec:"A4V" },
      { name:"56 Gem", ra:[7.0, 21.0, 56.9], dec:[20.0, 26.0, 37.4], mag:5.09, spec:"M0III" },
      { name:"HD 52960", ra:[7.0, 3.0, 38.07], dec:[10.0, 57.0, 6.6], mag:5.14, spec:"K3III" },
      { name:"\u03c0 Gem", ra:[7.0, 47.0, 30.34], dec:[33.0, 24.0, 56.8], mag:5.14, spec:"M0III" },
      { name:"26 Gem", ra:[6.0, 42.0, 24.32], dec:[17.0, 38.0, 43.9], mag:5.20, spec:"A2V" },
      { name:"\u03c9 Gem", ra:[7.0, 2.0, 24.78], dec:[24.0, 12.0, 55.6], mag:5.20, spec:"G5II" },
      { name:"63 Gem", ra:[7.0, 27.0, 44.39], dec:[21.0, 26.0, 44.0], mag:5.20, spec:"F5IV" },
      { name:"68 Gem", ra:[7.0, 33.0, 36.5], dec:[15.0, 49.0, 36.1], mag:5.27, spec:"A1V" },
      { name:"36 Gem", ra:[6.0, 51.0, 33.05], dec:[21.0, 45.0, 40.4], mag:5.28, spec:"A2V" },
      { name:"76 Gem", ra:[7.0, 44.0, 6.92], dec:[25.0, 47.0, 3.2], mag:5.30, spec:"K5III" },
      { name:"HD 60318", ra:[7.0, 35.0, 8.82], dec:[30.0, 57.0, 39.3], mag:5.34, spec:"K0III" },
      { name:"85 Gem", ra:[7.0, 55.0, 39.9], dec:[19.0, 53.0, 2.6], mag:5.38, spec:"A0V" },
      { name:"28 Gem", ra:[6.0, 44.0, 45.46], dec:[28.0, 58.0, 15.6], mag:5.42, spec:"K4III" },
      { name:"HD 59686", ra:[7.0, 31.0, 48.37], dec:[17.0, 5.0, 10.4], mag:5.45, spec:"K2III" },
      { name:"45 Gem", ra:[7.0, 8.0, 22.04], dec:[15.0, 55.0, 51.3], mag:5.47, spec:"G8III" },
    ],
    connections: [[8, 11], [9, 5], [11, 10], [12, 9], [4, 8], [2, 12], [14, 12], [14, 15], [5, 3], [10, 6], [14, 16], [5, 2], [11, 14], [12, 0], [9, 13], [9, 7]],
    mainIndices: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
  },
{ /* SCORPIUS */
    name: "Scorpius", date: "26/10",
    stars: [
      { name:"Fang", ra:[15.0, 58.0, 51.12], dec:[-26.0, 6.0, 50.6], mag:2.89, spec:"B1V" },
      { name:"Dschubba", ra:[16.0, 0.0, 20.01], dec:[-22.0, 37.0, 17.8], mag:2.29, spec:"B0.2IV" },
      { name:"Acrab", ra:[16.0, 5.0, 26.23], dec:[-19.0, 48.0, 19.4], mag:2.62, spec:"B0.5V" },
      { name:"Antares A", ra:[16.0, 29.0, 24.47], dec:[-26.0, 25.0, 55.0], mag:0.91, spec:"M1.5Ia" },
      { name:"Paikauhale", ra:[16.0, 35.0, 52.96], dec:[-28.0, 12.0, 57.5], mag:2.82, spec:"B0V" },
      { name:"Wei", ra:[16.0, 50.0, 10.24], dec:[-34.0, 17.0, 33.4], mag:2.29, spec:"K2IIIb" },
      { name:"Xamidimura", ra:[16.0, 51.0, 52.24], dec:[-38.0, 2.0, 50.4], mag:3.00, spec:"B1.5IV" },
      { name:"\u03b7 Sco", ra:[17.0, 12.0, 9.18], dec:[-43.0, 14.0, 18.6], mag:3.32, spec:"F3" },
      { name:"Lesath", ra:[17.0, 30.0, 45.84], dec:[-37.0, 17.0, 44.7], mag:2.70, spec:"B2IV" },
      { name:"Shaula", ra:[17.0, 33.0, 36.53], dec:[-37.0, 6.0, 13.5], mag:1.62, spec:"B2IV" },
      { name:"Sargas", ra:[17.0, 37.0, 19.13], dec:[-42.0, 59.0, 52.2], mag:1.86, spec:"F1II" },
      { name:"Girtab", ra:[17.0, 42.0, 29.28], dec:[-39.0, 1.0, 47.7], mag:2.39, spec:"B1.5III" },
      { name:"\u03b91 Sco", ra:[17.0, 47.0, 35.08], dec:[-40.0, 7.0, 37.1], mag:2.99, spec:"F3Ia" },
      { name:"\u03b61 Sco", ra:[16.0, 53.0, 59.73], dec:[-42.0, 21.0, 43.3], mag:4.70, spec:"B1Ia" },
      { name:"Alniyat", ra:[16.0, 21.0, 11.32], dec:[-25.0, 35.0, 33.9], mag:2.90, spec:"B1III" },
      { name:"G Sco", ra:[17.0, 49.0, 51.45], dec:[-37.0, 2.0, 36.1], mag:3.19, spec:"K0" },
      { name:"Pipirima", ra:[16.0, 52.0, 20.15], dec:[-38.0, 1.0, 2.9], mag:3.56, spec:"B2IV" },
      { name:"\u03b62 Sco", ra:[16.0, 54.0, 35.11], dec:[-42.0, 21.0, 38.7], mag:3.62, spec:"K4III" },
      { name:"Iklil", ra:[15.0, 56.0, 53.09], dec:[-29.0, 12.0, 50.4], mag:3.87, spec:"B2IV" },
      { name:"Jabhat al Akrab", ra:[16.0, 6.0, 48.43], dec:[-20.0, 40.0, 8.9], mag:3.93, spec:"B1V" },
      { name:"Jabbah", ra:[16.0, 11.0, 59.74], dec:[-19.0, 27.0, 38.3], mag:4.00, spec:"B2IV" },
      { name:"H Sco", ra:[16.0, 36.0, 22.46], dec:[-35.0, 15.0, 19.3], mag:4.18, spec:"K5III" },
      { name:"N Sco", ra:[16.0, 31.0, 22.94], dec:[-34.0, 42.0, 15.6], mag:4.24, spec:"B2III" },
      { name:"Q Sco", ra:[17.0, 36.0, 32.85], dec:[-38.0, 38.0, 5.5], mag:4.26, spec:"G8" },
      { name:"Jabhat al Akrab", ra:[16.0, 7.0, 24.3], dec:[-20.0, 52.0, 7.2], mag:4.31, spec:"G6" },
      { name:"\u03bf Sco", ra:[16.0, 20.0, 38.18], dec:[-24.0, 10.0, 9.4], mag:4.55, spec:"A4II" },
      { name:"13 Sco", ra:[16.0, 12.0, 18.21], dec:[-27.0, 55.0, 34.7], mag:4.58, spec:"B2V" },
      { name:"2 Sco", ra:[15.0, 53.0, 36.73], dec:[-25.0, 19.0, 37.5], mag:4.59, spec:"B2.5V" },
      { name:"1 Sco", ra:[15.0, 50.0, 58.75], dec:[-25.0, 45.0, 4.4], mag:4.63, spec:"B1.5V" },
      { name:"\u03b92 Sco", ra:[17.0, 50.0, 11.11], dec:[-40.0, 5.0, 25.5], mag:4.78, spec:"A6Ib" },
      { name:"22 Sco", ra:[16.0, 30.0, 12.48], dec:[-25.0, 6.0, 54.6], mag:4.79, spec:"B3V" },
      { name:"HD&#160;161840", ra:[17.0, 49.0, 10.47], dec:[-31.0, 42.0, 11.5], mag:4.79, spec:"B8Ib" },
      { name:"HD 146624", ra:[16.0, 18.0, 17.92], dec:[-28.0, 36.0, 49.6], mag:4.80, spec:"A0V" },
      { name:"V1073 Sco", ra:[17.0, 4.0, 49.35], dec:[-34.0, 7.0, 22.5], mag:4.83, spec:"B2Ia" },
      { name:"HD 163145", ra:[17.0, 56.0, 47.43], dec:[-44.0, 20.0, 31.9], mag:4.85, spec:"K2III" },
      { name:"HD 163376", ra:[17.0, 57.0, 47.81], dec:[-41.0, 42.0, 58.5], mag:4.88, spec:"M0III" },
      { name:"component of the \u03b2 Sco system", ra:[16.0, 5.0, 26.58], dec:[-19.0, 48.0, 6.6], mag:4.90, spec:"B2V" },
      { name:"\u03c8 Sco", ra:[16.0, 12.0, 0.0], dec:[-10.0, 3.0, 51.1], mag:4.93, spec:"A3IV" },
      { name:"HD 143787", ra:[16.0, 3.0, 20.67], dec:[-25.0, 51.0, 54.5], mag:4.96, spec:"K3III" },
      { name:"HD 153613", ra:[17.0, 1.0, 52.65], dec:[-32.0, 8.0, 36.2], mag:5.03, spec:"B8V" },
      { name:"HD 154948", ra:[17.0, 10.0, 42.35], dec:[-44.0, 33.0, 27.2], mag:5.06, spec:"G8" },
      { name:"component of the \u03be Sco system", ra:[16.0, 4.0, 22.3], dec:[-11.0, 22.0, 18.0], mag:5.07, spec:"F5IV" },
      { name:"HD 145250", ra:[16.0, 11.0, 2.13], dec:[-29.0, 24.0, 57.6], mag:5.09, spec:"K0III" },
      { name:"HD 157243", ra:[17.0, 24.0, 13.09], dec:[-44.0, 9.0, 45.0], mag:5.10, spec:"B7III" },
      { name:"HD 151804", ra:[16.0, 51.0, 33.72], dec:[-41.0, 13.0, 49.9], mag:5.23, spec:"O8Ia" },
      { name:"\u03c7 Sco", ra:[16.0, 13.0, 50.91], dec:[-11.0, 50.0, 15.8], mag:5.24, spec:"K3III" },
      { name:"HD 148688", ra:[16.0, 31.0, 41.77], dec:[-41.0, 49.0, 1.7], mag:5.31, spec:"B1Ia" },
      { name:"HD 144690", ra:[16.0, 8.0, 7.52], dec:[-26.0, 19.0, 36.0], mag:5.35, spec:"M2III" },
      { name:"HD 147513", ra:[16.0, 24.0, 1.24], dec:[-39.0, 11.0, 34.8], mag:5.37, spec:"G3" },
      { name:"HD 142165", ra:[15.0, 53.0, 53.92], dec:[-24.0, 31.0, 59.1], mag:5.38, spec:"B5V" },
      { name:"HR 5907", ra:[15.0, 53.0, 55.87], dec:[-23.0, 58.0, 40.9], mag:5.41, spec:"B2V" },
      { name:"HD 147628", ra:[16.0, 24.0, 31.77], dec:[-37.0, 33.0, 57.5], mag:5.42, spec:"B8V" },
      { name:"HD 142990", ra:[15.0, 58.0, 34.87], dec:[-24.0, 49.0, 53.1], mag:5.43, spec:"B5V" },
      { name:"16 Sco", ra:[16.0, 12.0, 7.29], dec:[-8.0, 32.0, 51.3], mag:5.43, spec:"A4V" },
      { name:"HD 149404", ra:[16.0, 36.0, 22.57], dec:[-42.0, 51.0, 31.9], mag:5.46, spec:"O9Ia" },
      { name:"HD 152234", ra:[16.0, 54.0, 1.84], dec:[-41.0, 48.0, 23.0], mag:5.46, spec:"B0.5Ia" },
      { name:"HD 151078", ra:[16.0, 46.0, 47.97], dec:[-39.0, 22.0, 36.8], mag:5.48, spec:"K0III" },
      { name:"27 Sco", ra:[16.0, 57.0, 11.17], dec:[-33.0, 15.0, 34.1], mag:5.48, spec:"K5III" },
      { name:"18 Sco", ra:[16.0, 15.0, 37.13], dec:[-8.0, 22.0, 5.7], mag:5.49, spec:"G1V" },
      { name:"HD 144987", ra:[16.0, 9.0, 52.61], dec:[-33.0, 32.0, 44.5], mag:5.50, spec:"B8V" },
    ],
    connections: [[10, 7], [7, 6], [4, 3], [3, 2], [11, 12], [12, 10], [5, 4], [3, 1], [3, 0], [9, 11], [6, 5], [8, 7], [8, 9]],
    mainIndices: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
  },

{ /* ANDROMEDA */
    name: "Andromeda", date: "31/03",
    stars: [
      { name:"Alpheratz", ra:[0.0, 8.0, 23.17], dec:[29.0, 5.0, 27.0], mag:2.07, spec:"B9" },
      { name:"\u03b4 And", ra:[0.0, 39.0, 19.6], dec:[30.0, 51.0, 40.4], mag:3.27, spec:"K3III" },
      { name:"\u03bc And", ra:[0.0, 56.0, 45.1], dec:[38.0, 29.0, 57.3], mag:3.86, spec:"A5V" },
      { name:"Mirach", ra:[1.0, 9.0, 43.8], dec:[35.0, 37.0, 15.0], mag:2.07, spec:"M0III" },
      { name:"Almach", ra:[2.0, 3.0, 53.92], dec:[42.0, 19.0, 47.5], mag:2.10, spec:"K3IIb" },
      { name:"\u03bd And", ra:[0.0, 49.0, 48.83], dec:[41.0, 4.0, 44.2], mag:4.53, spec:"B5V" },
      { name:"51 And", ra:[1.0, 37.0, 59.5], dec:[48.0, 37.0, 42.6], mag:3.59, spec:"K3III" },
      { name:"\u03bf And", ra:[23.0, 1.0, 55.25], dec:[42.0, 19.0, 33.5], mag:3.62, spec:"B6" },
      { name:"Udkadua", ra:[23.0, 37.0, 33.71], dec:[46.0, 27.0, 33.0], mag:3.81, spec:"G8III" },
      { name:"Shimu", ra:[0.0, 47.0, 20.39], dec:[24.0, 16.0, 2.6], mag:4.08, spec:"K1II" },
      { name:"Titawin", ra:[1.0, 36.0, 47.98], dec:[41.0, 24.0, 23.0], mag:4.10, spec:"F8V" },
      { name:"Kaffalmusalsala", ra:[23.0, 40.0, 24.44], dec:[44.0, 20.0, 2.3], mag:4.15, spec:"B9IV" },
      { name:"Junnanmen", ra:[1.0, 9.0, 30.12], dec:[47.0, 14.0, 30.6], mag:4.26, spec:"B7III" },
      { name:"Rasalnaqa", ra:[23.0, 38.0, 8.18], dec:[43.0, 16.0, 5.1], mag:4.29, spec:"B8V" },
      { name:"\u03c0 And", ra:[0.0, 36.0, 52.84], dec:[33.0, 43.0, 9.7], mag:4.34, spec:"B5V" },
      { name:"\u03b5 And", ra:[0.0, 38.0, 33.5], dec:[29.0, 18.0, 44.5], mag:4.34, spec:"G5III" },
      { name:"Kui", ra:[0.0, 57.0, 12.43], dec:[23.0, 25.0, 3.9], mag:4.40, spec:"G8III" },
      { name:"\u03c3 And", ra:[0.0, 18.0, 19.71], dec:[36.0, 47.0, 7.2], mag:4.51, spec:"A2V" },
      { name:"7 And", ra:[23.0, 12.0, 32.92], dec:[49.0, 24.0, 21.5], mag:4.53, spec:"F0V" },
      { name:"\u03b8 And", ra:[0.0, 17.0, 5.54], dec:[38.0, 40.0, 54.0], mag:4.61, spec:"A2V" },
      { name:"3 And", ra:[23.0, 4.0, 10.83], dec:[50.0, 3.0, 6.1], mag:4.64, spec:"K0III" },
      { name:"65 And", ra:[2.0, 25.0, 37.4], dec:[50.0, 16.0, 43.2], mag:4.73, spec:"K4III" },
      { name:"58 And", ra:[2.0, 8.0, 29.15], dec:[37.0, 51.0, 33.1], mag:4.78, spec:"A5IV" },
      { name:"8 And", ra:[23.0, 17.0, 44.62], dec:[49.0, 0.0, 55.0], mag:4.82, spec:"M2III" },
      { name:"\u03c9 And", ra:[1.0, 27.0, 39.09], dec:[45.0, 24.0, 25.0], mag:4.83, spec:"F5IV" },
      { name:"60 And", ra:[2.0, 13.0, 13.34], dec:[44.0, 13.0, 54.1], mag:4.84, spec:"K4III" },
      { name:"Adhil", ra:[1.0, 22.0, 20.39], dec:[45.0, 31.0, 43.5], mag:4.87, spec:"K0III" },
      { name:"\u03c4 And", ra:[1.0, 40.0, 34.8], dec:[40.0, 34.0, 37.6], mag:4.96, spec:"B8III" },
      { name:"41 H. And", ra:[1.0, 41.0, 46.52], dec:[42.0, 36.0, 49.7], mag:4.96, spec:"G2V" },
      { name:"\u03c8 And", ra:[23.0, 46.0, 2.04], dec:[46.0, 25.0, 13.0], mag:4.97, spec:"G5Ib" },
      { name:"22 And", ra:[0.0, 10.0, 19.24], dec:[46.0, 4.0, 20.2], mag:5.01, spec:"F2II" },
      { name:"\u03c7 And", ra:[1.0, 39.0, 21.02], dec:[44.0, 23.0, 10.1], mag:5.01, spec:"G8III" },
      { name:"41 And", ra:[1.0, 8.0, 0.72], dec:[43.0, 56.0, 32.1], mag:5.04, spec:"A3" },
      { name:"2 And", ra:[23.0, 2.0, 36.34], dec:[42.0, 45.0, 28.1], mag:5.09, spec:"A3V" },
      { name:"V428 And", ra:[0.0, 36.0, 46.47], dec:[44.0, 29.0, 18.6], mag:5.14, spec:"K5III" },
      { name:"\u03c1 And", ra:[0.0, 21.0, 7.23], dec:[37.0, 58.0, 7.3], mag:5.16, spec:"F5III" },
      { name:"HD 2421", ra:[0.0, 28.0, 13.59], dec:[44.0, 23.0, 40.2], mag:5.18, spec:"A2V" },
      { name:"64 And", ra:[2.0, 24.0, 24.89], dec:[50.0, 0.0, 23.9], mag:5.19, spec:"G8III" },
      { name:"GN And", ra:[0.0, 30.0, 7.34], dec:[29.0, 45.0, 6.1], mag:5.20, spec:"A7III" },
      { name:"14 And", ra:[23.0, 31.0, 17.2], dec:[39.0, 14.0, 11.0], mag:5.22, spec:"K0III" },
      { name:"49 And", ra:[1.0, 30.0, 6.1], dec:[47.0, 0.0, 26.6], mag:5.27, spec:"K0III" },
      { name:"32 And", ra:[0.0, 41.0, 7.2], dec:[39.0, 27.0, 31.2], mag:5.30, spec:"G8III" },
      { name:"4 And", ra:[23.0, 7.0, 39.28], dec:[46.0, 23.0, 14.3], mag:5.30, spec:"K5III" },
      { name:"6 Per", ra:[2.0, 13.0, 36.02], dec:[51.0, 3.0, 58.4], mag:5.31, spec:"G8III" },
      { name:"62 And", ra:[2.0, 19.0, 16.85], dec:[47.0, 22.0, 48.0], mag:5.31, spec:"A1V" },
      { name:"18 And", ra:[23.0, 39.0, 8.35], dec:[50.0, 28.0, 18.3], mag:5.35, spec:"B9V" },
      { name:"55 And", ra:[1.0, 53.0, 17.35], dec:[40.0, 43.0, 47.3], mag:5.42, spec:"K1III" },
      { name:"11 And", ra:[23.0, 19.0, 29.79], dec:[48.0, 37.0, 30.7], mag:5.44, spec:"K0III" },
      { name:"2942", ra:[0.0, 37.0, 21.23], dec:[35.0, 23.0, 58.2], mag:5.45, spec:"G5III" },
      { name:"36 And", ra:[0.0, 54.0, 58.02], dec:[23.0, 37.0, 42.4], mag:5.46, spec:"K1IV" },
    ],
    connections: [[0, 1], [1, 3], [3, 2], [4, 3]],
    mainIndices: [0, 1, 2, 3, 4],
  },









];

var consDataByName = {};
for (var ci = 0; ci < consData.length; ci++) {
  var key = consData[ci].name.toUpperCase().replace(/ /g, '_');
  consDataByName[key] = consData[ci];
}

function randomSpectralType() {
  var r = Math.random();
  var cum = 0;
  for (var i = 0; i < SPECTRAL_WEIGHTS.length; i++) {
    cum += SPECTRAL_WEIGHTS[i].prob;
    if (r < cum) {
      var sw = SPECTRAL_WEIGHTS[i];
      var sub = sw.subRange[0] + Math.floor(Math.random() * (sw.subRange[1] - sw.subRange[0] + 1));
      var lum = sw.lum[Math.floor(Math.random() * sw.lum.length)];
      return sw.cls + sub + lum;
    }
  }
  return "M0V";
}

function randomStarMagnitude() {
  // Most stars are faint, distribution peaks around mag 5-6
  var r = Math.random();
  if (r < 0.05) return Math.random() * 2;        // 5%: very bright (0-2)
  if (r < 0.20) return 2 + Math.random() * 2;     // 15%: bright (2-4)
  if (r < 0.50) return 4 + Math.random() * 1.5;   // 30%: moderate (4-5.5)
  return 5.5 + Math.random() * 1.5;                // 50%: faint (5.5-7)
}

function createBackgroundStar(width, height) {
  var spec = randomSpectralType();
  var mag = randomStarMagnitude();
  return {
    x: Math.random() * width,
    y: Math.random() * height,
    size: Math.pow(2.512, (5 - mag) / 5) * 1.2,
    colour: spectralToHex(spec),
    mag: mag,
    spec: spec,
  };
}

// ── Cross-file utilities ──────────────────────────────
var requestAnimFrame = window.requestAnimationFrame ||
  window.webkitRequestAnimationFrame ||
  window.mozRequestAnimationFrame ||
  window.oRequestAnimationFrame ||
  window.msRequestAnimationFrame ||
  function(cb) { window.setTimeout(cb, 1000 / 60); };

function lerp(a, b, t) { return a + (b - a) * t; }

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

// ── Spectral weight distribution (for randomSpectralType) ───
var SPECTRAL_WEIGHTS = [
  { cls: "B", prob: 0.05, subRange: [0, 9], lum: ["V", "IV", "III"] },
  { cls: "A", prob: 0.10, subRange: [0, 9], lum: ["V", "IV", "III"] },
  { cls: "F", prob: 0.15, subRange: [0, 9], lum: ["V", "IV", "III"] },
  { cls: "G", prob: 0.25, subRange: [0, 9], lum: ["V", "IV", "III"] },
  { cls: "K", prob: 0.30, subRange: [0, 9], lum: ["V", "IV", "III"] },
  { cls: "M", prob: 0.15, subRange: [0, 9], lum: ["V", "IV", "III"] },
];

// ── Shared background star system ─────────────────────
// Generate background stars with consistent twinkle properties.
// opts can include:
//   parallax: bool     — add depth for scroll-based parallax
//   depthRange: [min, max] — range of parallax depth values
//   yBias: float       — exponent for vertical distribution (ocean: 1.4)
//   sizeRange: [min, max] — range of star sizes
function createBgStars(count, width, height, opts) {
  opts = opts || {};
  var stars = [];
  for (var i = 0; i < count; i++) {
    var spec = randomSpectralType();
    var mag = randomStarMagnitude();
    var star = {
      x: Math.random() * width,
      y: Math.random() * height,
      size: (opts.sizeRange ? opts.sizeRange[0] + Math.random() * (opts.sizeRange[1] - opts.sizeRange[0])
                           : Math.pow(2.512, (5 - mag) / 5) * 1.2),
      colour: spectralToHex(spec),
      mag: mag,
      spec: spec,
      phase: Math.random() * Math.PI * 2,
      speed: 0.01 + Math.random() * 0.03,
    };
    if (opts.yBias) star.y = Math.pow(Math.random(), opts.yBias) * height;
    if (opts.parallax) star.depth = (opts.depthRange || [0.3, 1.0])[0] +
      Math.random() * ((opts.depthRange || [0.3, 1.0])[1] - (opts.depthRange || [0.3, 1.0])[0]);
    stars.push(star);
  }
  return stars;
}

// Render a single background star with twinkle
function renderBgStar(ctx, star, time, alpha) {
  var twinkle = 0.5 + 0.5 * Math.sin(time * star.speed + star.phase);
  var a = (alpha !== undefined ? alpha : 1) * (0.3 + 0.7 * twinkle);
  ctx.fillStyle = hexToRgba(star.colour, a);
  ctx.beginPath();
  ctx.arc(star.x, star.y, star.size * (0.5 + 0.5 * twinkle), 0, Math.PI * 2);
  ctx.fill();
}

// Render all background stars
function renderBgStars(ctx, stars, time, alpha) {
  for (var i = 0; i < stars.length; i++) {
    renderBgStar(ctx, stars[i], time, alpha);
  }
}

// Project a constellation to screen coordinates
// Returns array of {x, y, size, colour, name}
function projectConstellation(consData, cx, cy, sc, rC, dC) {
  var cosFac = Math.cos(dC * Math.PI / 180);
  var pts = [];
  for (var i = 0; i < consData.stars.length; i++) {
    var s = consData.stars[i];
    var ra = typeof s.ra === "number" ? s.ra : raDeg(s.ra[0], s.ra[1], s.ra[2] || 0);
    var dec = typeof s.dec === "number" ? s.dec : decDeg(s.dec[0], s.dec[1], s.dec[2] || 0);
    pts.push({
      x: cx - sc * (ra - rC) * cosFac,
      y: cy - sc * (dec - dC),
      size: starSize(s.mag),
      colour: spectralToHex(s.spec || "G2V"),
      mag: s.mag,
      name: s.name,
    });
  }
  return pts;
}

// Draw constellation connection lines
function renderConstellationLines(ctx, pts, connections, style) {
  ctx.strokeStyle = style || "rgba(200, 200, 255, 0.15)";
  ctx.lineWidth = 1;
  for (var i = 0; i < connections.length; i++) {
    var c = connections[i];
    var from = pts[c[0]], to = pts[c[1]];
    if (from && to) {
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.stroke();
    }
  }
}

// Draw constellation stars (projected) with glow
function renderConstellationStars(ctx, pts, mainIndices, time) {
  for (var i = 0; i < pts.length; i++) {
    var p = pts[i];
    var isMain = mainIndices && mainIndices.indexOf(i) !== -1;
    var glow = isMain ? 1 : 0.4;
    var twinkle = 0.6 + 0.4 * Math.sin(time * 0.02 + i * 1.7);
    var r = hexToRgba(p.colour, glow * 0.3 * twinkle);
    ctx.fillStyle = r;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.size * 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = hexToRgba(p.colour, glow * twinkle);
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
    ctx.fill();
  }
}

// ── Canvas setup ──────────────────────────────────────
// Returns { canvas, ctx, width, height, sx, sy } with sane defaults and resize listener.
function initCanvas(callback) {
  var c = document.getElementById("bgCanvas");
  var cx = c.getContext("2d");
  var w, h;

  function resize() {
    var rw = window.innerWidth, rh = window.innerHeight;
    if (!isFinite(rw) || rw < 100) rw = 1920;
    if (!isFinite(rh) || rh < 100) rh = 1080;
    w = rw; h = rh;
    c.width = w; c.height = h;
    if (callback) callback(w, h);
  }

  resize();
  window.addEventListener("resize", resize, { passive: true });
  return { canvas: c, ctx: cx, width: function() { return w; }, height: function() { return h; },
           sx: function() { return w / 1920; }, sy: function() { return h / 1080; },
           mScale: function() { return Math.min(w / 1920, h / 1080); } };
}
