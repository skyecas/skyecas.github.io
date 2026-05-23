var bg = initCanvas(function(w, h) {
	width = w; height = h;
});
var bgCtx = bg.ctx;
// width,height set by initCanvas callback

// the sky
function drawSky() {
	const bottom = height * 0.7;

	const gradient = bgCtx.createLinearGradient(0, 0, 0, bottom);
	gradient.addColorStop(0, '#0b0033');  // Top: deep night blue
	gradient.addColorStop(0.1, '#2e1a47');  // Twilight purple
	gradient.addColorStop(0.4, '#ff758c');  // Pink glow
	gradient.addColorStop(0.7, '#ffd580');  // Sunset orange
	gradient.addColorStop(0.9, '#fff1a8');  // Yellow near horizon
	gradient.addColorStop(1, '#ffe4b5');  // Horizon glow

	bgCtx.fillStyle = gradient;
	bgCtx.fillRect(0, 0, width, bottom);
}

// the sea
function drawSea() {
	const top = height * 0.7;

	const gradient = bgCtx.createLinearGradient(0, top, 0, height);
	gradient.addColorStop(0, '#98f5e1');  // Horizon: soft aqua
	gradient.addColorStop(0.3, '#56cfe1');  // Light turquoise
	gradient.addColorStop(0.6, '#2d6cdf');  // Deeper blue
	gradient.addColorStop(1, '#0b1a40');    // Beach edge: dark ocean blue

	bgCtx.fillStyle = gradient;
	bgCtx.fillRect(0, top, width, height - top);
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
		const y = lerp(startY, endY, t);

		// shimmer width grows with t, from 0 to maxWidth
		const maxWidth = 300;
		const widthFactor = Math.sin(t * Math.PI); // soft cone shape
		const halfWidth = maxWidth * widthFactor / 2;

		// slight x jitter to imitate flickering water
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


// the sun
function drawSun() {
	const sunX = width / 2;
	const sunY = height * 0.6;

	const sunRadius = 40;

	// Smooth gradient from warm white to golden yellow
	const sunGradient = bgCtx.createRadialGradient(sunX, sunY, 0, sunX, sunY, sunRadius * 2.5);
	sunGradient.addColorStop(0, 'rgba(255, 255, 220, 0.9)');  // soft warm white
	sunGradient.addColorStop(0.6, 'rgba(252, 252, 210, 0.7)'); // fade to pale yellow
	sunGradient.addColorStop(0.8, 'rgba(255, 255, 150, 0.6)'); // fade to pale yellow
	sunGradient.addColorStop(1, 'rgba(255, 215, 0, 0)');       // transparent golden edge

	bgCtx.fillStyle = sunGradient;
	bgCtx.beginPath();
	bgCtx.arc(sunX, sunY, sunRadius * 2.5, 0, Math.PI * 2);
	bgCtx.fill();
}

// Cloud entity
function Cloud() {
	this.x = Math.random() * width;
	this.y = 0.35 * height + (Math.random() ** 1.6 - 0.5) * height * 0.35;
	this.size = 40 * Math.random() + 40;
	this.speed = 0.1 * Math.random() + 0.05;
	this.puffs = [];

	const puffCount = Math.floor(30 * Math.random()) + 30;
	const bufferSize = 2.5 * this.size;

	// Create offscreen canvas for compositing
	this.buffer = document.createElement("canvas");
	this.buffer.width = bufferSize;
	this.buffer.height = bufferSize;
	const o = this.buffer.getContext("2d");

	// Apply soft shadow effect for the cloud puffs
	o.shadowColor = "rgba(255, 255, 255, 0.3)";
	o.shadowBlur = 30;

	// Apply a gradient for smoother edges
	for (let i = 0; i < puffCount; i++) {
		const angle = Math.random() * Math.PI * 2;
		const radius = Math.random() * (this.size / 2);
		const px = bufferSize / 2 + Math.cos(angle) * radius;
		const py = bufferSize / 2 + Math.sin(angle) * radius;

		const rx = this.size / 3 + 6 * Math.random();
		const ry = this.size / 4 + 4 * Math.random();
		const opacity = 0.3 + 0.3 * Math.random();

		// Draw each puff with varying opacity
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

	// Apply global alpha transparency for smooth blending
	bgCtx.globalAlpha = 0.7;  // Adjust opacity as needed
	bgCtx.drawImage(this.buffer, this.x, this.y - this.buffer.height / 2);
};



// Bubble entity
function Bubble() {
	this.x = Math.random() * width;
	this.y = Math.random() * height;
	this.radius = Math.random() * 20 + 5;
	this.speedX = -(Math.random() * 0.5 + 0.1); // drift left
	this.offset = Math.random() * 1000; // for jitter phase
	this.hueShift = Math.random() * 360; // different hues per bubble
}
Bubble.prototype.update = function (t) {
	// Ensure x, y, and radius are finite numbers
	if (isFinite(this.x) && isFinite(this.y) && isFinite(this.radius)) {
		this.y += 0.3 * Math.sin(0.002 * (t + this.offset));
		this.x += this.speedX;

		// Reset bubble if it goes off the screen
		if (this.x < -this.radius) {
			this.x = width + this.radius;
			this.y = Math.random() * height;
		}

		// Create the radial gradient for the bubble
		const i = bgCtx.createRadialGradient(this.x, this.y, 0, this.x, this.y, this.radius);

		i.addColorStop(0, "rgba(255, 255, 255, 0.05)");
		i.addColorStop(0.4, `hsla(${this.hueShift}, 80%, 85%, 0.12)`);
		i.addColorStop(0.7, `hsla(${(this.hueShift + 120) % 360}, 90%, 75%, 0.18)`);
		i.addColorStop(1, `hsla(${(this.hueShift + 240) % 360}, 100%, 80%, 0.4)`);

		// Drawing the bubble with the gradient
		bgCtx.save();
		bgCtx.globalCompositeOperation = "lighter";
		bgCtx.fillStyle = i;
		bgCtx.beginPath();
		bgCtx.arc(this.x, this.y, this.radius, 0, 2 * Math.PI);
		bgCtx.fill();
		bgCtx.restore();

		// Inner bubble reflection
		bgCtx.fillStyle = "rgba(255, 255, 255, 0.25)";
		bgCtx.beginPath();
		bgCtx.arc(this.x + this.radius / 3, this.y - this.radius / 3, this.radius / 6, 0, 2 * Math.PI);
		bgCtx.fill();
	} else {
		console.error("Invalid bubble parameters:", this.x, this.y, this.radius);
	}
};

// Wave entity
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


// Shooting star entity
function ShootingStar() {
	this.reset(-200);
}
ShootingStar.prototype.update = function () {

	bottom = height * 0.7;

	if (this.active) {
		// update position
		this.x -= this.speed;
		this.y += this.speed;

		// reset if out of bounds
		if (this.x < -this.len || this.y >= height + this.len) {
			this.speed = 0;
			this.reset();
		} else {
			const x1 = this.x;
			const y1 = this.y;
			const x2 = this.x + this.len;
			const y2 = this.y - this.len;

			// only draw if part of the line is visible above the bottom
			if (y1 < bottom || y2 < bottom) {
				// find intersection point at `bottom`, if needed
				let drawX1 = x1, drawY1 = y1;
				let drawX2 = x2, drawY2 = y2;

				if (y1 > bottom) {
					const t = (bottom - y2) / (y1 - y2); // interpolate intersection
					drawX1 = x2 + (x1 - x2) * t;
					drawY1 = bottom;
				}

				if (y2 > bottom) {
					const t = (bottom - y1) / (y2 - y1);
					drawX2 = x1 + (x2 - x1) * t;
					drawY2 = bottom;
				}

				// draw the clipped line
				bgCtx.strokeStyle = this.colour;
				bgCtx.lineWidth = this.size;
				bgCtx.beginPath();
				bgCtx.moveTo(drawX1, drawY1);
				bgCtx.lineTo(drawX2, drawY2);
				bgCtx.stroke();
			}
		}
	} else {
		if (this.waitTime < new Date().getTime()) {
			this.active = true;
		}
	}
}
ShootingStar.prototype.reset = function (x = "0") {
	// select the starting position, along the two screen axes
	var pos = Math.random() * (width + height);
	this.y = Math.max(0, pos - width);
	(x == "0") ? this.x = Math.min(width, pos) : this.x = x;
	// the other bits
	this.len = (Math.random() * 80) + 10;
	this.size = (Math.random() * 1) + 0.1;
	this.speed = (Math.random() * 10) + 5;
	this.colour = spectralToHex(randomSpectralType());
	this.waitTime = new Date().getTime() + (Math.random() * 20000);
	this.active = false;
}

// create an array of animated entities
var stars = createBgStars(300, width, height, {yBias: 1.4, speedRange: [0.5, 1.5]});
var shootingstars = [];
var clouds = [];
var bubbles = [];
var waves = [];

// Add clouds
for (var i = 15; i > 0; i--) { clouds.push(new Cloud()); }
// Add bubbles
for (var i = 30; i > 0; i--) { bubbles.push(new Bubble()); }
// Add waves
const wavecount = 20
for (var i = wavecount; i > 0; i--) {
	const yBase = lerp(height*0.7, height, i / wavecount) + (Math.random() - 0.5) * height * 0.01;
	waves.push(new Wave(yBase));
}
// Add shooting stars
for (var i = 10; i > 0; i--) { shootingstars.push(new ShootingStar()); }

// Project constellations from shared.js data
var orionPts = projectConstellation(consDataByName.ORION, 2400, 200, 8, 0, 0, true);
var cassPts = projectConstellation(consDataByName.CASSIOPEIA, 400, 120, 8, 0, 60, true);

// animate the background
function animate() {
	const time = performance.now() / 1000; // Use seconds for slower twinkle
	// The sky is the background
	drawSky();

	// Draw constellations and stars
	renderBgStars(bgCtx, stars, time, 1);
	renderConstellationLines(bgCtx, orionPts, consDataByName.ORION.connections);
	renderConstellationLines(bgCtx, cassPts, consDataByName.CASSIOPEIA.connections);
	renderConstellationStars(bgCtx, orionPts, consDataByName.ORION.mainIndices, time);
	renderConstellationStars(bgCtx, cassPts, consDataByName.CASSIOPEIA.mainIndices, time);

	// Sea and sun — sun first so it's always behind water
	drawSun();
	drawSea();
	for (let wave of waves) { wave.update(time); };
	drawShimmer();

	// Then the remaining moving entities
	for (let shooting of shootingstars) { shooting.update(); };
	for (let cloud of clouds) { cloud.update(); };
	for (let bubble of bubbles) { bubble.update(time); };

	requestAnimFrame(animate);
}


// call the first animation
animate();

