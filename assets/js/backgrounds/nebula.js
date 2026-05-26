var pageHeight;
var bg = initCanvas(function(w, h, c) {
	rawWidth = w; rawHeight = h;
	width = w; height = h;
	if (!pageHeight) pageHeight = Math.max(document.body.scrollHeight, h) || h;
	c.height = pageHeight;
	c.style.height = pageHeight + "px";
	sx = w / 1920; sy = h / 1080;
	mScale = Math.min(sx, sy);
	stars = createBgStars(800, w, pageHeight, { parallax: true });
	cons = buildCons();
});
var bgCtx = bg.ctx;
var width = rawWidth, height = rawHeight;
var sx = bg.sx(), sy = bg.sy(), mScale = bg.mScale();
bg.canvas.style.position = "absolute";
bg.canvas.style.top = "0";
bg.canvas.style.left = "0";

var scrollDrift = 0.05;


function noise2D(x, y, t) {
  return Math.sin(x * 0.003 + t * 0.0003) * 0.5 +
         Math.sin(y * 0.004 + t * 0.0002) * 0.3 +
         Math.sin((x + y) * 0.002 + t * 0.0004) * 0.2;
}

// === Nebula gas (viewport-fixed, time-animated) ===
var _gasBuf = null, _gasCtx = null;
function drawNebulaGas(t, sy) {
  if (!_gasBuf || _gasBuf.width !== width) {
    _gasBuf = document.createElement("canvas");
    _gasBuf.width = width;
    _gasBuf.height = height * 0.85;
    _gasCtx = _gasBuf.getContext("2d");
  }
  _gasCtx.clearRect(0, 0, _gasBuf.width, _gasBuf.height);
  var centres = [
    { x: 500 * sx, y: 350 * sy, rx: 450 * sx, ry: 300 * sy, colours: ["rgba(180, 40, 200, 0.06)", "rgba(120, 20, 160, 0.1)", "rgba(60, 10, 100, 0.05)"], speed: 0.00008, phase: 0 },
    { x: 900 * sx, y: 500 * sy, rx: 500 * sx, ry: 350 * sy, colours: ["rgba(30, 80, 200, 0.05)", "rgba(20, 50, 160, 0.08)", "rgba(10, 20, 100, 0.03)"], speed: -0.00006, phase: 1.5 },
    { x: 700 * sx, y: 350 * sy, rx: 350 * sx, ry: 250 * sy, colours: ["rgba(255, 80, 120, 0.05)", "rgba(200, 40, 80, 0.08)", "rgba(140, 20, 60, 0.03)"], speed: 0.0001, phase: -0.8 },
    { x: 1100 * sx, y: 650 * sy, rx: 400 * sx, ry: 250 * sy, colours: ["rgba(200, 140, 40, 0.03)", "rgba(160, 100, 20, 0.06)", "rgba(100, 60, 10, 0.03)"], speed: -0.00005, phase: 2.5 },
    { x: 400 * sx, y: 700 * sy, rx: 350 * sx, ry: 200 * sy, colours: ["rgba(40, 180, 160, 0.03)", "rgba(20, 140, 120, 0.06)", "rgba(10, 90, 80, 0.03)"], speed: 0.00007, phase: -1.5 },
    { x: 1300 * sx, y: 350 * sy, rx: 300 * sx, ry: 350 * sy, colours: ["rgba(130, 40, 220, 0.03)", "rgba(90, 20, 180, 0.06)", "rgba(50, 10, 120, 0.03)"], speed: -0.00009, phase: 0.5 },
  ];
  for (var c of centres) {
    var ox = Math.sin(t * 0.00003 + c.phase) * 30;
    var oy = Math.cos(t * 0.00004 + c.phase * 0.7) * 20 + sy * (1 - scrollDrift);
    var grad = _gasCtx.createRadialGradient(c.x + ox, c.y + oy, 0, c.x + ox, c.y + oy, Math.max(c.rx, c.ry));
    for (var i = 0; i < c.colours.length; i++)
      grad.addColorStop(i / (c.colours.length - 1), c.colours[i]);
    _gasCtx.fillStyle = grad;
    _gasCtx.beginPath();
    _gasCtx.ellipse(c.x + ox, c.y + oy, c.rx, c.ry, c.phase * 0.1, 0, Math.PI * 2);
    _gasCtx.fill();
  }
  bgCtx.drawImage(_gasBuf, 0, 0, _gasBuf.width, _gasBuf.height, 0, sy, width, _gasBuf.height);
}

// === Bright cores (viewport-fixed) ===
function drawBrightCore(t, sy) {
  var pulse = Math.sin(t * 0.005) * 0.2 + 0.8;
  var cores = [
    { x: 650 * sx, y: 380 * sy, r: 80 * mScale, colour: "rgba(200, 150, 255, " + pulse * 0.18 + ")" },
    { x: 850 * sx, y: 520 * sy, r: 60 * mScale, colour: "rgba(100, 200, 255, " + pulse * 0.15 + ")" },
    { x: 500 * sx, y: 300 * sy, r: 100 * mScale, colour: "rgba(255, 150, 200, " + pulse * 0.12 + ")" },
  ];
  for (var c of cores) {
    var cy = c.y + sy * (1 - scrollDrift);
    var grad = bgCtx.createRadialGradient(c.x, cy, 0, c.x, cy, c.r);
    grad.addColorStop(0, c.colour);
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");
    bgCtx.fillStyle = grad;
    bgCtx.beginPath();
    bgCtx.arc(c.x, cy, c.r, 0, Math.PI * 2);
    bgCtx.fill();
  }
}

// === Constellations ===
function buildCons() {
	return buildConstellations([
		{ name: "CASSIOPEIA", label: "Cassiopeia", cx: width * 0.15, cy: height * 0.2, sc: 12 * sy, plx: 0.2, onlyMain: true },
		{ name: "ANDROMEDA", label: "Andromeda", cx: width * 0.75, cy: height * 0.3, sc: 5 * sx, plx: 0.15, onlyMain: true },
		{ name: "SCORPIUS", label: "Scorpius", cx: width * 0.2, cy: height * 0.8, sc: 6 * sx, plx: 0.25, onlyMain: true },
	]);
}

var time = 0;

function animate() {
  time++;
  var sy = window.getScrollY ? window.getScrollY() : 0;

  bgCtx.fillStyle = "#030308";
  bgCtx.fillRect(0, sy - 50, width, height + 100);

  drawNebulaGas(time, sy);

  drawBrightCore(time, sy);

  renderBgStars(bgCtx, stars, time, undefined, sy);

  for (var ec of cons) {
    renderConstellationLines(bgCtx, ec.pts, ec.connections, "rgba(255, 255, 255, 0.12)", sy, ec.parallax);
    renderConstellationStars(bgCtx, ec.pts, ec.mainIndices, time, sy, ec.parallax);
  }

  // Labels
  bgCtx.font = "11px sans-serif";
  bgCtx.textAlign = "center";
  bgCtx.fillStyle = "rgba(255, 255, 255, 0.2)";
  for (var ec of cons) {
    if (!ec.pts || ec.pts.length === 0 || !ec.label) continue;
    var lx = 0, lowestY = -Infinity, n = 0;
    var idxs = ec.mainIndices || [];
    if (idxs.length === 0) idxs = [0];
    for (var j = 0; j < Math.min(4, idxs.length); j++) {
      var p = ec.pts[idxs[j]];
      if (p) { lx += p.x; n++; if (p.y > lowestY) lowestY = p.y; }
    }
    if (n > 0)
      bgCtx.fillText(ec.label, lx / n, lowestY + 16 + sy * (1 - ec.parallax));
  }

  var todayKey = getDateKey();
  for (var key in consDataByName) {
    if (consDataByName[key].date === todayKey) {
      var pulse = Math.sin(time * 0.02) * 0.4 + 0.6;
      var grad = bgCtx.createRadialGradient(width * 0.4, height * 0.4, 0, width * 0.4, height * 0.4, 600 * mScale);
      grad.addColorStop(0, "rgba(255, 215, 0, " + pulse * 0.03 + ")");
      grad.addColorStop(0.5, "rgba(255, 215, 0, " + pulse * 0.015 + ")");
      grad.addColorStop(1, "rgba(255, 215, 0, 0)");
      bgCtx.fillStyle = grad;
      bgCtx.fillRect(0, sy - 50, width, height + 100);
      break;
    }
  }

  requestAnimFrame(animate);
}

animate();
