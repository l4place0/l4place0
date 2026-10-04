"""Regenerate dark_mode.svg / light_mode.svg with live GitHub stats.

Runs daily via GitHub Actions. Stdlib only, no third-party dependencies.
"""
import calendar
import html
import json
import os
import subprocess
import unicodedata
import urllib.request
from datetime import date, datetime, timezone

USER = "l4place0"
JOINED_DATE = date(2024, 5, 7)
JOINED_YEAR = 2024
W = 56  # info column width in monospace units

# 蓬莱山辉夜 (Houraisan Kaguya) ASCII Art
ART = r"""
              ::::.
            :%#**++.
          ..@**@@@@*
          :+*-@@@@%@:            .=:
          :#%#@#%+=@=        .+=:*%-
           @++@=+ :*         =*+==*=
          .@+#@-  .*      :++-++-+=
          *@%%@:  +=      -*+:*+=+=*=
         :#@%%%:-%@.      ==*.=***+#:
        ::%@=-#*-*#-      =**++:---.
       : =@*#::%*=#*      :++===-+*.
     .- :@*-%@:#####*      .#=+*=*=
    := :@@+++%#+#*%*#:    :++ +++:.
    * -#@%*@%+**%*%###  .=+=:
   :+=+%@#-+%*%@*+=+*%==#+*-
   :*.*@@*%#*-+#-+#*=@%%*+@.
  :* +@@@*@%**+-+++--****+@:
  % :@*@%*@@@#+#@== .=#@#=%:
 =+ %%*@@-@%+**@*=%*+%@##-#:
 --.@+#%@=+*=+@@=+%+-=%+#=+:
   -@=%#%=%%@#@#=*%#==##%=+:
   :@-%*=+@@@##*=#*+%#*%+===
    #-##=%@@**++=#-+*#*#:=+*
     .:+*@@*--+-*+-#:#*%===%
       =+%@%+=--%-+% *%%%=+@.
      .+**#@=-:@==*#=+%%%=+@:
      ++#@@=::*@=+##++%%%-+@-
"""

def get_token():
    token = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        try:
            token = subprocess.check_output(["gh", "auth", "token"]).decode().strip()
        except Exception:
            pass
    return token

TOKEN = get_token()
PRIV_TOKEN = os.environ.get("ACCESS_TOKEN") or TOKEN


def gh(url, payload=None, token=None):
    tok = token or TOKEN
    headers = {"Accept": "application/vnd.github+json"}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload else None,
        headers=headers,
    )
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read() or "{}")


def graphql(query, variables=None, token=None):
    _, resp = gh("https://api.github.com/graphql", {"query": query, "variables": variables or {}}, token)
    if resp.get("errors"):
        raise RuntimeError(resp["errors"])
    return resp["data"]


def str_width(s):
    """Calculate visual width in monospace font (full-width chars count as 2)."""
    return sum(2 if unicodedata.east_asian_width(c) in ("F", "W") else 1 for c in str(s))


def fetch_stats():
    yr_aliases = "\n".join(
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y + 1}-01-01T00:00:00Z")'
        " { totalCommitContributions restrictedContributionsCount }"
        for y in range(JOINED_YEAR, datetime.now(timezone.utc).year + 1)
    )
    contrib = graphql(f'query {{ user(login: "{USER}") {{ {yr_aliases} }} }}')["user"]
    commits = sum(
        v["totalCommitContributions"] + v["restrictedContributionsCount"]
        for v in contrib.values()
    )
    u = graphql(f"""
    query {{
      user(login: "{USER}") {{
        id
        followers {{ totalCount }}
        repositories(first: 100, ownerAffiliations: OWNER) {{
          totalCount
          nodes {{ name stargazerCount isFork }}
        }}
        repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) {{
          totalCount
        }}
      }}
    }}""", token=PRIV_TOKEN)["user"]
    stats = {
        "followers": u["followers"]["totalCount"],
        "repos": u["repositories"]["totalCount"],
        "contributed": u["repositoriesContributedTo"]["totalCount"],
        "stars": sum(n["stargazerCount"] for n in u["repositories"]["nodes"]),
        "commits": commits,
    }
    stats.update(loc([n["name"] for n in u["repositories"]["nodes"] if not n["isFork"]], u["id"]))
    return stats


LOC_QUERY = """
query($owner: String!, $name: String!, $id: ID!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { target { ... on Commit {
      history(first: 100, author: {id: $id}, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { additions deletions }
      }
    } } }
  }
}"""


def loc(repo_names, user_id):
    add = rem = 0
    for name in repo_names:
        cursor = None
        try:
            while True:
                ref = graphql(LOC_QUERY, {"owner": USER, "name": name, "id": user_id, "cursor": cursor}, token=PRIV_TOKEN)["repository"]["defaultBranchRef"]
                if ref is None:
                    break
                h = ref["target"]["history"]
                add += sum(n["additions"] for n in h["nodes"])
                rem += sum(n["deletions"] for n in h["nodes"])
                if not h["pageInfo"]["hasNextPage"]:
                    break
                cursor = h["pageInfo"]["endCursor"]
        except Exception as e:
            print(f"loc {name}: {e}")
    return {"loc_add": add, "loc_del": rem, "loc": add - rem}


PALETTES = {
    "dark": {
        "bg": "#0d1117", "border": "#30363d", "art": "#8b949e", "h": "#58a6ff",
        "k": "#ffa657", "v": "#c9d1d9", "d": "#484f58", "g": "#3fb950", "r": "#f85149"
    },
    "light": {
        "bg": "#ffffff", "border": "#d0d7de", "art": "#57606a", "h": "#0969da",
        "k": "#953800", "v": "#24292f", "d": "#afb8c1", "g": "#1a7f37", "r": "#cf222e"
    },
}


def kv(key, val, width=W):
    dot_count = max(width - str_width(key) - str_width(val) - 3, 1)
    dots = "." * dot_count
    return [(f"{key}: ", "k"), (dots + " ", "d"), (str(val), "v")]


def kv2(k1, v1, k2, v2):
    left = kv(k1, v1, 30)
    return left + [(" | ", "d")] + kv(k2, v2, 23)


def rule(title=""):
    label = f"─ {title} " if title else ""
    return [(label, "h"), ("─" * max(W - str_width(label), 0), "d")]


def info_lines(s):
    uptime_days = (date.today() - JOINED_DATE).days
    n = lambda x: f"{x:,}"
    return [
        [(f"{USER.lower()}@github ", "h"), ("─" * (W - len(USER) - 8), "d")],
        [],
        kv("OS", "Windows, Linux"),
        kv("Uptime", f"{uptime_days:,} days (GitHub)"),
        kv("Host", "个人开发者"),
        kv("Kernel", "CS 爱好者"),
        kv("IDE", "VSCode"),
        [],
        kv("Languages.Code", "Python, JavaScript, TypeScript, C/C++"),
        kv("Languages.Real", "Chinese, English"),
        kv("Favorite", "Touhou Project (東方Project)"),
        [],
        rule("Contact"),
        kv("Blog", "https://your-blog.example.com"),
        kv("Email", "your-email@example.com"),
        [],
        rule("GitHub Stats"),
        kv2("Repos", f"{s['repos']} {{Contributed: {s['contributed']}}}", "Stars", n(s["stars"])),
        kv2("Commits", n(s["commits"]), "Followers", n(s["followers"])),
        [("Lines of Code: ", "k"), (n(s["loc"]), "v"), (" ( ", "d"),
         (n(s["loc_add"]) + "++", "g"), (", ", "d"), (n(s["loc_del"]) + "--", "r"), (" )", "d")],
    ]


def render(mode, stats):
    p = PALETTES[mode]
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="840" height="500" viewBox="0 0 840 500" '
        'font-family="Consolas, Menlo, \'Noto Sans Mono CJK SC\', \'Microsoft YaHei Mono\', monospace" font-size="13px">',
        f'<rect x="0.5" y="0.5" width="839" height="499" rx="10" fill="{p["bg"]}" stroke="{p["border"]}"/>',
    ]
    for i, line in enumerate(ART.strip("\n").split("\n")):
        out.append(f'<text x="25" y="{40 + i * 15}" fill="{p["art"]}" xml:space="preserve">{html.escape(line)}</text>')
    for i, segs in enumerate(info_lines(stats)):
        if not segs:
            continue
        spans = "".join(f'<tspan fill="{p[c]}">{html.escape(t)}</tspan>' for t, c in segs)
        out.append(f'<text x="390" y="{45 + i * 21}" xml:space="preserve">{spans}</text>')
    out.append("</svg>")
    return "\n".join(out)


def selfcheck():
    assert str_width("test") == 4
    assert str_width("测试") == 4
    assert len("".join(t for t, _ in kv("OS", "Windows, Linux"))) == W


if __name__ == "__main__":
    selfcheck()
    print(f"Fetching GitHub stats for {USER}...")
    stats = fetch_stats()
    print("Stats fetched successfully:", stats)
    for mode in PALETTES:
        filepath = f"{mode}_mode.svg"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(render(mode, stats))
        print(f"Generated {filepath}")
