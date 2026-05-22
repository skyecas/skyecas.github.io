// Let the browser handle the animation cycles
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

// function to get todays date
function today(d) {
  var day = d.getDate(),
      mon = d.getMonth()+1;
  (day < 10) ? day = "0"+day : day;
  (mon < 10) ? mon = "0"+mon : mon;
  return day+"/"+mon;
}

// fetch the background canvas
var background = document.getElementById("bgCanvas"),
    bgCtx = background.getContext("2d"),
    width = window.innerWidth,
    height = window.innerHeight;

if (!isFinite(width) || width < 100) width = 1920;
if (!isFinite(height) || height < 100) height = 1080;

// Switch to absolute positioning so canvas scrolls with page
var pageHeight = Math.max(height * 4, document.body.scrollHeight || height * 4);
background.style.position = "absolute";
background.style.top = "0";
background.style.left = "0";
background.width = width;
background.height = pageHeight;
background.style.height = pageHeight + "px";

// Parallax scroll offset
var scrollY = 0;
window.addEventListener("scroll", function() { scrollY = window.scrollY; }, { passive: true });

// Update page height on resize
window.addEventListener("resize", function() {
  var rw = window.innerWidth, rh = window.innerHeight;
  if (!isFinite(rw) || rw < 100) rw = 1920;
  if (!isFinite(rh) || rh < 100) rh = 1080;
  width = rw; height = rh;
  pageHeight = Math.max(height * 4, document.body.scrollHeight || height * 4);
  background.style.height = pageHeight + "px";
  background.width = width; background.height = pageHeight;
});

// draw the night sky
bgCtx.fillStyle = "#110E19";
bgCtx.fillRect(0, 0, width, pageHeight);

// draw the night sky
bgCtx.fillStyle = "#110E19";
bgCtx.fillRect(0, 0, width, height);

// === Cassiopeia Constellation ===

var cassBase = { x: width * 0.13, y: height * 0.93 };
var cassSX = -6.5 * (width / 1920);
var cassSY = -12 * (height / 1080);

var cassWCoords = [];
for (var i = 0; i < cassiopeiaStars.length; i++) {
  var s = cassiopeiaStars[i];
  cassWCoords.push({
    x: cassBase.x + cassSX * s.ra,
    y: cassBase.y + cassSY * s.dec,
    size: starSize(s.mag),
    colour: spectralToHex(s.spec),
    name: s.name,
    mag: s.mag,
  });
}

var cassTime = 0;

function drawConstellationStars(t) {
  for (var s of cassWCoords) {
    var twinkle = Math.sin(t * 0.02 + s.x * 0.005) * 0.3 + 0.7;
    // Magnitude-based dimming: mag 2.0 = full, mag 5.5 = 15%
    var magFactor = Math.max(0.15, 1.15 - s.mag * 0.2);
    var alpha = (0.7 + twinkle * 0.3) * magFactor;
    var glowSize = s.size * 3.5;

    bgCtx.save();
    var glow = bgCtx.createRadialGradient(s.x, s.y, 0, s.x, s.y, glowSize);
    glow.addColorStop(0, hexToRgba(s.colour, alpha * 0.3));
    glow.addColorStop(1, hexToRgba(s.colour, 0));
    bgCtx.fillStyle = glow;
    bgCtx.beginPath();
    bgCtx.arc(s.x, s.y, glowSize, 0, Math.PI * 2);
    bgCtx.fill();
    bgCtx.restore();

    bgCtx.fillStyle = s.colour;
    bgCtx.globalAlpha = alpha;
    bgCtx.beginPath();
    bgCtx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
    bgCtx.fill();
    bgCtx.globalAlpha = 1;
  }

  bgCtx.strokeStyle = "rgba(255, 255, 255, 0.15)";
  bgCtx.lineWidth = 1;
  bgCtx.beginPath();
  for (var c of cassiopeiaConnections) {
    bgCtx.moveTo(cassWCoords[c[0]].x, cassWCoords[c[0]].y);
    bgCtx.lineTo(cassWCoords[c[1]].x, cassWCoords[c[1]].y);
  }
  bgCtx.stroke();

  bgCtx.font = "11px sans-serif";
  bgCtx.textAlign = "center";
  bgCtx.fillStyle = "rgba(255, 255, 255, 0.24)";
  var labelX = 0, minY = Infinity;
  for (var i = 0; i < 5; i++) { var s = cassWCoords[i]; labelX += s.x; if (s.y < minY) minY = s.y; }
  bgCtx.fillText("Cassiopeia", labelX / 5, minY - 20);
}

// determine which star colours are allowed
const starColour = ["white", "floralWhite", "aliceBlue", "powderBlue", "azure", "moccasin", "sandyBrown", "peachPuff"]

// function to draw background stars
function Star() {
  this.size = Math.random() * 2 + .1;
  this.x = Math.random() * width;
  this.y = Math.random() * pageHeight;
  // select it's colour
  this.colour = starColour[Math.floor(Math.random() * starColour.length)]
}

// function to draw shooting stars
function ShootingStar(special = false) {
  this.special = special;
  this.reset(-200);
}

// function to draw satellites
function Satellite() {
  this.y = Math.random() * height;
  this.x = Math.random() * width;
  this.speed = (Math.random() * .29) + .01;
  this.size = (Math.random() * 2) + 0.1;
  this.colour = "white";
  this.waitTime = new Date().getTime();
  this.active = true;
}

// update the star positions
Star.prototype.update = function() {
  // change the size of the star due to atmospheric twinkling
  this.size = Math.max(.1, Math.min(2, this.size + 0.1 * Math.random() - 0.05));
  // and draw the star
  bgCtx.fillStyle = this.colour;
  bgCtx.fillRect(this.x, this.y, this.size, this.size);
}

// and a function to update the shooting star position
ShootingStar.prototype.update = function() {
  if (this.active) {
    // update it's position
    this.x -= this.speed;
    this.y += this.speed;
    // if it goes out of the viewport, reset
    var screenY = this.y - scrollY;
    if (this.x < -this.len || screenY > height + this.len || screenY < -this.len) {
      this.speed = 0;
      // if the shooting star is special, and it's the right time
      if (this.special) {
        if (isSpecialDate) { this.reset(); }
      // otherwise, just reset it
      } else { this.reset(); }
    } else {
      // set the shooting star colour
      bgCtx.fillStyle = this.colour;
      bgCtx.strokeStyle = this.colour;
      bgCtx.lineWidth = this.size;
      // and draw it
      bgCtx.beginPath();
      bgCtx.moveTo(this.x, this.y);
      bgCtx.lineTo(this.x + this.len, this.y - this.len);
      bgCtx.stroke();
    }
  // wait for it to be active again
  } else {
    if (this.waitTime < new Date().getTime()) {
      this.active = true;
    }
  }
}

// a function to update the satellite star position
Satellite.prototype.update = function() {
  if (this.active) {
    // update it's position
    this.x -= this.speed;
    // if it goes out of the window, reset
    if (this.x < 0) {
      this.reset();
    } else {
      // set the colour
      bgCtx.fillStyle = this.colour;
      bgCtx.fillRect(this.x, this.y, this.size, this.size);
    }
  // wait for it to be active again
  } else {
    if (this.waitTime < new Date().getTime()) {
      this.active = true;
    }
  }
}

// function to reset the shooting stars
ShootingStar.prototype.reset = function(x="0") {
  // spawn within the current viewport (scroll-aware)
  var pos = Math.random() * (width + height);
  this.y = scrollY + Math.max(0, pos - width);
  (x=="0") ? this.x = Math.min(width, pos) : this.x=x;
  // the other bits
  this.len = (Math.random() * 80) + 10;
  this.size = (Math.random() * 1) + 0.1;
  this.speed = (Math.random() * 10) + 5;
  this.colour = starColour[Math.floor(Math.random() * starColour.length)];
  this.waitTime = new Date().getTime() + (Math.random() * 20000);
  this.active = false;
}

// function to reset the satellites
Satellite.prototype.reset = function() {
  this.y = scrollY + Math.random() * height;
  this.x = width;
  this.speed = (Math.random() * .19) + .01;
  this.size = (Math.random() * 2) + 0.1;
  this.colour = "white";
  this.waitTime = new Date().getTime() + (Math.random() * 20000);
  this.active = false;
}

// list of special dates
var specialDates = ["27/07", "12/08", "23/08", "04/09", "26/10", "31/03"];
var dateColours = {
  "27/07": "gold", "12/08": "silver", "23/08": "coral",
  "04/09": "pink", "26/10": "cyan", "31/03": "lightpink"
};

// boolean for if this date is special
var isSpecialDate = false;

// create arrays of animated entities - separate fixed stars from moving objects
var stars = [];
var movers = [];

// initialise the star field - cover full page for parallax
for (var i = 0; i < 600; i++) { stars.push(new Star()); }

// add a few satellites
for (var i = 10; i > 0; i--) { movers.push(new Satellite()); }

// add a shooting star
for (var i = 1; i > 0; i--) { movers.push(new ShootingStar()); }

// add the special shooting stars
for (var i = 20; i > 0; i--) { movers.push(new ShootingStar(true)); }

// animate the background
function animate() {
  // check if today is a special date
  isSpecialDate = specialDates.indexOf(today(new Date())) != -1;
  var todayStr = today(new Date());
  var dateColour = dateColours[todayStr] || null;
  // fetch the requiredbackground colour
  bgCtx.fillStyle = "#110E19";
  bgCtx.fillRect(0, 0, width, pageHeight);

  // Parallax: absolute canvas scrolls naturally; counter-offset downwards
  // so entities appear fixed in the sky (0% scroll). Shooting stars and satellites
  // get a slightly different rate for subtle depth.
  var parOffset = scrollY * 1.0;
  var cassOffset = scrollY * 1.0;

  bgCtx.fillStyle = '#ffffff';
  bgCtx.strokeStyle = '#ffffff';

  if (dateColour) {
    bgCtx.strokeStyle = dateColour;
  }

  // draw Cassiopeia constellation (fixed in the sky)
  cassTime++;
  bgCtx.save();
  bgCtx.translate(0, scrollY);
  drawConstellationStars(cassTime);
  bgCtx.restore();

  // update fixed stars (counter-offset so they appear fixed)
  bgCtx.save();
  bgCtx.translate(0, scrollY);
  for (let s of stars) { s.update(); };
  bgCtx.restore();

  // update moving objects (shooting stars, satellites) — scroll naturally
  for (let m of movers) { m.update(); };

  //schedule the next animation frame
  requestAnimFrame(animate);
}

// call the first animation
animate();
