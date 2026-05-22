// fetch the background canvas
var background = document.getElementById("bgCanvas"),
    bgCtx = background.getContext("2d"),
    width = window.innerWidth,
    height = window.innerHeight;

if (!isFinite(width) || width < 100) width = 1920;
if (!isFinite(height) || height < 100) height = 1080;

// Switch to absolute positioning so canvas scrolls with page
var pageHeight = Math.max(height * 4, document.body.scrollHeight || height * 4);
background.style.position = "absolute";
background.style.top = "0";
background.style.left = "0";
background.width = width;
background.height = pageHeight;
background.style.height = pageHeight + "px";

// Parallax scroll offset
var scrollY = 0;
window.addEventListener("scroll", function() { scrollY = window.scrollY; }, { passive: true });

// Update page height on resize
window.addEventListener("resize", function() {
  var rw = window.innerWidth, rh = window.innerHeight;
  if (!isFinite(rw) || rw < 100) rw = 1920;
  if (!isFinite(rh) || rh < 100) rh = 1080;
  width = rw; height = rh;
  pageHeight = Math.max(height * 4, document.body.scrollHeight || height * 4);
  background.style.height = pageHeight + "px";
  background.width = width; background.height = pageHeight;
});

// draw the night sky
bgCtx.fillStyle = "#110E19";
bgCtx.fillRect(0, 0, width, pageHeight);

// draw the night sky
bgCtx.fillStyle = "#110E19";
bgCtx.fillRect(0, 0, width, height);

// === Cassiopeia Constellation ===

var cassConstellation = new Constellation(consData[1]);
var cassWCoords = cassConstellation.project(
  width * 0.13, height * 0.93,
  6.5 * (width / 1920),
  0, 0
);

var cassTime = 0;

function drawConstellationStars(t) {
  var minMag = Infinity;
  for (var s of cassWCoords) if (s.mag < minMag) minMag = s.mag;

  for (var s of cassWCoords) {
    var twinkle = Math.sin(t * 0.02 + s.x * 0.005) * 0.3 + 0.7;
    var magFactor = Math.max(0.12, 1 - (s.mag - minMag) * 0.35);
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
  for (var c of consData[1].connections) {
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

// --- Orion constellation (right side, lower portion) ---
var orionCenterRA = 82.5, orionCenterDec = 5;
var orionConstellation = new Constellation(consData[0]);
var orionWCoords = orionConstellation.project(
  width * 0.78, height * 0.78,
  7 * (width / 1920),
  orionCenterRA, orionCenterDec
);

function drawOrionConstellation(t) {
  var minMag = Infinity;
  for (var s of orionWCoords) if (s.mag < minMag) minMag = s.mag;

  for (var s of orionWCoords) {
    var twinkle = Math.sin(t * 0.02 + s.x * 0.005) * 0.3 + 0.7;
    var magFactor = Math.max(0.12, 1 - (s.mag - minMag) * 0.35);
    var alpha = (0.4 + twinkle * 0.6) * magFactor;
    var glowSize = s.size * 2.5;

    bgCtx.save();
    var glow = bgCtx.createRadialGradient(s.x, s.y, 0, s.x, s.y, glowSize);
    glow.addColorStop(0, hexToRgba(s.colour, alpha * 0.25));
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

  bgCtx.strokeStyle = "rgba(255, 255, 255, 0.12)";
  bgCtx.lineWidth = 0.8;
  bgCtx.beginPath();
  for (var c of consData[0].connections) {
    bgCtx.moveTo(orionWCoords[c[0]].x, orionWCoords[c[0]].y);
    bgCtx.lineTo(orionWCoords[c[1]].x, orionWCoords[c[1]].y);
  }
  bgCtx.stroke();

  bgCtx.font = "10px sans-serif";
  bgCtx.textAlign = "center";
  bgCtx.fillStyle = "rgba(255, 255, 255, 0.18)";
  var lx = 0, maxY = -Infinity;
  for (var i = 0; i < 4; i++) { var s = orionWCoords[i]; lx += s.x; if (s.y > maxY) maxY = s.y; }
  bgCtx.fillText("Orion", lx / 4, maxY + 16);
}

// function to draw background stars with per-star parallax depth and spectral colour
function BgStar() {
  var data = createBackgroundStar(width, pageHeight);
  this.x = data.x;
  this.y = data.y;
  this.size = data.size;
  this.colour = data.colour;
  this.mag = data.mag;
  this.depth = 0.3 + Math.random() * 0.7;
}

BgStar.prototype.update = function() {
  this.size = Math.max(.1, Math.min(2, this.size + 0.1 * Math.random() - 0.05));
  var paraY = this.y + scrollY * (1 - this.depth);
  bgCtx.fillStyle = this.colour;
  bgCtx.fillRect(this.x, paraY, this.size, this.size);
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

// and a function to update the shooting star position
ShootingStar.prototype.update = function() {
  if (this.active) {
    this.x -= this.speed;
    this.y += this.speed;
    if (this.x < -this.len || this.y > pageHeight + this.len || this.y < -this.len) {
      this.speed = 0;
      if (this.special) {
        if (isSpecialDate) { this.reset(); }
      } else { this.reset(); }
    } else {
      bgCtx.fillStyle = this.colour;
      bgCtx.strokeStyle = this.colour;
      bgCtx.lineWidth = this.size;
      bgCtx.beginPath();
      bgCtx.moveTo(this.x, this.y);
      bgCtx.lineTo(this.x + this.len, this.y - this.len);
      bgCtx.stroke();
    }
  } else {
    if (this.waitTime < new Date().getTime()) {
      this.active = true;
    }
  }
}

// a function to update the satellite star position
Satellite.prototype.update = function() {
  if (this.active) {
    this.x -= this.speed;
    if (this.x < 0 || this.y > pageHeight || this.y < 0) {
      this.reset();
    } else {
      bgCtx.fillStyle = this.colour;
      bgCtx.fillRect(this.x, this.y, this.size, this.size);
    }
  } else {
    if (this.waitTime < new Date().getTime()) {
      this.active = true;
    }
  }
}

// function to reset the shooting stars
ShootingStar.prototype.reset = function(x="0") {
  var pos = Math.random() * (width + height);
  this.y = scrollY + Math.max(0, pos - width);
  (x=="0") ? this.x = Math.min(width, pos) : this.x=x;
  this.len = (Math.random() * 80) + 10;
  this.size = (Math.random() * 1) + 0.1;
  this.speed = (Math.random() * 10) + 5;
  this.colour = spectralToHex(randomSpectralType());
  this.waitTime = new Date().getTime() + (Math.random() * 20000);
  this.active = false;
}

// function to reset the satellites
Satellite.prototype.reset = function() {
  this.y = scrollY + Math.random() * height;
  this.x = width;
  this.speed = (Math.random() * .19) + .01;
  this.size = (Math.random() * 2) + 0.1;
  this.colour = "white";
  this.waitTime = new Date().getTime() + (Math.random() * 20000);
  this.active = false;
}

// boolean for if this date is special
var isSpecialDate = false;

// create arrays of animated entities - separate fixed stars from moving objects
var stars = [];
var movers = [];

// initialise the star field - cover full page for parallax
for (var i = 0; i < 600; i++) { stars.push(new BgStar()); }

// add a few satellites
for (var i = 10; i > 0; i--) { movers.push(new Satellite()); }

// add a shooting star
for (var i = 1; i > 0; i--) { movers.push(new ShootingStar()); }

// add the special shooting stars
for (var i = 20; i > 0; i--) { movers.push(new ShootingStar(true)); }

// animate the background
function animate() {
  var todayStr = getDateKey();
  isSpecialDate = false;
  for (var i = 0; i < consData.length; i++) {
    if (consData[i].date === todayStr) {
      isSpecialDate = true;
      break;
    }
  }
  bgCtx.fillStyle = "#110E19";
  bgCtx.fillRect(0, 0, width, pageHeight);

  var cassOffset = scrollY * 0.8;
  var orionOffset = scrollY * 0.85;

  bgCtx.fillStyle = '#ffffff';
  bgCtx.strokeStyle = '#ffffff';

  cassTime++;
  bgCtx.save();
  bgCtx.translate(0, cassOffset);
  drawConstellationStars(cassTime);
  bgCtx.restore();

  bgCtx.save();
  bgCtx.translate(0, orionOffset);
  drawOrionConstellation(cassTime);
  bgCtx.restore();

  for (let s of stars) { s.update(); };

  for (let m of movers) { m.update(); };

  requestAnimFrame(animate);
}

// call the first animation
animate();