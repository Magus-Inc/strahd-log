  // Who is not counted (Chris, 2026-11-08): his reports were mostly his own visits and scans. A browser
  // that says it is automated (navigator.webdriver: headless scanners, test tools) counts nothing. Open
  // any page with ?notrack=1 and this browser is remembered as Chris's own and counts nothing until a
  // page is opened with ?notrack=0. The choice lives in this browser's localStorage; when storage is
  // blocked the page still works and still counts (?notrack=1 then keeps only its own page out).
  // Google Analytics, the GoatCounter page view, votes and read events all check window.dontCount.
  (function () {
    var asked = null, mine = false;
    try { asked = new URLSearchParams(location.search).get("notrack"); } catch (e) {}
    try {
      if (asked === "1") localStorage.setItem("notrack", "1");
      else if (asked === "0") localStorage.removeItem("notrack");
      mine = localStorage.getItem("notrack") === "1";
    } catch (e) {}
    if (asked === "1") mine = true;
    else if (asked === "0") mine = false;
    window.dontCount = !!navigator.webdriver || mine;
  })();
