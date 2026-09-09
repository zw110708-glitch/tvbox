# -*- coding: utf-8 -*-
# //@name:JavDB
# //@id:javdb_official
# //@version:javdb_official_api

import base64
import hashlib
import json
import os
import re
import time
from urllib.parse import parse_qs, quote, unquote, urlsplit

import requests
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    name = "JavDB"

    API_BASE = "https://jdforrepam.com/api"
    WEB_BASE = "https://javdb.com"
    IMG_CDN = "https://c0.jdbstatic.com"

    SIGN_TOKEN = "lpw6vgqzsp"
    SIGN_SALT = "71cf27bb3c0bcdf207b64abecddc970098c7421ee7203b9cdae54478478a199e7d5a6e1a57691123c1a931c057842fb73ba3b3c83bcd69c17ccf174081e3d8aa"

    LOGIN_USER = "zw110708"
    LOGIN_PASS = "110708"

    UA_API = "Dart/3.5 (dart:io)"
    UA_WEB = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"

    PLAY_PREFIX = "javdb-play:"
    DEFAULT_PIC = IMG_CDN + "/favicon.ico"
    PAGE_SIZE = 24

    CATEGORIES = (
        ("latest", "最新"),
        ("playback", "热播"),
        ("top", "TOP250"),
        ("c0", "有码"),
        ("c1", "无码"),
        ("c2", "欧美"),
        ("c3", "FC2"),
        ("c4", "动漫"),
    )
    TYPE_MAP = {"c0": "0", "c1": "1", "c2": "2", "c3": "3", "c4": "4"}

    # 实体：path/key/letter/label（详情页可点击跳转）
    ENTITY = {
        "actor": ("/v1/actors/", "actor", "a", "演员"),
        "series": ("/v1/series/", "series", "s", "系列"),
        "maker": ("/v1/makers/", "maker", "m", "片商"),
        "director": ("/v1/directors/", "director", "d", "导演"),
        "publisher": ("/v1/publishers/", "publisher", "c", "发行"),
    }

    ROUTE_MAP = {
        "actors": ("entity", "actor"), "series": ("entity", "series"), "makers": ("entity", "maker"),
        "directors": ("entity", "director"), "publishers": ("entity", "publisher"),
        "lists": ("list", None), "tags": ("tag", None),
    }

    SORTS = (("发行 ↓", "release desc"), ("发行 ↑", "release asc"), ("更新 ↓", "update desc"), ("评分 ↓", "score desc"), ("热度 ↓", "hit desc"))
    MAINS = (("全部", ""), ("可播放", "p"), ("含磁链", "m"), ("中字", "c"))

    def __init__(self):
        super().__init__()
        self.timeout = 20
        self.token = ""
        self.proxy = {}
        self.token_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "javdb_token.json")
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self.UA_WEB, "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8"})
        self._session.proxies = self.proxy
        self._load_token()

    def getName(self):
        return self.name

    def init(self, extend=""):
        extend = self._dict(extend)
        self.timeout = max(5, min(45, int(extend.get("timeout", self.timeout))))
        self.plp = extend.get('plp', '')
        self.proxy = extend.get("proxy", {})
        self._session.proxies = self.proxy

    def destroy(self):
        try:
            self._session.close()
        except Exception:
            pass

    # ================= 首页 / 分类 / 搜索 =================
    def homeContent(self, filter=False):
        return {"class": [{"type_id": k, "type_name": n} for k, n in self.CATEGORIES], "filters": self._filters()}

    def homeVideoContent(self):
        try:
            return {"list": self._page_result(self._api("/v1/movies/recommend", {"page": 1, "limit": self.PAGE_SIZE}).get("movies"), 1)["list"]}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        route = self._route(tid)
        if route:
            return self._route_page(route, pg)
        tid = str(tid or "").strip()
        page = self._page(pg)
        ext = self._dict(extend)
        try:
            if tid == "playback":
                data = self._api("/v1/rankings/playback", {"filter_by": "all", "period": "daily"})
            elif tid == "top":
                data = self._api("/v1/movies/top", {"page": page, "limit": self.PAGE_SIZE}, auth=True)
            elif tid == "latest":
                data = self._api("/v1/movies/latest", {"page": page, "limit": self.PAGE_SIZE, "type": "all"})
            elif tid in self.TYPE_MAP:
                main = str(ext.get("main") or "")
                sort = str(ext.get("sort") or "release desc").split(" ")
                data = self._api("/v1/movies/tags", {"filter_by": self.TYPE_MAP[tid] + ":t:" + main + "::::", "sort_by": sort[0], "order_by": sort[1] if len(sort) > 1 else "desc", "page": page, "limit": self.PAGE_SIZE})
            else:
                return self._empty(page)
            return self._page_result(data.get("movies"), page)
        except Exception as e:
            return self._empty(page, self._clean(e))

    def searchContent(self, key, quick=False, pg="1"):
        route = self._route(key)
        if route:
            return self._route_page(route, pg)
        page = self._page(pg)
        q = self._clean(key)
        if not q:
            return self._empty(page)
        try:
            data = self._api("/v2/search", {"q": q, "page": page, "type": "movie", "movie_type": "all", "movie_sort_by": "relevance", "movie_filter_by": "all"})
            return self._page_result(data.get("movies"), page)
        except Exception as e:
            return self._empty(page, self._clean(e))

    # ================= 详情 =================
    def detailContent(self, ids):
        route = self._route(ids)
        if route:
            return self._route_page(route, 1)
        movie_id = self._movie_id(ids)
        if not re.match(r"^[A-Za-z0-9._:-]{1,120}$", movie_id):
            return {"list": []}
        try:
            movie = self._api("/v4/movies/" + quote(movie_id, safe="")).get("movie") or {}
            if not movie:
                raise RuntimeError("详情响应缺少 movie")
        except Exception as e:
            return {"list": [self._detail_error(movie_id, e)]}

        number = self._clean(movie.get("number") or movie.get("number_letter") or movie_id)
        title = self._clean(movie.get("title") or movie.get("origin_title") or number)
        pic = self._img_proxy(movie.get("cover_url") or movie.get("thumb_url") or self._first_preview(movie)) or self.DEFAULT_PIC

        # 播放线路：官方在线 + 磁力
        groups = []
        sources = [(sid, name) for sid, name in self._play_sources(movie)]
        if sources:
            groups.append(("官方在线", [(name, self._pack_play({"kind": "official", "code": movie_id, "source_id": sid})) for sid, name in sources]))
        magnets = []
        if float(movie.get("magnets_count") or 0) > 0:
            try:
                magnets = self._sort_magnets((self._api("/v1/movies/" + quote(movie_id, safe="") + "/magnets").get("magnets") or [])[:50])
            except Exception:
                magnets = []
        if magnets:
            groups.append(("磁力完整版", [(self._magnet_label(m), self._pack_play({"kind": "magnet", "magnet": m["magnet"]})) for m in magnets]))

        play_from, play_url = [], []
        for line_name, items in groups:
            rows = [(self._clean(a).replace("#", " ").replace("$", " ")[:120] or "播放", b) for a, b in items if b]
            if rows:
                play_from.append(line_name)
                play_url.append("#".join(f"{a}${b}" for a, b in rows))

        # 关联信息（可点击）
        tags = self._linked_tags(movie.get("tags") or [])
        lists = self._linked_lists(movie_id)
        director = self._linked_field(movie, "director", "/directors/")
        actors = [self._linked_item(x, "/actors/") for x in (movie.get("actors") or []) if x]
        content = []
        if tags:
            content.append("类别: " + " ".join(tags))
        if lists:
            content.append("相关清单: " + " ".join(lists))
        for label, field, prefix in (("片商", "maker", "/makers/"), ("发行", "publisher", "/publishers/"), ("系列", "series", "/series/"), ("导演", "director", "/directors/")):
            v = self._linked_field(movie, field, prefix)
            if v:
                content.append(label + ": " + v)
        if movie.get("origin_title") and self._clean(movie["origin_title"]) != title:
            content.append("原名: " + self._clean(movie["origin_title"]))
        if movie.get("summary"):
            content.append("视频介绍: " + self._clean(movie["summary"]))

        remarks = []
        if movie.get("can_play"):
            remarks.append("可播")
        if magnets:
            remarks.append("磁力" + str(len(magnets)))
        if movie.get("has_cnsub") or float(movie.get("play_subtitle") or 0) > 0:
            remarks.append("中字")
        score = movie.get("score") or movie.get("rate") or ""

        return {"list": [{
            "vod_id": movie_id,
            "vod_name": f"{number} {title}".strip(),
            "vod_pic": pic,
            "vod_remarks": " · ".join(remarks) or number,
            "vod_content": "\n".join(content),
            "vod_actor": " ".join([x for x in actors if x]),
            "vod_class": " ".join([x for x in tags if x]),
            "vod_director": director,
            "vod_year": self._date(movie.get("release_date")),
            "vod_area": {"0": "日本", "1": "日本", "2": "欧美", "3": "FC2", "4": "动漫"}.get(str(movie.get("type") or ""), ""),
            "vod_duration": self._duration(movie.get("duration")),
            "vod_score": float(score) if score else 0,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }]}

    # ================= 播放 =================
    def playerContent(self, flag, id, vipFlags=None):
        payload = self._unpack_play(id)
        kind = payload.get("kind")
        try:
            if kind == "official":
                data = self._api("/v1/movies/" + quote(payload.get("code") or "", safe="") + "/play", {"source_id": str(payload.get("source_id") or ""), "from_rankings": "false", "operation": "play"}, auth=True)
                u = self._pick_url(data)
                if not u:
                    return self._player_error("未解析到官方播放地址（可能需要登录）")
                return {"parse": 0, "jx": 0, "playUrl": "", "url": f'{self.plp}{u}', "header": {"User-Agent": self.UA_API, "Accept": "application/vnd.apple.mpegurl,*/*;q=0.8", "Referer": self.API_BASE.rstrip("/") + "/"}}
            if kind == "magnet":
                return {"parse": 0, "jx": 0, "playUrl": "", "url": "push://" + self._normalize_magnet(payload.get("magnet")), "header": {}}
        except Exception as e:
            return self._player_error(e)
        return self._player_error("无法识别播放 ID")

    # ================= 网络 =================
    def _signature(self):
        ts = str(int(time.time()))
        return ts + "." + self.SIGN_TOKEN + "." + hashlib.md5((ts + self.SIGN_SALT).encode()).hexdigest()

    def _api(self, path, query=None, auth=False):
        query = query or {}
        url = self.API_BASE.rstrip("/") + "/" + path.lstrip("/")
        if query:
            url += "?" + "&".join(f"{quote(str(k), safe='')}={quote(str(v), safe='')}" for k, v in sorted(query.items()) if v not in (None, ""))
        headers = {"Accept": "application/json", "jdsignature": self._signature(), "User-Agent": self.UA_API, "Accept-Language": "zh-TW"}
        if auth:
            headers["authorization"] = "Bearer " + self._ensure_token()
        body = self._get_json(url, headers)
        if body.get("success") != 1:
            msg = body.get("message") or "API 返回失败"
            # 鉴权失效：清 token 强制重登，重试一次
            if auth and re.search(r"登錄|登录|登入|login|auth|token|jwt|401|403|unauthor", msg, re.I):
                self.token = ""
                headers["authorization"] = "Bearer " + self._login(force=True)
                body = self._get_json(url, headers)
                if body.get("success") == 1:
                    return body.get("data") or {}
            raise RuntimeError(msg)
        return body.get("data") or {}

    def _get_json(self, url, headers=None):
        resp = self._session.get(url, headers=headers or {}, timeout=(10, self.timeout), verify=True, allow_redirects=True)
        try:
            resp.raise_for_status()
            return resp.json()
        finally:
            resp.close()

    # ================= 登录 =================
    def _login(self, force=False):
        if self.token and not force:
            return self.token
        q = {"username": self.LOGIN_USER, "password": self.LOGIN_PASS, "device_uuid": self._uuid(), "device_name": "HikerView", "device_model": "Android", "platform": "android", "system_version": "Android", "app_channel": "official", "app_version": "official", "app_version_number": "1.9.35"}
        url = self.API_BASE.rstrip("/") + "/v1/sessions?" + "&".join(f"{quote(str(k), safe='')}={quote(str(v), safe='')}" for k, v in sorted(q.items()))
        resp = self._session.post(url, headers={"Accept": "application/json", "jdsignature": self._signature(), "User-Agent": self.UA_API}, data="", timeout=(10, self.timeout))
        try:
            token = (resp.json().get("data") or {}).get("token") or ""
        finally:
            resp.close()
        if not token:
            raise RuntimeError("登录未返回 token")
        self.token = token
        self._save_token()
        return token

    def _ensure_token(self):
        return self.token or self._login()

    def _uuid(self):
        try:
            with open(self.token_file, encoding="utf-8") as f:
                uuid = json.load(f).get("uuid")
                if uuid:
                    return uuid
        except Exception:
            pass
        return "py-" + hashlib.md5(("javdb" + str(int(time.time() * 1000))).encode()).hexdigest()[:24]

    def _load_token(self):
        try:
            with open(self.token_file, encoding="utf-8") as f:
                self.token = json.load(f).get("token") or ""
        except Exception:
            self.token = ""

    def _save_token(self):
        try:
            with open(self.token_file, "w", encoding="utf-8") as f:
                json.dump({"token": self.token, "uuid": self._uuid()}, f)
        except Exception:
            pass

    @staticmethod
    def _pick_url(v):
        if isinstance(v, str):
            s = v.strip()
            return s if re.match(r"^https?://", s, re.I) else ""
        if isinstance(v, (list, tuple)):
            for x in v:
                u = Spider._pick_url(x)
                if u:
                    return u
        elif isinstance(v, dict):
            for x in v.values():
                u = Spider._pick_url(x)
                if u:
                    return u
        return ""

    # ================= 图片 =================
    def _img_proxy(self, url):
        u = str(url or "").replace("&amp;", "&").strip()
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = self.WEB_BASE + u
        u = u.replace("/small_covers/", "/covers/")
        u = re.sub(r"^https?://[^/]+/rhe951l4q", self.IMG_CDN, u, flags=re.I)
        return u if re.match(r"^https?://", u, re.I) else ""

    # ================= 播放辅助 =================
    def _play_sources(self, movie):
        out = []
        for s in (movie.get("play_sources") or []):
            if isinstance(s, dict):
                sid = str(s.get("id") if s.get("id") is not None else s.get("source_id") or "")
                if sid:
                    out.append((sid, self._clean(s.get("name") or s.get("title") or s.get("label")) or "源" + sid))
            elif s is not None:
                out.append((str(s), "源" + str(s)))
        return out

    # ================= 筛选 / 路由 =================
    def _filters(self):
        sort_rows = [{"key": "sort", "name": "排序", "value": [{"n": n, "v": v} for n, v in self.SORTS]}]
        main_rows = [{"key": "main", "name": "资源", "value": [{"n": n, "v": v} for n, v in self.MAINS]}]
        return {tid: (sort_rows + main_rows if tid in self.TYPE_MAP else []) for tid, _ in self.CATEGORIES}

    def _route(self, value):
        text = self._unwrap(value)
        if not text.startswith("/"):
            return ""
        p = urlsplit(text)
        if p.path.startswith("/movie/") or p.path.startswith("/categories"):
            return p.path + (("?" + p.query) if p.query else "")
        for kind in self.ROUTE_MAP:
            if p.path.startswith("/" + kind + "/"):
                q = p.query if "page=" in p.query else ((p.query + "&") if p.query else "") + "page=1"
                return p.path + ("?" + q if q else "")
        return ""

    def _route_page(self, route, pg):
        page = self._page(pg)
        try:
            p = urlsplit(route)
            q = parse_qs(p.query)
            if str(pg).strip().lower() in ("", "none", "null"):
                page = self._page(q.get("page", [page])[0])
            parts = [x for x in p.path.split("/") if x]
            if not parts:
                return self._empty(page)
            sort = str(q.get("sort", ["release desc"])[0] or "release desc").split(" ")
            sort_by, order_by = sort[0], (sort[1] if len(sort) > 1 else "desc")
            if parts[0] == "categories":
                data = self._api("/v2/search", {"q": self._clean(q.get("q", [""])[0]), "page": page, "type": "movie", "movie_type": "all", "movie_sort_by": "relevance", "movie_filter_by": "all"})
                return self._page_result(data.get("movies"), page)
            spec = self.ROUTE_MAP.get(parts[0])
            entity_id = parts[1] if len(parts) > 1 else ""
            if not spec or not entity_id:
                return self._empty(page)
            mode, sub = spec
            if mode == "list":
                fb = "0:l:" + entity_id + ":"
            elif mode == "tag":
                fb = "0:t:::::"
                data = self._api("/v1/movies/tags", {"filter_by": fb, "filter_by_tags": entity_id, "sort_by": sort_by, "order_by": order_by, "page": page, "limit": self.PAGE_SIZE})
                return self._page_result(data.get("movies"), page)
            else:
                path, key, letter, _ = self.ENTITY.get(sub, ("", "", "", ""))
                meta = self._api(path + quote(entity_id, safe="")).get(key) or {}
                fb = (str(meta.get("type") or "0") or "0") + ":" + letter + ":" + entity_id + ":"
            data = self._api("/v1/movies/tags", {"filter_by": fb, "sort_by": sort_by, "order_by": order_by, "page": page, "limit": self.PAGE_SIZE})
            return self._page_result(data.get("movies"), page)
        except Exception as e:
            return self._empty(page, self._clean(e))

    def _page_result(self, movies, page):
        rows, seen = [], set()
        for m in (movies or []):
            if not isinstance(m, dict):
                continue
            mid = self._clean(m.get("id"))
            if not mid or mid in seen:
                continue
            seen.add(mid)
            number = self._clean(m.get("number") or m.get("number_letter") or mid)
            title = self._clean(m.get("title") or m.get("origin_title") or number)
            rd = m.get("release_date") or ""
            date_str = rd[:10] if len(rd) >= 10 else ""
            marks = []
            if m.get("can_play"):
                marks.append("可播")
            if int(float(m.get("magnets_count") or 0)):
                marks.append("磁力" + str(int(float(m.get("magnets_count") or 0))))
            if m.get("has_cnsub") or float(m.get("play_subtitle") or 0) > 0:
                marks.append("中字")
            rows.append({
                "vod_id": mid,
                "vod_name": f"{number} {title}".strip(),
                "vod_pic": self.plp + (self._img_proxy(m.get("cover_url") or m.get("thumb_url") or self._first_preview(m)) or self.DEFAULT_PIC),
                "vod_remarks": " · ".join(marks),
                "vod_year": date_str,
            })
        more = 1 if len(movies or []) >= self.PAGE_SIZE else 0
        return {"list": rows, "page": page, "pagecount": page + more, "limit": self.PAGE_SIZE, "total": (page + more) * self.PAGE_SIZE}

    def _sort_magnets(self, items):
        rows, seen = [], set()
        for item in items or []:
            if not isinstance(item, dict):
                continue
            magnet = self._normalize_magnet(item.get("hash") or item.get("magnet"))
            btih = self._extract_btih(magnet)
            if not btih or btih in seen:
                continue
            seen.add(btih)
            name = self._clean(item.get("name"))
            rows.append({
                "magnet": magnet, "name": name,
                "sub": bool(item.get("cnsub")) or bool(re.search(r"中文字幕|简体中文|繁体中文|中字|字幕|CHS|CHT|SUB", name, re.I)),
                "hd": bool(item.get("hd")) or bool(re.search(r"(?:^|[^A-Z0-9])(HD|FHD|UHD|4K|2160P|1080P|720P)(?:[^A-Z0-9]|$)", name, re.I)),
                "size": float(item.get("size") or 0),
                "files": int(float(item.get("files_count") or 0)),
                "date": int(re.sub(r"\D", "", str(item.get("created_at") or ""))[:14].ljust(14, "0") or 0),
            })
        rows.sort(key=lambda x: (0 if x["sub"] else 1, 0 if x["hd"] else 1, -x["size"], -x["date"], -x["files"]))
        return rows

    def _magnet_label(self, item):
        marks = []
        if item.get("sub"):
            marks.append("中字")
        if item.get("hd"):
            marks.append("HD")
        size = item.get("size") or 0
        size_text = f"{size / 1024:.2f}GB" if size >= 1024 else (f"{int(size)}MB" if size > 0 else "")
        meta = [x for x in [size_text, f"{int(item.get('files') or 0)}文件" if item.get("files") else ""] if x]
        prefix = " ".join(f"[{x}]" for x in marks)
        return " | ".join([x for x in [prefix, " · ".join(meta), self._clean(item.get("name") or "磁力资源")] if x])

    # ================= 关联字段（可点击） =================
    def _linked_lists(self, movie_id):
        try:
            rows = self._api("/v1/lists/related", {"movie_id": movie_id, "limit": 50}).get("lists") or []
        except Exception:
            rows = []
        out, seen = [], set()
        for item in rows:
            if not isinstance(item, dict):
                continue
            name = self._clean(item.get("name") or item.get("title"))
            iid = str(item.get("id") or "")
            if name and iid and (name, iid) not in seen:
                seen.add((name, iid))
                out.append(self._click(name, f"/lists/{quote(iid, safe='')}?page=1"))
        return out

    def _click(self, name, href):
        name = self._clean(name)
        href = str(href or "").strip().replace("&amp;", "&")
        return "[a=cr:%s/]%s[/a]" % (json.dumps({"id": href, "name": name}, ensure_ascii=False), name) if name and href.startswith("/") else name

    def _linked_item(self, item, prefix):
        if not isinstance(item, dict):
            return self._clean(item)
        iid = self._clean(item.get("id"))
        name = self._clean(item.get("name") or item.get("title") or item.get("number"))
        return self._click(name, f"{prefix}{quote(iid, safe='')}?page=1") if iid else name

    def _linked_field(self, movie, field, prefix):
        iid = self._clean(movie.get(field + "_id"))
        name = self._clean(movie.get(field + "_name"))
        return self._click(name, f"{prefix}{quote(iid, safe='')}?page=1") if iid else name

    def _linked_tags(self, tags):
        out = []
        for item in tags or []:
            if isinstance(item, dict):
                name = self._clean(item.get("name"))
                iid = self._clean(item.get("id"))
                if name and iid:
                    out.append(self._click(name, f"/tags/{quote(iid, safe='')}?page=1"))
        return out

    # ================= 工具 =================
    def _movie_id(self, value):
        text = self._unwrap(value)
        m = re.search(r"/movie/([A-Za-z0-9._:-]{1,120})", text)
        return m.group(1) if m else self._clean(text)

    def _unwrap(self, value):
        raw = value[0] if isinstance(value, (list, tuple)) and value else value
        if isinstance(raw, dict):
            raw = raw.get("id") or raw.get("url") or raw.get("name") or ""
        text = str(raw or "").strip().replace("&amp;", "&")
        if text.startswith("[a=cr:"):
            text = text[6:].split('/]', 1)[0]
        for _ in range(2):
            if text.startswith("{"):
                d = self._dict(text)
                nxt = str(d.get("id") or d.get("url") or d.get("name") or "").strip()
                if nxt and nxt != text:
                    text = nxt
                    continue
            break
        text = unquote(text).strip().replace("&amp;", "&")
        if text.startswith(("http://", "https://")):
            p = urlsplit(text)
            text = p.path + (("?" + p.query) if p.query else "")
        return text

    def _pack_play(self, payload):
        return self.PLAY_PREFIX + base64.urlsafe_b64encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()).decode().rstrip("=")

    def _unpack_play(self, value):
        text = str(value or "").strip()
        if not text.startswith(self.PLAY_PREFIX):
            return {}
        try:
            data = json.loads(base64.urlsafe_b64decode(text[len(self.PLAY_PREFIX):] + "=" * (-len(text[len(self.PLAY_PREFIX):]) % 4)).decode())
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _extract_btih(value):
        text = str(value or "")
        m = re.search(r"btih:([A-F0-9]{40}|[A-Z2-7]{32})", text, re.I)
        return m.group(1).upper() if m else (text.strip().upper() if re.match(r"^(?:[A-F0-9]{40}|[A-Z2-7]{32})$", text.strip(), re.I) else "")

    def _normalize_magnet(self, value):
        btih = self._extract_btih(value)
        return f"magnet:?xt=urn:btih:{btih}" if btih else ""

    @staticmethod
    def _dict(value):
        if isinstance(value, dict):
            return value
        if not value:
            return {}
        try:
            data = json.loads(str(value))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _clean(value):
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def _page(value):
        try:
            return max(1, int(value))
        except Exception:
            return 1

    @staticmethod
    def _date(value):
        m = re.search(r"\d{4}-\d{2}-\d{2}", str(value or ""))
        return m.group(0) if m else str(value or "")[:10]

    @staticmethod
    def _duration(value):
        try:
            n = float(value or 0)
            return f"{int(round(n))}分钟" if n > 0 else ""
        except Exception:
            return ""

    @staticmethod
    def _first_preview(movie):
        for item in movie.get("preview_images") or []:
            val = (item or {}).get("large_url") or (item or {}).get("thumb_url") or (item or {}).get("url") if isinstance(item, dict) else item
            if str(val or "").strip():
                return str(val).strip()
        return ""

    def _empty(self, page, msg=""):
        data = {"list": [], "page": page, "pagecount": page, "limit": self.PAGE_SIZE, "total": 0}
        if msg:
            data["msg"] = self._clean(msg)
        return data

    def _detail_error(self, movie_id, msg):
        eid = self._pack_play({"kind": "error", "message": self._clean(msg) or "详情读取失败"})
        return {"vod_id": movie_id or "error", "vod_name": "详情读取失败", "vod_pic": self.DEFAULT_PIC, "vod_content": self._clean(msg), "vod_play_from": "错误", "vod_play_url": "查看错误$" + eid}

    def _player_error(self, msg):
        text = self._clean(msg) or "播放失败"
        return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}, "msg": text, "content": text, "error": text}
