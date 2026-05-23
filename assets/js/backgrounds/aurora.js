var pageHeight, stars, bands, extraCons;
var bg = initCanvas(function(w, h, c) {
	rawWidth = w; rawHeight = h;
	width = w; height = h;
	pageHeight = Math.max(h * 4, document.body.scrollHeight || h * 4);
	c.height = pageHeight;
	c.style.height = pageHeight + "px";
	sx = w / 1920; sy = h / 1080;
	mScale = Math.min(sx, sy);
	stars = createBgStars(500, w, pageHeight, {yBias: 1.2, parallax: true});
	bands = [
		new AuroraBand(80 * sy, 180, [
			"rgba(0, 255, 100, 0.3)", "rgba(0, 200, 150, 0.2)", "rgba(100, 0, 200, 0.15)"
		], 0.0008, 0, 0.04),
		new AuroraBand(120 * sy, 200, [
			"rgba(0, 220, 120, 0.25)", "rgba(50, 255, 150, 0.2)", "rgba(150, 50, 255, 0.15)"
		], 0.001, 2.1, 0.06),
		new AuroraBand(160 * sy, 250, [
			"rgba(100, 255, 200, 0.2)", "rgba(200, 100, 255, 0.2)", "rgba(0, 255, 80, 0.15)"
		], 0.0006, 4.3, 0.08),
	];
	extraCons = buildExtraCons();
});
var bgCtx = bg.ctx;
var width = rawWidth, height = rawHeight;
var sx = bg.sx(), sy = bg.sy(), mScale = bg.mScale();
bg.canvas.style.position = "absolute";
bg.canvas.style.top = "0";
bg.canvas.style.left = "0";

var scrollY = 0;
window.addEventListener("scroll", function() { scrollY = window.scrollY; }, { passive: true });

function AuroraBand(yBase, height, colours, speed, phase, bandParallax) {
	this.yBase = yBase;
	this.height = height;
	this.colours = colours;
	this.speed = speed;
	this.phase = phase;
	this.bandParallax = bandParallax !== undefined ? bandParallax : 0.04;
}
AuroraBand.prototype.render = function(t) {
	var adjY = scrollY + this.yBase;
	var grad = bgCtx.createLinearGradient(0, adjY - 30, 0, adjY + this.height + 30);
	for (var i = 0; i < this.colours.length; i++) {
		grad.addColorStop(i / (this.colours.length - 1), this.colours[i]);
	}
	bgCtx.save();
	bgCtx.globalAlpha = 0.18;
	bgCtx.fillStyle = grad;
	bgCtx.beginPath();
	bgCtx.moveTo(0, adjY);
	for (var x = 0; x <= width; x += 8) {
		var y = adjY
			+ Math.sin(x * 0.008 + t * this.speed + this.phase) * 25
			+ Math.sin(x * 0.015 + t * this.speed * 0.7 + this.phase * 1.3) * 15
			+ Math.sin(x * 0.003 + t * this.speed * 1.3 + this.phase * 0.7) * 20;
		bgCtx.lineTo(x, y);
	}
	bgCtx.lineTo(width, adjY + this.height);
	bgCtx.lineTo(0, adjY + this.height);
	bgCtx.closePath();
	bgCtx.fill();
	bgCtx.restore();

	bgCtx.save();
	bgCtx.globalAlpha = 0.15;
	bgCtx.filter = "blur(20px)";
	bgCtx.fillStyle = grad;
	bgCtx.beginPath();
	bgCtx.moveTo(0, adjY);
	for (var x = 0; x <= width; x += 8) {
		var y = adjY
			+ Math.sin(x * 0.008 + t * this.speed + this.phase) * 25
			+ Math.sin(x * 0.015 + t * this.speed * 0.7 + this.phase * 1.3) * 15
			+ Math.sin(x * 0.003 + t * this.speed * 1.3 + this.phase * 0.7) * 20;
		bgCtx.lineTo(x, y);
	}
	bgCtx.lineTo(width, adjY + this.height + 40);
	bgCtx.lineTo(0, adjY + this.height + 40);
	bgCtx.closePath();
	bgCtx.fill();
	bgCtx.restore();
	bgCtx.filter = "none";
};

var time = 0;

function getDateColour() {
	var key = getDateKey();
	for (var consKey in consDataByName) {
		var c = consDataByName[consKey];
		if (c.date === key) {
			var s = c.stars;
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
		{ name: "CASSIOPEIA", cx: width * 0.1, cy: height * 0.12, sc: 2, rC: 0, dC: 60, plx: 0.3 },
		{ name: "ORION", cx: width * 0.85, cy: height * 0.78, sc: 8, rC: 5.5, dC: 0, plx: 0.35 },
		{ name: "LYRA", cx: width * 0.92, cy: height * 0.1, sc: 8, rC: 18.6, dC: 38, plx: 0.32 },
		{ name: "CYGNUS", cx: width * 0.88, cy: height * 0.32, sc: 10, rC: 20.5, dC: 40, plx: 0.28 },
		{ name: "SCORPIUS", cx: width * 0.12, cy: height * 0.85, sc: 6, rC: 16.8, dC: -35, plx: 0.3 },
		{ name: "ANDROMEDA", cx: width * 0.06, cy: height * 0.45, sc: 3, rC: 1.5, dC: 40, plx: 0.35 },
	];
	for (var i = 0; i < configs.length; i++) {
		var c = configs[i];
		var data = consDataByName[c.name];
		if (!data) continue;
		cons.push({
			pts: projectConstellation(data, c.cx, c.cy, c.sc, c.rC, c.dC),
			connections: data.connections,
			mainIndices: data.mainIndices,
			parallax: c.plx,
		});
	}
	return cons;
}

function drawMountains() {
	var baseY = scrollY + height * 0.85;
	bgCtx.fillStyle = "#060612";
	bgCtx.beginPath();
	bgCtx.moveTo(0, baseY);
	for (var x = 0; x <= width; x += 15) {
		var h = Math.sin(x * 0.015) * 20 + Math.sin(x * 0.04) * 10 + Math.sin(x * 0.008) * 30 + 25;
		bgCtx.lineTo(x, baseY - h);
	}
	bgCtx.lineTo(width, baseY + 100);
	bgCtx.lineTo(0, baseY + 100);
	bgCtx.closePath();
	bgCtx.fill();
}

function animate() {
	time++;

	bgCtx.fillStyle = "#08081a";
	bgCtx.fillRect(0, 0, width, pageHeight);

	var skyGrad = bgCtx.createLinearGradient(0, 0, 0, height * 0.85);
	skyGrad.addColorStop(0, "#08081a");
	skyGrad.addColorStop(0.4, "#0a0a24");
	skyGrad.addColorStop(0.7, "#0d0d1e");
	skyGrad.addColorStop(1, "#0a0a14");
	bgCtx.fillStyle = skyGrad;
	bgCtx.fillRect(0, 0, width, pageHeight);

	var dc = getDateColour();
	if (dc) {
		var pulse = Math.sin(time * 0.02) * 0.5 + 0.5;
		for (var b of bands) {
			var adjY = scrollY + b.yBase;
			var extra = "rgba(" + dc[0] + ", " + dc[1] + ", " + dc[2] + ", " + pulse * 0.08 + ")";
			var colours = b.colours.slice();
			colours.push(extra);
			var grad = bgCtx.createLinearGradient(0, adjY - 30, 0, adjY + b.height + 30);
			for (var i = 0; i < colours.length; i++) {
				grad.addColorStop(i / (colours.length - 1), colours[i]);
			}
			bgCtx.save();
			bgCtx.globalAlpha = 0.3;
			bgCtx.fillStyle = grad;
			bgCtx.beginPath();
			bgCtx.moveTo(0, adjY);
			for (var x = 0; x <= width; x += 8) {
				var y = adjY
					+ Math.sin(x * 0.008 + time * b.speed + b.phase) * 25
					+ Math.sin(x * 0.015 + time * b.speed * 0.7 + b.phase * 1.3) * 15
					+ Math.sin(x * 0.003 + time * b.speed * 1.3 + b.phase * 0.7) * 20;
				bgCtx.lineTo(x, y);
			}
			bgCtx.lineTo(width, adjY + b.height);
			bgCtx.lineTo(0, adjY + b.height);
			bgCtx.closePath();
			bgCtx.fill();
			bgCtx.restore();
		}
	} else {
		for (var b of bands) { b.render(time); }
	}

	renderBgStars(bgCtx, stars, time, undefined, scrollY);

	for (var ec of extraCons) {
		renderConstellationStars(bgCtx, ec.pts, ec.mainIndices, time, scrollY, ec.parallax);
		renderConstellationLines(bgCtx, ec.pts, ec.connections, "rgba(255, 255, 255, 0.15)", scrollY, ec.parallax);
	}

	drawMountains();

	requestAnimFrame(animate);
}

animate();
