// Let the browser handle the animation cycles
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

// function to get todays date
function today(d) {
  var day = d.getDate(),
      mon = d.getMonth()+1;
  (day < 10) ? day = "0"+day : day;
  (mon < 10) ? mon = "0"+mon : mon;
  return day+"/"+mon;
}

// fetch the background canvas
var background = document.getElementById("bgCanvas"),
    bgCtx = background.getContext("2d"),
    width = window.innerWidth,
    height = window.innerHeight;

if (!isFinite(width) || width < 100) width = 1920;
if (!isFinite(height) || height < 100) height = 1080;
background.width = width;
background.height = height;

// Parallax scroll offset
var scrollY = 0;
var pageHeight = height * 4;
window.addEventListener("scroll", function() { scrollY = window.scrollY; }, { passive: true });
// Detect page content height for absolute canvas sizing
function updatePageHeight() { pageHeight = Math.max(height * 4, document.body.scrollHeight || height * 4); }
updatePageHeight();
window.addEventListener("resize", updatePageHeight, { passive: true });

// draw the night sky
bgCtx.fillStyle = "#110E19";
bgCtx.fillRect(0, 0, width, height);

// === Cassiopeia Constellation ===

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

var cassBase = { x: width * 0.13, y: height * 0.93 };
var cassSX = -6.5 * (width / 1920);
var cassSY = -12 * (height / 1080);

var cassiopeiaStars = [
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

var cassiopeiaConnections = [
  [1, 0], [0, 2], [2, 3], [3, 4]
];

function hexToRgba(hex, alpha) {
  var r = parseInt(hex.slice(1,3), 16);
  var g = parseInt(hex.slice(3,5), 16);
  var b = parseInt(hex.slice(5,7), 16);
  return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
}

var cassTime = 0;

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

// determine which star colours are allowed
const starColour = ["white", "floralWhite", "aliceBlue", "powderBlue", "azure", "moccasin", "sandyBrown", "peachPuff"]

// function to draw background stars
function Star() {
  this.size = Math.random() * 2 + .1;
  this.x = Math.random() * width;
  this.y = Math.random() * pageHeight;
  // select it's colour
  this.colour = starColour[Math.floor(Math.random() * starColour.length)]
}

// function to draw shooting stars
function ShootingStar(special = false) {
  this.special = special;
  this.reset(-200);
}

// function to draw satellites
function Satellite() {
  this.y = Math.random() * height;
  this.x = Math.random() * width;
  this.speed = (Math.random() * .29) + .01;
  this.size = (Math.random() * 2) + 0.1;
  this.colour = "white";
  this.waitTime = new Date().getTime();
  this.active = true;
}

// update the star positions
Star.prototype.update = function() {
  // change the size of the star due to atmospheric twinkling
  this.size = Math.max(.1, Math.min(2, this.size + 0.1 * Math.random() - 0.05));
  // and draw the star
  bgCtx.fillStyle = this.colour;
  bgCtx.fillRect(this.x, this.y, this.size, this.size);
}

// and a function to update the shooting star position
ShootingStar.prototype.update = function() {
  if (this.active) {
    // update it's position
    this.x -= this.speed;
    this.y += this.speed;
    // if it goes out of the window, reset
    if (this.x < -this.len || this.y >= height+this.len) {
      this.speed = 0;
      // if the shooting star is special, and it's the right time
      if (this.special) {
        if (isSpecialDate) { this.reset(); }
      // otherwise, just reset it
      } else { this.reset(); }
    } else {
      // set the shooting star colour
      bgCtx.fillStyle = this.colour;
      bgCtx.strokeStyle = this.colour;
      bgCtx.lineWidth = this.size;
      // and draw it
      bgCtx.beginPath();
      bgCtx.moveTo(this.x, this.y);
      bgCtx.lineTo(this.x + this.len, this.y - this.len);
      bgCtx.stroke();
    }
  // wait for it to be active again
  } else {
    if (this.waitTime < new Date().getTime()) {
      this.active = true;
    }
  }
}

// a function to update the satellite star position
Satellite.prototype.update = function() {
  if (this.active) {
    // update it's position
    this.x -= this.speed;
    // if it goes out of the window, reset
    if (this.x < 0) {
      this.reset();
    } else {
      // set the colour
      bgCtx.fillStyle = this.colour;
      bgCtx.fillRect(this.x, this.y, this.size, this.size);
    }
  // wait for it to be active again
  } else {
    if (this.waitTime < new Date().getTime()) {
      this.active = true;
    }
  }
}

// function to reset the shooting stars
ShootingStar.prototype.reset = function(x="0") {
  // select the starting position, along the two screen axes
  var pos = Math.random() * (width + height);
  this.y = Math.max(0, pos - width);
  (x=="0") ? this.x = Math.min(width, pos) : this.x=x;
  // the other bits
  this.len = (Math.random() * 80) + 10;
  this.size = (Math.random() * 1) + 0.1;
  this.speed = (Math.random() * 10) + 5;
  this.colour = starColour[Math.floor(Math.random() * starColour.length)];
  this.waitTime = new Date().getTime() + (Math.random() * 20000);
  this.active = false;
}

// function to reset the satellites
Satellite.prototype.reset = function() {
  this.y = Math.random() * height;
  this.x = width;
  this.speed = (Math.random() * .19) + .01;
  this.size = (Math.random() * 2) + 0.1;
  this.colour = "white";
  this.waitTime = new Date().getTime() + (Math.random() * 20000);
  this.active = false;
}

// list of special dates
var specialDates = ["27/07", "12/08", "23/08", "04/09", "26/10", "31/03"];
var dateColours = {
  "27/07": "gold", "12/08": "silver", "23/08": "coral",
  "04/09": "pink", "26/10": "cyan", "31/03": "lightpink"
};

// boolean for if this date is special
var isSpecialDate = false;

// create an array of animated entities
var entities = [];

// initialise the star field - cover full page for parallax
for (var i = 0; i < 600; i++) { entities.push(new Star()); }

// add a few satellites
for (var i = 10; i > 0; i--) { entities.push(new Satellite()); }

// add a shooting star
for (var i = 1; i > 0; i--) { entities.push(new ShootingStar()); }

// add the special shooting stars
for (var i = 20; i > 0; i--) { entities.push(new ShootingStar(true)); }

// animate the background
function animate() {
  // check if today is a special date
  isSpecialDate = specialDates.indexOf(today(new Date())) != -1;
  var todayStr = today(new Date());
  var dateColour = dateColours[todayStr] || null;
  // fetch the requiredbackground colour
  bgCtx.fillStyle = "#110E19";
  bgCtx.fillRect(0, 0, width, height);

  // Parallax: stars drift up at 30% of scroll speed (like distant sky)
  var parOffset = scrollY * 0.3;
  var cassOffset = scrollY * 0.5;

  bgCtx.fillStyle = '#ffffff';
  bgCtx.strokeStyle = '#ffffff';

  if (dateColour) {
    bgCtx.strokeStyle = dateColour;
  }

  // draw Cassiopeia constellation with its own parallax
  cassTime++;
  bgCtx.save();
  bgCtx.translate(0, -cassOffset);
  drawConstellationStars(cassTime);
  bgCtx.restore();

  // update all entities with parallax
  bgCtx.save();
  bgCtx.translate(0, -parOffset);
  for (let entity of entities) { entity.update(); };
  bgCtx.restore();

  //schedule the next animation frame
  requestAnimFrame(animate);
}

// call the first animation
animate();

window.addEventListener("resize", function() {
  var rw = window.innerWidth, rh = window.innerHeight;
  if (!isFinite(rw) || rw < 100) rw = 1920;
  if (!isFinite(rh) || rh < 100) rh = 1080;
  width = rw; height = rh;
  background.width = width; background.height = height;
});
