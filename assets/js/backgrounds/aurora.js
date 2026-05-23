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

var scrollY = 0;
window.addEventListener("scroll", function() {
	scrollY = window.scrollY;
	console.log("scrollY:", scrollY);
}, { passive: true });

var para = 0.5;
var cassPts = projectConstellation(consDataByName.CASSIOPEIA,
	width * 0.5, height * 0.5,
	13 * (width / 1920),
	1, 60
);

var time = 0;

function animate() {
	time++;
	bgCtx.fillStyle = "#08081a";
	bgCtx.fillRect(0, 0, width, pageHeight);
	renderBgStars(bgCtx, stars, time, undefined, scrollY);
	renderConstellationLines(bgCtx, cassPts, consDataByName.CASSIOPEIA.connections, "rgba(255, 255, 255, 0.15)", scrollY, para);
	renderConstellationStars(bgCtx, cassPts, consDataByName.CASSIOPEIA.mainIndices, time, scrollY, para);

	// Fixed crosshair at viewport center (should NOT move with scroll)
	var vpCX = width * 0.5, vpCY = height * 0.5;
	var cx = vpCX, cy = scrollY + vpCY;
	bgCtx.strokeStyle = "rgba(255, 0, 0, 0.6)";
	bgCtx.lineWidth = 2;
	bgCtx.beginPath();
	bgCtx.moveTo(cx - 15, cy); bgCtx.lineTo(cx + 15, cy);
	bgCtx.moveTo(cx, cy - 15); bgCtx.lineTo(cx, cy + 15);
	bgCtx.stroke();
	bgCtx.fillStyle = "rgba(255, 0, 0, 0.4)";
	bgCtx.font = "12px monospace";
	bgCtx.fillText("scrollY: " + scrollY, cx + 20, cy + 4);

	requestAnimFrame(animate);
}

animate();
