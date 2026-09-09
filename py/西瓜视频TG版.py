# -*- coding: utf-8 -*-
import json
import sys
import requests
from urllib.parse import urlencode

sys.path.append('..')
from base.spider import Spider as BaseSpider

class Spider(BaseSpider):
    def getName(self):
        return "小果短剧"

    def init(self, extend=""):
        self.host = "https://m.xgshort.com"
        self.token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxNzY1Njk1MTMxNTU4IiwiaWF0IjoxNzY1Njk5OTYzLCJleHAiOjE3NjYzMDQ3NjN9.yhhGifH6vVYP0lxwwKwdq4soreG8OR3vFHHoIgG6e80"
        if extend:
            try:
                cfg = json.loads(extend)
                self.host = cfg.get("site", self.host)
                self.token = cfg.get("token", self.token)
            except:
                pass

    def get_headers(self, extra=None):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{self.host}/",
            "Origin": self.host,
            "Authorization": f"Bearer {self.token}"
        }
        if extra:
            headers.update(extra)
        return headers

    def fetch(self, url, method="GET", data=None, headers=None):
        try:
            if method == "POST":
                r = requests.post(url, json=data, headers=headers, timeout=10)
            else:
                r = requests.get(url, headers=headers, timeout=10)
            r.encoding = "utf-8"
            return r.json()
        except:
            return None

    def homeContent(self, filter):
        result = {"class": []}
        cats = self.fetch(f"{self.host}/api/home/categories", headers=self.get_headers())
        if not cats:
            result["class"] = [
                {"type_name": "短剧", "type_id": "1"},
                {"type_name": "电影", "type_id": "2"},
                {"type_name": "电视剧", "type_id": "3"}
            ]
            return result

        filters = {}
        tags = self.fetch(f"{self.host}/api/list/getfilterstags", headers=self.get_headers())
        for c in cats:
            tid = str(c.get("id", ""))
            result["class"].append({"type_name": c.get("name", ""), "type_id": tid})
            if not tags or tags.get("code") != 200:
                continue
            fl = []
            for g in tags["data"]["list"]:
                k = self.get_filter_key(g.get("name", ""))
                if not k:
                    continue
                fl.append({
                    "key": k,
                    "name": g.get("name", ""),
                    "value": [{"n": i.get("classifyName", ""), "v": str(i.get("classifyId", ""))} for i in g.get("list", [])]
                })
            filters[tid] = fl
        if filters:
            result["filters"] = filters
        return result

    def get_filter_key(self, name):
        return {
            "排序": "sort",
            "题材": "theme",
            "地区": "area",
            "语言": "lang",
            "年份": "year",
            "状态": "status"
        }.get(name, name.lower())

    def homeVideoContent(self):
        result = {"list": []}
        data = self.fetch(f"{self.host}/api/home/gethomemodules?channeid=1", headers=self.get_headers())
        if not data or data.get("code") != 200:
            return result
        for m in data["data"].get("list", []):
            if m.get("type") == 3:
                for v in m.get("list", []):
                    result["list"].append({
                        "vod_id": v.get("shortId", ""),
                        "vod_name": v.get("title", ""),
                        "vod_pic": v.get("coverUrl", ""),
                        "vod_remarks": v.get("upStatus", ""),
                        "vod_score": v.get("score", ""),
                        "vod_play_count": v.get("playCount", 0)
                    })
                break
        return result

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": int(pg), "limit": 20, "pagecount": 999, "total": 999999}
        params = {
            "channeid": tid,
            "ids": self.build_filter_ids(extend),
            "page": pg,
            "size": 20
        }
        data = self.fetch(f"{self.host}/api/list/getfiltersdata?{urlencode(params)}", headers=self.get_headers())
        if not data or data.get("code") != 200:
            return result
        lst = data["data"].get("list", [])
        for v in lst:
            result["list"].append({
                "vod_id": v.get("shortId", ""),
                "vod_name": v.get("title", ""),
                "vod_pic": v.get("coverUrl", ""),
                "vod_remarks": f'{v.get("upStatus","")} | {v.get("score","")}分',
                "vod_score": v.get("score", ""),
                "vod_play_count": v.get("playCount", 0),
                "vod_author": v.get("author", ""),
                "vod_content": v.get("description", "")
            })
        total = data["data"].get("total", 0)
        if total:
            result["total"] = total
            result["pagecount"] = (total + 19) // 20
        return result

    def build_filter_ids(self, extend):
        ids = ["0"] * 7
        idx = {"sort": 0, "theme": 1, "area": 2, "lang": 3, "year": 4, "status": 5}
        for k, v in extend.items():
            if k in idx:
                ids[idx[k]] = str(v)
        return ",".join(ids)

    def detailContent(self, ids):
        result = {"list": []}
        sid = ids[0]
        data = self.fetch(f"{self.host}/api/video/episodes?seriesShortId={sid}&page=1&size=200", headers=self.get_headers())
        if not data or data.get("code") != 200:
            return result

        info = data["data"].get("seriesInfo", {})
        eps = data["data"].get("list", [])
        play = []
        for e in eps:
            if e.get("shortId") and e.get("episodeAccessKey"):
                play.append(f'{e.get("episodeTitle","")}${e["shortId"]}@@{e["episodeAccessKey"]}')
        vod = {
            "vod_id": sid,
            "vod_name": info.get("title", ""),
            "vod_pic": info.get("coverUrl", ""),
            "vod_remarks": info.get("updateStatus", ""),
            "vod_score": info.get("score", ""),
            "vod_play_count": info.get("playCount", 0),
            "vod_author": info.get("starring", ""),
            "vod_director": info.get("director", ""),
            "vod_content": info.get("description", ""),
            "vod_play_from": "小果短剧",
            "vod_play_url": "#".join(play)
        }
        tags = data["data"].get("tags", [])
        if tags:
            vod["vod_tag"] = ",".join(tags)
        result["list"].append(vod)
        return result

    def playerContent(self, flag, id, vipFlags):
        result = {}
        try:
            eid, key = id.split("@@")
            data = self.fetch(
                f"{self.host}/api/video/url/query",
                method="POST",
                data={"type": "episode", "accessKey": key},
                headers=self.get_headers({"Content-Type": "application/json"})
            )
            if data and data.get("code") == 200:
                for u in data["data"].get("urls", []):
                    if u.get("cdnUrl"):
                        result.update({"parse": 0, "url": u["cdnUrl"], "header": self.get_headers()})
                        break
        except:
            pass
        return result

    def searchContent(self, key, quick, pg="1"):
        result = {"list": [], "page": int(pg), "limit": 20, "pagecount": 1, "total": 0}
        data = self.fetch(f"{self.host}/api/list/getfiltersdata?channeid=1&ids=0,0,0,0,0,0,0&page={pg}&size=20", headers=self.get_headers())
        if not data or data.get("code") != 200:
            return result
        for v in data["data"].get("list", []):
            t = v.get("title", "")
            d = v.get("description", "")
            if key.lower() in t.lower() or key.lower() in d.lower():
                result["list"].append({
                    "vod_id": v.get("shortId", ""),
                    "vod_name": t,
                    "vod_pic": v.get("coverUrl", ""),
                    "vod_remarks": f'{v.get("upStatus","")} | {v.get("score","")}分',
                    "vod_score": v.get("score", ""),
                    "vod_play_count": v.get("playCount", 0)
                })
        result["total"] = len(result["list"])
        return result

    def isVideoFormat(self, url):
        return any(url.lower().endswith(x) for x in (".m3u8", ".mp4", ".flv", ".avi", ".mkv", ".ts"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def localProxy(self, param):
        return None