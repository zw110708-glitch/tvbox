import sys
import json
import re
import time
import requests
from base64 import b64decode, b64encode

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    def init(self, extend=""):
        config = {}
        try:
            config = json.loads(extend) if isinstance(extend, str) and extend.strip() else (extend or {})
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        self.host = "https://beeg.com"
        self.api_host = "https://store.externulls.com"
        self.video_host = "https://video.externulls.com"
        self.plp = config.get('plp', '')       # 播放器/封面/播放地址 URL 前缀，空=直连
        self.proxy = config.get('proxy', {})   # 内部请求代理，空 dict=直连
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; Pixel 4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Mobile Safari/537.36",
            "Referer": self.host + "/",
            "Origin": self.host,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
        }
        self.timeout = 15
        self.retries = 2

    def getName(self):
        return "Beeg"

    def isVideoFormat(self, url):
        return True

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def homeContent(self, filter):
        return {"class": [
            {"type_id": "latest", "type_name": "最新动态"},
            {"type_id": "channels", "type_name": "频道"},
            {"type_id": "pornstars", "type_name": "明星"},
            {"type_id": "categories", "type_name": "分类"}
        ]}

    def homeVideoContent(self):
        return self.categoryContent("latest", 1, None, {})

    def categoryContent(self, tid, pg, filter, extend):
        limit = 48
        offset = (int(pg) - 1) * limit
        if tid == "latest":
            videos = self._fetch_video_list(f"{self.api_host}/facts/tag?id=27173&limit={limit}&offset={offset}")
        elif tid in ("channels", "pornstars", "categories"):
            videos = self._fetch_section_list(tid)
        else:
            url = tid if tid.startswith("http") else f"{self.api_host}/facts/tag?slug={tid}&limit={limit}&offset=0"
            url = re.sub(r"([?&])offset=\d+", rf"\1offset={offset}", url)
            videos = self._fetch_video_list(url)
        return {"list": videos, "page": pg, "pagecount": 9999, "limit": limit, "total": 999999}

    def searchContent(self, key, quick, pg="1"):
        return {"list": []}

    def detailContent(self, ids):
        url = ids[0]
        video_id = self._video_id(url)
        data = json.loads(self.fetch(f"{self.api_host}/facts/file/{video_id}", headers=self.headers).text)
        title = self._file_title(data.get("file", {}), f"Beeg Video {video_id}")
        tags, actors, desc = self._detail_tags(data.get("tags", []))
        content = (desc + (" " + " ".join(tags) if tags else "")).strip()
        vod = {
            "vod_id": url,
            "vod_name": title,
            "vod_pic": self.plp + self._video_thumb(video_id),
            "vod_remarks": "",
            "vod_content": content,
            "vod_play_from": "Beeg",
            "vod_play_url": f"播放${self.e64(video_id)}"
        }
        if actors:
            vod["vod_actor"] = " ".join(actors)
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        vid = self._video_id(self.d64(id))
        data = json.loads(self.fetch(f"{self.api_host}/facts/file/{vid}", headers=self.headers).text)
        resources = data["file"]["hls_resources"]
        numeric = [(int(k[7:]), v) for k, v in resources.items() if k.startswith("fl_cdn_") and k[7:].isdigit()]
        path = max(numeric)[1] if numeric else resources["fl_cdn_multi"].replace("/_TPL_/", "/1080p/")
        return {
            "parse": 0,
            "url": self.plp + f"{self.video_host}/{path}",
            "header": {"User-Agent": self.headers["User-Agent"], "Referer": self.host + "/", "Origin": self.host}
        }

    def _fetch_video_list(self, url):
        items = json.loads(self.fetch(url, headers=self.headers).text)
        videos = []
        for elem in items if isinstance(items, list) else []:
            file_info = elem.get("file", {})
            video_id = file_info.get("id")
            if video_id:
                videos.append({
                    "vod_id": f"{self.host}/{video_id}",
                    "vod_name": self._file_title(file_info, str(video_id)),
                    "vod_pic": self.plp + self._video_thumb(video_id),
                    "vod_remarks": str(file_info.get("fl_duration", ""))
                })
        return videos

    def _fetch_section_list(self, section_type):
        tag_type = {"categories": "other", "channels": "brand", "pornstars": "person"}[section_type]
        data = json.loads(self.fetch(f"{self.api_host}/tag/recommends?type={tag_type}&slug=index", headers=self.headers).text)
        videos = []
        for elem in data if isinstance(data, list) else []:
            title = elem.get("tg_name", "")
            slug = elem.get("tg_slug", "")
            if title and slug:
                videos.append({
                    "vod_id": f"{self.api_host}/facts/tag?slug={slug}&limit=48&offset=0",
                    "vod_name": title,
                    "vod_pic": self._tag_thumb(elem),
                    "vod_tag": "folder",
                    "vod_remarks": "分类"
                })
        return videos

    def _detail_tags(self, tags_raw):
        tags, actors, desc = [], [], ""
        for tag in tags_raw:
            name = (tag.get("tg_name") or "").strip()
            slug = (tag.get("tg_slug") or "").strip()
            kind = ""
            for item in tag.get("data", []):
                col = item.get("td_column")
                val = (item.get("td_value") or "").strip()
                if col == "tg_caption" and not desc:
                    desc = val
                elif col == "tg_name" and not name:
                    name = val
                elif col == "tg_slug" and not slug:
                    slug = val
                elif col == "tg_kind":
                    kind = val
            if name and slug:
                text = f"[a=cr:{json.dumps({'id': f'{self.api_host}/facts/tag?slug={slug}&limit=48&offset=0', 'name': name}, ensure_ascii=False)}/]{name}[/a]"
                tags.append(text)
                if tag.get("is_person") or kind == "human":
                    actors.append(text)
        return tags, actors, desc

    def _file_title(self, file_info, default):
        data = file_info.get("data", [])
        return data[0].get("cd_value") or default if data else default

    def _video_id(self, value):
        value = str(value).rstrip("/").split("/")[-1]
        return re.sub(r"^0+", "", re.sub(r"\D", "", value)) or value

    def _video_thumb(self, video_id):
        return f"https://thumbs.externulls.com/videos/{video_id}/0.webp?size=480x270"

    def _tag_thumb(self, elem):
        thumbs = elem.get("thumbs", [])
        if not thumbs or not thumbs[0].get("id"):
            return ""
        crop = thumbs[0].get("crops", [])
        query = f"?crop_id={crop[0]['id']}&size_new=128x128" if crop and crop[0].get("id") else "?size_new=128x128"
        return f"{self.plp}https://thumbs.externulls.com/photos/{thumbs[0]['id']}/to.webp{query}"

    def e64(self, text):
        return b64encode(str(text).encode()).decode()

    def d64(self, encoded_text):
        return b64decode(encoded_text.encode()).decode()

    def fetch(self, url, params=None, headers=None, timeout=None):
        for i in range(self.retries + 1):
            try:
                r = requests.get(url, params=params, headers=headers or self.headers, timeout=timeout or self.timeout, verify=False, proxies=self.proxy)
                r.encoding = "utf-8"
                return r
            except Exception:
                if i == self.retries:
                    raise
                time.sleep(1)
