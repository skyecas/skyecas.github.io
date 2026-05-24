var bg = initCanvas(function(w, h) {
	width = w; height = h;
});

// the sky
function drawSky() {
	const gradient = bgCtx.createLinearGradient(0, 0, 0, height * 0.7);
	gradient.addColorStop(0, '#0b0033');
	gradient.addColorStop(0.1, '#2e1a47');
	gradient.addColorStop(0.4, '#ff758c');
	gradient.addColorStop(0.7, '#ffd580');
	gradient.addColorStop(0.9, '#fff1a8');
	gradient.addColorStop(1, '#ffe4b5');
	bgCtx.fillStyle = gradient;
	bgCtx.fillRect(0, 0, width, height * 0.7);
}

// the sea
function drawSea() {
	const gradient = bgCtx.createLinearGradient(0, height * 0.7, 0, height);
	gradient.addColorStop(0, '#98f5e1');
	gradient.addColorStop(0.3, '#56cfe1');
	gradient.addColorStop(0.6, '#2d6cdf');
	gradient.addColorStop(1, '#0b1a40');
	bgCtx.fillStyle = gradient;
	bgCtx.fillRect(0, height * 0.7, width, height * 0.3);
}

function drawShimmer() {
	const sunX = width / 2;
	const startY = height * 0.7;
	const endY = height * 0.95;
	const shimmerLines = 40;

	bgCtx.save();
	bgCtx.globalAlpha = 0.4;
	bgCtx.lineWidth = 4;

	for (let i = 0; i < shimmerLines; i++) {
		const t = i / shimmerLines;
		const y = startY + (endY - startY) * t;
		const maxWidth = 300;
		const widthFactor = Math.sin(t * Math.PI);
		const halfWidth = maxWidth * widthFactor / 2;
		const jitter = (Math.random() - 0.5) * 4;
		const x1 = sunX - halfWidth + jitter;
		const x2 = sunX + halfWidth + jitter;
		const gradient = bgCtx.createLinearGradient(x1, y, x2, y);
		gradient.addColorStop(0, "rgba(255, 223, 100, 0)");
		gradient.addColorStop(0.5, "rgba(255, 255, 125, 0.8)");
		gradient.addColorStop(1, "rgba(255, 223, 100, 0)");
		bgCtx.strokeStyle = gradient;
		bgCtx.beginPath();
		bgCtx.moveTo(x1, y);
		bgCtx.lineTo(x2, y);
		bgCtx.stroke();
	}
	bgCtx.restore();
}

function drawSun() {
	const sunX = width / 2;
	const sunY = height * 0.6;
	const sunRadius = 40;

	const sunGradient = bgCtx.createRadialGradient(sunX, sunY, 0, sunX, sunY, sunRadius * 2.5);
	sunGradient.addColorStop(0, 'rgba(255, 255, 220, 0.9)');
	sunGradient.addColorStop(0.6, 'rgba(252, 252, 210, 0.7)');
	sunGradient.addColorStop(0.8, 'rgba(255, 255, 150, 0.6)');
	sunGradient.addColorStop(1, 'rgba(255, 215, 0, 0)');

	bgCtx.fillStyle = sunGradient;
	bgCtx.beginPath();
	bgCtx.arc(sunX, sunY, sunRadius * 2.5, 0, Math.PI * 2);
	bgCtx.fill();
}

function Cloud() {
	this.x = Math.random() * width;
	this.y = 0.35 * height + (Math.random() ** 1.6 - 0.5) * height * 0.35;
	this.size = 40 * Math.random() + 40;
	this.speed = 0.1 * Math.random() + 0.05;
	this.puffs = [];
	const puffCount = Math.floor(30 * Math.random()) + 30;
	const bufferSize = 2.5 * this.size;
	this.buffer = document.createElement("canvas");
	this.buffer.width = bufferSize;
	this.buffer.height = bufferSize;
	const o = this.buffer.getContext("2d");
	o.shadowColor = "rgba(255, 255, 255, 0.3)";
	o.shadowBlur = 30;
	for (let i = 0; i < puffCount; i++) {
		const angle = Math.random() * Math.PI * 2;
		const radius = Math.random() * (this.size / 2);
		const px = bufferSize / 2 + Math.cos(angle) * radius;
		const py = bufferSize / 2 + Math.sin(angle) * radius;
		const rx = this.size / 3 + 6 * Math.random();
		const ry = this.size / 4 + 4 * Math.random();
		const opacity = 0.3 + 0.3 * Math.random();
		o.fillStyle = `rgba(255, 255, 255, ${opacity})`;
		o.beginPath();
		o.ellipse(px, py, rx, ry, 0, 0, Math.PI * 2);
		o.fill();
		this.puffs.push({ x: px, y: py, rx: rx, ry: ry });
	}
}
Cloud.prototype.update = function () {
	this.x -= this.speed;
	if (this.x < -this.buffer.width) {
		this.x = width + this.buffer.width;
		this.y = 0.35 * height + (Math.random() ** 1.6 - 0.5) * height * 0.35;
	}
	bgCtx.globalAlpha = 0.7;
	bgCtx.drawImage(this.buffer, this.x, this.y - this.buffer.height / 2);
};

function Bubble() {
	this.x = Math.random() * width;
	this.y = Math.random() * height;
	this.radius = Math.random() * 20 + 5;
	this.speedX = -(Math.random() * 0.5 + 0.1);
	this.offset = Math.random() * 1000;
	this.hueShift = Math.random() * 360;
}
Bubble.prototype.update = function (t) {
	if (isFinite(this.x) && isFinite(this.y) && isFinite(this.radius)) {
		this.y += 0.3 * Math.sin(0.002 * (t + this.offset));
		this.x += this.speedX;
		if (this.x < -this.radius) {
			this.x = width + this.radius;
			this.y = Math.random() * height;
		}
		const i = bgCtx.createRadialGradient(this.x, this.y, 0, this.x, this.y, this.radius);
		i.addColorStop(0, "rgba(255, 255, 255, 0.05)");
		i.addColorStop(0.4, `hsla(${this.hueShift}, 80%, 85%, 0.12)`);
		i.addColorStop(0.7, `hsla(${(this.hueShift + 120) % 360}, 90%, 75%, 0.18)`);
		i.addColorStop(1, `hsla(${(this.hueShift + 240) % 360}, 100%, 80%, 0.4)`);
		bgCtx.save();
		bgCtx.globalCompositeOperation = "lighter";
		bgCtx.fillStyle = i;
		bgCtx.beginPath();
		bgCtx.arc(this.x, this.y, this.radius, 0, 2 * Math.PI);
		bgCtx.fill();
		bgCtx.restore();
		bgCtx.fillStyle = "rgba(255, 255, 255, 0.25)";
		bgCtx.beginPath();
		bgCtx.arc(this.x + this.radius / 3, this.y - this.radius / 3, this.radius / 6, 0, 2 * Math.PI);
		bgCtx.fill();
	}
};

function smoothNoise(x, y, t) {
	return Math.sin(x * 0.05 + t * 0.002) * 0.5 +
		Math.sin(y * 0.07 + t * 0.001) * 0.3 +
		Math.sin((x + y) * 0.03 + t * 0.003) * 0.2;
}
function Wave(yBase) {
	this.yBase = yBase;
	this.amplitude = 10 + Math.random() * 15;
	this.opacity = 0.05 + Math.random() * 0.05;
	this.colour = `rgba(255, 255, 255, ${this.opacity})`;
}
Wave.prototype.update = function (t) {
	const step = 10;
	bgCtx.beginPath();
	bgCtx.moveTo(0, this.yBase);
	for (let x = 0; x <= width; x += step) {
		const noiseY = smoothNoise(x, this.yBase, t);
		const y = this.yBase + noiseY * this.amplitude;
		bgCtx.lineTo(x, y);
	}
	bgCtx.strokeStyle = this.colour;
	bgCtx.lineWidth = 1;
	bgCtx.shadowColor = this.colour;
	bgCtx.shadowBlur = 4;
	bgCtx.stroke();
	bgCtx.shadowBlur = 0;
};

function ShootingStar() {
	this.reset(-200);
}
ShootingStar.prototype.update = function () {
	if (this.active) {
		this.x -= this.speed;
		this.y += this.speed;
		if (this.x < -this.len || this.y >= height + this.len) {
			this.speed = 0;
			this.reset();
		} else {
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
ShootingStar.prototype.reset = function (x) {
	if (x === undefined) x = "0";
	var pos = Math.random() * (width + height);
	this.y = Math.max(0, pos - width);
	(x == "0") ? this.x = Math.min(width, pos) : this.x = x;
	this.len = (Math.random() * 80) + 10;
	this.size = (Math.random() * 1) + 0.1;
	this.speed = (Math.random() * 10) + 5;
	this.colour = spectralToHex(randomSpectralType());
	this.waitTime = new Date().getTime() + (Math.random() * 20000);
	this.active = false;
}

var stars = createBgStars(300, width, height, {});
var shootingstars = [];
var clouds = [];
var bubbles = [];
var waves = [];

for (var i = 15; i > 0; i--) { clouds.push(new Cloud()); }
for (var i = 30; i > 0; i--) { bubbles.push(new Bubble()); }
const wavecount = 20
for (var i = wavecount; i > 0; i--) {
	const yBase = height * 0.7 + (height * 0.3) * (i / wavecount) + (Math.random() - 0.5) * height * 0.01;
	waves.push(new Wave(yBase));
}
for (var i = 10; i > 0; i--) { shootingstars.push(new ShootingStar()); }

var orionPts = projectConstellation(consDataByName.ORION, 2400, 200, 8, undefined, undefined, true);
var cassPts = projectConstellation(consDataByName.CASSIOPEIA, 400, 120, 8, undefined, undefined, true);

function animate() {
	const time = performance.now() / 1000;
	drawSky();
	renderBgStars(bgCtx, stars, time, 1, undefined);
	renderConstellationLines(bgCtx, orionPts, consDataByName.ORION.connections, "rgba(255, 255, 255, 0.15)", 0, 0.3);
	renderConstellationLines(bgCtx, cassPts, consDataByName.CASSIOPEIA.connections, "rgba(255, 255, 255, 0.15)", 0, 0.35);
	renderConstellationStars(bgCtx, orionPts, consDataByName.ORION.mainIndices, time, 0, 0.3);
	renderConstellationStars(bgCtx, cassPts, consDataByName.CASSIOPEIA.mainIndices, time, 0, 0.35);
	drawSun();
	drawSea();
	for (let wave of waves) { wave.update(time); };
	drawShimmer();
	for (let shooting of shootingstars) { shooting.update(); };
	for (let cloud of clouds) { cloud.update(); };
	for (let bubble of bubbles) { bubble.update(time); };
	requestAnimFrame(animate);
}

animate();
