#!/usr/bin/env bash
# Opens the dashboard in a hidden (headless) Chromium for ~75 s and prints what the page
# itself sees: which slides are available, whether markets.json loaded, and what the
# live-news video does when its slide is forced on. Run as the kiosk user (it asks for
# sudo only to drop a temporary diag.html into the web folder):
#   bash ~/athan-tv/scripts/diag-slides.sh
set -u
WEB=${WEB:-/opt/athan/web}
URL=${URL:-http://127.0.0.1:8080}
SECS=${SECS:-75}
CHROME=$(command -v chromium || command -v chromium-browser || command -v google-chrome) || { echo "chromium not found"; exit 1; }

echo "== config.js"; grep -E 'markets|newsVideo|forecast|family' "$WEB/config.js" | sed 's/^/   /'
echo "== markets.json via nginx"
curl -s -o /dev/null -w "   HTTP %{http_code}, %{size_download} bytes\n" "$URL/markets.json"
echo "== YouTube reachable from this box"
curl -s -o /dev/null -m 10 -w "   iframe_api: HTTP %{http_code}\n" https://www.youtube.com/iframe_api

SUDO=""; [ -w "$WEB" ] || SUDO=sudo                      # the web folder is root-owned
$SUDO tee "$WEB/diag.html" >/dev/null <<'HTML'
<!doctype html><meta charset="utf-8"><body style="margin:0">
<iframe id="f" src="index.html" style="width:1920px;height:1080px;border:0" allow="autoplay"></iframe>
<script>
const f = document.getElementById("f"), t0 = Date.now();
const ev = s => { try { return f.contentWindow.eval(s); } catch (e) { return "ERR " + e.message; } };
const log = m => console.log("DIAG " + Math.round((Date.now() - t0) / 1000) + "s " + m);
f.onload = () => {
  f.contentWindow.addEventListener("error", e => log("PAGE ERROR " + e.message + " @" + e.lineno));
  setInterval(() => log(
    "slides=" + ev("availableSlides().join(',')") +
    " on=" + ev('(SLIDES.find(([k,id]) => $(id).classList.contains("on"))||["none"])[0]') +
    " mkt=" + ev("mkt ? mkt.quotes.length + ' quotes' : String(mkt)") +
    " vSkip=" + ev("vSkip") + " YT=" + ev("!!(window.YT && YT.Player)") +
    " player=" + ev("ytPlayer && ytPlayer.getPlayerState ? ytPlayer.getPlayerState() : (ytPlayer ? 'creating' : 'none')") +
    " msg=" + String(ev('($("vmsg")||{}).textContent||"-"')).replace(/"/g, "")
  ), 5000);
  setTimeout(() => {                                   // jump straight to the news video slide
    log("forcing newsvideo slide");
    ev('vSkip=false; (function(){ const a=availableSlides(); slideIdx=a.indexOf("newsvideo")-1; nextSlide(); })()');
  }, 15000);
};
</script>
HTML

echo "== running page headless for ${SECS}s (player states: -1 unstarted, 1 PLAYING, 3 buffering, 5 cued)"
PROFILE=$(mktemp -d)
timeout "$SECS" "$CHROME" --headless=new --user-data-dir="$PROFILE" --enable-logging=stderr --v=0 \
  --autoplay-policy=no-user-gesture-required --window-size=1920,1080 "$URL/diag.html" 2>&1 \
  | grep -E 'DIAG|youtube|YouTube' | sed -E 's/.*"(DIAG[^"]*)".*/   \1/' | grep -v '^\s*$'
rm -rf "$PROFILE"; $SUDO rm -f "$WEB/diag.html"
