name: X metrics daily

on:
  schedule:
    # 00:55 UTC = 09:55 JST
    - cron: '55 0 * * *'
  workflow_dispatch:

jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - run: pip install requests

      - name: Fetch X metrics and post to Discord
        env:
          X_CONSUMER_KEY: ${{ secrets.X_CONSUMER_KEY }}
          X_CONSUMER_SECRET: ${{ secrets.X_CONSUMER_SECRET }}
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
        run: |
          python - <<'PY'
          import os, sys, base64, datetime as dt, requests

          # ---- 設定 ----------------------------------------------------
          USERNAME    = "BANDVAPE_"
          POSTS       = 8      # 自社の表示件数
          RIVALS      = ["mymoods_vape", "nicopuff_pr", "nicohub_japan", "vapepenzonejp"]
          RIVAL_HOURS = 26     # この時間内の新規投稿だけ＝差分
          RIVAL_MAX   = 5      # 1社あたり上限（費用の歯止め）
          # --------------------------------------------------------------

          JST = dt.timezone(dt.timedelta(hours=9))
          WD  = "月火水木金土日"

          def clean(v):
              return os.environ[v].strip().strip('"').strip("'")

          key, sec, hook = clean("X_CONSUMER_KEY"), clean("X_CONSUMER_SECRET"), clean("DISCORD_WEBHOOK_URL")

          cred = base64.b64encode(f"{key}:{sec}".encode()).decode()
          r = requests.post("https://api.x.com/oauth2/token",
              headers={"Authorization": f"Basic {cred}",
                       "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
              data={"grant_type": "client_credentials"}, timeout=30)
          if r.status_code != 200:
              sys.exit(f"Bearer取得に失敗 {r.status_code}: {r.text[:300]}")
          H = {"Authorization": f"Bearer {r.json()['access_token']}"}

          def get(path, params, soft=False):
              rr = requests.get("https://api.x.com/2" + path, headers=H, params=params, timeout=30)
              if rr.status_code != 200:
                  msg = f"APIエラー {rr.status_code} on {path}: {rr.text[:200]}"
                  if soft:
                      print("WARN:", msg); return None
                  sys.exit(msg)
              return rr.json()

          now = dt.datetime.now(JST)
          TF  = "created_at,public_metrics,attachments,text"

          def excerpt(t, cap=54):
              s = " ".join((t or "").split())
              for tok in ("http://", "https://"):
                  if tok in s:
                      s = s.split(tok)[0].strip()
              s = s.replace("`", "'").replace("*", "")
              return (s[:cap] + "…") if len(s) > cap else s

          def when(iso):
              c = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(JST)
              return c, f"{c.month}/{c.day} {c:%H:%M}", (now - c).total_seconds() / 3600

          # ---- 自社 ----------------------------------------------------
          u   = get(f"/users/by/username/{USERNAME}", {"user.fields": "public_metrics"})["data"]
          fol = u["public_metrics"]["followers_count"]
          tl  = get(f"/users/{u['id']}/tweets",
                    {"max_results": POSTS, "exclude": "retweets", "tweet.fields": TF})

          out = [f"## X ／ {now.month}/{now.day}({WD[now.weekday()]}) {now:%H:%M}",
                 f"フォロワー **{fol:,}**", ""]
          for t in tl.get("data", []):
              m = t.get("public_metrics", {})
              c, label, age = when(t["created_at"])
              rt, qt = m.get("retweet_count") or 0, m.get("quote_count") or 0
              img = len(t.get("attachments", {}).get("media_keys", []))
              url = f"https://x.com/{USERNAME}/status/{t['id']}"
              rtx = f"RT{rt}" + (f"+引用{qt}" if qt else "")
              bits = [f"**{m.get('impression_count') or 0:,}表示**", rtx,
                      f"♥{m.get('like_count') or 0}", f"💬{m.get('reply_count') or 0}",
                      ("画像なし" if img == 0 else f"画像{img}")]
              out.append(f"**[{label}]({url})**{'  🕒まだ伸びます' if age < 24 else ''}")
              out.append("　" + " ・ ".join(bits))
              out.append(f"> {excerpt(t.get('text'))}")
              out.append("")

          body1 = "\n".join(out).rstrip()

          # ---- 競合の差分 ----------------------------------------------
          since_s = (dt.datetime.now(dt.timezone.utc)
                     - dt.timedelta(hours=RIVAL_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
          rows = []
          ru = get("/users/by", {"usernames": ",".join(RIVALS)}, soft=True)
          for e in (ru or {}).get("data", []):
              res = get(f"/users/{e['id']}/tweets",
                        {"max_results": RIVAL_MAX, "exclude": "retweets,replies",
                         "start_time": since_s, "tweet.fields": TF}, soft=True)
              for t in (res or {}).get("data", []):
                  m = t.get("public_metrics", {})
                  c, label, _ = when(t["created_at"])
                  rows.append((c, e["username"], label, t["id"],
                               m.get("impression_count") or 0,
                               (m.get("retweet_count") or 0) + (m.get("quote_count") or 0),
                               m.get("like_count") or 0,
                               len(t.get("attachments", {}).get("media_keys", [])),
                               excerpt(t.get("text"), 60)))
          rows.sort(key=lambda x: -x[4])

          o2 = [f"## 競合の新規投稿 ／ 直近{RIVAL_HOURS}時間", ""]
          if not rows:
              o2.append("この時間内に新しい投稿はありませんでした。")
          for c, acc, label, tid, v, rq, lk, img, tx in rows[:10]:
              o2.append(f"**@{acc}**　{label}　"
                        f"[**{v:,}表示** ・ RT{rq} ・ ♥{lk} ・ "
                        f"{'画像なし' if img == 0 else f'画像{img}'}]"
                        f"(https://x.com/{acc}/status/{tid})")
              o2.append(f"> {tx}")
              o2.append("")
          body2 = "\n".join(o2).rstrip()

          # ---- 送信 ----------------------------------------------------
          def post(text):
              while len(text) > 1900:
                  text = text.rsplit("\n\n", 1)[0]
              resp = requests.post(hook, json={
                  "username": "Marketer",
                  "avatar_url": "https://abs.twimg.com/emoji/v2/72x72/1f98a.png",
                  "content": text, "flags": 4}, timeout=30)   # flags=4: リンクのプレビューを出さない
              print("Discord:", resp.status_code, resp.text[:150])
              resp.raise_for_status()

          print(body1); post(body1)
          print(body2); post(body2)
          PY
