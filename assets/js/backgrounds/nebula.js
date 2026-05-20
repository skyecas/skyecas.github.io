var requestAnimFrame = (function(){
  return window.requestAnimationFrame       ||
         window.webkitRequestAnimationFrame ||
         window.mozRequestAnimationFrame    ||
         window.oRequestAnimationFrame      ||
         window.msRequestAnimationFrame     ||
         function( callback ){
           window.setTimeout(callback, 1000 / 60);
         };
})();

var background = document.getElementById("bgCanvas"),
    bgCtx = background.getContext("2d"),
    width = 1920,
    height = 1080;

background.width = width;
background.height = height;

function lerp(a, b, t) { return a + (b - a) * t; }

function noise2D(x, y, t) {
  return Math.sin(x * 0.003 + t * 0.0003) * 0.5 +
         Math.sin(y * 0.004 + t * 0.0002) * 0.3 +
         Math.sin((x + y) * 0.002 + t * 0.0004) * 0.2;
}

var specColours = ["white", "aliceBlue", "powderBlue", "azure", "moccasin", "sandyBrown", "coral"];

function SpecStar() {
  this.x = Math.random() * width;
  this.y = Math.random() * height;
  this.size = Math.random() * 2 + 0.2;
  this.colour = specColours[Math.floor(Math.random() * specColours.length)];
  this.phase = Math.random() * Math.PI * 2;
  this.speed = 0.01 + Math.random() * 0.02;
  this.bright = Math.random() < 0.02;
}
SpecStar.prototype.update = function(t) {
  var twinkle = Math.sin(t * this.speed + this.phase) * 0.4 + 0.6;
  bgCtx.globalAlpha = 0.2 + twinkle * 0.8;
  bgCtx.fillStyle = this.colour;
  bgCtx.fillRect(this.x, this.y, this.size, this.size);

  if (this.bright) {
    bgCtx.save();
    bgCtx.globalAlpha = 0.15 * twinkle;
    bgCtx.filter = "blur(3px)";
    bgCtx.fillStyle = this.colour;
    bgCtx.beginPath();
    bgCtx.arc(this.x, this.y, this.size * 4, 0, Math.PI * 2);
    bgCtx.fill();
    bgCtx.restore();
    bgCtx.filter = "none";

    bgCtx.strokeStyle = "rgba(255, 255, 255, 0.08)";
    bgCtx.lineWidth = 0.5;
    bgCtx.beginPath();
    bgCtx.moveTo(this.x - 8, this.y);
    bgCtx.lineTo(this.x - 2, this.y);
    bgCtx.moveTo(this.x + 2, this.y);
    bgCtx.lineTo(this.x + 8, this.y);
    bgCtx.moveTo(this.x, this.y - 8);
    bgCtx.lineTo(this.x, this.y - 2);
    bgCtx.moveTo(this.x, this.y + 2);
    bgCtx.lineTo(this.x, this.y + 8);
    bgCtx.stroke();
  }

  bgCtx.globalAlpha = 1;
};

function DustLane(xBase, yBase, width, height, angle, speed) {
  this.xBase = xBase;
  this.yBase = yBase;
  this.width = width;
  this.height = height;
  this.angle = angle;
  this.speed = speed;
  this.phase = Math.random() * Math.PI * 2;
}
DustLane.prototype.update = function(t) {
  bgCtx.save();
  bgCtx.translate(this.xBase, this.yBase);
  bgCtx.rotate(this.angle);

  var segments = 40;
  var segW = this.width / segments;
  bgCtx.fillStyle = "rgba(2, 2, 8, 0.15)";
  bgCtx.beginPath();
  bgCtx.moveTo(0, 0);
  for (var i = 0; i <= segments; i++) {
    var x = i * segW;
    var y = noise2D(x, this.yBase, t * this.speed + this.phase) * this.height * 0.5;
    bgCtx.lineTo(x, y);
  }
  bgCtx.lineTo(this.width, 0);
  bgCtx.closePath();
  bgCtx.fill();

  bgCtx.fillStyle = "rgba(2, 2, 8, 0.1)";
  bgCtx.beginPath();
  bgCtx.moveTo(0, this.height * 0.3);
  for (var i = 0; i <= segments; i++) {
    var x = i * segW;
    var y = noise2D(x, this.yBase + this.height, t * this.speed + this.phase + 2) * this.height * 0.4 + this.height * 0.3;
    bgCtx.lineTo(x, y);
  }
  bgCtx.lineTo(this.width, this.height * 0.3);
  bgCtx.closePath();
  bgCtx.fill();

  bgCtx.restore();
};

var stars = [];
for (var i = 1200; i > 0; i--) { stars.push(new SpecStar()); }

var dustLanes = [
  new DustLane(200, 300, 800, 120, -0.2, 0.0002),
  new DustLane(900, 500, 700, 100, 0.3, 0.00015),
  new DustLane(400, 700, 600, 80, -0.1, 0.00025),
];

function drawNebulaGas(t) {
  var centres = [
    { x: 500, y: 350, rx: 450, ry: 300, colours: ["rgba(180, 40, 200, 0.04)", "rgba(120, 20, 160, 0.07)", "rgba(60, 10, 100, 0.03)"], speed: 0.00008, phase: 0 },
    { x: 900, y: 500, rx: 500, ry: 350, colours: ["rgba(30, 80, 200, 0.03)", "rgba(20, 50, 160, 0.06)", "rgba(10, 20, 100, 0.02)"], speed: -0.00006, phase: 1.5 },
    { x: 700, y: 350, rx: 350, ry: 250, colours: ["rgba(255, 80, 120, 0.03)", "rgba(200, 40, 80, 0.06)", "rgba(140, 20, 60, 0.02)"], speed: 0.0001, phase: -0.8 },
    { x: 1100, y: 650, rx: 400, ry: 250, colours: ["rgba(200, 140, 40, 0.02)", "rgba(160, 100, 20, 0.04)", "rgba(100, 60, 10, 0.02)"], speed: -0.00005, phase: 2.5 },
    { x: 400, y: 700, rx: 350, ry: 200, colours: ["rgba(40, 180, 160, 0.02)", "rgba(20, 140, 120, 0.04)", "rgba(10, 90, 80, 0.02)"], speed: 0.00007, phase: -1.5 },
    { x: 1300, y: 350, rx: 300, ry: 350, colours: ["rgba(130, 40, 220, 0.02)", "rgba(90, 20, 180, 0.04)", "rgba(50, 10, 120, 0.02)"], speed: -0.00009, phase: 0.5 },
  ];

  var blurred = document.createElement("canvas");
  blurred.width = width;
  blurred.height = height;
  var bCtx = blurred.getContext("2d");

  for (var c of centres) {
    var ox = Math.sin(t * 0.00003 + c.phase) * 30;
    var oy = Math.cos(t * 0.00004 + c.phase * 0.7) * 20;

    var grad = bCtx.createRadialGradient(c.x + ox, c.y + oy, 0, c.x + ox, c.y + oy, Math.max(c.rx, c.ry));
    for (var i = 0; i < c.colours.length; i++) {
      grad.addColorStop(i / (c.colours.length - 1), c.colours[i]);
    }
    bCtx.fillStyle = grad;
    bCtx.beginPath();
    bCtx.ellipse(c.x + ox, c.y + oy, c.rx, c.ry, c.phase * 0.1, 0, Math.PI * 2);
    bCtx.fill();
  }

  bgCtx.save();
  bgCtx.filter = "blur(40px)";
  bgCtx.drawImage(blurred, 0, 0);
  bgCtx.restore();
  bgCtx.filter = "none";
}

function drawBrightCore(t) {
  var pulse = Math.sin(t * 0.005) * 0.2 + 0.8;
  var cores = [
    { x: 650, y: 380, r: 80, colour: "rgba(200, 150, 255, " + pulse * 0.06 + ")" },
    { x: 850, y: 520, r: 60, colour: "rgba(100, 200, 255, " + pulse * 0.05 + ")" },
    { x: 500, y: 300, r: 100, colour: "rgba(255, 150, 200, " + pulse * 0.04 + ")" },
  ];
  for (var c of cores) {
    var grad = bgCtx.createRadialGradient(c.x, c.y, 0, c.x, c.y, c.r);
    grad.addColorStop(0, c.colour);
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");
    bgCtx.fillStyle = grad;
    bgCtx.beginPath();
    bgCtx.arc(c.x, c.y, c.r, 0, Math.PI * 2);
    bgCtx.fill();
  }
}

var time = 0;

var specialDates = {
  "27/07": "255, 215, 0", "12/08": "192, 192, 224",
  "23/08": "255, 127, 127", "04/09": "255, 105, 180",
  "26/10": "0, 229, 255", "31/03": "255, 143, 171"
};
function getDateRGB() {
  var d = new Date();
  var key = ("0" + d.getDate()).slice(-2) + "/" + ("0" + (d.getMonth() + 1)).slice(-2);
  return specialDates[key] || null;
}

function animate() {
  time++;

  bgCtx.fillStyle = "#030308";
  bgCtx.fillRect(0, 0, width, height);

  drawNebulaGas(time);

  for (var d of dustLanes) { d.update(time); }

  drawBrightCore(time);

  for (var s of stars) { s.update(time); }

  var dc = getDateRGB();
  if (dc) {
    var pulse = Math.sin(time * 0.02) * 0.4 + 0.6;
    var grad = bgCtx.createRadialGradient(width * 0.4, height * 0.4, 0, width * 0.4, height * 0.4, 600);
    grad.addColorStop(0, "rgba(" + dc + ", " + pulse * 0.03 + ")");
    grad.addColorStop(0.5, "rgba(" + dc + ", " + pulse * 0.015 + ")");
    grad.addColorStop(1, "rgba(" + dc + ", 0)");
    bgCtx.fillStyle = grad;
    bgCtx.fillRect(0, 0, width, height);
  }

  requestAnimFrame(animate);
}

animate();
