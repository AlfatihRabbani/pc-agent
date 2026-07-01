import re, urllib.parse, urllib.request, sys
q = " ".join(sys.argv[1:]) or "Radiant Emerald Diamonds in the sky Sonic R"
u = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q)
req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "ignore")
m = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
print("query:", q)
print("top result:", ("https://www.youtube.com/watch?v=" + m.group(1)) if m else "NOT FOUND")
