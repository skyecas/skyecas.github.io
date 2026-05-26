const mugWidth = 69;
const mugHeight = 100;
var mugX, mugY, secondMugX, secondMugY;
var steamCount = 6;
var prevW, prevH;
var pools = [], drops = [], dripTrails = [], steamWaves = [];
var windTime = 0;
var fogOffset = 0;

var bg = initCanvas(function (w, h, c) {
    width = w; height = h;
    mugX = w - 2 * mugWidth;
    mugY = h - mugHeight - 30;
    secondMugX = mugX - mugWidth - 40;
    secondMugY = mugY + 10;
    var xr = w / prevW, yr = h / prevH;
    if (isFinite(xr) && isFinite(yr) && prevW && prevH) {
        for (var p of pools) { p.x *= xr; p.y *= yr; }
        for (var d of drops) { d.x *= xr; d.y *= yr; }
        for (var t of dripTrails) { t.x *= xr; t.y *= yr; }
    }
    prevW = w; prevH = h;
    steamWaves = [];
    for (let i = 0; i < steamCount; i++) {
        steamWaves.push(new SteamWave(mugX + 8 + (mugWidth - 16) * i / (steamCount - 1), mugY));
    }
    for (let i = 0; i < steamCount; i++) {
        steamWaves.push(new SteamWave(secondMugX + 8 + (mugWidth - 16) * i / (steamCount - 1), secondMugY));
    }
});
var bgCtx = bg.ctx;

var cons = buildConstellations([
    { name: "CASSIOPEIA", cx: 400, cy: 120, sc: 8, onlyMain: false, },
]);

function drawWindow() {
    const top = height * 0.95;
    const gradient = bgCtx.createLinearGradient(0, top, 0, height);
    gradient.addColorStop(0, 'rgba(34, 34, 34, 0.1)');
    gradient.addColorStop(1, 'rgba(0, 0, 0, 0.1)');
    bgCtx.fillStyle = gradient;
    bgCtx.fillRect(0, top, width, height - top);
}

function smoothNoise(x, y, t) {
    return Math.sin(x * 0.05 + t * 0.002) * 0.5 +
        Math.sin(y * 0.07 + t * 0.001) * 0.3 +
        Math.sin((x + y) * 0.03 + t * 0.003) * 0.2;
}

// === ENTITIES ===

function RainDrop() {
    this.reset();
}
RainDrop.prototype.reset = function () {
    const xoffset = 0.2;
    const yoffset = 0.5;
    this.x = width * (Math.random() * (xoffset + 1) - xoffset);
    this.y = height * (Math.random() * (yoffset + 1) - yoffset);
    this.length = 20 + Math.random() * 20;
    this.speed = 4 + Math.random() * 4;
    this.opacity = 0.1 + Math.random() * 0.2;
};
RainDrop.prototype.update = function () {
    const windEffect = baseWind + gust;
    this.y += this.speed;
    this.x += this.speed * 0.3 + windEffect * 0.5;
    if (this.y + this.length + 10 > height) this.reset();
    this.draw();
};
RainDrop.prototype.draw = function () {
    const windEffect = baseWind + gust;
    const dx = this.speed * 0.3 + windEffect * 0.5;
    bgCtx.beginPath();
    bgCtx.moveTo(this.x, this.y);
    bgCtx.lineTo(this.x - dx * (this.length / this.speed), this.y - this.length);
    bgCtx.strokeStyle = `rgba(255, 255, 255, ${this.opacity})`;
    bgCtx.lineWidth = 1;
    bgCtx.stroke();
};

function DripDrop() {
    this.reset();
}
DripDrop.prototype.reset = function () {
    this.x = Math.random() * width;
    this.y = Math.random() * height;
    this.length = 8 + Math.random() * 15;
    this.speed = 0.3 + Math.random() * 0.7;
    this.opacity = 0.1 + Math.random() * 0.15;
};

DripDrop.prototype.update = function () {
    this.y += this.speed;
    const sillY = height * (0.96 + Math.random() * 0.05);
    if (this.y > sillY) {
        if (this.x > mugX - 10 && this.x < mugX + mugWidth + 10) {
            this.reset();
        } else if (this.x > secondMugX - 10 && this.x < secondMugX + mugWidth + 10) {
            this.reset();
        } else {
            pools.push(new RainPool(this.x, sillY + 2));
            dripTrails.push(new DripTrail(this.x, sillY + 2, this.length, this.speed, this.opacity));
            this.reset();
        }
    }
    this.draw();
};
DripDrop.prototype.draw = function () {
    bgCtx.beginPath();
    bgCtx.moveTo(this.x, this.y);
    bgCtx.lineTo(this.x, this.y - this.length);
    bgCtx.strokeStyle = `rgba(255, 255, 255, ${this.opacity})`;
    bgCtx.lineWidth = 2;
    bgCtx.stroke();
};
function DripTrail(x, y, length, speed, opacity) {
    this.x = x;
    this.y = y;
    this.taily = y - length;
    this.length = length;
    this.opacity = opacity;
    this.speed = speed;
}
DripTrail.prototype.update = function () {
    if (this.y > this.taily) return;
    this.taily += this.speed;
    this.opacity = lerp(0, this.opacity, (this.y - this.taily) / this.length);

    const gradient = bgCtx.createLinearGradient(this.x, this.y - this.length, this.x, this.y);
    gradient.addColorStop(0, `rgba(255, 255, 255, 0)`);
    gradient.addColorStop(1, `rgba(255, 255, 255, ${this.opacity})`);

    bgCtx.strokeStyle = gradient;
    bgCtx.lineWidth = 2;
    bgCtx.beginPath();
    bgCtx.moveTo(this.x, this.y - this.length);
    bgCtx.lineTo(this.x, this.y);
    bgCtx.stroke();
};

function RainPool(x, y) {
    this.x = x;
    this.y = y;
    this.radius = 0;
    this.opacity = 0.4;
}
RainPool.prototype.update = function () {
    this.radius += 0.2;
    this.opacity -= 0.002;
    this.draw();
};
RainPool.prototype.draw = function () {
    let maxRings = 3;
    for (let i = 0; i < maxRings; i++) {
        let ringRadius = this.radius * (0.6 + 0.2 * i);
        let ringOpacity = this.opacity * (1 - i / maxRings);
        let offset = Math.sin(i * 0.5 + this.radius * 0.1) * 3;

        bgCtx.beginPath();
        bgCtx.ellipse(this.x + offset, this.y, ringRadius * 1.3, ringRadius * 0.7, 0, 0, Math.PI * 2);
        bgCtx.strokeStyle = `rgba(255, 255, 255, ${ringOpacity})`;
        bgCtx.lineWidth = 1;
        bgCtx.stroke();
    }
};

function LightningFlash() {
    this.timer = 0;
    this.opacity = 0;
}
LightningFlash.prototype.trigger = function () {
    this.timer = 3 + Math.floor(Math.random() * 3);
    this.opacity = 0.4;
    this.hasBolt = Math.random() < 0.5;
    this.bolt = this.hasBolt ? generateLightningPath() : null;
};
LightningFlash.prototype.update = function () {
    if (Math.random() < 0.005 && this.timer <= 0) this.trigger();
    if (this.timer > 0) {
        this.drawGlow();
        if (this.hasBolt && this.bolt) drawLightningBolt(this.bolt);
        this.timer--;
    }
};
LightningFlash.prototype.drawGlow = function () {
    const grad = bgCtx.createLinearGradient(0, 0, 0, height);
    grad.addColorStop(0, `rgba(255, 255, 255, ${this.opacity * 0.1})`);
    grad.addColorStop(1, `rgba(255, 255, 255, 0)`);
    bgCtx.fillStyle = grad;
    bgCtx.fillRect(0, 0, width, height);
};
function generateLightningPath(segments = 10 + Math.floor(Math.random() * 5)) {
    const points = [];
    let x = width * 0.3 + Math.random() * width * 0.4;
    let y = -10;
    const maxHeight = height * 0.5 + Math.random() ** 2 * height * 0.4;
    const stepY = maxHeight / segments;

    for (let i = 0; i <= segments; i++) {
        x += (Math.random() - 0.5) * 80;
        y = i * stepY + Math.random() * 5;
        points.push({ x, y });
    }

    return points;
}
function drawLightningBolt(path) {
    bgCtx.beginPath();
    bgCtx.moveTo(path[0].x, path[0].y);

    for (let i = 1; i < path.length - 2; i++) {
        const cpX = (path[i].x + path[i + 1].x) / 2;
        const cpY = (path[i].y + path[i + 1].y) / 2;
        bgCtx.quadraticCurveTo(path[i].x, path[i].y, cpX, cpY);
    }

    const grad = bgCtx.createLinearGradient(
        path[0].x, path[0].y,
        path[path.length - 1].x, path[path.length - 1].y
    );
    grad.addColorStop(0.0, 'rgba(255, 255, 255, 1)');
    grad.addColorStop(0.4, 'rgba(255, 255, 255, 0.7)');
    grad.addColorStop(0.7, 'rgba(255, 255, 255, 0.3)');
    grad.addColorStop(1.0, 'rgba(255, 255, 255, 0)');

    bgCtx.strokeStyle = grad;
    bgCtx.lineWidth = 2;
    bgCtx.stroke();

    for (let i = 0; i < path.length; i++) {
        let opacity = (1 - (path.length / i)) * 0.2 + 0.2
        if (Math.random() < 0.5) drawLightningFork(path[i], opacity);
    }
}
function drawLightningFork(start, opacity) {
    const segments = 4 + Math.floor(Math.random() * 7);
    let x = start.x;
    let y = start.y;

    bgCtx.beginPath();
    bgCtx.moveTo(x, y);

    for (let i = 0; i < segments; i++) {
        x += (Math.random() - 0.5) * 150;
        y += 10 + Math.random() * 40;
        bgCtx.lineTo(x, y);
    }

    bgCtx.strokeStyle = `rgba(255, 255, 255, ${opacity})`;
    bgCtx.lineWidth = 1;
    bgCtx.stroke();
}

var fogCanvas = document.createElement('canvas');
fogCanvas.width = width;
fogCanvas.height = height;
var fogCtx = fogCanvas.getContext('2d');

for (let i = 0; i < 200; i++) {
    let x = Math.random() * width;
    let y = Math.random() * height;
    let radius = 100 + Math.random() * 100;
    let opacity = 0.01 + Math.random() * 0.03;

    fogCtx.beginPath();
    fogCtx.arc(x, y, radius, 0, 2 * Math.PI);
    fogCtx.fillStyle = `rgba(255, 255, 255, ${opacity})`;
    fogCtx.fill();
}

function drawMug(ctx, x = mugX, y = mugY) {
    ctx.fillStyle = "#222";
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + mugWidth, y);
    ctx.lineTo(x + mugWidth, y + mugHeight);
    ctx.lineTo(x, y + mugHeight);
    ctx.closePath();
    ctx.fill();

    ctx.beginPath();
    ctx.strokeStyle = "#111";
    ctx.ellipse(x + mugWidth / 2, y, mugWidth / 2, 6, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.beginPath();
    ctx.strokeStyle = "#111";
    ctx.ellipse(x + mugWidth / 2, y + mugHeight, mugWidth / 2, 6, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.beginPath();
    ctx.fillStyle = "#1a0e08";
    ctx.ellipse(x + mugWidth / 2, y + 2, (mugWidth / 2) * 0.9, 4.5, 0, 0, Math.PI * 2);
    ctx.fill();

    const handleCX = x;
    const handleCY = y + mugHeight / 2;
    ctx.beginPath();
    ctx.strokeStyle = "#222";
    ctx.lineWidth = 12;
    ctx.arc(handleCX, handleCY, 15, Math.PI / 2.2, -Math.PI / 2.2, false);
    ctx.stroke();
}
function SteamWave(xBase, yBase) {
    this.xBase = xBase;
    this.yBase = yBase;
    this.amplitude = 4 + Math.random() * 4;
    this.opacity = 0.08 + Math.random() * 0.08;
    this.colour = `255, 255, 255`;
}
SteamWave.prototype.update = function (ctx, t) {
    const step = 2;
    const waveHeight = 100 + 25 * smoothNoise(this.xBase + this.amplitude, this.yBase - this.amplitude, t / 2);
    const topY = this.yBase - waveHeight;
    const bottomY = this.yBase;

    ctx.beginPath();
    for (let y = topY; y <= bottomY; y += step) {
        const heightFactor = 1 - (y - topY) / waveHeight;
        const localAmp = this.amplitude * heightFactor;
        const noiseX = smoothNoise(this.xBase, y, t / 2);
        const drift = Math.sin(t * 0.0003 + this.xBase * 0.05 + y * 0.01) * heightFactor * 5;

        const x = this.xBase + noiseX * localAmp + drift;
        ctx.lineTo(x, y);
    }
    const gradient = ctx.createLinearGradient(this.xBase, bottomY, this.xBase, topY);
    gradient.addColorStop(0, `rgba(${this.colour}, 0)`);
    gradient.addColorStop(0.1, `rgba(${this.colour}, ${this.opacity})`);
    gradient.addColorStop(1, `rgba(${this.colour}, 0)`);
    ctx.strokeStyle = gradient;
    ctx.lineWidth = 1;
    ctx.shadowColor = `rgba(${this.colour}, ${this.opacity})`;
    ctx.shadowBlur = 4;
    ctx.stroke();
    ctx.shadowBlur = 0;
};

// === INIT ENTITIES ===
let lightning = new LightningFlash();
var rains = [];
var baseWind = 0, gust = 0, gustTarget = 0, gustSpeed = 0.01;

for (var i = 0; i < 200; i++) { rains.push(new RainDrop()); }
for (var i = 0; i < 100; i++) { drops.push(new DripDrop()); }
for (var i = 0; i < steamCount; i++) {
    const steamX = mugX + 8 + (mugWidth - 16) * i / (steamCount - 1);
    steamWaves.push(new SteamWave(steamX, mugY));
}
for (let i = 0; i < steamCount; i++) {
    const steamX = secondMugX + 8 + (mugWidth - 16) * i / (steamCount - 1);
    steamWaves.push(new SteamWave(steamX, secondMugY));
}

// === ANIMATION LOOP ===
function animate() {
    windTime += 0.01;
    baseWind = Math.sin(windTime * 0.3) * 2;
    if (Math.random() < 0.005) {
        gustTarget = (Math.random() - 0.5) * 4;
        gustSpeed = 0.01 + Math.random() * 0.02;
    }
    gust += (gustTarget - gust) * gustSpeed;

    bgCtx.fillStyle = "#110E19";
    bgCtx.fillRect(0, 0, width, height);

    lightning.update();

    let tintGrad = bgCtx.createLinearGradient(0, 0, 0, height);
    tintGrad.addColorStop(0, "rgba(100, 80, 150, 0.1)");
    tintGrad.addColorStop(1, "rgba(30, 20, 60, 0.3)");
    bgCtx.fillRect(0, 0, width, height);

    fogOffset += 0.05;
    bgCtx.globalAlpha = 0.05;
    bgCtx.drawImage(fogCanvas, fogOffset % width - width, 0);
    bgCtx.drawImage(fogCanvas, fogOffset % width, 0);
    bgCtx.globalAlpha = 1.0;
    bgCtx.filter = 'none';

    for (let rain of rains) rain.update();

    for (var ci = 0; ci < cons.length; ci++) {
        var c = cons[ci];
        renderConstellationLines(bgCtx, c.pts, c.connections, "rgba(255, 255, 255, 0.15)", 0, c.parallax);
        renderConstellationStars(bgCtx, c.pts, c.mainIndices, time, 0, c.parallax);
    }

    drawWindow();

    for (let drop of drops) drop.update();

    pools.forEach(p => p.update());
    pools = pools.filter(p => p.opacity > 0);

    dripTrails.forEach(t => t.update());
    dripTrails = dripTrails.filter(t => t.opacity > 0);

    drawMug(bgCtx, mugX, mugY);
    drawMug(bgCtx, secondMugX, secondMugY);
    for (let wave of steamWaves) { wave.update(bgCtx, performance.now()); }

    requestAnimFrame(animate);
}

animate();
