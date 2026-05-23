var pageHeight;
var bg = initCanvas(function(w, h, c) {
	rawWidth = w; rawHeight = h;
	width = w; height = h;
	pageHeight = Math.max(h * 4, document.body.scrollHeight || h * 4);
	c.height = pageHeight;
	c.style.height = pageHeight + "px";
	sx = w / 1920; sy = h / 1080;
	mScale = Math.min(sx, sy);
	stars = createBgStars(500, w, pageHeight, {yBias: 1.2, parallax: true});
});
var bgCtx = bg.ctx;
var width = rawWidth, height = rawHeight;
var sx = bg.sx(), sy = bg.sy(), mScale = bg.mScale();
bg.canvas.style.position = "absolute";
bg.canvas.style.top = "0";
bg.canvas.style.left = "0";

console.log("COMPUTED position:", window.getComputedStyle(bg.canvas).position);

var scrollY = 0;
window.addEventListener("scroll", function() {
	scrollY = window.scrollY;
}, { passive: true });

var para = 0.5;
var cassPts = projectConstellation(consDataByName.CASSIOPEIA,
	width * 0.5, height * 0.5,
	13 * (width / 1920),
	1, 60
);

// Draw a static bar at absolute page y=2000 (should only be visible when scrolled there)
bgCtx.fillStyle = "#00ff0088";
bgCtx.fillRect(100, 2000, 300, 20);

var time = 0;
var frame = 0;

function animate() {
	frame++;
	time++;
	bgCtx.fillStyle = "#08081a";
	bgCtx.fillRect(0, 0, width, pageHeight);
	renderBgStars(bgCtx, stars, time, undefined, scrollY);
	renderConstellationLines(bgCtx, cassPts, consDataByName.CASSIOPEIA.connections, "rgba(255, 255, 255, 0.15)", scrollY, para);
	renderConstellationStars(bgCtx, cassPts, consDataByName.CASSIOPEIA.mainIndices, time, scrollY, para);

	if (frame % 30 === 0) {
		console.log("scrollY:", scrollY, "| frame:", frame);
	}

	requestAnimFrame(animate);
}

animate();
