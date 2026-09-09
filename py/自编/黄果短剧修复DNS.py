# -*- coding: utf-8 -*-
# 黄果短剧 —— 极简重构版
# 数据源：页面 JSON-LD ItemList（精准主列表），搜索/兜底用 data-track 卡片
# 封面：AES-CBC 加密图，走本地代理解密
# 播放：GET /api/videos/{id}/play?ep=N -> data.video_url（m3u8），加 plp 前缀直接返回
import json, re
import requests
from urllib.parse import quote, unquote
from base.spider import Spider

try:
    from Crypto.Cipher import AES
except Exception:
    AES = None

# 封面 AES 密钥/向量（站点 crypto-worker.js 固定值，16 字节）
_KEY = b"f5d965df75336270"
_IV = b"97b60394abc2fbe1"


class Spider(Spider):
    def init(self, extend="{}"):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        self.host = "https://huangguoai.com"
        self.plp = config.get("plp", "")
        self.proxy = config.get("proxy", {})
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.cats = [
            ("recommend", "热门推荐"),
            ("newest", "最近上新"),
            ("ai-duanju", "AI成人短剧"),
            ("ai-manju", "AI成人漫剧"),
            ("ai-huanlian", "AI换脸"),
            ("ai-mogai", "AI魔改"),
        ]
        self._pic_cache = {}

    def getName(self):
        return "黄果短剧"

    # ---------- 请求 ----------
    def _get(self, url):
        r = requests.get(url, headers=self.headers, proxies=self.proxy, timeout=15, verify=False)
        return r.text

    def _get_json(self, url):
        try:
            r = requests.get(url, headers=self.headers, proxies=self.proxy, timeout=15, verify=False)
            return r.json()
        except Exception:
            return {}

    # ---------- 封面：加密图走本地代理解密 ----------
    def _pic(self, url):
        if not url:
            return ""
        try:
            b = self.getProxyUrl()
            if "?" not in b:
                b += "?do=py"
            return b + "&url=" + quote(url)
        except Exception:
            return ""

    # ---------- 封面签名 URL（批量） ----------
    def _covers(self, ids):
        out = {}
        if not ids:
            return out
        try:
            r = requests.post(self.host + "/api/media/covers",
                              json={"items": [{"type": "video", "id": int(i)} for i in ids]},
                              headers=self.headers, proxies=self.proxy, timeout=15, verify=False)
            covers = (r.json().get("data") or {}).get("covers") or {}
            for k, v in covers.items():
                m = re.match(r"video:(\d+)", k)
                if m and v:
                    out[m.group(1)] = v
        except Exception:
            pass
        return out

    # ---------- 列表解析（JSON-LD 优先，data-track 兜底） ----------
    def _parse_list(self, html):
        # id -> 备注（更新至x集 / 全x集）
        rem_map = {}
        for m in re.finditer(r'data-track-id="(\d+)"', html):
            chunk = html[m.start():m.start() + 1600]
            em = re.search(r'data-ep-base="([^"]*)"', chunk)
            if em:
                rem_map[m.group(1)] = em.group(1).strip()
            else:
                em2 = re.search(r'hg-drama-card__episode">([^<]*)<', chunk)
                if em2:
                    rem_map[m.group(1)] = em2.group(1).strip()
        items = []
        fallback_pic = {}
        for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
            try:
                j = json.loads(m.group(1).strip())
                for node in j.get("@graph", []):
                    if node.get("@type") == "ItemList":
                        for it in node.get("itemListElement", []):
                            u = it.get("url") or ""
                            mid = re.search(r'/detail/(\d+)/', u)
                            nm = (it.get("name") or "").strip()
                            if mid and nm:
                                items.append((mid.group(1), nm))
            except Exception:
                continue
        if not items:
            for m in re.finditer(r'data-track-id="(\d+)"[^>]*data-track-title="([^"]*)"', html):
                vid, nm = m.group(1), m.group(2).strip()
                chunk = html[m.start():m.start() + 1600]
                pm = re.search(r'data-src="(https?://[^"]+)"', chunk)
                if pm:
                    fallback_pic[vid] = pm.group(1)
                items.append((vid, nm))
        if not items:
            return []
        covers = self._covers([vid for vid, _ in items]) if not fallback_pic else {}
        videos, seen = [], set()
        for vid, name in items:
            if not name or vid in seen:
                continue
            seen.add(vid)
            pic = covers.get(vid) or fallback_pic.get(vid, "")
            videos.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": self._pic(pic) if pic else "",
                "vod_remarks": rem_map.get(vid, ""),
            })
        return videos

    def homeContent(self, filter):
        result = {"class": [{"type_id": c, "type_name": n} for c, n in self.cats], "list": []}
        try:
            result["list"] = self._parse_list(self._get(self.host + "/"))
        except Exception:
            pass
        return result

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        result = {"list": [], "page": page, "pagecount": 9999, "limit": 20, "total": 999999}
        try:
            if page <= 1:
                url = "%s/%s/" % (self.host, tid)
            else:
                url = "%s/%s/%d/" % (self.host, tid, page)
            result["list"] = self._parse_list(self._get(url))
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        result = {"list": []}
        vid = ids[0] if isinstance(ids, list) else ids
        vid = re.sub(r"\D", "", str(vid))
        if not vid:
            return result
        html = self._get("%s/detail/%s/" % (self.host, vid))
        if not html:
            return result
        vod = {"vod_id": vid}
        h1 = re.search(r"<h1[^>]*>([^<]+)</h1>", html)
        vod["vod_name"] = h1.group(1).strip() if h1 else vid
        pic = re.search(r'data-src="(https?://[^"]+)"', html)
        vod["vod_pic"] = self._pic(pic.group(1)) if pic else ""
        eps = re.findall(r'<a[^>]*href="(/video/\d+(?:/ep-\d+)?/)"[^>]*data-ep-id="(\d+)"', html)
        if not eps:
            eps = [("/video/%s/" % vid, "1")]
        plays = []
        for href, eid in eps:
            plays.append("第%02d集$%s/api/videos/%s/play?ep=%s" % (int(eid), self.host, vid, eid))
        vod["vod_play_from"] = "黄果短剧"
        vod["vod_play_url"] = "#".join(plays)
        result["list"] = [vod]
        return result

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        result = {"list": [], "page": page}
        try:
            url = "%s/search/video/%s/" % (self.host, quote(key))
            if page > 1:
                url = "%s/search/video/%s/%d/" % (self.host, quote(key), page)
            result["list"] = self._parse_list(self._get(url))
        except Exception:
            pass
        return result

    def playerContent(self, flag, id, vipFlags):
        url = id if isinstance(id, str) else str(id)
        if re.search(r"\.(m3u8|mp4)(\?|$)", url, re.I):
            return {"parse": 0, "url": self.plp + url, "header": self.headers}
        data = self._get_json(url)
        vurl = (data.get("data") or {}).get("video_url") or ""
        if not vurl:
            return {"parse": 1, "url": url, "header": self.headers}
        vurl = vurl.replace("\\u0026", "&")
        return {"parse": 0, "url": self.plp + vurl, "header": self.headers}

    def localProxy(self, param):
        if not param:
            return [404, "text/plain", b""]
        url = param.get("url") or ""
        if not url:
            return [404, "text/plain", b""]
        try:
            url = unquote(url)
        except Exception:
            pass
        if url in self._pic_cache:
            return self._pic_cache[url]
        try:
            r = requests.get(url, headers=self.headers, proxies=self.proxy, timeout=15, verify=False)
            ct = r.content
        except Exception:
            return [404, "text/plain", b""]
        mime = self._sniff(ct)
        if not mime and AES and len(ct) % 16 == 0:
            try:
                dec = AES.new(_KEY, AES.MODE_CBC, _IV).decrypt(ct)
                pad = dec[-1]
                if 1 <= pad <= 16:
                    dec = dec[:-pad]
                mime = self._sniff(dec)
                if mime:
                    ct = dec
            except Exception:
                pass
        out = [200, mime or "image/jpeg", ct]
        if len(self._pic_cache) > 300:
            self._pic_cache.clear()
        self._pic_cache[url] = out
        return out

    def _sniff(self, b):
        if b[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if b[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
            return "image/webp"
        if b[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        return ""
