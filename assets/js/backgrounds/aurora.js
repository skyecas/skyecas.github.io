var pageHeight;
var bg = initCanvas(function(w, h, c) {
	rawWidth = w; rawHeight = h;
	width = w; height = h;
	if (!pageHeight) {
		pageHeight = Math.max(document.body.scrollHeight, h) || h;
	}
	c.height = pageHeight;
	c.style.height = pageHeight + "px";
	sx = w / 1920; sy = h / 1080;
	mScale = Math.min(sx, sy);
	stars = createBgStars(300, w, pageHeight, {yBias: 1.2, parallax: true, twinkle: false});
	bands = [
		new AuroraBand(0, height * 0.45, ["rgba(0, 255, 100, 0.4)", "rgba(0, 200, 150, 0.3)", "rgba(100, 0, 200, 0.2)"], 0.0008, 0, 0.80),
		new AuroraBand(height * 0.3, height * 0.4, ["rgba(0, 220, 120, 0.35)", "rgba(50, 255, 150, 0.3)", "rgba(150, 50, 255, 0.2)"], 0.001, 2.1, 0.90),
		new AuroraBand(height * 0.55, height * 0.35, ["rgba(100, 255, 200, 0.3)", "rgba(200, 100, 255, 0.25)", "rgba(0, 255, 80, 0.2)"], 0.0006, 4.3, 0.97),
	];
	cons = buildCons();
});
var bgCtx = bg.ctx;
var width = rawWidth, height = rawHeight;
var sx = bg.sx(), sy = bg.sy(), mScale = bg.mScale();
bg.canvas.style.position = "absolute";
bg.canvas.style.top = "0";
bg.canvas.style.left = "0";

function AuroraBand(yBase, height, colours, speed, phase, bandParallax) {
	this.yBase = yBase;
	this.height = height;
	this.colours = colours;
	this.speed = speed;
	this.phase = phase;
	this.bandParallax = bandParallax || 0.97;
}
AuroraBand.prototype.render = function(t, sy) {
	var adjY = this.yBase + sy * (1 - this.bandParallax);
	var grad = bgCtx.createLinearGradient(0, adjY - 30, 0, adjY + this.height + 30);
	for (var i = 0; i < this.colours.length; i++)
		grad.addColorStop(i / (this.colours.length - 1), this.colours[i]);
	bgCtx.save();
	bgCtx.globalAlpha = 0.18;
	bgCtx.fillStyle = grad;
	bgCtx.beginPath();
	bgCtx.moveTo(0, adjY);
	for (var x = 0; x <= width; x += 8) {
		var y = adjY + Math.sin(x * 0.008 + t * this.speed + this.phase) * 25
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
		var y = adjY + Math.sin(x * 0.008 + t * this.speed + this.phase) * 25
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

function buildCons() {
	var cons = [];
	var configs = [
		{ name: "CASSIOPEIA", label: "Cassiopeia", cx: width * 0.08, cy: height * 0.12, sc: 13 * sx, plx: 0.05 },
		{ name: "ORION", label: "Orion", cx: width * 0.92, cy: height * 0.2, sc: 8 * sx, plx: 0.1 },
		{ name: "LYRA", label: "Lyra", cx: width * 0.06, cy: height * 0.5, sc: 8 * sx, plx: 0.08 },
		{ name: "CYGNUS", label: "Cygnus", cx: width * 0.88, cy: height * 0.55, sc: 8 * sx, plx: 0.06 },
		{ name: "SCORPIUS", label: "Scorpius", cx: width * 0.12, cy: height * 0.82, sc: 6 * sx, plx: 0.07 },
		{ name: "ANDROMEDA", label: "Andromeda", cx: width * 0.94, cy: height * 0.4, sc: 5 * sx, plx: 0.05 },
	];
	for (var i = 0; i < configs.length; i++) {
		var c = configs[i];
		var data = consDataByName[c.name];
		if (!data) continue;
		cons.push({
			pts: projectConstellation(data, c.cx, c.cy, c.sc),
			connections: data.connections,
			mainIndices: data.mainIndices,
			parallax: c.plx,
			label: c.label,
		});
	}
	return cons;
}

function getDateColour() {
	var key = getDateKey();
	for (var consKey in consDataByName) {
		var c = consDataByName[consKey];
		if (c.date === key) {
			var bri = null, briMag = Infinity;
			for (var j = 0; j < c.stars.length; j++) {
				if (c.stars[j].mag < briMag) { briMag = c.stars[j].mag; bri = c.stars[j]; }
			}
			if (bri) {
				var hex = spectralToHex(bri.spec || "G2V");
				return [parseInt(hex.slice(1,3),16), parseInt(hex.slice(3,5),16), parseInt(hex.slice(5,7),16)];
			}
		}
	}
	return null;
}

function getY() {
	return window.lenisScroll !== undefined ? window.lenisScroll
		: document.documentElement.scrollTop || window.pageYOffset || 0;
}

var mountainLayers = [
	{ colour: "#030308", drift: 1, amp: 20, freq: 0.012, heightMul: 0.25 },
	{ colour: "#050510", drift: 3, amp: 40, freq: 0.025, heightMul: 0.35 },
	{ colour: "#08081a", drift: 6, amp: 60, freq: 0.04, heightMul: 0.45 },
];

function drawMountains(sy) {
	for (var m = 0; m < mountainLayers.length; m++) {
		var layer = mountainLayers[m];
		var bottomY = pageHeight;
		var topY = bottomY - height * layer.heightMul;
		var topY = bottomY - height * layer.heightMul;
		bgCtx.fillStyle = layer.colour;
		bgCtx.beginPath();
		bgCtx.moveTo(0, bottomY);
		for (var x = 0; x <= width; x += 15) {
			var h = Math.sin(x * layer.freq + sy * layer.drift * 0.001) * layer.amp
				+ Math.sin(x * layer.freq * 2.5 + sy * layer.drift * 0.002) * layer.amp * 0.4
				+ Math.sin(x * layer.freq * 0.5 + sy * layer.drift * 0.0005) * layer.amp * 0.6;
			bgCtx.lineTo(x, topY - h);
		}
		bgCtx.lineTo(width, bottomY + 200);
		bgCtx.lineTo(0, bottomY + 200);
		bgCtx.closePath();
		bgCtx.fill();
	}
}

var time = 0;

function animate() {
	time++;
	var sy = getY();

	bgCtx.fillStyle = "#08081a";
	bgCtx.fillRect(0, sy, width, height);

	var skyGrad = bgCtx.createLinearGradient(0, sy, 0, sy + height);
	skyGrad.addColorStop(0, "#08081a");
	skyGrad.addColorStop(0.4, "#0a0a24");
	skyGrad.addColorStop(0.7, "#0d0d1e");
	skyGrad.addColorStop(1, "#0a0a14");
	bgCtx.fillStyle = skyGrad;
	bgCtx.fillRect(0, sy, width, height);

	var dc = getDateColour();
	if (dc) {
		var pulse = Math.sin(time * 0.02) * 0.5 + 0.5;
		for (var b of bands) {
			var adjY = b.yBase + sy * (1 - b.bandParallax);
			var colours = b.colours.slice();
			colours.push("rgba(" + dc[0] + ", " + dc[1] + ", " + dc[2] + ", " + pulse * 0.08 + ")");
			var grad = bgCtx.createLinearGradient(0, adjY - 30, 0, adjY + b.height + 30);
			for (var i = 0; i < colours.length; i++)
				grad.addColorStop(i / (colours.length - 1), colours[i]);
			bgCtx.save();
			bgCtx.globalAlpha = 0.3;
			bgCtx.fillStyle = grad;
			bgCtx.beginPath();
			bgCtx.moveTo(0, adjY);
			for (var x = 0; x <= width; x += 8) {
				var y = adjY + Math.sin(x * 0.008 + time * b.speed + b.phase) * 25
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
		for (var b of bands) { b.render(time, sy); }
	}

	renderBgStars(bgCtx, stars, time, undefined, sy);

	for (var ec of cons) {
		renderConstellationStars(bgCtx, ec.pts, ec.mainIndices, time, sy, ec.parallax);
		renderConstellationLines(bgCtx, ec.pts, ec.connections, "rgba(255, 255, 255, 0.15)", sy, ec.parallax);
	}

	// Labels below lowest main star of each constellation
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
		if (n > 0) {
			bgCtx.fillText(ec.label, lx / n, lowestY + 16 + sy * (1 - ec.parallax));
		}
	}

	drawMountains(sy);

	requestAnimFrame(animate);
}

animate();