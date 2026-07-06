(function () {
  // reading progress bar
  var bar = document.getElementById('progress');
  function onScroll() {
    var h = document.documentElement;
    var max = h.scrollHeight - h.clientHeight;
    if (bar && max > 0) bar.style.width = (100 * h.scrollTop / max) + '%';
  }
  document.addEventListener('scroll', onScroll, { passive: true });

  // scrollspy for TOC
  var links = Array.prototype.slice.call(document.querySelectorAll('.toc a'));
  var targets = links
    .map(function (a) { return document.getElementById(a.getAttribute('href').slice(1)); })
    .filter(Boolean);
  function spy() {
    var pos = window.scrollY + 120;
    var current = null;
    for (var i = 0; i < targets.length; i++) {
      if (targets[i].offsetTop <= pos) current = targets[i].id;
    }
    links.forEach(function (a) {
      a.classList.toggle('active', a.getAttribute('href') === '#' + current);
    });
  }
  document.addEventListener('scroll', spy, { passive: true });
  spy();

  // mobile TOC toggle
  var btn = document.getElementById('menu-btn');
  var sidebar = document.getElementById('sidebar');
  if (btn && sidebar) {
    btn.addEventListener('click', function () { sidebar.classList.toggle('open'); });
    sidebar.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') sidebar.classList.remove('open');
    });
  }
})();
