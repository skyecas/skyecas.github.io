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

var nebulaMult = 2.5;

function noise2D(x, y, t) {
  return Math.sin(x * 0.003 + t * 0.0003) * 0.5 +
         Math.sin(y * 0.004 + t * 0.0002) * 0.3 +
         Math.sin((x + y) * 0.002 + t * 0.0004) * 0.2;
}

function BgStar() {
  this.x = Math.random() * width;
  this.y = Math.random() * height;
  this.size = Math.random() * 2 + 0.2;
  this.colour = spectralToHex(randomSpectralType());
  this.phase = Math.random() * Math.PI * 2;
  this.speed = 0.01 + Math.random() * 0.02;
  this.bright = Math.random() < 0.02;
}
BgStar.prototype.update = function(t) {
  var twinkle = Math.sin(t * this.speed + this.phase) * 0.4 + 0.6;
  bgCtx.globalAlpha = 0.2 + twinkle * 0.8;
  bgCtx.fillStyle = this.colour;
  bgCtx.fillRect(this.x, this.y, this.size, this.size);

  if (this.bright) {
    bgCtx.save();
    bgCtx.globalAlpha = 0.15 * twinkle;
    bgCtx.filter = "blur(3px)";
    bgCtx.fillStyle = this.colour;
    bgCtx.beginPath();
    bgCtx.arc(this.x, this.y, this.size * 4, 0, Math.PI * 2);
    bgCtx.fill();
    bgCtx.restore();
    bgCtx.filter = "none";

    bgCtx.strokeStyle = "rgba(255, 255, 255, 0.08)";
    bgCtx.lineWidth = 0.5;
    bgCtx.beginPath();
    bgCtx.moveTo(this.x - 8, this.y);
    bgCtx.lineTo(this.x - 2, this.y);
    bgCtx.moveTo(this.x + 2, this.y);
    bgCtx.lineTo(this.x + 8, this.y);
    bgCtx.moveTo(this.x, this.y - 8);
    bgCtx.lineTo(this.x, this.y - 2);
    bgCtx.moveTo(this.x, this.y + 2);
    bgCtx.lineTo(this.x, this.y + 8);
    bgCtx.stroke();
  }

  bgCtx.globalAlpha = 1;
};

function DustLane(xBase, yBase, width, height, angle, speed) {
  this.xBase = xBase;
  this.yBase = yBase;
  this.width = width;
  this.height = height;
  this.angle = angle;
  this.speed = speed;
  this.phase = Math.random() * Math.PI * 2;
}
DustLane.prototype.update = function(t) {
  bgCtx.save();
  bgCtx.translate(this.xBase, this.yBase);
  bgCtx.rotate(this.angle);

  var segments = 40;
  var segW = this.width / segments;
  bgCtx.fillStyle = "rgba(2, 2, 8, 0.3)";
  bgCtx.beginPath();
  bgCtx.moveTo(0, 0);
  for (var i = 0; i <= segments; i++) {
    var x = i * segW;
    var y = noise2D(x, this.yBase, t * this.speed + this.phase) * this.height * 0.5;
    bgCtx.lineTo(x, y);
  }
  bgCtx.lineTo(this.width, 0);
  bgCtx.closePath();
  bgCtx.fill();

  bgCtx.fillStyle = "rgba(2, 2, 8, 0.2)";
  bgCtx.beginPath();
  bgCtx.moveTo(0, this.height * 0.3);
  for (var i = 0; i <= segments; i++) {
    var x = i * segW;
    var y = noise2D(x, this.yBase + this.height, t * this.speed + this.phase + 2) * this.height * 0.4 + this.height * 0.3;
    bgCtx.lineTo(x, y);
  }
  bgCtx.lineTo(this.width, this.height * 0.3);
  bgCtx.closePath();
  bgCtx.fill();

  bgCtx.restore();
};

var stars = [];
for (var i = 1200; i > 0; i--) { stars.push(new BgStar()); }

var dustLanes = [
  new DustLane(200 * sx, 300 * sy, 800 * sx, 120 * sy, -0.2, 0.0002),
  new DustLane(900 * sx, 500 * sy, 700 * sx, 100 * sy, 0.3, 0.00015),
  new DustLane(400 * sx, 700 * sy, 600 * sx, 80 * sy, -0.1, 0.00025),
];

function drawNebulaGas(t) {
  var centres = [
    { x: 500 * sx, y: 350 * sy, rx: 450 * sx, ry: 300 * sy, colours: ["rgba(180, 40, 200, 0.1)", "rgba(120, 20, 160, 0.18)", "rgba(60, 10, 100, 0.08)"], speed: 0.00008, phase: 0 },
    { x: 900 * sx, y: 500 * sy, rx: 500 * sx, ry: 350 * sy, colours: ["rgba(30, 80, 200, 0.08)", "rgba(20, 50, 160, 0.15)", "rgba(10, 20, 100, 0.05)"], speed: -0.00006, phase: 1.5 },
    { x: 700 * sx, y: 350 * sy, rx: 350 * sx, ry: 250 * sy, colours: ["rgba(255, 80, 120, 0.08)", "rgba(200, 40, 80, 0.15)", "rgba(140, 20, 60, 0.05)"], speed: 0.0001, phase: -0.8 },
    { x: 1100 * sx, y: 650 * sy, rx: 400 * sx, ry: 250 * sy, colours: ["rgba(200, 140, 40, 0.05)", "rgba(160, 100, 20, 0.1)", "rgba(100, 60, 10, 0.05)"], speed: -0.00005, phase: 2.5 },
    { x: 400 * sx, y: 700 * sy, rx: 350 * sx, ry: 200 * sy, colours: ["rgba(40, 180, 160, 0.05)", "rgba(20, 140, 120, 0.1)", "rgba(10, 90, 80, 0.05)"], speed: 0.00007, phase: -1.5 },
    { x: 1300 * sx, y: 350 * sy, rx: 300 * sx, ry: 350 * sy, colours: ["rgba(130, 40, 220, 0.05)", "rgba(90, 20, 180, 0.1)", "rgba(50, 10, 120, 0.05)"], speed: -0.00009, phase: 0.5 },
  ];

  var blurred = document.createElement("canvas");
  blurred.width = width;
  blurred.height = height;
  var bCtx = blurred.getContext("2d");

  for (var c of centres) {
    var ox = Math.sin(t * 0.00003 + c.phase) * 30;
    var oy = Math.cos(t * 0.00004 + c.phase * 0.7) * 20;

    var grad = bCtx.createRadialGradient(c.x + ox, c.y + oy, 0, c.x + ox, c.y + oy, Math.max(c.rx, c.ry));
    for (var i = 0; i < c.colours.length; i++) {
      grad.addColorStop(i / (c.colours.length - 1), c.colours[i]);
    }
    bCtx.fillStyle = grad;
    bCtx.beginPath();
    bCtx.ellipse(c.x + ox, c.y + oy, c.rx, c.ry, c.phase * 0.1, 0, Math.PI * 2);
    bCtx.fill();
  }

  bgCtx.save();
  bgCtx.filter = "blur(40px)";
  bgCtx.drawImage(blurred, 0, 0);
  bgCtx.restore();
  bgCtx.filter = "none";
}

function drawBrightCore(t) {
  var pulse = Math.sin(t * 0.005) * 0.2 + 0.8;
  var cores = [
    { x: 650 * sx, y: 380 * sy, r: 80 * mScale, colour: "rgba(200, 150, 255, " + pulse * 0.18 + ")" },
    { x: 850 * sx, y: 520 * sy, r: 60 * mScale, colour: "rgba(100, 200, 255, " + pulse * 0.15 + ")" },
    { x: 500 * sx, y: 300 * sy, r: 100 * mScale, colour: "rgba(255, 150, 200, " + pulse * 0.12 + ")" },
  ];
  for (var c of cores) {
    var grad = bgCtx.createRadialGradient(c.x, c.y, 0, c.x, c.y, c.r);
    grad.addColorStop(0, c.colour);
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");
    bgCtx.fillStyle = grad;
    bgCtx.beginPath();
    bgCtx.arc(c.x, c.y, c.r, 0, Math.PI * 2);
    bgCtx.fill();
  }
}

// === Cassiopeia Constellation ===

var cassBase = { x: width * 0.13, y: height * 0.93 };
var cassSX = -6.5 * sx;
var cassSY = -12 * sy;

var cassWCoords = [];
for (var i = 0; i < consData[1].stars.length; i++) {
  var s = consData[1].stars[i];
  cassWCoords.push({
    x: cassBase.x + cassSX * s.ra,
    y: cassBase.y + cassSY * s.dec,
    size: starSize(s.mag),
    colour: spectralToHex(s.spec),
    name: s.name,
    mag: s.mag,
  });
}

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

var time = 0;

function animate() {
  time++;

  bgCtx.fillStyle = "#030308";
  bgCtx.fillRect(0, 0, width, height);

  drawNebulaGas(time);

  for (var d of dustLanes) { d.update(time); }

  drawBrightCore(time);

  for (var s of stars) { s.update(time); }

  drawConstellationStars(time);

  var d = new Date();
  var todayKey = ("0" + d.getDate()).slice(-2) + "/" + ("0" + (d.getMonth() + 1)).slice(-2);
  for (var i = 0; i < consData.length; i++) {
    if (consData[i].date === todayKey) {
      var pulse = Math.sin(time * 0.02) * 0.4 + 0.6;
      var grad = bgCtx.createRadialGradient(width * 0.4, height * 0.4, 0, width * 0.4, height * 0.4, 600 * mScale);
      grad.addColorStop(0, "rgba(255, 215, 0, " + pulse * 0.03 + ")");
      grad.addColorStop(0.5, "rgba(255, 215, 0, " + pulse * 0.015 + ")");
      grad.addColorStop(1, "rgba(255, 215, 0, 0)");
      bgCtx.fillStyle = grad;
      bgCtx.fillRect(0, 0, width, height);
      break;
    }
  }

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
  cassSX = -6.5 * sx;
  cassSY = -12 * sy;
  cassBase = { x: width * 0.13, y: height * 0.93 };
  for (var i = 0; i < consData[1].stars.length; i++) {
    var s = consData[1].stars[i];
    cassWCoords[i].x = cassBase.x + cassSX * s.ra;
    cassWCoords[i].y = cassBase.y + cassSY * s.dec;
  }
  // regenerate stars for new dimensions
  stars = [];
  for (var i = 1200; i > 0; i--) { stars.push(new BgStar()); }
  dustLanes = [
    new DustLane(200 * sx, 300 * sy, 800 * sx, 120 * sy, -0.2, 0.0002),
    new DustLane(900 * sx, 500 * sy, 700 * sx, 100 * sy, 0.3, 0.00015),
    new DustLane(400 * sx, 700 * sy, 600 * sx, 80 * sy, -0.1, 0.00025),
  ];
});