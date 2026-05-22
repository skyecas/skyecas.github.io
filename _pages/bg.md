---
layout: bg
permalink: /bg/
title: 
description:
nav: false
---
<script>
var bgNames = ["stars", "rain", "ocean", "aurora", "nebula", "orbital"];
var params = new URLSearchParams(window.location.search);
var bg = params.get("name");

if (bg && bgNames.indexOf(bg) !== -1) {
  document.querySelector(".content").style.display = "none";
  document.body.style.paddingBottom = "0";
  var script = document.createElement("script");
  script.src = "/assets/js/backgrounds/" + bg + ".js?v=" + Date.now();
  document.body.appendChild(script);
} else {
  document.write('<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:80vh;gap:12px;font-family:monospace;color:#aaa;">');
  document.write('<h2 style="color:#fff;margin-bottom:12px;">Background Preview</h2>');
  for (var i = 0; i < bgNames.length; i++) {
    document.write('<a href="/bg/?name=' + bgNames[i] + '" style="color:#6af;font-size:18px;text-decoration:none;padding:6px 24px;border:1px solid #6af;border-radius:6px;width:200px;text-align:center;">' + bgNames[i] + '</a>');
  }
  document.write('</div>');
}
</script>
