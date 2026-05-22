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

var stars = createBgStars(500, width, height);

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
			var s = consData[i].stars;
			var bri = null, briMag = Infinity;
			for (var j = 0; j < s.length; j++) {
				if (s[j].mag < briMag) {
					briMag = s[j].mag;
					bri = s[j];
				}
			}
			if (bri) {
				var hex = spectralToHex(bri.spec || "G2V");
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

function buildExtraCons() {
	var cons = [];
	var configs = [
		{ idx: 1, cx: width * 0.4, cy: height * 0.2, sc: 2, rC: 0, dC: 60 },
		{ idx: 0, cx: width * 0.6, cy: height * 0.35, sc: 8, rC: 5.5, dC: 0 },
		{ idx: 2, cx: width * 0.8, cy: height * 0.2, sc: 8, rC: 18.6, dC: 38 },
		{ idx: 3, cx: width * 0.85, cy: height * 0.3, sc: 10, rC: 20.5, dC: 40 },
		{ idx: 5, cx: width * 0.5, cy: height * 0.7, sc: 6, rC: 16.8, dC: -35 },
		{ idx: 6, cx: width * 0.2, cy: height * 0.5, sc: 3, rC: 1.5, dC: 40 },
	];
	for (var i = 0; i < configs.length; i++) {
		var c = configs[i];
		var data = consData[c.idx];
		if (!data) continue;
		if (!data.always && data.date !== getDateKey()) continue;
		cons.push({
			pts: projectConstellation(data, c.cx, c.cy, c.sc, c.rC, c.dC),
			connections: data.connections,
			mainIndices: data.mainIndices,
		});
	}
	return cons;
}
var extraCons = buildExtraCons();

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

	renderBgStars(bgCtx, stars, time);

	for (var ec of extraCons) {
		renderConstellationStars(bgCtx, ec.pts, ec.mainIndices, time);
		renderConstellationLines(bgCtx, ec.pts, ec.connections, "rgba(255, 255, 255, 0.15)");
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
	stars = createBgStars(500, width, height);
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