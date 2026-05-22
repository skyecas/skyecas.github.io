var background = document.getElementById("bgCanvas"),
	bgCtx = background.getContext("2d"),
	width = window.innerWidth,
	height = window.innerHeight;

if (!isFinite(width) || width < 100) width = 1920;
if (!isFinite(height) || height < 100) height = 1080;

var pageHeight = Math.max(height * 4, document.body.scrollHeight || height * 4);
background.style.position = "absolute";
background.style.top = "0";
background.style.left = "0";
background.width = width;
background.height = pageHeight;
background.style.height = pageHeight + "px";

var scrollY = 0;
window.addEventListener("scroll", function() { scrollY = window.scrollY; }, { passive: true });

window.addEventListener("resize", function() {
	var rw = window.innerWidth, rh = window.innerHeight;
	if (!isFinite(rw) || rw < 100) rw = 1920;
	if (!isFinite(rh) || rh < 100) rh = 1080;
	width = rw; height = rh;
	pageHeight = Math.max(height * 4, document.body.scrollHeight || height * 4);
	background.style.height = pageHeight + "px";
	background.width = width; background.height = pageHeight;
});

bgCtx.fillStyle = "#110E19";
bgCtx.fillRect(0, 0, width, pageHeight);
bgCtx.fillRect(0, 0, width, height);

// === Constellations ===
var cassWCoords = projectConstellation(consData[1],
	width * 0.13, height * 0.93,
	6.5 * (width / 1920),
	0, 0
);

var orionCenterRA = 82.5, orionCenterDec = 5;
var orionWCoords = projectConstellation(consData[0],
	width * 0.78, height * 0.78,
	7 * (width / 1920),
	orionCenterRA, orionCenterDec
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

ShootingStar.prototype.reset = function(x) {
	if (x === undefined) x = "0";
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

Satellite.prototype.reset = function() {
	this.y = scrollY + Math.random() * height;
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
	renderConstellationLines(bgCtx, cassWCoords, consData[1].connections, "rgba(255, 255, 255, 0.15)");
	renderConstellationStars(bgCtx, cassWCoords, consData[1].mainIndices, cassTime);

	bgCtx.font = "11px sans-serif";
	bgCtx.textAlign = "center";
	bgCtx.fillStyle = "rgba(255, 255, 255, 0.24)";
	var labelX = 0, minY = Infinity;
	var cassMains = consData[1].mainIndices || [];
	for (var j = 0; j < Math.min(5, cassMains.length); j++) {
		var s = cassWCoords[cassMains[j]];
		labelX += s.x;
		if (s.y < minY) minY = s.y;
	}
	bgCtx.fillText("Cassiopeia", labelX / Math.min(5, cassMains.length), minY - 20);
	bgCtx.restore();

	bgCtx.save();
	bgCtx.translate(0, orionOffset);
	renderConstellationLines(bgCtx, orionWCoords, consData[0].connections, "rgba(255, 255, 255, 0.12)");
	renderConstellationStars(bgCtx, orionWCoords, consData[0].mainIndices, cassTime);

	bgCtx.font = "10px sans-serif";
	bgCtx.textAlign = "center";
	bgCtx.fillStyle = "rgba(255, 255, 255, 0.18)";
	var lx = 0, maxY = -Infinity;
	var orionMains = consData[0].mainIndices || [];
	for (var j = 0; j < Math.min(4, orionMains.length); j++) {
		var s = orionWCoords[orionMains[j]];
		lx += s.x;
		if (s.y > maxY) maxY = s.y;
	}
	bgCtx.fillText("Orion", lx / Math.min(4, orionMains.length), maxY + 16);
	bgCtx.restore();

	bgTime++;
	for (var s of stars) {
		var paraY = s.y + scrollY * (1 - s.depth);
		var twinkle = 0.5 + 0.5 * Math.sin(bgTime * s.speed + s.phase);
		var a = 0.3 + 0.7 * twinkle;
		bgCtx.fillStyle = hexToRgba(s.colour, a);
		bgCtx.beginPath();
		bgCtx.arc(s.x, paraY, s.size * (0.5 + 0.5 * twinkle), 0, Math.PI * 2);
		bgCtx.fill();
	}

	for (let m of movers) { m.update(); }

	requestAnimFrame(animate);
}

animate();