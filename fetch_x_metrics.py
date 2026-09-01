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
          USERNAME = "BANDVAPE_"
          POSTS    = 10        # 自社の取得件数
          RIVALS   = ["mymoods_vape", "nicopuff_pr", "nicohub_japan", "vapepenzonejp"]
          RIVAL_HOURS = 26     # この時間内に投稿されたものだけ＝差分
          RIVAL_MAX   = 5      # 1社あたり最大件数（費用の上限）
          # --------------------------------------------------------------

          JST = dt.timezone(dt.timedelta(hours=9))
          WD = "月火水木金土日"

          def clean(v):
              return os.environ[v].strip().strip('"').strip("'")

          key, sec, hook = clean("X_CONSUMER_KEY"), clean("X_CONSUMER_SECRET"), clean("DISCORD_WEBHOOK_URL")

          cred = base64.b64encode(f"{key}:{sec}".encode()).decode()
          r = requests.post(
              "https://api.x.com/oauth2/token",
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
                      print("WARN:", msg)
                      return None
                  sys.exit(msg)
              return rr.json()

          now = dt.datetime.now(JST)
          TF = "created_at,public_metrics,attachments"

          # ---- 自社 ----------------------------------------------------
          u = get(f"/users/by/username/{USERNAME}", {"user.fields": "public_metrics"})["data"]
          fol = u["public_metrics"]["followers_count"]
          tl = get(f"/users/{u['id']}/tweets",
                   {"max_results": POSTS, "exclude": "retweets", "tweet.fields": TF})

          own = ["#XMETRICS v2",
                 f"fetched_at\t{now.isoformat(timespec='seconds')}",
                 f"followers\t{fol}",
                 "id\tcreated_at\timpressions\treposts\tlikes\treplies\tquotes\tbookmarks\timages"]
          for t in tl.get("data", []):
              m = t.get("public_metrics", {})
              own.append("\t".join(str(x) for x in [
                  t["id"], t.get("created_at"), m.get("impression_count"),
                  m.get("retweet_count"), m.get("like_count"), m.get("reply_count"),
                  m.get("quote_count"), m.get("bookmark_count"),
                  len(t.get("attachments", {}).get("media_keys", []))]))

          body1 = (f"## X 実測 ／ {now.month}/{now.day}({WD[now.weekday()]}) {now:%H:%M} JST\n"
                   f"フォロワー **{fol:,}**\n```\n" + "\n".join(own) + "\n```")

          # ---- 競合の差分（直近RIVAL_HOURS時間の新規投稿だけ） --------
          since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=RIVAL_HOURS))
          since_s = since.strftime("%Y-%m-%dT%H:%M:%SZ")

          riv = ["#XRIVALS v1", f"window\t直近{RIVAL_HOURS}時間",
                 "account\tid\tcreated_at\timpressions\treposts\tlikes\treplies\tquotes\timages\ttext"]
          found = 0
          ru = get("/users/by", {"usernames": ",".join(RIVALS)}, soft=True)
          for entry in (ru or {}).get("data", []):
              res = get(f"/users/{entry['id']}/tweets",
                        {"max_results": RIVAL_MAX, "exclude": "retweets,replies",
                         "start_time": since_s, "tweet.fields": TF + ",text"}, soft=True)
              for t in (res or {}).get("data", []):
                  m = t.get("public_metrics", {})
                  txt = (t.get("text") or "").replace("\n", " ").replace("\t", " ")[:80]
                  riv.append("\t".join(str(x) for x in [
                      entry["username"], t["id"], t.get("created_at"),
                      m.get("impression_count"), m.get("retweet_count"), m.get("like_count"),
                      m.get("reply_count"), m.get("quote_count"),
                      len(t.get("attachments", {}).get("media_keys", [])), txt]))
                  found += 1

          if found == 0:
              riv.append("（この時間内に競合の新規投稿なし）")
          body2 = f"## 競合の新規投稿 ／ 直近{RIVAL_HOURS}時間で {found}件\n```\n" + "\n".join(riv) + "\n```"

          # ---- 送信 ----------------------------------------------------
          def post(text):
              while len(text) > 1900:
                  text = text.rsplit("\n", 2)[0] + "\n```"
              resp = requests.post(hook, json={
                  "username": "Marketer",
                  "avatar_url": "https://abs.twimg.com/emoji/v2/72x72/1f98a.png",
                  "content": text}, timeout=30)
              print("Discord:", resp.status_code, resp.text[:150])
              resp.raise_for_status()

          print(body1); post(body1)
          print(body2); post(body2)
          PY
