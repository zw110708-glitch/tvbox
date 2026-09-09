# -*- coding: utf-8 -*-
"""https://www.uaa001.com/"""
import json
import sys

sys.path.append('..')
try:
    from base.spider import Spider as _BaseSpider
except ImportError:
    class _BaseSpider:
        pass

try:
    import requests
except ImportError:
    requests = None

_API = bytes([104,116,116,112,115,58,47,47,97,112,105,46,109,97,114,99,104,50,52,49,54,56,46,111,110,108,105,110,101]).decode()
_CDN = bytes([104,116,116,112,115,58,47,47,99,100,110,46,117,97,109,101,116,97,46,97,105,47,102,105,108,101,47,98,117,99,107,101,116,45,109,101,100,105,97]).decode()
_UA = "Dart/3.11 (dart:io)"
_LOGIN_NAME = bytes([50,56,53,56,56,54,55,53,49,64,113,113,46,99,111,109]).decode()
_PASSWORD = bytes([113,119,101,114,52,51,50,49]).decode()

_AUTHORS = (
    ("FC2", "FC2"),
    ("MOODYZ", "MOODYZ(Moody's)"),
    ("S1", "S1 No. 1 Style"),
    ("加勒比", "加勒比"),
    ("一本道", "一本道"),
    ("麻豆传媒", "麻豆传媒"),
)


class Spider(_BaseSpider):
    def init(self, extend=""):
        self.session = requests.Session()
        self.session.headers.update({"user-agent": _UA, "accept-encoding": "gzip"})
        self.token = ""
        self.items = {}
        try:
            cfg = json.loads(extend) if extend else {}
        except Exception:
            cfg = {}
        self.login_name = cfg.get("loginName") or _LOGIN_NAME
        self.password = cfg.get("password") or _PASSWORD
        self.plp = cfg.get('plp', '')
        self.proxy = cfg.get("proxy") or {}
        self.session.proxies = self.proxy

    def getName(self):
        return "March 视频"

    def _login(self):
        if self.token:
            return True
        if not self.login_name or not self.password:
            return False
        try:
            resp = self.session.post(
                _API + "/console/app/login",
                params={"loginName": self.login_name, "password": self.password, "platform": "app"},
                timeout=25,
            ).json()
            self.token = resp.get("model", {}).get("token", "") if resp.get("code") == 0 else ""
            return bool(self.token)
        except Exception:
            return False

    def _request(self, path, params=None):
        if not self._login():
            return None
        try:
            resp = self.session.get(_API + path, params=params or {}, headers={"token": self.token}, timeout=25)
            if resp.status_code in (401, 403):
                self.token = ""
                return None
            data = resp.json()
            return data.get("model") if data.get("code") == 0 else None
        except Exception:
            return None

    def _cover(self, item):
        cover = item.get("coverUrl") or item.get("cover") or ""
        if cover.startswith("http"):
            return cover
        return _CDN + cover if cover.startswith("/") else ""

    def _item(self, item):
        return {
            "vod_id": str(item.get("id", "")),
            "vod_name": item.get("title") or item.get("number") or "未命名视频",
            "vod_pic": self.plp + self._cover(item),
            "vod_remarks": item.get("categories") or item.get("tags") or "",
        }

    def homeContent(self, filter=False):
        # 最新视频放在最前
        classes = [{"type_id": "video", "type_name": "最新视频"}]
        classes.extend({"type_id": str(i), "type_name": name} for i, name in enumerate(("国产视频", "日本av", "H动漫"), 1))
        classes.extend({"type_id": "author:%d" % idx, "type_name": name} for idx, (name, _) in enumerate(_AUTHORS))
        return {"class": classes}

    def homeVideoContent(self):
        return self.categoryContent("video", 1)

    def categoryContent(self, tid, pg=1, filter=False, extend=None):
        page = max(1, int(pg))
        params = {"orderType": 2, "page": page, "size": 50}
        tid_str = str(tid)

        if tid_str.startswith("author:"):
            try:
                author = _AUTHORS[int(tid_str.split(":", 1)[1])][1]
                params.update({"searchType": 2, "author": author})
            except (IndexError, ValueError):
                return {"list": [], "page": page, "pagecount": 1, "limit": 50, "total": 0}
        elif tid_str in ("1", "2", "3"):
            params["origin"] = tid_str
        elif tid_str == "video":
            pass
        elif tid_str.startswith("tag:"):
            tag = tid_str.split(":", 1)[1]
            if tag:
                params.update({"searchType": 1, "tag": tag})
        elif tid_str.startswith("actress:"):
            actress = tid_str.split(":", 1)[1]
            if actress:
                params.update({"searchType": 1, "keyword": actress})
        elif tid_str.startswith("studio:"):
            studio = tid_str.split(":", 1)[1]
            if studio:
                params.update({"searchType": 2, "author": studio})
        else:
            params.update({"searchType": 1, "keyword": tid_str})

        model = self._request("/video/app/video/search", params)
        if not model:
            return {"list": [], "page": page, "pagecount": 1, "limit": 50, "total": 0}
        data = model.get("data") or []
        for item in data:
            self.items[str(item.get("id", ""))] = item
        return {
            "list": [self._item(item) for item in data],
            "page": model.get("currentPage", page),
            "pagecount": model.get("totalPage", 1),
            "limit": model.get("pageSize", 50),
            "total": model.get("totalCount", 0),
        }

    def searchContent(self, key, quick=False, pg=1):
        return self.categoryContent("keyword:" + key, pg)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        video_id = str(ids[0])
        item = self.items.get(video_id)
        if not item:
            detail = self._request("/video/app/video/detail", {"id": video_id})
            if not detail:
                return {"list": []}
            item = detail

        vod = self._item(item)
        url = item.get("url") or ""

        actress = item.get("actress") or item.get("actressNames") or ""
        if actress:
            if isinstance(actress, str):
                names = [n.strip() for n in actress.split(',') if n.strip()]
            elif isinstance(actress, list):
                names = [str(a.get("name") or a) for a in actress if a]
            else:
                names = [str(actress)]
            vod["vod_actor"] = " ".join(f'[a=cr:{{"id":"actress:{n}","name":"{n}"}}/]{n}[/a]' for n in names if n)

        author = item.get("authors") or item.get("author") or ""
        if author:
            vod["vod_director"] = f'[a=cr:{{"id":"studio:{author}","name":"{author}"}}/]{author}[/a]'

        tags = item.get("tags") or item.get("tagList") or []
        if isinstance(tags, str):
            tag_list = [t.strip() for t in tags.split(',') if t.strip()]
        else:
            tag_list = [str(t) for t in tags if t]
        brief = item.get("brief") or item.get("description") or ""
        if tag_list:
            tag_html = " ".join(f'[a=cr:{{"id":"tag:{t}","name":"{t}"}}/]#{t}[/a]' for t in tag_list)
            vod["vod_content"] = tag_html + " " + brief if brief else tag_html
        else:
            vod["vod_content"] = brief

        vod["vod_play_from"] = "官方线路"
        vod["vod_play_url"] = "播放$" + url if url else ""
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags=None):
        return {"url": id, "header": json.dumps({"user-agent": _UA})} if id else {"url": ""}

    def localProxy(self, param):
        return [404, "text/plain", b""]
