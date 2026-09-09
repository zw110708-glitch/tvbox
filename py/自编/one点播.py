# -*- coding: utf-8 -*-
import base64
import hashlib
import json
import re
import time
import urllib.parse
import zlib
import datetime

import requests

from base.spider import Spider as BaseSpider


# 分类：model_id_demand_tag_id -> 名称（实测 model_id=6 为主视频区，tag 1~5 = 欧美/日本/国产/直播/新作；3_3 = 4K独播）
FILM_FILTERS = {"6_1": "欧美", "6_2": "日本", "6_3": "国产", "6_4": "直播", "6_5": "新作", "3_3": "4K独播", "manga": "漫画", "album": "写真"}
FILM_ORDER = ("6_3", "6_2", "6_1", "6_5", "3_3", "6_4", "manga", "album")

ONE_API = "https://api.em1oifd0.com/"
ONE_MIRRORS = ("https://api.3459381.com/", "https://api.61c76a0.com/", "https://api.87735d5.com/", "https://api.c6dd5cc.com/", "https://api.j7y675.com/", "https://api.em1oifd0.com/")
BOOTSTRAP_LINES = ("http://198.44.248.101:9672/", "http://198.44.248.102:9672/", "http://122.10.20.249:9672/")
BOX_KEY = b"dnf45as45fs1ace1"
BOX_IV = b"dn5as4fs1ac5f4e1"
ONE_KEY = b"l*bv%Ziq000Biaog"
ONE_IV = b"8597506002939249"
ONE_SIGN_SUFFIX = "m4n2hjPeYWkD6tFpqKF^3HO^h24P@idT"
ONE_IMAGE_KEY = b"saIZXc4yMvq0Iz56"
ONE_IMAGE_IV = b"kbJYtBJUECT0oyjo"
REQUEST_TIMEOUT = 15
PAGE_SIZE = 30

# 排序参数（实测 discovery 的 sort 有效值）
SORT_OPTIONS = [
    {"n": "最新", "v": "published_at"},
    {"n": "最热", "v": "views"},
    {"n": "点赞", "v": "like_number"},
    {"n": "下载", "v": "download_count"},
    {"n": "收藏", "v": "collection_number"},
]


def _pad(data):
    length = 16 - (len(data) % 16)
    return data + bytes([length]) * length


def _unpad(data):
    if not data:
        return data
    length = data[-1]
    if length < 1 or length > 16 or data[-length:] != bytes([length]) * length:
        raise ValueError("invalid cipher padding")
    return data[:-length]


def _aes(data, key, iv, decrypt=False):
    try:
        from Crypto.Cipher import AES
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return cipher.decrypt(data) if decrypt else cipher.encrypt(_pad(data))
    except ImportError:
        import subprocess
        command = ["openssl", "enc", "-aes-128-cbc"]
        if decrypt:
            command.append("-d")
        command.extend(["-nopad", "-K", key.hex(), "-iv", iv.hex()])
        source = data if decrypt else _pad(data)
        process = subprocess.run(command, input=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return process.stdout


def _decrypt_one_image(data):
    return _unpad(_aes(data, ONE_IMAGE_KEY, ONE_IMAGE_IV, decrypt=True))


def _image_kind(data):
    if data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n") and data.endswith(b"IEND\xaeB`\x82"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")) and data.endswith(b";"):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP" and len(data) >= 12 and int.from_bytes(data[4:8], "little") == len(data) - 8:
        return "image/webp"
    return None


def _choose_media(item):
    if not isinstance(item, dict):
        return None
    for field in ("video_hls", "video_hls_h265", "video_file", "video"):
        value = item.get(field)
        if isinstance(value, str) and value and not Spider._is_audio_path(value) and not any(word in field.lower() for word in ("preview", "trailer", "sample")):
            return field, value
    return None


def _diagnostic(message, detail=None):
    safe = str(message).replace("\n", " ")[:180]
    if detail:
        safe += ": " + str(detail).replace("\n", " ")[:180]
    return {"error": safe}


class Spider(BaseSpider):
    def __init__(self):
        super().__init__()
        self._ready = False
        self._token = None
        self._hosts = {}
        self.proxy = {}
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "Dart/3.4 (dart:io)"})

    def init(self, extend=""):
        self.extend = extend or ""
        self._ready = False
        cfg = {}
        if self.extend:
            try:
                parsed = json.loads(self.extend)
                if isinstance(parsed, dict):
                    cfg = parsed
            except Exception:
                cfg = {}
        self.plp = cfg.get('plp', '')
        self.proxy = cfg.get("proxy") or {}
        # 可选：extend 传自定义身份（uuid / user_key）访问 VIP 内容
        self._uuid = cfg.get('uuid') or cfg.get('_uuid') or ''
        self._user_key = cfg.get('user_key') or cfg.get('_user_key') or ''

    # ---------- 初始化 / 加密请求 ----------
    def _ensure_ready(self):
        if self._ready:
            return None
        try:
            self._bootstrap()
            self._ready = True
            return None
        except Exception as error:
            return _diagnostic("初始化失败", type(error).__name__)

    def _bootstrap(self):
        last = None
        for line in BOOTSTRAP_LINES:
            try:
                response = self._session.post(line + "box/api/config", params={"channel": "Channel"}, timeout=REQUEST_TIMEOUT, proxies=self.proxy)
                response.raise_for_status()
                config = self._decode_box(response.content)
                if not isinstance(config.get("data"), dict):
                    raise ValueError("invalid config shape")
                self._token = next(item["token"] for item in config["data"].get("token", []) if item.get("name") == "token_one")
                self._hosts = {item.get("name"): item.get("host", "") for item in config["data"].get("api", [])}
                return
            except Exception as error:
                last = error
        raise RuntimeError(type(last).__name__ if last else "bootstrap unavailable")

    @staticmethod
    def _decode_box(body):
        raw = _unpad(_aes(body, BOX_KEY, BOX_IV, decrypt=True))
        return json.loads(zlib.decompress(raw).decode("utf-8"))

    def _one_headers(self):
        timestamp = str(int(time.time()))
        uuid = getattr(self, "_uuid", None) or "48b067ec-6cfd-3491-84f5-023eb1e7d562"
        user_key = getattr(self, "_user_key", None) or "563e8eeef42931cc858dc0d1080f4f6f"
        first = hashlib.md5(".".join(("0.0.0.0", "3", timestamp, user_key, uuid)).encode()).hexdigest()
        sign = hashlib.md5((first + ONE_SIGN_SUFFIX).encode()).hexdigest()
        return {"ip": "0.0.0.0", "uuid": uuid, "timestamp": timestamp, "platform": "3", "token": self._token, "sign": sign, "user-key": user_key, "app-version": "2.6.3.1", "Content-Type": "application/x-www-form-urlencoded"}

    def _request(self, endpoint, params, retries=1):
        query = "&".join("{}={}".format(key, params[key]) for key in sorted(params))
        encoded = base64.b64encode(_aes(query.encode(), ONE_KEY, ONE_IV)).decode()
        primary = self._hosts.get("one", ONE_API)
        bases = [primary] + [m for m in ONE_MIRRORS if m != primary][:1]
        last = None
        for attempt in range(retries + 1):
            for base in bases:
                try:
                    response = self._session.post(base.rstrip("/") + "/" + endpoint.lstrip("/"), data=encoded, headers=self._one_headers(), timeout=8, proxies=self.proxy)
                    response.raise_for_status()
                    decoded = _aes(base64.b64decode(response.text.strip()), ONE_KEY, ONE_IV, decrypt=True)
                    return json.loads(_unpad(decoded).decode("utf-8"))
                except Exception as error:
                    last = error
            if attempt < retries:
                time.sleep(0.4 * (attempt + 1))
        raise last

    def _one_url(self, name, path):
        prefix = self._hosts.get(name, "")
        if not prefix:
            return ""
        return urllib.parse.urljoin(prefix, path.lstrip("/"))

    def _proxy_url(self, url):
        return self.getProxyUrl() + "&url=" + urllib.parse.quote(url, safe="")

    @staticmethod
    def _is_audio_path(path):
        return isinstance(path, str) and path.lower().split("?", 1)[0].endswith((".mp3", ".m4a", ".aac", ".wav", ".flac"))

    def _is_playable(self, item):
        # 有正式视频、content 里有正文图（漫画/图文）、或纯 GIF 封面 都可播放
        if _choose_media(item):
            return True
        content = str(item.get("content") or "")
        if '<img' in content:
            return True
        thumb = str(item.get("thumb") or "")
        return thumb.lower().endswith(".gif") or item.get("model_id") == 1

    # 可点击标签：点击后前端调 categoryContent(tid=id)；id 用 quote 编码的关键词，categoryContent 里 unquote 还原后走搜索
    def _cr(self, vid, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({"id": str(vid), "name": str(name)}, ensure_ascii=False), name)

    def _srch(self, keyword):
        return self._cr(urllib.parse.quote(str(keyword), safe=''), keyword)

    # ---------- 列表项构造 ----------
    def _cover(self, item):
        cover = item.get("thumb") or item.get("thumbnail") or ""
        if cover and not cover.startswith(("http://", "https://")):
            cover = self._one_url("one_img", cover)
        if cover:
            cover = self._proxy_url(cover)
        return cover

    def _item(self, item):
        playable = self._is_playable(item)
        return {
            "vod_id": str(item.get("id", "")),
            "vod_name": item.get("title", ""),
            "vod_pic": self._cover(item),
            "vod_remarks": item.get("length") or item.get("video_length") or "",
            "vod_content": item.get("description", ""),
            "vod_play_from": "One" if playable else "",
            "vod_play_url": "正片$" + str(item.get("id")) if playable else "",
        }

    def _series_item(self, item, kind):
        vid = ("m:" if kind == "manga" else "a:") + str(item.get("id", ""))
        return {
            "vod_id": vid,
            "vod_name": item.get("title", ""),
            "vod_pic": self._cover(item),
            "vod_remarks": (item.get("latest_at") or "")[:10],
            "vod_year": (item.get("first_at") or "")[:4],
            "vod_content": "作者: {}".format(item.get("author", "")),
            "vod_play_from": "漫画" if kind == "manga" else "写真",
            "vod_play_url": "全篇${}".format(vid),
        }

    def _dedup_rows(self, result, by_title=False):
        items = result.get("data", []) if isinstance(result, dict) else []
        seen = set()
        seen_title = set()
        rows = []
        for item in items:
            if not item.get("id") or item.get("id") in seen:
                continue
            title = item.get("title") or ""
            if by_title and title and title in seen_title:
                continue
            seen.add(item.get("id"))
            if by_title and title:
                seen_title.add(title)
            rows.append(self._item(item))
        return rows

    # ---------- 首页 / 分类 ----------
    def _filters(self):
        result = {}
        for key in FILM_ORDER:
            if key in ("manga", "album"):
                continue
            result[key] = [{"key": "order", "name": "排序", "value": SORT_OPTIONS}]
        return result

    def homeContent(self, filter):
        result = {"class": [{"type_id": key, "type_name": FILM_FILTERS[key]} for key in FILM_ORDER], "filters": self._filters(), "list": []}
        error = self._ensure_ready()
        if error:
            return result
        try:
            data = self._request("v2.5/article/discovery", {"demand_tag_id": 0, "model_id": 6, "page": 1, "published_at": self._month_str(0), "size": PAGE_SIZE, "sort": "published_at"})
            result["list"] = self._dedup_rows(data)
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return {"list": []}

    @staticmethod
    def _month_str(back):
        now = datetime.datetime.now()
        year, month = now.year, now.month - back
        while month <= 0:
            month += 12
            year -= 1
        return "%04d-%02d" % (year, month)

    def _monthly_discovery(self, model, tag, page, sort="published_at", months=12):
        acc = 0
        for back in range(months):
            month = self._month_str(back)
            result = self._request("v2.5/article/discovery", {"demand_tag_id": tag, "model_id": model, "page": 1, "published_at": month, "size": PAGE_SIZE, "sort": sort})
            first = result.get("data", []) if isinstance(result, dict) else []
            pages = (len(first) + PAGE_SIZE - 1) // PAGE_SIZE
            if not pages:
                continue
            if page <= acc + pages:
                inner = page - acc
                if inner > 1:
                    again = self._request("v2.5/article/discovery", {"demand_tag_id": tag, "model_id": model, "page": inner, "published_at": month, "size": PAGE_SIZE, "sort": sort})
                    first = again.get("data", []) if isinstance(again, dict) else []
                return first, back, inner
            acc += pages
        return [], -1, 1

    def _has_next(self, model, tag, month_back, inner_page, sort="published_at"):
        try:
            if inner_page > 1:
                month = self._month_str(month_back)
                result = self._request("v2.5/article/discovery", {"demand_tag_id": tag, "model_id": model, "page": inner_page + 1, "published_at": month, "size": PAGE_SIZE, "sort": sort})
                if result.get("data"):
                    return True
            for nb in (month_back + 1, month_back + 2):
                result = self._request("v2.5/article/discovery", {"demand_tag_id": tag, "model_id": model, "page": 1, "published_at": self._month_str(nb), "size": PAGE_SIZE, "sort": sort})
                if result.get("data"):
                    return True
            return False
        except Exception:
            return True

    def categoryContent(self, tid, pg, filter, extend):
        error = self._ensure_ready()
        if error:
            return error
        demand_tag_id = str(tid)
        page = max(1, int(pg))
        if demand_tag_id not in FILM_FILTERS:
            # 可点击标签（标签/演员/作者）跳转：按关键词搜索
            key = urllib.parse.unquote(demand_tag_id)
            if not key:
                return {"page": page, "pagecount": 1, "limit": PAGE_SIZE, "total": 0, "list": []}
            return self._search_page(key, page)
        sort = "published_at"
        if isinstance(extend, dict) and extend.get("order"):
            sort = str(extend["order"])
        try:
            if demand_tag_id in ("manga", "album"):
                ep = "v2.5/series/manga/list" if demand_tag_id == "manga" else "v2.5/series/album/list"
                result = self._request(ep, {"page": page, "size": PAGE_SIZE})
                items = result.get("data", []) if isinstance(result, dict) else []
                rows = [self._series_item(item, demand_tag_id) for item in items if item.get("id")]
                return {"page": page, "pagecount": page + 1 if len(rows) >= PAGE_SIZE else page, "limit": PAGE_SIZE, "total": len(rows), "list": rows}
            model, tag = (int(x) for x in demand_tag_id.split("_"))
            items, month_back, inner_page = self._monthly_discovery(model, tag, page, sort)
        except Exception:
            return {"page": page, "pagecount": page, "limit": PAGE_SIZE, "total": 0, "list": []}
        seen = set()
        rows = []
        for item in items:
            if not item.get("id") or item.get("id") in seen:
                continue
            seen.add(item.get("id"))
            rows.append(self._item(item))
        page_count = page
        if month_back >= 0:
            page_count = page + 1 if self._has_next(model, tag, month_back, inner_page, sort) else page
        return {"page": page, "pagecount": page_count, "limit": PAGE_SIZE, "total": len(rows), "list": rows}

    # ---------- 详情 / 搜索 / 播放 ----------
    def _search_page(self, keyword, page):
        try:
            result = self._request("v2.5/article/search", {"keyword": str(keyword), "page": page, "size": PAGE_SIZE})
            items = result.get("data", []) if isinstance(result, dict) else []
            # 搜索按标题去重：合集每集标题相同，只保留一个（否则搜索被合集的每一集刷屏）
            rows = self._dedup_rows(result, by_title=True)
            # 分页用原始条数判断（去重会减少条数，不能据此误判无下一页）
            has_next = len(items) >= PAGE_SIZE
            return {"list": rows, "page": page, "pagecount": page + 1 if has_next else page, "limit": PAGE_SIZE, "total": len(rows)}
        except Exception:
            return {"list": [], "page": page, "pagecount": 1, "limit": PAGE_SIZE, "total": 0}

    def _fill_video_detail(self, detail, item):
        # 演员（API 无导演字段，仅有 actor / author / tags）
        actor = str(item.get("actor") or "").strip()
        if actor:
            detail["vod_actor"] = self._srch(actor)

        tags = item.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        author = str(item.get("author") or "").strip()

        desc = str(item.get("description") or "").strip()
        if not desc:
            desc = re.sub(r"<[^>]+>", "", str(item.get("content") or "")).strip()

        # 可点击标签统一放最前面（空格连接），简介正文放最后（\n 分隔）—— 规范同 miss.py
        head = [self._srch(t) for t in tags[:8] if str(t) != actor]
        if author:
            head.append(self._srch(author))
        head_str = " ".join(head)
        if head_str:
            detail["vod_content"] = head_str + ("\n" + desc if desc else "")
        else:
            detail["vod_content"] = desc

    def detailContent(self, ids):
        error = self._ensure_ready()
        if error:
            return error
        try:
            raw = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
            kind = ""
            if raw.startswith(("m:", "a:")):
                kind = raw[:1]
                raw = raw[2:]
            item_id = int(raw)
            if kind:
                result = self._request("v2.5/series/chapters", {"series_id": item_id})
                d = result.get("data") or {}
                chapters = (d.get("chapters") or []) if isinstance(d, dict) else []
                play_url = "#".join("{}${}".format((c.get("title") or "第{}话".format(c.get("chapter", ""))).replace("#", " ").replace("$", " "), c.get("id")) for c in chapters if c.get("id"))
                author = str(d.get("author") or "").strip()
                detail = {"vod_id": raw, "vod_name": d.get("title", ""), "vod_pic": self._cover(d), "vod_area": "", "vod_class": "", "vod_director": "", "vod_actor": self._srch(author) if author else "", "vod_content": ("作者: " + self._srch(author)) if author else "", "vod_remarks": "共{}话".format(len(chapters)), "vod_play_from": "漫画" if kind == "m" else "写真", "vod_play_url": play_url}
                return {"list": [detail]}
            item = self._request("v2.5/article/detail", {"id": item_id}).get("data", {}) or {}
            media = _choose_media(item)
            detail = self._item(item)
            detail["vod_id"] = str(item_id)
            if media:
                # 合集（collection_list 多集）→ 剧集直接选集播放；单集 → 正片
                collection = item.get("collection_list") or []
                if not isinstance(collection, list):
                    collection = []
                if len(collection) > 1:
                    eps = []
                    for c in collection:
                        cid = c.get("id")
                        if not cid:
                            continue
                        num = c.get("episode") or c.get("number") or cid
                        eps.append("第%s集$%s" % (num, cid))
                    detail["vod_play_from"] = "One"
                    detail["vod_play_url"] = "#".join(eps)
                else:
                    detail["vod_play_from"] = "One"
                    detail["vod_play_url"] = "正片$" + str(item_id)
            elif self._is_playable(item):
                # 纯 GIF / 图文内容（无视频，封面即内容）
                detail["vod_play_from"] = "One"
                detail["vod_play_url"] = "正片$" + str(item_id)
            else:
                detail["vod_play_from"] = ""
                detail["vod_play_url"] = ""
            self._fill_video_detail(detail, item)
            return {"list": [detail]}
        except Exception as error:
            return _diagnostic("详情请求失败", type(error).__name__)

    def searchContent(self, key, quick, pg="1"):
        error = self._ensure_ready()
        if error:
            return error
        return self._search_page(str(key), max(1, int(pg)))

    def playerContent(self, flag, id, vipFlags):
        error = self._ensure_ready()
        if error:
            return error
        try:
            item_id = int(str(id).split("$")[-1])
            result = self._request("v2.5/article/detail", {"id": item_id})
            item = result.get("data", {})
            media = _choose_media(item)
            if media:
                # 有正式视频 → 优先播视频（直播类同时有 video_file 和 gif 图，须以视频为准）
                field, path = media
                url = self._one_url("one_video", path)
                return {"parse": 0, "playUrl": "", "url": self.plp + url, "header": {"User-Agent": "Dart/3.4 (dart:io)"}, "media_field": field}
            content = item.get("content") or item.get("description") or ""
            images = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content)
            if images:
                urls = []
                for src in images:
                    urls.append(src if src.startswith("http") else self._one_url("one_img", src))
                pics = "&&".join(self._proxy_url(u) for u in urls)
                return {"parse": 0, "playUrl": "", "url": "manga://" + pics, "header": ""}
            # 纯 GIF / 图文内容（无视频、无正文图，封面即内容）
            thumb = str(item.get("thumb") or "")
            if thumb and (thumb.lower().endswith(".gif") or item.get("model_id") == 1):
                url = thumb if thumb.startswith("http") else self._one_url("one_img", thumb)
                return {"parse": 0, "playUrl": "", "url": "manga://" + self._proxy_url(url), "header": ""}
            return {"parse": 0, "playUrl": "", "url": "", "header": {}, "error": "无已证实正片源（可能为付费/VIP 内容，需在 App 内购买或开通会员后观看）"}
        except Exception as error:
            return _diagnostic("播放请求失败", type(error).__name__)

    def localProxy(self, param):
        if not isinstance(param, dict):
            return [400, "text/plain", b"invalid proxy parameters"]
        url = param.get("url", "")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return [400, "text/plain", b"invalid proxy URL"]
        try:
            parsed = urllib.parse.urlparse(url)
            configured = urllib.parse.urlparse(self._hosts.get("one_img", ""))
            if not configured.hostname or parsed.hostname != configured.hostname or parsed.netloc.lower() != configured.netloc.lower():
                return [403, "text/plain", b"proxy host is not allowed"]
            if parsed.query or parsed.fragment or parsed.username or parsed.password:
                return [400, "text/plain", b"proxy query is not allowed"]
            response = self._session.get(url, headers={"User-Agent": "Dart/3.4 (dart:io)"}, timeout=REQUEST_TIMEOUT, proxies=self.proxy)
            response.raise_for_status()
            content = _decrypt_one_image(response.content)
            content_type = _image_kind(content)
            if not content_type:
                return [502, "text/plain", b"proxy image integrity check failed"]
            return [200, content_type, content]
        except Exception as error:
            return [502, "text/plain", ("proxy error: " + type(error).__name__).encode()]
