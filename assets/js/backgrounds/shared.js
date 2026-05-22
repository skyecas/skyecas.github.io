// --- Astronomical coordinate utilities ---
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

// --- Constellation data: Cassiopeia (16 stars, W asterism) ---
var CASSIOPEIA_STARS = [
  { name: "Schedar",  ra: raDeg(0, 40, 30.4411),  dec: decDeg(56, 32, 14.392), mag: 2.24, colour: "#FFB870",  spec: "K0IIIa"   },
  { name: "Caph",     ra: raDeg(0, 9, 10.68518),  dec: decDeg(59, 8, 59.2120), mag: 2.28, colour: "#F0DDB0",  spec: "F2III"    },
  { name: "Navi",     ra: raDeg(0, 56, 42.50108), dec: decDeg(60, 43, 0.2984), mag: 2.47, colour: "#A0B4FF",  spec: "B0.5IVe"  },
  { name: "Ruchbah",  ra: raDeg(1, 25, 48.95147), dec: decDeg(60, 14, 7.0225), mag: 2.66, colour: "#E8E0D0",  spec: "A5III-IV" },
  { name: "Segin",    ra: raDeg(1, 54, 23.73409), dec: decDeg(63, 40, 12.3602), mag: 3.35, colour: "#A8C0F0",  spec: "B3III"    },
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

var CASSIOPEIA_CONNECTIONS = [
  [1, 0], [0, 2], [2, 3], [3, 4]
];

// --- Constellation data: Orion (8 stars) ---
var ORION_STARS = [
  { ra: raDeg(5,55,10.29),  dec: decDeg(7,24,25.4),   mag: 0.45, spec: "M2I",  name: "Betelgeuse" },
  { ra: raDeg(5,25,7.86),   dec: decDeg(6,20,58.9),   mag: 1.64, spec: "B2III", name: "Bellatrix" },
  { ra: raDeg(5,40,45.53),  dec: decDeg(-1,56,34.3),  mag: 1.77, spec: "O9.5I", name: "Alnitak" },
  { ra: raDeg(5,36,12.81),  dec: decDeg(-1,12,6.9),   mag: 1.69, spec: "B0I",   name: "Alnilam" },
  { ra: raDeg(5,32,0.40),   dec: decDeg(-0,17,4.4),   mag: 2.25, spec: "O9.5II",name: "Mintaka" },
  { ra: raDeg(5,35,16.48),  dec: decDeg(-5,23,23.2),  mag: 3.43, spec: "B3V",   name: "Sword" },
  { ra: raDeg(5,47,45.34),  dec: decDeg(-9,40,10.6),  mag: 2.06, spec: "B1.5I", name: "Saiph" },
  { ra: raDeg(5,14,32.28),  dec: decDeg(-8,12,5.9),   mag: 0.13, spec: "B8I",   name: "Rigel" },
];

var ORION_CONNECTIONS = [
  [0,1],[1,2],[2,3],[3,4],[2,5],[4,5],[2,6],[4,7],[6,7],[0,1]
];
