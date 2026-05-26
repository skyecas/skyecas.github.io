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
var cassWCoords = projectConstellation(consDataByName.CASSIOPEIA,
	width * 0.15, height * 0.25,
	13 * (width / 1920),
    undefined, undefined, true
);

var orionWCoords = projectConstellation(consDataByName.ORION,
	width * 0.85, height * 0.75,
	7 * (width / 1920)
);

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
var cassTime = 0;

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

	cassTime++;
	renderBgStars(bgCtx, stars, bgTime, undefined, sy);
	renderConstellationLines(bgCtx, cassWCoords, consDataByName.CASSIOPEIA.connections, "rgba(255, 255, 255, 0.15)", sy, 0.7);
	renderConstellationStars(bgCtx, cassWCoords, consDataByName.CASSIOPEIA.mainIndices, cassTime, sy, 0.7);
	renderConstellationLines(bgCtx, orionWCoords, consDataByName.ORION.connections, "rgba(255, 255, 255, 0.12)", sy, 0.8);
	renderConstellationStars(bgCtx, orionWCoords, consDataByName.ORION.mainIndices, cassTime, sy, 0.8);

	bgCtx.font = "10px sans-serif";
	bgCtx.textAlign = "center";
	bgCtx.fillStyle = "rgba(255, 255, 255, 0.18)";
	var lx = 0, maxY = -Infinity;
	var orionMains = consDataByName.ORION.mainIndices || [];
	for (var j = 0; j < Math.min(4, orionMains.length); j++) {
		var s = orionWCoords[orionMains[j]];
		lx += s.x;
		if (s.y > maxY) maxY = s.y;
	}
	bgCtx.fillText("Orion", lx / Math.min(4, orionMains.length), maxY + 16 + sy * (1 - 0.8));

	bgTime++;
	for (let m of movers) { m.update(); }

	requestAnimFrame(animate);
}

animate();
