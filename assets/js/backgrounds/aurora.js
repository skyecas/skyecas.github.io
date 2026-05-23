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
var scrollEl = null;

function findScroller() {
	var candidates = [
		window,
		document.documentElement,
		document.body,
		document.querySelector(".content"),
		document.querySelector("main"),
		document.querySelector("#main"),
		document.querySelector(".wrapper"),
		document.querySelector(".page"),
	];
	for (var i = 0; i < candidates.length; i++) {
		var el = candidates[i];
		if (!el) continue;
		var sy = el.scrollY !== undefined ? el.scrollY : el.scrollTop;
		if (sy !== undefined && sy > 0) {
			scrollEl = el;
			return el;
		}
	}
	return null;
}

function updateScrollY() {
	if (scrollEl === window) {
		scrollY = window.scrollY;
	} else if (scrollEl) {
		scrollY = scrollEl.scrollTop;
	} else {
		scrollY = window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
	}
}

setTimeout(function() {
	var found = findScroller();
	if (found) {
		var name = found === window ? "window" : (found.tagName + (found.id ? "#" + found.id : ""));
		console.log("SCROLLER:", name, "scrollPos:", (found.scrollY !== undefined ? found.scrollY : found.scrollTop));
		if (found !== window) {
			found.addEventListener("scroll", function() { updateScrollY(); }, { passive: true });
		}
	} else {
		console.log("SCROLLER: none found (pos=0 at all candidates)");
	}
	window.addEventListener("scroll", function() { updateScrollY(); }, { passive: true });
	console.log("scrollY after timeout:", scrollY);
}, 500);

window.addEventListener("scroll", function() { updateScrollY(); }, { passive: true });

// Also try reading scroll from every major source each frame
var frame = 0;

var para = 0.5;
var cassPts = projectConstellation(consDataByName.CASSIOPEIA,
	width * 0.5, height * 0.5,
	13 * (width / 1920),
	1, 60
);

var time = 0;

function animate() {
	frame++;
	time++;
	bgCtx.fillStyle = "#08081a";
	bgCtx.fillRect(0, 0, width, pageHeight);
	renderBgStars(bgCtx, stars, time, undefined, scrollY);
	renderConstellationLines(bgCtx, cassPts, consDataByName.CASSIOPEIA.connections, "rgba(255, 255, 255, 0.15)", scrollY, para);
	renderConstellationStars(bgCtx, cassPts, consDataByName.CASSIOPEIA.mainIndices, time, scrollY, para);

	if (frame % 30 === 0) {
		console.log("scrollY:", scrollY, "| win:", window.scrollY, "| doc:", document.documentElement.scrollTop, "| body:", document.body.scrollTop, "| frame:", frame);
	}

	requestAnimFrame(animate);
}

animate();
