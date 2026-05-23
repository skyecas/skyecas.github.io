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

var para = 0.5;
var cassPts = projectConstellation(consDataByName.CASSIOPEIA,
	width * 0.5, height * 0.5,
	13 * (width / 1920),
	1, 60
);

var time = 0;

function animate() {
	time++;
	var sy = window.lenisScroll !== undefined ? window.lenisScroll : 0;
	bgCtx.fillStyle = "#08081a";
	bgCtx.fillRect(0, 0, width, pageHeight);
	renderBgStars(bgCtx, stars, time, undefined, sy);
	renderConstellationLines(bgCtx, cassPts, consDataByName.CASSIOPEIA.connections, "rgba(255, 255, 255, 0.15)", sy, para);
	renderConstellationStars(bgCtx, cassPts, consDataByName.CASSIOPEIA.mainIndices, time, sy, para);
	requestAnimFrame(animate);
}

animate();