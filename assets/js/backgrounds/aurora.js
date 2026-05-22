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

function BgStar() {
	this.x = Math.random() * width;
	this.y = Math.random() * height * 0.8;
	this.size = Math.random() * 1.5 + 0.1;
	this.colour = spectralToHex(randomSpectralType());
	this.phase = Math.random() * Math.PI * 2;
	this.speed = 0.02 + Math.random() * 0.03;
}
BgStar.prototype.update = function(t) {
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
for (var i = 500; i > 0; i--) { stars.push(new BgStar()); }

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

function getDateColour() {
	var key = getDateKey();
	for (var i = 0; i < consData.length; i++) {
		if (consData[i].date === key) {
			var c = new Constellation(consData[i]);
			var bri = null, briMag = Infinity;
			for (var j = 0; j < c.stars.length; j++) {
				if (c.stars[j].mag < briMag) {
					briMag = c.stars[j].mag;
					bri = c.stars[j];
				}
			}
			if (bri) {
				var hex = bri.getColour();
				return [
					parseInt(hex.slice(1,3), 16),
					parseInt(hex.slice(3,5), 16),
					parseInt(hex.slice(5,7), 16),
				];
			}
		}
	}
	return null;
}

// Cassiopeia stars projected to their screen position
var cassBase = { x: 250 * sx, y: 1000 * sy };
var cassSX = -6.5 * sx;
var cassSY = -12 * sy;

var cassConst = new Constellation(consData[1]);
var cassWCoords = [];
for (var i = 0; i < cassConst.stars.length; i++) {
	var s = cassConst.stars[i];
	cassWCoords.push({
		x: cassBase.x + cassSX * s.ra,
		y: cassBase.y + cassSY * s.dec,
		size: s.getSize(),
		colour: s.getColour(),
		name: s.name,
		mag: s.mag,
	});
}
var cassiopeiaConnections = cassConst.connections;

// Build extra constellation display objects from shared consData
function buildExtraCons() {
	var cons = [];
	var spec = [
		{ name:"Lyra",		cx:200*sx,	cy:135*sy,	sc:16*mScale, rC:281.92, dC:35.61 },
		{ name:"Cygnus",	cx:1700*sx, cy:145*sy,	sc:9*mScale,  rC:304.64, dC:37.77 },
		{ name:"Gemini",	cx:180*sx,	cy:580*sy,	sc:10*mScale, rC:108.09, dC:24.69 },
		{ name:"Scorpius",	cx:1730*sx, cy:640*sy,	sc:8*mScale,  rC:251.69, dC:-29.88 },
		{ name:"Andromeda", cx:960*sx,	cy:165*sy,	sc:13*mScale, rC:14.50,  dC:36.25 },
		{ name:"Orion",		cx:1700*sx, cy:420*sy,	sc:10*mScale, rC:83.96,  dC:-1.62 },
	];
	for (var i = 0; i < spec.length; i++) {
		var s = spec[i];
		var consDataEntry = null;
		for (var j = 0; j < consData.length; j++) {
			if (consData[j].name === s.name) { consDataEntry = consData[j]; break; }
		}
		if (!consDataEntry) continue;
		var c = new Constellation(consDataEntry);
		cons.push({
			n: c.name,
			cx: s.cx, cy: s.cy, sc: s.sc, rC: s.rC, dC: s.dC,
			pts: c.project(s.cx, s.cy, s.sc, s.rC, s.dC),
			m: c.mainIndices,
			c: c.connections,
			date: consDataEntry.date,
			always: consDataEntry.always,
		});
	}
	return cons;
}
var extraCons = buildExtraCons();

function drawConstellationDef(d, t) {
	var prom = d.always || (d.date && d.date === getDateKey()) ? 1.0 : 0.35;
	var pts = d.pts;

	var connAlpha = 0.04 + prom * 0.12;
	var glowMul = 0.15 + prom * 0.15;
	var starMul = 0.3 + prom * 0.5;

	var minMag = Infinity;
	for (var pi of pts) if (pi.mag !== undefined && pi.mag < minMag) minMag = pi.mag;

	for (var pi of pts) {
		var tw = Math.sin(t * 0.02 + pi.x * 0.005) * 0.3 + 0.7;
		var magFactor = pi.mag !== undefined ? Math.max(0.12, 1 - (pi.mag - minMag) * 0.35) : 1;
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

	var dc = getDateColour();
	if (dc) {
		var pulse = Math.sin(time * 0.02) * 0.5 + 0.5;
		for (var b of bands) {
			var extra = "rgba(" + dc[0] + ", " + dc[1] + ", " + dc[2] + ", " + pulse * 0.08 + ")";
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
	cassConst = new Constellation(consData[1]);
	for (var i = 0; i < cassConst.stars.length; i++) {
		var s = cassConst.stars[i];
		cassWCoords[i].x = cassBase.x + cassSX * s.ra;
		cassWCoords[i].y = cassBase.y + cassSY * s.dec;
		cassWCoords[i].size = s.getSize();
		cassWCoords[i].colour = s.getColour();
	}
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
	extraCons = buildExtraCons();
});