var pageHeight;
var bg = initCanvas(function(w, h, c) {
	width = w; height = h;
	if (!pageHeight) pageHeight = Math.max(document.body.scrollHeight, h) || h;
	c.height = pageHeight;
	c.style.height = pageHeight + "px";
});
var bgCtx = bg.ctx;
bg.canvas.style.position = "absolute";

bgCtx.fillStyle = "#110E19";
bgCtx.fillRect(0, 0, width, pageHeight);

// === Constellations ===
var cons = buildCons();

function buildCons() {
	var configs = [
		{ name: "CASSIOPEIA", cx: width * 0.15, cy: height * 0.25, sc: 13 * (width / 1920), plx: 0.7 },
		{ name: "ORION", cx: width * 0.85, cy: height * 0.75, sc: 7 * (width / 1920), plx: 0.8 },
	];
	var arr = [];
	for (var i = 0; i < configs.length; i++) {
		var c = configs[i];
		var data = consDataByName[c.name];
		if (!data) continue;
		arr.push({
			pts: projectConstellation(data, c.cx, c.cy, c.sc, undefined, undefined, false),
			connections: data.connections,
			mainIndices: data.mainIndices,
			parallax: c.plx,
			label: c.name,
		});
	}
	return arr;
}

// === Background stars via shared.js ===
function ShootingStar(special) {
	if (special === undefined) special = false;
	this.special = special;
	this.reset(-200);
}

function Satellite() {
	this.y = Math.random() * height;
	this.x = Math.random() * width;
	this.speed = (Math.random() * .29) + .01;
	this.size = (Math.random() * 2) + 0.1;
	this.colour = "white";
	this.waitTime = new Date().getTime();
	this.active = true;
}

ShootingStar.prototype.update = function() {
	if (this.active) {
		this.x -= this.speed;
		this.y += this.speed;
		if (this.x < -this.len || this.y > height + this.len || this.y < -this.len) {
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

Satellite.prototype.update = function() {
	if (this.active) {
		this.x -= this.speed;
		if (this.x < 0 || this.y > height || this.y < 0) {
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

ShootingStar.prototype.reset = function(x) {
	if (x === undefined) x = "0";
	var pos = Math.random() * (width + height);
	this.y = Math.max(0, pos - width);
	(x=="0") ? this.x = Math.min(width, pos) : this.x=x;
	this.len = (Math.random() * 80) + 10;
	this.size = (Math.random() * 1) + 0.1;
	this.speed = (Math.random() * 10) + 5;
	this.colour = spectralToHex(randomSpectralType());
	this.waitTime = new Date().getTime() + (Math.random() * 20000);
	this.active = false;
}

Satellite.prototype.reset = function() {
	this.y = Math.random() * height;
	this.x = width;
	this.speed = (Math.random() * .19) + .01;
	this.size = (Math.random() * 2) + 0.1;
	this.colour = "white";
	this.waitTime = new Date().getTime() + (Math.random() * 20000);
	this.active = false;
}

var isSpecialDate = false;
var stars = [];
var movers = [];

stars = createBgStars(600, width, pageHeight, { parallax: true });

for (var i = 10; i > 0; i--) { movers.push(new Satellite()); }
for (var i = 1; i > 0; i--) { movers.push(new ShootingStar()); }
for (var i = 20; i > 0; i--) { movers.push(new ShootingStar(true)); }

var bgTime = 0;

function animate() {
	var todayStr = getDateKey();
	isSpecialDate = false;
	for (var key in consDataByName) {
		if (consDataByName[key].date === todayStr) {
			isSpecialDate = true;
			break;
		}
	}

  var sy = window.getScrollY ? window.getScrollY() : 0;

	bgCtx.fillStyle = "#110E19";
	bgCtx.fillRect(0, 0, width, pageHeight);

	bgTime++;
	renderBgStars(bgCtx, stars, bgTime, undefined, sy);

	for (var ci = 0; ci < cons.length; ci++) {
		var ec = cons[ci];
		renderConstellationLines(bgCtx, ec.pts, ec.connections, "rgba(255, 255, 255, 0.15)", sy, ec.parallax);
		renderConstellationStars(bgCtx, ec.pts, ec.mainIndices, bgTime, sy, ec.parallax);
	}

	// Labels
	bgCtx.font = "10px sans-serif";
	bgCtx.textAlign = "center";
	bgCtx.fillStyle = "rgba(255, 255, 255, 0.18)";
	for (var ci = 0; ci < cons.length; ci++) {
		var ec = cons[ci];
		if (!ec.pts || ec.pts.length === 0) continue;
		var lx = 0, maxY = -Infinity, n = 0;
		var mains = ec.mainIndices || [];
		for (var j = 0; j < Math.min(4, mains.length); j++) {
			var p = ec.pts[mains[j]];
			if (p) { lx += p.x; n++; if (p.y > maxY) maxY = p.y; }
		}
		if (n > 0)
			bgCtx.fillText(ec.label, lx / n, maxY + 16 + sy * (1 - ec.parallax));
	}

	bgTime++;
	for (let m of movers) { m.update(); }

	requestAnimFrame(animate);
}

animate();
