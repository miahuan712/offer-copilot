# -*- coding: utf-8 -*-
import json
import os

import requests


def get_token():
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": os.environ.get("FEISHU_APP_ID", ""), "app_secret": os.environ.get("FEISHU_APP_SECRET", "")},
        headers={"Content-Type": "application/json"},
        timeout=20,
    )
    return r.json().get("tenant_access_token")


def send_text(chat_id, text):
    token = get_token()
    if not token:
        raise RuntimeError("未取到 tenant_access_token，请检查 FEISHU_APP_ID/SECRET")
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    r = requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        json={"receive_id": chat_id, "msg_type": "text", "content": json.dumps({"text": text}, ensure_ascii=False)},
        headers=headers,
        timeout=20,
    )
    d = r.json()
    if d.get("code") != 0:
        raise RuntimeError("飞书发送失败 code=%s msg=%s" % (d.get("code"), d.get("msg")))
    return d
