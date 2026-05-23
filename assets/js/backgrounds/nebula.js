var cassData = consDataByName.CASSIOPEIA;
var cassPts = [];

var pageHeight;
var bg = initCanvas(function(w, h, c) {
	rawWidth = w; rawHeight = h;
	width = w; height = h;
	pageHeight = Math.max(h * 4, document.body.scrollHeight || h * 4);
	c.height = pageHeight;
	c.style.height = pageHeight + "px";
	sx = w / 1920; sy = h / 1080;
	mScale = Math.min(sx, sy);
	stars = createBgStars(1200, w, pageHeight, { parallax: true });
	dustLanes = [
		new DustLane(200 * sy, 300 * sy, 800 * sx, 120 * sy, -0.2, 0.0002),
		new DustLane(900 * sx, 500 * sy, 700 * sx, 100 * sy, 0.3, 0.00015),
		new DustLane(400 * sx, 700 * sy, 600 * sx, 80 * sy, -0.1, 0.00025),
	];
	projectConstellationLocal();
});
var bgCtx = bg.ctx;
var width = rawWidth, height = rawHeight;
var sx = bg.sx(), sy = bg.sy(), mScale = bg.mScale();
bg.canvas.style.position = "absolute";
bg.canvas.style.top = "0";
bg.canvas.style.left = "0";

var scrollY = 0;
window.addEventListener("scroll", function() { scrollY = window.scrollY; }, { passive: true });

var nebulaMult = 2.5;
var scrollDrift = 0.05;

function noise2D(x, y, t) {
  return Math.sin(x * 0.003 + t * 0.0003) * 0.5 +
         Math.sin(y * 0.004 + t * 0.0002) * 0.3 +
         Math.sin((x + y) * 0.002 + t * 0.0004) * 0.2;
}

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
  var driftY = this.yBase + scrollY * (1 - scrollDrift);
  bgCtx.save();
  bgCtx.translate(this.xBase, driftY);
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
    var oy = Math.cos(t * 0.00004 + c.phase * 0.7) * 20 + scrollY * (1 - scrollDrift);

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
    var cy = c.y + scrollY * (1 - scrollDrift);
    var grad = bgCtx.createRadialGradient(c.x, cy, 0, c.x, cy, c.r);
    grad.addColorStop(0, c.colour);
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");
    bgCtx.fillStyle = grad;
    bgCtx.beginPath();
    bgCtx.arc(c.x, cy, c.r, 0, Math.PI * 2);
    bgCtx.fill();
  }
}

// === Cassiopeia Constellation ===

function projectConstellationLocal() {
  var sc = 12 * sy;
  var cosFac = 6.5 * sx / (12 * sy);
  if (cosFac > 1) cosFac = 1;
  var dC = Math.acos(cosFac) * 180 / Math.PI;
  var cx = width * 0.13;
  var cy = height * 0.93 - sc * dC;
  cassPts = projectConstellation(cassData, cx, cy, sc, 0, dC);
}

function drawConstellationLabel() {
  bgCtx.font = "11px sans-serif";
  bgCtx.textAlign = "center";
  bgCtx.fillStyle = "rgba(255, 255, 255, 0.24)";
  var labelX = 0, minY = Infinity;
  for (var i = 0; i < 5; i++) {
    var s = cassPts[i];
    labelX += s.x;
    if (s.y < minY) minY = s.y;
  }
  bgCtx.fillText("Cassiopeia", labelX / 5, minY - 20 + scrollY * (1 - 0.65));
}

var time = 0;

function animate() {
  time++;

  bgCtx.fillStyle = "#030308";
  bgCtx.fillRect(0, 0, width, pageHeight);

  drawNebulaGas(time);

  for (var d of dustLanes) { d.update(time); }

  drawBrightCore(time);

	renderBgStars(bgCtx, stars, time, undefined, scrollY);

	renderConstellationLines(bgCtx, cassPts, cassData.connections, "rgba(255, 255, 255, 0.15)", scrollY, 0.65);
	renderConstellationStars(bgCtx, cassPts, cassData.mainIndices, time, scrollY, 0.65);
  drawConstellationLabel();

  var todayKey = getDateKey();
  for (var key in consDataByName) {
    if (consDataByName[key].date === todayKey) {
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
