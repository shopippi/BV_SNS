#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BandVape X メトリクス取得スクリプト

@BANDVAPE_ のフォロワー数と直近投稿の指標（表示回数・いいね・リポスト・返信・引用・ブックマーク）
を X API v2 から取得し、JSONで保存する。--discord を付けると Discord にも投稿する。

■ 使い方
  1) 環境変数にキーを入れる（このファイルにキーを書かないこと）
       export X_CONSUMER_KEY='...'
       export X_CONSUMER_SECRET='...'
       export DISCORD_WEBHOOK_URL='...'      # --discord を使うときだけ
  2) 実行
       python3 fetch_x_metrics.py
       python3 fetch_x_metrics.py --discord
       python3 fetch_x_metrics.py --status 2093540139066929233   # 特定投稿だけ

■ 依存
  requests のみ。  pip3 install requests

■ 消費する読み取り回数
  通常実行で 2回（ユーザー情報1 + タイムライン1）。--status を足すと +1。
"""

import os
import sys
import json
import base64
import argparse
import datetime as dt

try:
    import requests
except ImportError:
    sys.exit("requests が必要です:  pip3 install requests")

USERNAME = "BANDVAPE_"
OUT_DIR = os.path.expanduser("~/bandvape-x-metrics")

TWEET_FIELDS = "created_at,public_metrics,attachments,text"
USER_FIELDS = "public_metrics,username,name"


def get_bearer(key: str, secret: str) -> str:
    """コンシューマーキー/シークレットから app-only Bearer Token を取得する。"""
    cred = base64.b64encode(f"{key}:{secret}".encode()).decode()
    r = requests.post(
        "https://api.x.com/oauth2/token",
        headers={
            "Authorization": f"Basic {cred}",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        },
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    if r.status_code != 200:
        sys.exit(f"Bearer Token の取得に失敗 ({r.status_code}): {r.text[:400]}")
    return r.json()["access_token"]


def api_get(bearer: str, path: str, params: dict) -> dict:
    r = requests.get(
        f"https://api.x.com/2{path}",
        headers={"Authorization": f"Bearer {bearer}"},
        params=params,
        timeout=30,
    )
    if r.status_code == 429:
        sys.exit("レート制限に達しました。時間をおいて再実行してください。")
    if r.status_code == 403:
        sys.exit(
            f"403: このエンドポイントは現在のプランで読めません。\n"
            f"Developer Portal でプラン/クレジット残高を確認してください。\n{r.text[:400]}"
        )
    if r.status_code != 200:
        sys.exit(f"API エラー ({r.status_code}): {r.text[:400]}")
    return r.json()


def fetch(bearer: str, status_id: str | None):
    user = api_get(bearer, f"/users/by/username/{USERNAME}", {"user.fields": USER_FIELDS})
    if "data" not in user:
        sys.exit(f"ユーザーが取得できません: {json.dumps(user, ensure_ascii=False)[:400]}")
    u = user["data"]
    uid = u["id"]

    result = {
        "取得時刻": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "アカウント": u["username"],
        "フォロワー": u["public_metrics"]["followers_count"],
        "フォロー中": u["public_metrics"]["following_count"],
        "投稿数": u["public_metrics"]["tweet_count"],
        "投稿": [],
    }

    tl = api_get(
        bearer,
        f"/users/{uid}/tweets",
        {"max_results": 20, "tweet.fields": TWEET_FIELDS, "exclude": "retweets"},
    )
    for t in tl.get("data", []):
        pm = t.get("public_metrics", {})
        result["投稿"].append(
            {
                "url": f"https://x.com/{USERNAME}/status/{t['id']}",
                "投稿日時": t.get("created_at"),
                "表示回数": pm.get("impression_count"),
                "いいね": pm.get("like_count"),
                "リポスト": pm.get("retweet_count"),
                "引用": pm.get("quote_count"),
                "返信": pm.get("reply_count"),
                "ブックマーク": pm.get("bookmark_count"),
                "画像枚数": len(t.get("attachments", {}).get("media_keys", [])),
                "本文": (t.get("text") or "").replace("\n", " / ")[:100],
            }
        )

    if status_id:
        one = api_get(bearer, f"/tweets/{status_id}", {"tweet.fields": TWEET_FIELDS})
        d = one.get("data")
        if d:
            pm = d.get("public_metrics", {})
            result["指定投稿"] = {
                "url": f"https://x.com/{USERNAME}/status/{d['id']}",
                "投稿日時": d.get("created_at"),
                "表示回数": pm.get("impression_count"),
                "いいね": pm.get("like_count"),
                "リポスト": pm.get("retweet_count"),
                "引用": pm.get("quote_count"),
                "返信": pm.get("reply_count"),
                "ブックマーク": pm.get("bookmark_count"),
            }
    return result


def to_discord_text(r: dict) -> str:
    """機械可読な形で出す。先頭行のマーカーで自動処理側が拾えるようにしてある。"""
    head = (
        f"## X 実測 ／ {r['取得時刻'][:16].replace('T', ' ')}\n"
        f"フォロワー **{r['フォロワー']}**（フォロー中 {r['フォロー中']} / 総投稿 {r['投稿数']}）"
    )
    rows = [
        "#XMETRICS v1",
        f"fetched_at\t{r['取得時刻']}",
        f"followers\t{r['フォロワー']}",
        "id\tcreated_at\timpressions\treposts\tlikes\treplies\tquotes\tbookmarks\timages",
    ]
    for p_ in r["投稿"][:10]:
        tid = p_["url"].rsplit("/", 1)[-1]
        rows.append(
            "\t".join(
                str(x)
                for x in [
                    tid,
                    p_["投稿日時"],
                    p_["表示回数"],
                    p_["リポスト"],
                    p_["いいね"],
                    p_["返信"],
                    p_["引用"],
                    p_["ブックマーク"],
                    p_["画像枚数"],
                ]
            )
        )
    block = "```\n" + "\n".join(rows) + "\n```"
    out = head + "\n" + block
    while len(out) > 1900 and len(rows) > 5:
        rows.pop()
        block = "```\n" + "\n".join(rows) + "\n```"
        out = head + "\n" + block
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", help="この投稿IDの指標も個別に取る")
    ap.add_argument("--discord", action="store_true", help="Discordにも投稿する")
    args = ap.parse_args()

    key = os.environ.get("X_CONSUMER_KEY")
    secret = os.environ.get("X_CONSUMER_SECRET")
    if not key or not secret:
        sys.exit(
            "環境変数 X_CONSUMER_KEY と X_CONSUMER_SECRET を設定してください。\n"
            "このファイルにキーを直接書かないこと。"
        )

    bearer = get_bearer(key, secret)
    result = fetch(bearer, args.status)

    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    path = os.path.join(OUT_DIR, f"x-{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    print(to_discord_text(result))
    print(f"\n保存先: {path}")

    if args.discord:
        hook = os.environ.get("DISCORD_WEBHOOK_URL")
        if not hook:
            sys.exit("DISCORD_WEBHOOK_URL が未設定です。")
        resp = requests.post(
            hook,
            json={
                "username": "Marketer",
                "avatar_url": "https://abs.twimg.com/emoji/v2/72x72/1f98a.png",
                "content": to_discord_text(result),
            },
            timeout=30,
        )
        print("Discord:", resp.status_code)


if __name__ == "__main__":
    main()
