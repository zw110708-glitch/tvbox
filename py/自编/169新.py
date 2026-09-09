# -*- coding: utf-8 -*-
import re
import os
import json
import base64
import threading
import hashlib
import time
from datetime import datetime
from urllib.parse import (
    urljoin, unquote, quote, urlparse, parse_qsl, urlencode, urlunparse
)
from requests import Session
from pyquery import PyQuery as pq
from base.spider import Spider as BaseSpider

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass


class Spider(BaseSpider):
    host = "https://169bbs.com"
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    def init(self, extend=""):
        self.headers = dict(self.default_headers)
        self.site_cookie = ""
        self.pan_115_cookie = ""
        # 115离线/API缓存配置
        self.cache_115_file = "/storage/emulated/0/Download/115api_cache/115_cache.json"
        self.offline_115_timeout = 180
        self.offline_115_poll_interval = 5
        self.min_115_video_size = 100 * 1024 * 1024
        self.pan_115_save_cid = ""
        self.enable_magnet_push = True
        self.confirm_115 = False
        self.confirm_cache = set()
        self.last_vod_pic = ""
        self.play_pic_map = {}
        self.ack_mp4 = (
            "https://vd2.bdstatic.com/mda-nj5kxa8kr7wgq6ie/sc/"
            "cae_h264_nowatermark/1653272065989267185/mda-nj5kxa8kr7wgq6ie.mp4"
        )

        # OpenList 配置（对齐4k2）
        self.openlist_url = ""
        self.openlist_token = ""
        self.openlist_parent = "/云下载"
        self.openlist_latest_depth = 3
        self.openlist_force_dav = False
        self.openlist_test_stream = False
        self.openlist_enable_refresh = False
        self.test_m3u8 = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"
        self.openlist_scan_max_nodes = 120
        self.openlist_scan_sleep_ms = 120
        self.openlist_search_cache_ttl = 0
        self._openlist_search_cache = {}
        # OpenList 点击“刷新缓存”后临时保存的最新视频文件，仅内存，不落盘
        self._openlist_recent_files = []
        # 点击刷新缓存时，只处理父目录下最新3个条目
        self.openlist_refresh_latest_n = 3
        self._openlist_last_scan_ts = 0.0

        # OpenList 本地索引
        self.openlist_index_file = ""
        self.openlist_index_max_age_days = 30
        self.openlist_index_refresh_n = 20

        # 启动时索引文件年龄状态（48小时阈值）
        self.index_age_threshold_seconds = 48 * 3600
        self._index_stale_48h = True

        if extend:
            try:
                ext = json.loads(extend)
                if isinstance(ext, dict):
                    if ext.get("host"):
                        self.host = str(ext.get("host")).rstrip("/")
                    self.site_cookie = str(ext.get("cookie", "")).strip()
                    if self.site_cookie:
                        self.headers["Cookie"] = self.site_cookie
                    self.pan_115_cookie = str(ext.get("pan_115_cookie", "")).strip()
                    if str(ext.get("enable_magnet_push", "1")) in ["0", "false", "False", "no", "No"]:
                        self.enable_magnet_push = False
                    if str(ext.get("confirm_115", "0")) in ["1", "true", "True", "yes", "Yes"]:
                        self.confirm_115 = True
                    self.openlist_url = self.normalizeOpenlistBaseUrl(str(ext.get("openlist_url", "")).strip())
                    self.openlist_token = str(ext.get("openlist_token", "")).strip()
                    if ext.get("openlist_parent"):
                        p = str(ext.get("openlist_parent")).strip()
                        self.openlist_parent = "/" + p.lstrip("/") if p else "/"
                    try:
                        self.openlist_latest_depth = max(1, int(ext.get("openlist_latest_depth", 3)))
                    except Exception:
                        pass
                    if str(ext.get("openlist_force_dav", "0")) in ["1", "true", "True"]:
                        self.openlist_force_dav = True
                    if str(ext.get("openlist_test_stream", "0")) in ["1", "true", "True"]:
                        self.openlist_test_stream = True
                    if str(ext.get("openlist_enable_refresh", "0")) in ["1", "true", "True"]:
                        self.openlist_enable_refresh = True
                    if ext.get("test_m3u8"):
                        self.test_m3u8 = str(ext.get("test_m3u8")).strip()
                    try:
                        self.openlist_scan_max_nodes = max(20, int(ext.get("openlist_scan_max_nodes", 120)))
                    except Exception:
                        pass
                    try:
                        self.openlist_scan_sleep_ms = max(0, int(ext.get("openlist_scan_sleep_ms", 120)))
                    except Exception:
                        pass
                    try:
                        self.openlist_search_cache_ttl = max(0, int(ext.get("openlist_search_cache_ttl", 0)))
                    except Exception:
                        pass
                    if ext.get("openlist_index_file"):
                        self.openlist_index_file = str(ext.get("openlist_index_file")).strip()
                    try:
                        self.openlist_index_max_age_days = max(1, int(ext.get("openlist_index_max_age_days", 30)))
                    except Exception:
                        pass
                    try:
                        self.openlist_index_refresh_n = max(1, int(ext.get("openlist_index_refresh_n", 20)))
                    except Exception:
                        pass
            except Exception as e:
                print(f"[INIT] extend parse error: {e}")

        self.headers["Referer"] = f"{self.host}/"
        self.session = Session()
        self.session.headers.update(self.headers)
        self.session.verify = False

        # OpenList/AList 使用独立 Session，避免携带 169bbs Cookie / Referer 请求 OpenList
        self.openlist_session = Session()
        self.openlist_session.verify = False
        self.openlist_session.headers.clear()
        self._index_lock = threading.Lock()

        if not self.openlist_index_file:
            # 默认写到 /tmp，避免插件目录只读导致索引无法生成
            self.openlist_index_file = "/tmp/openlist_shared_index.json"

        # 启动时自动对比索引目录文件最后修改时间与当前时间（48小时）
        self._check_index_file_age_on_startup()
        print(f">>> 169BBS Spider loaded, host={self.host}, has_cookie={bool(self.site_cookie)}")

    def getName(self):
        return "169BBS-OpenList对齐版"

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass
        try:
            if hasattr(self, "openlist_session"):
                self.openlist_session.close()
        except Exception:
            pass
    def _check_index_file_age_on_startup(self):
        try:
            p = self.openlist_index_file
            if not p or (not os.path.exists(p)):
                self._index_stale_48h = True
                print("[index] 启动检查：索引文件不存在，视为超过48小时（stale=True）")
                return
            mtime = os.path.getmtime(p)
            delta = time.time() - float(mtime)
            self._index_stale_48h = (delta > self.index_age_threshold_seconds)
            print(f"[index] 启动检查：mtime差值={int(delta)}秒, stale48h={self._index_stale_48h}")
        except Exception as e:
            self._index_stale_48h = True
            print(f"[index] 启动检查失败，按stale处理: {e}")

    # ===================== 工具函数 =====================
    def getHtml(self, url):
        try:
            rsp = self.session.get(url, timeout=30, allow_redirects=True)
            if rsp.encoding and rsp.encoding.lower() in ["iso-8859-1", "ascii"]:
                rsp.encoding = rsp.apparent_encoding or "utf-8"
            elif not rsp.encoding:
                rsp.encoding = rsp.apparent_encoding or "utf-8"
            text = rsp.text or ""
            print(f"[GET] {url} => {rsp.status_code}, final={rsp.url}, len={len(text)}")
            if any(k in text for k in [
                "请先登录", "您需要登录", "登录后", "會員登錄", "会员登录",
                "验证码", "安全验证", "访问受限", "抱歉", "您无权进行当前操作",
            ]):
                print("[WARN] 页面可能需要登录 Cookie、验证码，或当前账号权限不足")
            if rsp.status_code == 200:
                return text
        except Exception as e:
            print(f"[getHtml] {url} error: {e}")
        return ""

    def getpq(self, url):
        html = self.getHtml(url)
        try:
            return pq(html)
        except Exception as e:
            print(f"[getpq] parse error: {e}")
            return pq("")

    def fixUrl(self, url):
        if not url:
            return ""
        url = str(url).strip().replace("&amp;", "&")
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return urljoin(self.host + "/", url)

    def removeUrlParam(self, url, keys):
        if not url:
            return ""
        keys = set(keys)
        try:
            p = urlparse(url)
            query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k not in keys]
            return urlunparse((p.scheme, p.netloc, p.path, p.params, urlencode(query), p.fragment))
        except Exception:
            return url

    def setUrlParam(self, url, key, value):
        if not url:
            return ""
        try:
            p = urlparse(url)
            query = dict(parse_qsl(p.query, keep_blank_values=True))
            query[str(key)] = str(value)
            return urlunparse((p.scheme, p.netloc, p.path, p.params, urlencode(query), p.fragment))
        except Exception:
            joiner = "&" if "?" in url else "?"
            return f"{url}{joiner}{key}={value}"

    def cleanText(self, text):
        if not text:
            return ""
        text = str(text).replace("\xa0", " ").replace("&nbsp;", " ").replace("\u3000", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def cleanTitleForSearch(self, title):
        s = self.cleanText(title or "")
        s = re.sub(r"[\[\]【】()（）{}「」『』《》<>]", " ", s)
        bad_words = [
            "中文字幕", "中字", "无码", "有码", "破解", "流出",
            "高清", "4K", "UHD", "HD", "1080P", "720P",
            "最新", "原创", "合集", "磁力", "BT", "115"
        ]
        for w in bad_words:
            s = re.sub(re.escape(w), " ", s, flags=re.I)
        s = re.sub(r"\s+", " ", s)
        return self.cleanText(s)

    def getFirst(self, root, selectors):
        try:
            for sel in selectors:
                item = root(sel).eq(0)
                if len(item) > 0:
                    return item
        except Exception:
            pass
        return pq("")

    def isAdUrl(self, url):
        if not url:
            return True
        low = str(url).lower()
        bad = [
            "ads", "adservice", "analytics", "cnzz", "hm.baidu", "logo", "button",
            "loading", "avatar", "static/image/common", "common/logo", "none.gif", "blank.gif",
            "static/image/smiley", "static/image/editor", "static/image/filetype",
            "source/plugin", "template/bygsjw_3/image", "uc_server/avatar.php",
            "stamp/", "emotion", "face",
        ]
        return any(k in low for k in bad) or low.startswith("javascript:")

    def getImgSrc(self, img):
        try:
            if img is None or len(img) == 0:
                return ""

            # 列表页很多图片是懒加载：
            # src 可能只是 loading/blank/占位图，真实封面通常在 data-original/data-src/file/zoomfile。
            # 所以 src 必须放最后。
            src = (
                img.attr("data-original")
                or img.attr("data-src")
                or img.attr("data-lazy")
                or img.attr("lay-src")
                or img.attr("file")
                or img.attr("zoomfile")
                or img.attr("zsrc")
                or img.attr("src")
                or ""
            )

            src = self.fixUrl(src)
            return "" if self.isAdUrl(src) else src
        except Exception:
            return ""

    def getThreadListPic(self, row):
        """
        专门解析 Discuz 帖子列表页封面。

        169bbs 列表页结构一般是：
          <div class="picturebox" style="display:none">
            <img class="picture" file="https://www.imgccc.com/xxxx.jpg" src="" />
          </div>

        注意：
          1. 真实大图在 file 属性；
          2. src 可能为空；
          3. row 前面还有作者头像 avatar，不能误取；
          4. 还有附件/热度/thanks 图标，不能误取。
        """
        try:
            if row is None or len(row) == 0:
                return ""

            # 第一优先级：隐藏大图 file，最准确
            img = self.getFirst(row, [
                ".picturedisplay .picturebox .bigpicture img.picture[file]",
                ".picturedisplay .picturebox img.picture[file]",
                ".picturebox .bigpicture img.picture[file]",
                ".picturebox img.picture[file]",
                "img.picture[file]",
                "img[file]",
            ])
            if len(img) > 0:
                pic = (
                    img.attr("file")
                    or img.attr("zoomfile")
                    or img.attr("data-original")
                    or img.attr("data-src")
                    or img.attr("src")
                    or ""
                )
                pic = self.fixUrl(pic)
                if pic and not self.isAdUrl(pic):
                    return pic

            # 第二优先级：正则兜底，防止 pyquery 选择器没选中
            try:
                html = row.html() or ""
                m = re.search(
                    r'<img[^>]+class=["\\\'][^"\\\']*picture[^"\\\']*["\\\'][^>]+file=["\\\']([^"\\\']+)["\\\']',
                    html,
                    re.I
                )
                if not m:
                    m = re.search(
                        r'<img[^>]+file=["\\\']([^"\\\']+\\.(?:jpg|jpeg|png|webp))["\\\']',
                        html,
                        re.I
                    )
                if m:
                    pic = self.fixUrl(m.group(1))
                    if pic and not self.isAdUrl(pic):
                        return pic
            except Exception:
                pass

            # 第三优先级：缩略图，本地 tiebalist 缩略图
            img = self.getFirst(row, [
                ".picturedisplay ul.thumblist li img[src]",
                "ul.thumblist li img[src]",
                ".thumblist img[src]",
            ])
            if len(img) > 0:
                pic = self.getImgSrc(img)
                if pic and not self.isAdUrl(pic):
                    return pic

            # 最后兜底：普通图片，但要尽量避免头像/图标
            img = self.getFirst(row, [
                ".attachment img",
                "img[data-original]",
                "img[data-src]",
                "img[data-lazy]",
                "img[lay-src]",
                "img[zsrc]",
                "img[src]",
            ])
            if len(img) > 0:
                pic = self.getImgSrc(img)
                if pic and not self.isAdUrl(pic):
                    return pic

            return ""
        except Exception:
            return ""


    def dedupeVodList(self, vlist):
        out = []
        seen = set()
        for x in vlist:
            k = x.get("vod_id", "") or x.get("vod_name", "")
            if k and k not in seen:
                seen.add(k)
                out.append(x)
        return out

    def _set_play_pic(self, pid, pic):
        try:
            if pid and pic:
                self.play_pic_map[str(pid)] = pic
        except Exception:
            pass

    def _get_play_pic(self, pid):
        try:
            if pid and str(pid) in self.play_pic_map:
                return self.play_pic_map[str(pid)]
        except Exception:
            pass
        return self.last_vod_pic or ""

    # ===================== 首页分类 =====================
    def homeContent(self, filter):
        try:
            classes = []
            seen = set()
            urls = [f"{self.host}/forum.php", f"{self.host}/"]
            selectors = [
                "td.fl_g dt a[href*='forum.php?mod=forumdisplay&fid=']",
                "td.fl_g dt a[href*='forumdisplay&fid=']",
                "td.fl_icn + td h2 a[href*='forumdisplay&fid=']",
                ".fl_tb dt a[href*='forumdisplay&fid=']",
                ".fl_tb a[href*='mod=forumdisplay'][href*='fid=']",
                "a[href*='mod=forumdisplay'][href*='fid=']",
            ]
            ban_forum_names = ["公告区", "游客/等待验证会员", "等待验证会员"]
            ban_fids = {"37", "51"}
            for u in urls:
                data = self.getpq(u)
                for sel in selectors:
                    for a in data(sel).items():
                        href = self.fixUrl(a.attr("href") or "")
                        name = self.cleanText(a.text())
                        if not href or not name:
                            continue
                        if "forumdisplay" not in href or "fid=" not in href:
                            continue
                        if any(x in name for x in ban_forum_names):
                            continue
                        if any(x in name for x in ["返回", "上一页", "下一页", "全部公告"]):
                            continue
                        href = self.removeUrlParam(href, ["mobile"])
                        m = re.search(r"fid=(\d+)", href)
                        fid = m.group(1) if m else ""
                        key = fid if fid else href
                        if fid in ban_fids:
                            continue
                        if key in seen:
                            continue
                        seen.add(key)
                        classes.append({"type_name": name, "type_id": href})
                if classes:
                    break
            if not classes:
                classes = [
                    {"type_name": "『有码原创』", "type_id": f"{self.host}/forum.php?mod=forumdisplay&fid=211"},
                    {"type_name": "『4K UHD』", "type_id": f"{self.host}/forum.php?mod=forumdisplay&fid=192"},
                    {"type_name": "『无码原创』", "type_id": f"{self.host}/forum.php?mod=forumdisplay&fid=212"},
                    {"type_name": "『国产原创』", "type_id": f"{self.host}/forum.php?mod=forumdisplay&fid=210"},
                    {"type_name": "『欧美原创』", "type_id": f"{self.host}/forum.php?mod=forumdisplay&fid=215"},
                ]
            top_order = ["有码原创", "4K UHD", "4kuhd", "无码原创", "国产原创", "欧美原创"]

            def norm_name(s):
                s = self.cleanText(s).lower().replace(" ", "")
                s = s.replace("『", "").replace("』", "").replace("【", "").replace("】", "")
                return s

            top_order_norm = [norm_name(x) for x in top_order]

            def rank(item):
                n = norm_name(item.get("type_name", ""))
                for i, k in enumerate(top_order_norm):
                    if k in n:
                        return (0, i, n)
                if ("bt" in n) or ("115" in n):
                    return (1, 0, n)
                return (2, 0, n)

            classes.sort(key=rank)
            print(f"[homeContent] class count={len(classes)}")
            return {"class": classes}
        except Exception as e:
            print(f"[homeContent] error: {e}")
            return {"class": []}

    # ===================== 分类列表 =====================
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = str(pg or "1")
            base = str(tid or "").strip()
            if not base.startswith("http"):
                base = f"{self.host}/forum.php?mod=forumdisplay&fid={base}"
            base = self.fixUrl(base)
            base = self.removeUrlParam(base, ["mobile"])
            url = self.setUrlParam(base, "page", pg)
            data = self.getpq(url)
            vlist = []
            row_selectors = [
                "#threadlisttableid tbody[id^='normalthread_']",
                "#threadlisttableid tbody[id^='stickthread_']",
                "#threadlisttableid > tbody[id^='normalthread_']",
                "#threadlisttableid > tbody[id^='stickthread_']",
            ]
            rows = []
            for sel in row_selectors:
                rows.extend(list(data(sel).items()))
            uniq_rows, row_seen = [], set()
            for r in rows:
                rid = r.attr("id") or ""
                if rid and rid not in row_seen and rid != "separatorline":
                    row_seen.add(rid)
                    uniq_rows.append(r)
            rows = uniq_rows
            ban_title_keywords = [
                "严禁上传", "嚴禁上傳", "开放捐助会员", "開放捐助會員",
                "通知", "論壇規則", "论坛规则", "发帖规则", "發帖規則",
                "最新地址", "永久地址",
            ]
            for row in rows:
                row_id = row.attr("id") or ""
                if row_id.startswith("stickthread_"):
                    continue
                a_title = self.getFirst(row, [
                    "th.common a.s.xst",
                    "th.common a.xst",
                    "a.s.xst",
                    "a.xst",
                    "a[href*='mod=viewthread'][href*='tid=']",
                    "a[href^='thread-']",
                ])
                if len(a_title) == 0:
                    continue
                link = self.fixUrl(a_title.attr("href") or "")
                title = self.cleanText(a_title.text())
                if not link or not title:
                    continue
                if "viewthread" not in link and not re.search(r"thread-\d+", link):
                    continue
                if any(x in title for x in ["上一页", "下一页", "返回"]):
                    continue
                if any(x in title for x in ban_title_keywords):
                    continue
                link = self.removeUrlParam(link, ["mobile"])
                img = self.getFirst(row, [
                    ".picturebox .bigpicture img[data-original]",
                    ".picturebox .bigpicture img[data-src]",
                    ".picturebox .bigpicture img[file]",
                    ".picturebox .bigpicture img[zoomfile]",
                    "img[data-original]",
                    "img[data-src]",
                    "img[data-lazy]",
                    "img[lay-src]",
                    "img[file]",
                    "img[zoomfile]",
                    "img[zsrc]",
                    ".attachment img",
                    "ul.thumblist li img",
                    ".thumblist img",
                    "img",
                ])
                # Discuz 列表页真实封面优先在：
                # .picturebox img.picture[file]
                # 不要误取作者头像、附件图标、空 src。
                pic = self.getThreadListPic(row)
                author = ""
                author_el = self.getFirst(row, [
                    ".list_author .z a[href*='space']",
                    ".publishinfo a.author",
                    ".by cite a",
                    "a[href*='space-uid']",
                    "a[href*='mod=space']",
                ])
                if len(author_el) > 0:
                    author = self.cleanText(author_el.text())
                ctime = ""
                time_el = self.getFirst(row, [
                    ".list_author span[title]",
                    ".list_author .z span",
                    ".lastposttime",
                    "span[title]",
                    "em",
                ])
                if len(time_el) > 0:
                    ctime = time_el.attr("title") or self.cleanText(time_el.text())
                remarks = self.cleanText(f"{author} {ctime}")
                vlist.append({
                    "vod_id": link,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remarks,
                })
            vlist = self.dedupeVodList(vlist)
            pagecount = int(pg) if str(pg).isdigit() else 1
            pg_title = data(".pg label span[title]").eq(0).attr("title") or ""
            m = re.search(r"共\s*(\d+)\s*页", pg_title)
            if m:
                pagecount = max(pagecount, int(m.group(1)))
            for sp in data(".pg label span[title], .pg span[title]").items():
                txt = sp.attr("title") or ""
                mm = re.search(r"共\s*(\d+)\s*页|/(\d+)\s*页|(\d+)\s*页", txt)
                if mm:
                    nums = [x for x in mm.groups() if x]
                    if nums:
                        pagecount = max(pagecount, int(nums[0]))
            for a in data('a[href*="page="]').items():
                href = a.attr("href") or ""
                mm = re.search(r"[?&]page=(\d+)", href)
                if mm:
                    pagecount = max(pagecount, int(mm.group(1)))
            if pagecount < 1:
                pagecount = 1
            print(f"[categoryContent] url={url}, list={len(vlist)}, pagecount={pagecount}")
            return {
                "list": vlist,
                "page": pg,
                "pagecount": pagecount,
                "limit": 20,
                "total": pagecount * 20,
            }
        except Exception as e:
            print(f"[categoryContent] error: {e}")
            return {"list": [], "page": str(pg), "pagecount": 0, "limit": 20, "total": 0}

    # ===================== 搜索 =====================
    def searchContent(self, key, quick):
        try:
            key = str(key or "").strip()
            if not key:
                return {"list": []}
            url = f"{self.host}/search.php?mod=forum&searchsubmit=yes&srchtxt={quote(key)}"
            data = self.getpq(url)
            vlist = []
            selectors = [
                ".slst li h3 a[href*='viewthread']",
                ".slst li a[href*='viewthread']",
                "#threadlisttableid tbody a.s.xst",
                "tbody[id^='stickthread_'] a.s.xst",
                "tbody[id^='normalthread_'] a.s.xst",
                "a[href*='mod=viewthread']",
                "a[href^='thread-']",
            ]
            seen = set()
            for sel in selectors:
                for a in data(sel).items():
                    link = self.fixUrl(a.attr("href") or "")
                    title = self.cleanText(a.text())
                    if not link or not title:
                        continue
                    if "viewthread" not in link and not re.search(r"thread-\d+", link):
                        continue
                    link = self.removeUrlParam(link, ["mobile"])
                    k = link or title
                    if k in seen:
                        continue
                    seen.add(k)
                    vlist.append({"vod_id": link, "vod_name": title, "vod_pic": "", "vod_remarks": ""})
                if vlist:
                    break
            print(f"[searchContent] key={key}, count={len(vlist)}")
            return {"list": self.dedupeVodList(vlist)}
        except Exception as e:
            print(f"[searchContent] error: {e}")
            return {"list": []}

    # ===================== 详情页 =====================
    def detailContent(self, ids):
        try:
            url = self.fixUrl(ids[0])
            url = self.removeUrlParam(url, ["mobile"])
            data = self.getpq(url)
            self.last_vod_pic = ""
            title = self.cleanText(
                data("#thread_subject").text()
                or data(".ts span").text()
                or data("h1").eq(0).text()
                or data(".view_tit").text()
                or data("title").text()
                or "未知"
            )
            cover = ""
            for img in data(".t_f img[file], .message img[file], .pcb img[file], .plc img[file], img[zoomfile]").items():
                src = self.getImgSrc(img)
                if src and src.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    cover = src
                    break
            if not cover:
                for img in data(".t_f img, .message img, .pattl img, .pcb img, .plc img").items():
                    src = self.getImgSrc(img)
                    if src and not src.lower().endswith(".gif"):
                        cover = src
                        break
            if not cover:
                og = self.cleanText(data("meta[property='og:image']").attr("content") or "")
                cover = self.fixUrl(og) if og else ""
            self.last_vod_pic = cover
            vod_content = self._clean_post(data)
            magnets = self._get_magnets_advanced(data, url)
            play_from, play_url = [], []
            if magnets:
                # 4) 磁力链接
                if self.enable_magnet_push:
                    mag_items = []
                    for mg in magnets:
                        if mg.startswith("magnet:"):
                            name = f"磁力{mg[20:28]}"
                            play_id = mg.replace("magnet:", "ma2gnet:", 1)
                        elif mg.startswith("ed2k:"):
                            name = "ED2K链接"
                            play_id = mg
                        else:
                            name = f"链接{mg[:20]}"
                            play_id = mg
                        self._set_play_pic(play_id, cover)
                        mag_items.append(f"{name}${play_id}")
                    play_from.append("磁力链接")
                    play_url.append("#".join(mag_items))            
                # 1) 115云下载：下载状态排最前，原磁力项名称不变
                m115 = []
                try:
                    mg_json = json.dumps(magnets, ensure_ascii=False)
                    mg_b64 = base64.b64encode(mg_json.encode("utf-8")).decode("utf-8")
                    status_id = f"__115_STATUS_ALL__|{mg_b64}"
                    m115.append(f"下载状态${status_id}")
                    self._set_play_pic(status_id, cover)
                except Exception as e:
                    print(f"[115 cloud] build status item error: {e}")

                for mg in magnets:
                    if mg.startswith("magnet:"):
                        name = f"磁力{mg[20:28]}"
                    elif mg.startswith("ed2k:"):
                        name = "ED2K链接"
                    else:
                        name = f"链接{mg[:20]}"
                    b64 = base64.b64encode(mg.encode("utf-8")).decode("utf-8")
                    self._set_play_pic(b64, cover)
                    m115.append(f"{name}${b64}")

                if m115:
                    play_from.append("115云下载")
                    play_url.append("#".join(m115))

                # 2) 播放列表：根据115 API查询缓存生成，点击具体文件播放
                cached_list = self.build115CachedFilePlayItems(magnets)
                if not cached_list:
                    cached_list = "暂无115缓存，请先点115云下载-下载状态$__ACK__"
                play_from.append("播放列表")
                play_url.append(cached_list)
                for it in cached_list.split("#"):
                    if "$" in it:
                        _, pid = it.split("$", 1)
                        self._set_play_pic(pid, cover)

                # 2) 0 提示
                play_from.append("0")
                play_url.append("不会自动下载，请手动切换到115云下载$__ACK__")
                self._set_play_pic("__ACK__", cover)

                # 3) 115播放（OpenList）
                if self.openlist_url and self.openlist_token:
                    play_from.append("查询")
                    op = self.buildOpenlistPlayItems(title)
                    play_url.append(op)
                    for it in op.split("#"):
                        if "$" in it:
                            _, pid = it.split("$", 1)
                            self._set_play_pic(pid, cover)

            else:
                play_from.append("0")
                play_url.append("暂无可用磁力链接$__ACK__")
                self._set_play_pic("__ACK__", cover)

            vod = {
                "vod_id": url,
                "vod_name": title,
                "vod_pic": cover,
                "vod_content": vod_content[:500],
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_url),
            }
            print(f"[detailContent] title={title}, cover={bool(cover)}, magnets={len(magnets)}")
            return {"list": [vod]}
        except Exception as e:
            print(f"[detailContent] error: {e}")
            return {"list": []}

    # ===================== 详情辅助 =====================
    def _clean_post(self, data):
        try:
            raw = str(data(".t_f, .message, .pcb, .plc"))
            raw = re.sub(r'<div[^>]*class="[^"]*attach_nopermission[^"]*"[^>]*>.*?</div>', "", raw, flags=re.DOTALL | re.I)
            raw = re.sub(r'<span[^>]*class="[^"]*atips_close[^"]*"[^>]*>.*?</span>', "", raw, flags=re.DOTALL | re.I)
            raw = re.sub(r'<script[^>]*>.*?</script>', "", raw, flags=re.DOTALL | re.I)
            raw = re.sub(r'<style[^>]*>.*?</style>', "", raw, flags=re.DOTALL | re.I)
            text = re.sub(r"<[^>]+>", " ", raw)
            text = self.cleanText(text)
            text = re.sub(r"您需要登录才可以下载或查看.*?立即註冊", "", text)
            text = re.sub(r"您需要登录才可以下载或查看.*?立即注册", "", text)
            text = re.sub(r"本帖最后由.*?编辑", "", text)
            return self.cleanText(text)
        except Exception as e:
            print(f"[_clean_post] error: {e}")
            return ""

    def _get_magnets_advanced(self, data, page_url):
        magnets = []
        try:
            html = str(data).replace("&amp;", "&")
            full_text = html + "\n" + unquote(html)
            found = re.findall(r"magnet:\?xt=urn:btih:[a-zA-Z0-9]{32,40}[^\"'<>\s\\]*", full_text, re.I)
            magnets.extend(found)
            if not magnets:
                patterns = [
                    r"(?:種子特碼|特碼|特徵全碼|特征全码|特征码|HASH码|哈希值|HASH|hash|种子哈希|Hash)[：:\s]*([a-fA-F0-9]{40})",
                    r"([a-fA-F0-9]{40})",
                ]
                for pat in patterns:
                    m = re.search(pat, full_text)
                    if m:
                        magnets.append(f"magnet:?xt=urn:btih:{m.group(1).lower()}")
                        break
            if not magnets:
                magnets.extend(re.findall(
                    r"ed2k://\|file\|[^|]+\|[0-9]+\|[a-fA-F0-9]{32}\|/?", full_text, re.I
                ))
            if not magnets:
                magnets.extend(self._parse_torrent_attachments(data))
        except Exception as e:
            print(f"[_get_magnets_advanced] error: {e}")
        out, seen = [], set()
        for m in magnets:
            m = str(m).strip().replace("&amp;", "&")
            if m and m not in seen:
                seen.add(m)
                out.append(m)
        return out

    def _parse_torrent_attachments(self, data):
        magnets = []
        try:
            links = []
            for a in data("a[href*='mod=attachment'][href*='aid='], a[href*='attachment.php?aid=']").items():
                href = self.fixUrl(a.attr("href") or "")
                if href:
                    links.append(href)
            links = list(dict.fromkeys(links))
            for href in links:
                m = re.search(r"aid=(\d+)", href)
                aid = m.group(1) if m else ""
                if not aid:
                    continue
                plugin_url = f"{self.host}/plugin.php?id=torrent_info:info&aid={aid}"
                try:
                    r = self.session.get(plugin_url, headers=self.headers, timeout=10)
                    if r.status_code == 200:
                        txt = (r.text or "").replace("&amp;", "&")
                        found = re.findall(r"magnet:\?xt=urn:btih:[a-zA-Z0-9]{32,40}[^\"'<>\s\\]*", txt, re.I)
                        if found:
                            magnets.extend(found)
                            continue
                        try:
                            info = r.json()
                            if isinstance(info, dict):
                                mag = info.get("magnet") or info.get("data", {}).get("magnet")
                                if mag:
                                    magnets.append(mag)
                                    continue
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[torrent_info] error: {e}")
                for dl_url in [href, f"{self.host}/forum.php?mod=attachment&aid={aid}"]:
                    try:
                        file_rsp = self.session.get(dl_url, headers=self.headers, timeout=15)
                        ctype = file_rsp.headers.get("Content-Type", "")
                        content = file_rsp.content or b""
                        if file_rsp.status_code == 200 and len(content) > 100:
                            if b"<html" in content[:200].lower() or "text/html" in ctype.lower():
                                continue
                            mag = self._torrent_bytes_to_magnet(content)
                            if mag:
                                magnets.append(mag)
                                break
                    except Exception as e:
                        print(f"[download torrent] error: {e}")
        except Exception as e:
            print(f"[_parse_torrent_attachments] error: {e}")
        return magnets

    def _torrent_bytes_to_magnet(self, torrent_data):
        try:
            try:
                import bencoder
                meta = bencoder.decode(torrent_data)
                encoder = bencoder.encode
            except Exception:
                meta = self._simple_bdecode(torrent_data)
                encoder = self._simple_bencode
            if not meta or b"info" not in meta:
                return None
            info = meta[b"info"]
            info_b = encoder(info)
            if not info_b:
                return None
            info_hash = hashlib.sha1(info_b).hexdigest()
            name = ""
            if isinstance(info, dict) and b"name" in info:
                try:
                    name = info[b"name"].decode("utf-8", errors="ignore")
                except Exception:
                    pass
            if name:
                return f"magnet:?xt=urn:btih:{info_hash}&dn={quote(name)}"
            return f"magnet:?xt=urn:btih:{info_hash}"
        except Exception as e:
            print(f"[_torrent_bytes_to_magnet] error: {e}")
            return None

    # ===================== 简易Bencode =====================
    @staticmethod
    def _simple_bdecode(data):
        idx = 0

        def _decode():
            nonlocal idx
            if idx >= len(data):
                return None
            ch = data[idx:idx + 1]
            if ch == b"d":
                idx += 1
                d = {}
                while idx < len(data) and data[idx:idx + 1] != b"e":
                    key = _decode()
                    if not isinstance(key, bytes):
                        break
                    d[key] = _decode()
                if idx < len(data) and data[idx:idx + 1] == b"e":
                    idx += 1
                return d
            if ch == b"l":
                idx += 1
                lst = []
                while idx < len(data) and data[idx:idx + 1] != b"e":
                    lst.append(_decode())
                if idx < len(data) and data[idx:idx + 1] == b"e":
                    idx += 1
                return lst
            if ch == b"i":
                idx += 1
                end = data.index(b"e", idx)
                num = int(data[idx:end])
                idx = end + 1
                return num
            if ch.isdigit():
                colon = data.index(b":", idx)
                length = int(data[idx:colon])
                idx = colon + 1
                s = data[idx:idx + length]
                idx += length
                return s
            return None

        try:
            return _decode()
        except Exception:
            return None

    @staticmethod
    def _simple_bencode(obj):
        try:
            if isinstance(obj, dict):
                parts = [b"d"]
                for k in sorted(obj.keys()):
                    kb = k if isinstance(k, bytes) else str(k).encode("utf-8")
                    vb = Spider._simple_bencode(obj[k])
                    if vb is None:
                        return None
                    parts.append(str(len(kb)).encode() + b":" + kb)
                    parts.append(vb)
                parts.append(b"e")
                return b"".join(parts)
            if isinstance(obj, list):
                parts = [b"l"]
                for v in obj:
                    vb = Spider._simple_bencode(v)
                    if vb is None:
                        return None
                    parts.append(vb)
                parts.append(b"e")
                return b"".join(parts)
            if isinstance(obj, int):
                return b"i" + str(obj).encode() + b"e"
            if isinstance(obj, bytes):
                return str(len(obj)).encode() + b":" + obj
            if isinstance(obj, str):
                b = obj.encode("utf-8")
                return str(len(b)).encode() + b":" + b
            return None
        except Exception:
            return None

    # ===================== OpenList 核心 =====================
    def normalizeOpenlistBaseUrl(self, url):
        url = str(url or "").strip()
        if not url:
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url.rstrip("/")
        if url.startswith("http:") and not url.startswith("http://"):
            url = url.replace("http:", "", 1).lstrip("/")
            return ("http://" + url).rstrip("/")
        if url.startswith("https:") and not url.startswith("https://"):
            url = url.replace("https:", "", 1).lstrip("/")
            return ("https://" + url).rstrip("/")
        return ("http://" + url.lstrip("/")).rstrip("/")

    def openlistHeaders(self):
        token = (self.openlist_token or "").strip()
        return {
            "Authorization": token,
            "Content-Type": "application/json",
            "User-Agent": self.headers.get("User-Agent", ""),
            "Accept": "application/json, text/plain, */*",
        }
    def openlistApiPost(self, api_path, payload, timeout=15):
        """
        OpenList/AList API 请求。
        注意：
        1. 使用独立 openlist_session
        2. 不携带 169bbs 的 Cookie / Referer / Origin
        3. 打印错误日志，方便排查 token、地址、权限问题
        """
        if not self.openlist_url:
            return {}
        url = f"{self.openlist_url}{api_path}"
        try:
            headers = self.openlistHeaders()

            # 避免把论坛 Cookie / Referer 带给 OpenList/AList
            headers.pop("Cookie", None)
            headers.pop("Referer", None)
            headers.pop("Origin", None)
            headers.pop("Host", None)

            sess = getattr(self, "openlist_session", None)
            if sess is None:
                sess = Session()
                sess.verify = False
                self.openlist_session = sess

            r = sess.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
                verify=False
            )

            if r.status_code != 200:
                print(f"[OpenList API] {api_path} HTTP {r.status_code}, text={r.text[:300]}")
                return {}

            try:
                data = r.json()
            except Exception:
                print(f"[OpenList API] {api_path} json parse fail: {r.text[:300]}")
                return {}

            if data.get("code") != 200:
                print(f"[OpenList API] {api_path} code={data.get('code')}, message={data.get('message')}")

            return data

        except Exception as e:
            print(f"[OpenList API] {api_path} error: {e}")
            return {}
    def openlistNormalizePath(self, path):
        path = str(path or "/").strip()
        path = "/" + path.lstrip("/")
        if path != "/":
            path = path.rstrip("/")
        return path

    def openlistJoinPath(self, parent, name):
        parent = self.openlistNormalizePath(parent)
        name = str(name or "").strip("/")
        if parent == "/":
            return "/" + name
        return parent + "/" + name

    def isPathUnderOpenlistParent(self, path):
        try:
            parent = self.openlistNormalizePath(self.openlist_parent)
            path = self.openlistNormalizePath(path)
            if parent == "/":
                return True
            return path == parent or path.startswith(parent.rstrip("/") + "/")
        except Exception:
            return False

    def listOpenlistDir(self, path, refresh=False):
        """
        OpenList/AList 轻量目录读取：
        只读取第一页，不翻页，不递归，固定 per_page=200，强制 refresh=False。
        避免连续访问 115 挂载导致断连。
        """
        path = self.openlistNormalizePath(path)
        if not self.isPathUnderOpenlistParent(path):
            return []

        data = self.openlistApiPost(
            "/api/fs/list",
            {
                "path": path,
                "password": "",
                "page": 1,
                "per_page": 200,
                "refresh": False
            },
            20,
        )

        if data.get("code") != 200:
            return []

        d = data.get("data", {}) or {}
        return d.get("content", []) or []
    def parseOpenlistTime(self, item):
        t = item.get("modified") or item.get("created") or item.get("updated_at") or item.get("time") or ""
        if not t:
            return 0
        try:
            t = str(t).replace("Z", "+00:00")
            return datetime.fromisoformat(t).timestamp()
        except Exception:
            return 0

    def openlistIsDir(self, item):
        if not item:
            return False
        if "is_dir" in item:
            return bool(item.get("is_dir"))
        if "isDir" in item:
            return bool(item.get("isDir"))
        if item.get("type") == 1:
            return True
        mime = str(item.get("mime_type") or item.get("mime") or "").lower()
        return ("directory" in mime) or ("folder" in mime)

    def isOpenlistVideoFile(self, name):
        name = str(name or "").lower()
        return name.endswith((".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".ts", ".m2ts",
                              ".webm", ".m3u8", ".rmvb", ".mpg", ".mpeg", ".3gp", ".m4v", ".vob", ".f4v"))

    def normalizeSearchText(self, text):
        text = str(text or "").lower()
        text = unquote(text)
        text = re.sub(r"[\s\-_.,，。:：;；!！?？'\"“”‘’\[\]【】()（）{}《》<>「」『』/\\|&@]+", "", text)
        return text

    # ===== 番号工具 =====
    def extractVideoCode(self, text):
        s = self.cleanText(text or "")

        # 特殊番号优先
        special_patterns = [
            r"\b(FC2)[-_ ]?(?:PPV)?[-_ ]?(\d{5,8})\b",
            r"\b(HEYZO)[-_ ]?(\d{3,6})\b",
            r"\b(1PONDO)[-_ ]?(\d{6}[_-]\d{3})\b",
            r"\b(CARIB)[-_ ]?(\d{6}[-_]\d{3})\b",
        ]
        for p in special_patterns:
            m = re.search(p, s, re.I)
            if not m:
                continue
            prefix = (m.group(1) or "").upper()
            num = (m.group(2) or "")
            return {
                "raw": f"{prefix}-{num}",
                "prefix": prefix,
                "num": num,
                "dash": f"{prefix}-{num}",
                "nodash": f"{prefix}{re.sub(r'[^0-9A-Za-z]', '', num)}",
            }

        patterns = [
            r"\b([A-Za-z]{2,10}|\d{2,5}[A-Za-z]{2,10})[-_](\d{2,7})(?:[-_ ]?(?:cd\d+|part\d+|[a-z]{1,3}|\d{1,2}))?\b",
            r"\b([A-Za-z]{2,10}|\d{2,5}[A-Za-z]{2,10})\s+(\d{2,7})(?:[-_ ]?(?:cd\d+|part\d+|[a-z]{1,3}|\d{1,2}))?\b",
            r"\b([A-Za-z]{2,10}|\d{2,5}[A-Za-z]{2,10})(\d{2,7})(?:[-_ ]?(?:cd\d+|part\d+|[a-z]{1,3}|\d{1,2}))?\b",
        ]
        bad_prefix = {"CM", "MM", "GB", "MB", "TB", "FPS", "K"}
        for p in patterns:
            m = re.search(p, s, re.I)
            if not m:
                continue
            prefix = (m.group(1) or "").upper()
            num = (m.group(2) or "")
            if prefix in bad_prefix:
                continue
            if not num.isdigit():
                continue
            return {
                "raw": f"{prefix}-{num}",
                "prefix": prefix,
                "num": num,
                "dash": f"{prefix}-{num}",
                "nodash": f"{prefix}{num}",
            }
        return None

    def candidateMatchExactCode(self, candidate, code_info):
        if not candidate or not code_info:
            return False
        pfx = str(code_info.get("prefix", "")).lower()
        num = re.sub(r"[^0-9a-zA-Z]", "", str(code_info.get("num", "")).lower())
        if not pfx or not num:
            return False
        raw = (str(candidate.get("name", "")) + " " + str(candidate.get("path", ""))).lower()
        norm = re.sub(r"[\s\-_\.@]+", "", raw)
        return (f"{pfx}{num}" in norm)

    def candidateMatchCodeSuffixAllowed(self, candidate, code_info, allow_suffix=None):
        if not candidate or not code_info:
            return False
        if allow_suffix is None:
            allow_suffix = {"", "c", "ch", "uc"}
        pfx = str(code_info.get("prefix", "")).lower()
        num = re.sub(r"[^0-9a-zA-Z]", "", str(code_info.get("num", "")).lower())
        if not pfx or not num:
            return False
        raw = (str(candidate.get("name", "")) + " " + str(candidate.get("path", ""))).lower()
        norm = re.sub(r"[\s\-_\.@]+", "", raw)
        hits = re.findall(rf"{re.escape(pfx)}{re.escape(num)}([a-z]{{0,8}})", norm, re.I)
        if not hits:
            return False
        for suf in hits:
            suf = (suf or "").lower()
            if suf == "":
                return True
            if suf in allow_suffix:
                return True
            if suf.startswith("c") or suf.startswith("ch") or suf.startswith("uc"):
                return True
        return False

    def buildOpenlistSearchKeywords(self, title, n=5):
        title = self.cleanText(title or "")
        try:
            n = int(n)
        except Exception:
            n = 5
        n = max(1, min(30, n))

        keywords = []
        clean_title = self.cleanTitleForSearch(title)

        code = self.extractVideoCode(title) or self.extractVideoCode(clean_title)
        if code:
            keywords += [code["dash"], code["nodash"]]
        else:
            m = re.search(r"\b([A-Za-z0-9]{2,12})[-_\s]?(\d{2,7})\b", clean_title or title, re.I)
            if m:
                code1 = m.group(1).upper()
                code2 = m.group(2)
                keywords += [f"{code1}-{code2}", f"{code1}{code2}"]

        use_title = clean_title if clean_title else title
        raw = re.sub(r"\s+", "", use_title)
        if raw:
            keywords.append(raw[:n])

        compact = re.sub(r"[\[\]【】()（）{}《》<>「」『』]", "", use_title)
        compact = re.sub(r"[\/\\\|\-_.,，。:：;；!！?？'\"“”‘’&@]+", "", compact)
        compact = re.sub(r"\s+", "", compact)
        if compact:
            keywords.append(compact[:n])

        # 补充长词 token（无番号时更有用）
        tokens = re.split(r"[\s\-_.,，。:：;；!！?？\[\]【】()（）{}<>/\\|]+", use_title)
        tokens = [x for x in tokens if len(x) >= 3]
        keywords.extend(tokens[:5])

        out, seen = [], set()
        for k in keywords:
            k = self.cleanText(k)
            if k and k not in seen:
                seen.add(k)
                out.append(k)
        return out


    def buildOpenlistPlayItems(self, title):
        """
        保留刷新缓存按钮。
        删除刷新混存、播放最新。
        番号提取和搜N标题提取规则不变。
        """
        try:
            title = self.cleanText(title or "")
            title_b64 = base64.b64encode(title.encode("utf-8")).decode("utf-8")
            items = []

            # 只保留这一个刷新按钮：
            # 点击后只刷新 openlist_parent 最新3个条目
            items.append(f"刷新OpenList$__OPENLIST_REFRESH__|{title_b64}")

            code = self.extractVideoCode(title)
            if code:
                code_name = code.get("dash", code.get("raw", "番号"))
                code_b64 = base64.b64encode(code_name.encode("utf-8")).decode("utf-8")
                items.append(f"{code_name}$__OPENLIST_CODE__|{code_b64}")

            for n in range(2, 14):
                items.append(f"搜{n}$__OPENLIST_SEARCH__|{n}|{title_b64}")

            return "#".join(items)

        except Exception as e:
            print(f"[OpenList] build play items error: {e}")
            return "刷新缓存$__OPENLIST_REFRESH__"
    def openlistListDirOnce(self, path, per_page=200, refresh=False):
        """
        只读取指定目录一层。
        用途：
        1. /api/fs/search 命中目录后，展开该目录一层找视频
        2. 点击“刷新缓存”时刷新 openlist_parent 首页

        注意：
        不递归，不扫描全盘，不写索引。
        """
        result = []

        if not self.openlist_url:
            return result

        path = self.openlistNormalizePath(path)

        if not self.isPathUnderOpenlistParent(path):
            return result

        try:
            per_page = max(20, min(500, int(per_page)))
        except Exception:
            per_page = 200

        data = self.openlistApiPost(
            "/api/fs/list",
            {
                "path": path,
                "password": "",
                "page": 1,
                "per_page": per_page,
                "refresh": bool(refresh)
            },
            25
        )

        if data.get("code") != 200:
            return result

        d = data.get("data", {}) or {}
        content = d.get("content") or []

        for item in content:
            try:
                name = str(item.get("name") or "").strip()
                if not name:
                    continue

                full_path = self.openlistJoinPath(path, name)

                if not self.isPathUnderOpenlistParent(full_path):
                    continue

                try:
                    size = int(item.get("size") or 0)
                except Exception:
                    size = 0

                result.append({
                    "name": name,
                    "path": full_path,
                    "size": size,
                    "time": self.parseOpenlistTime(item),
                    "sign": item.get("sign", ""),
                    "is_dir": self.openlistIsDir(item),
                    "parent": path,
                })

            except Exception as e:
                print(f"[OpenList list once item] error: {e}")

        return result


    def openlistApiSearchFiles(self, keyword, page=1, per_page=100):
        """
        使用 OpenList/AList /api/fs/search 搜索。

        规则：
        1. 搜到视频文件：直接加入候选
        2. 搜到目录：只展开该命中目录一层，找视频文件
        3. 不递归扫描父目录
        4. 不写本地索引
        """
        results = []

        if not self.openlist_url:
            return results

        keyword = self.cleanText(keyword or "")
        if not keyword:
            return results

        try:
            page = max(1, int(page))
        except Exception:
            page = 1

        try:
            per_page = max(20, min(200, int(per_page)))
        except Exception:
            per_page = 100

        payload = {
            "parent": self.openlistNormalizePath(self.openlist_parent),
            "keywords": keyword,
            "scope": 0,
            "page": page,
            "per_page": per_page,
            "password": ""
        }

        data = self.openlistApiPost("/api/fs/search", payload, 20)

        if data.get("code") != 200:
            return results

        d = data.get("data", {}) or {}
        content = d.get("content") or []

        for item in content:
            try:
                name = str(item.get("name") or "").strip()
                if not name:
                    continue

                parent = str(item.get("parent") or "").strip()
                path = str(item.get("path") or "").strip()

                if path:
                    full_path = self.openlistNormalizePath(path)
                else:
                    full_path = self.openlistJoinPath(parent, name)

                if not self.isPathUnderOpenlistParent(full_path):
                    continue

                # 搜索结果是目录：只展开命中的目录一层
                if self.openlistIsDir(item):
                    children = self.openlistListDirOnce(full_path, per_page=300, refresh=False)

                    for child in children:
                        if child.get("is_dir"):
                            continue

                        child_name = str(child.get("name") or "")

                        if not self.isOpenlistVideoFile(child_name):
                            continue

                        results.append(child)

                    continue

                # 搜索结果是文件：只保留视频文件
                if not self.isOpenlistVideoFile(name):
                    continue

                try:
                    size = int(item.get("size") or 0)
                except Exception:
                    size = 0

                results.append({
                    "name": name,
                    "path": full_path,
                    "size": size,
                    "time": self.parseOpenlistTime(item),
                    "sign": item.get("sign", ""),
                    "parent": parent,
                    "is_dir": False,
                })

            except Exception as e:
                print(f"[OpenList API search item] error: {e}")

        return results


    def searchOpenlistByApi(self, keywords, max_pages=2, per_page=100):
        """
        根据 buildOpenlistSearchKeywords 生成的关键词调用 /api/fs/search。
        不改变原标题提取规则。
        不递归目录。
        """
        result = []
        seen = set()

        if not keywords:
            return result

        if isinstance(keywords, str):
            keywords = [keywords]

        keywords = [self.cleanText(x) for x in keywords if self.cleanText(x)]
        if not keywords:
            return result

        try:
            max_pages = max(1, min(5, int(max_pages)))
        except Exception:
            max_pages = 2

        for kw in keywords:
            for page in range(1, max_pages + 1):
                files = self.openlistApiSearchFiles(kw, page=page, per_page=per_page)

                if not files:
                    break

                for f in files:
                    p = self.openlistNormalizePath(f.get("path", ""))
                    if not p:
                        continue
                    if p in seen:
                        continue

                    seen.add(p)
                    result.append(f)

        return result


    def filterOpenlistApiCandidates(self, candidates, keywords):
        """
        对 /api/fs/search 返回候选进行二次过滤。
        保留原匹配思路：

        1. 有番号：使用 candidateMatchCodeSuffixAllowed
        2. 无番号：使用 normalizeSearchText 后的关键词包含判断
        3. 视频文件过滤仍用 isOpenlistVideoFile
        """
        if not candidates:
            return []

        if isinstance(keywords, str):
            keywords = [keywords]

        keywords = [self.cleanText(x) for x in keywords if self.cleanText(x)]
        norm_keys = [self.normalizeSearchText(x) for x in keywords if x]
        norm_keys = [x for x in norm_keys if x]

        code_info = self.extractVideoCode(" ".join(keywords))

        filtered = []

        for c in candidates:
            name = str(c.get("name") or "")
            path = str(c.get("path") or "")

            if not name or not path:
                continue

            if not self.isOpenlistVideoFile(name):
                continue

            # 有番号时，沿用原番号匹配规则
            if code_info:
                if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"}):
                    filtered.append(c)
                continue

            # 无番号时，沿用原 normalizeSearchText 包含匹配
            text_n = self.normalizeSearchText(name + " " + path)

            if norm_keys and any(k in text_n for k in norm_keys):
                filtered.append(c)

        return filtered


    def refreshOpenlistLatest3ToMemory(self, title=""):
        """
        点击“刷新缓存”时执行。

        功能：
        1. 清空内存搜索缓存
        2. refresh=True 刷新 openlist_parent 首页
        3. 取父目录下最新3个条目
        4. 如果条目是视频，加入内存 recent_files
        5. 如果条目是目录，只展开该目录一层，找视频加入 recent_files

        注意：
        不递归。
        不写索引。
        只点击时运行。
        """
        try:
            n = max(1, int(getattr(self, "openlist_refresh_latest_n", 3) or 3))
        except Exception:
            n = 3

        parent = self.openlistNormalizePath(self.openlist_parent)

        print(f"[OpenList REFRESH] refresh parent={parent}, latest_n={n}, title={title}")

        try:
            self._openlist_search_cache.clear()
        except Exception:
            pass

        items = self.openlistListDirOnce(parent, per_page=100, refresh=True)

        if not items:
            print("[OpenList REFRESH] parent list empty")
            self._openlist_recent_files = []
            return 0

        items.sort(
            key=lambda x: (
                int(x.get("time") or 0),
                int(x.get("size") or 0)
            ),
            reverse=True
        )

        latest_items = items[:n]

        videos = []
        seen = set()

        for it in latest_items:
            try:
                name = str(it.get("name") or "")
                path = self.openlistNormalizePath(it.get("path") or "")

                if not name or not path:
                    continue

                # 最新条目本身就是视频
                if not it.get("is_dir") and self.isOpenlistVideoFile(name):
                    if path not in seen:
                        seen.add(path)
                        videos.append(it)
                    continue

                # 最新条目是目录：只展开一层
                if it.get("is_dir"):
                    children = self.openlistListDirOnce(path, per_page=300, refresh=True)

                    for child in children:
                        child_name = str(child.get("name") or "")
                        child_path = self.openlistNormalizePath(child.get("path") or "")

                        if not child_name or not child_path:
                            continue

                        if child.get("is_dir"):
                            continue

                        if not self.isOpenlistVideoFile(child_name):
                            continue

                        if child_path in seen:
                            continue

                        seen.add(child_path)
                        videos.append(child)

            except Exception as e:
                print(f"[OpenList REFRESH] latest item error: {e}")

        self._openlist_recent_files = videos

        print(f"[OpenList REFRESH] recent video count={len(videos)}")

        for v in videos[:10]:
            print(f"[OpenList REFRESH] video={v.get('name')} path={v.get('path')}")

        return len(videos)
    def normalizeOpenlistUrl(self, url):
        if not url:
            return ""
        url = str(url).strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if url.startswith("/"):
            return self.openlist_url.rstrip("/") + url
        return urljoin(self.openlist_url.rstrip("/") + "/", url)

    def buildOpenlistDownloadUrl(self, full_path, sign=""):
        p = "/" + str(full_path or "").lstrip("/")
        url = f"{self.openlist_url.rstrip('/')}/d{quote(p, safe='/')}"
        if sign:
            url += ("&" if "?" in url else "?") + "sign=" + quote(str(sign))
        return url

    def buildOpenlistDavUrl(self, full_path):
        p = "/" + str(full_path or "").lstrip("/")
        return f"{self.openlist_url.rstrip('/')}/dav{quote(p, safe='/')}"

    def getPlayableUrlFromOpenlist(self, file_path):

        # 查询线路优先115缓存时，会传入 __115CACHE__|fid_or_pickcode
        try:
            if str(file_path or "").startswith("__115CACHE__|"):
                fk = str(file_path).split("|", 1)[1].strip()
                cache = self._115_cache_load()
                f = cache.get("files", {}).get(fk)
                if f:
                    pickcode = f.get("pickcode") or ""
                    if pickcode:
                        play_url, headers = self._115_get_play_url_by_pickcode(pickcode)
                        if play_url:
                            return play_url, headers
                return "", {}
        except Exception as e:
            print(f"[115 cache playable] error: {e}")
        file_path = self.openlistNormalizePath(file_path)
        if not self.isPathUnderOpenlistParent(file_path):
            return "", {}
        data = self.openlistApiPost("/api/fs/get", {"path": file_path, "password": ""}, 15)
        headers = {"User-Agent": self.headers.get("User-Agent", "")}
        if data.get("code") == 200:
            d = data.get("data", {}) or {}
            extra_header = d.get("header") or d.get("headers") or {}
            if isinstance(extra_header, dict):
                for k, v in extra_header.items():
                    if k and v:
                        headers[str(k)] = str(v)
            raw = d.get("raw_url") or d.get("rawUrl") or d.get("url") or ""
            if raw:
                return self.normalizeOpenlistUrl(raw), headers
            sign = d.get("sign") or ""
            return self.buildOpenlistDownloadUrl(file_path, sign), headers
        if self.openlist_force_dav:
            dav = self.buildOpenlistDavUrl(file_path)
            headers["Referer"] = self.openlist_url.rstrip("/") + "/"
            return dav, headers
        return self.buildOpenlistDownloadUrl(file_path), headers

    # ===================== OpenList 索引 =====================
    def getOpenlistNamespaceKey(self):
        return f"{self.normalizeOpenlistBaseUrl(self.openlist_url)}|{self.openlistNormalizePath(self.openlist_parent)}"

    def _index_read_all(self):
        try:
            if not self.openlist_index_file or (not os.path.exists(self.openlist_index_file)):
                return {"namespaces": {}}
            with open(self.openlist_index_file, "r", encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                return {"namespaces": {}}
            if "namespaces" not in d or not isinstance(d.get("namespaces"), dict):
                d["namespaces"] = {}
            return d
        except Exception:
            return {"namespaces": {}}

    def _index_write_all(self, data):
        """
        写入索引文件。
        修复点：
        1. 自动创建目录
        2. 使用临时文件 + os.replace 原子替换
        3. 打印成功/失败日志
        """
        try:
            if not isinstance(data, dict):
                return
            if "namespaces" not in data or not isinstance(data.get("namespaces"), dict):
                data["namespaces"] = {}

            p = self.openlist_index_file
            if not p:
                return

            dir_name = os.path.dirname(p)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name, exist_ok=True)

            tmp = p + ".tmp"

            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            os.replace(tmp, p)

            print(f"[index] write ok: {p}")

        except Exception as e:
            print(f"[index] write error: {e}, file={getattr(self, 'openlist_index_file', '')}")
    def _index_get_ns(self, data):
        ns_key = self.getOpenlistNamespaceKey()
        ns = data["namespaces"].get(ns_key)
        if not isinstance(ns, dict):
            ns = {"last_full_scan_ts": 0, "by_path": {}, "hash_map": {}}
            data["namespaces"][ns_key] = ns
        if "by_path" not in ns or not isinstance(ns.get("by_path"), dict):
            ns["by_path"] = {}
        if "hash_map" not in ns or not isinstance(ns.get("hash_map"), dict):
            ns["hash_map"] = {}
        if "last_full_scan_ts" not in ns:
            ns["last_full_scan_ts"] = 0
        return ns

    def _extract_btih_from_text(self, text):
        s = (text or "").strip()
        if not s:
            return ""
        m = re.search(r"\b([a-fA-F0-9]{40})\b", s)
        if m:
            return m.group(1).lower()
        m = re.search(r"\b([A-Z2-7]{32})\b", s)
        if m:
            return m.group(1).lower()
        return ""

    def _index_rebuild_hash_map(self, ns):
        hm = {}
        by_path = ns.get("by_path", {}) or {}
        for p, rec in by_path.items():
            h = (rec.get("hash_hint") or "").strip().lower()
            if not h:
                continue
            hm.setdefault(h, []).append(p)
        ns["hash_map"] = hm

    def _index_merge_files(self, files, update_full_scan_ts=True):
        now_ts = int(time.time())
        with self._index_lock:
            data = self._index_read_all()
            ns = self._index_get_ns(data)
            by_path = ns.get("by_path", {})
            for it in files or []:
                p = self.openlistNormalizePath(it.get("path", ""))
                if not p:
                    continue
                name = str(it.get("name") or "")
                rec = {
                    "name": name,
                    "path": p,
                    "size": int(it.get("size") or 0),
                    "time": int(it.get("time") or 0),
                    "sign": str(it.get("sign") or ""),
                    "hash_hint": self._extract_btih_from_text(name + " " + p),
                    "seen_at": now_ts,
                    "text_n": self.normalizeSearchText(name + " " + p),
                    "name_n": self.normalizeSearchText(name),
                    "path_n": self.normalizeSearchText(p),
                }
                by_path[p] = rec
            max_age = int(self.openlist_index_max_age_days) * 86400
            to_del = []
            for p, rec in by_path.items():
                seen_at = int(rec.get("seen_at") or 0)
                if seen_at > 0 and (now_ts - seen_at > max_age):
                    to_del.append(p)
            for p in to_del:
                by_path.pop(p, None)
            ns["by_path"] = by_path
            if update_full_scan_ts:
                ns["last_full_scan_ts"] = now_ts
            self._index_rebuild_hash_map(ns)
            self._index_write_all(data)

    def _index_all_records(self):
        data = self._index_read_all()
        ns_key = self.getOpenlistNamespaceKey()
        ns = data.get("namespaces", {}).get(ns_key, {})
        by_path = ns.get("by_path", {}) or {}
        return list(by_path.values())

    # 全量扫描（云下载目录）
    def fullScanOpenlistToIndex(self):
        """
        不执行全量递归扫描。
        只扫描 OpenList 父目录首页第一页，并生成索引。
        强制 refresh=False，避免触发 115 挂载刷新导致断连。
        """
        try:
            all_files = self.scanOpenlistHomeVideosWithSize(refresh=False)
            self._index_merge_files(all_files, update_full_scan_ts=True)
            print(f"[index] OpenList首页第一页扫描完成，索引文件数={len(all_files)}")
            return len(all_files)
        except Exception as e:
            print(f"[index] homepage scan error: {e}")
            return 0
    def refreshLatestNFilesToIndex(self, n=5):
        """
        只从 OpenList 首页第一页取最新N个视频文件，不递归、不翻页。
        强制 refresh=False，避免刷新 115 挂载。
        """
        try:
            n = max(1, int(n))
            all_files = self.scanOpenlistHomeVideosWithSize(refresh=False)
            if not all_files:
                return 0
            all_files.sort(
                key=lambda x: (
                    int(x.get("time") or 0),
                    int(x.get("size") or 0)
                ),
                reverse=True
            )
            latest = all_files[:n]
            self._index_merge_files(latest, update_full_scan_ts=False)
            print(f"[index] OpenList首页第一页最新{n}个文件刷新完成，数量={len(latest)}")
            return len(latest)
        except Exception as e:
            print(f"[index] refresh latest homepage files error: {e}")
            return 0
    def refreshLatestNFoldersToIndex(self, n=None):
        """
        不再扫描最新文件夹。
        仅扫描 OpenList 父目录首页第一页的视频文件。
        强制 refresh=False，避免触发 115 挂载刷新。
        """
        try:
            all_files = self.scanOpenlistHomeVideosWithSize(refresh=False)
            if not all_files:
                return 0
            all_files.sort(
                key=lambda x: (
                    int(x.get("time") or 0),
                    int(x.get("size") or 0)
                ),
                reverse=True
            )
            if n is None:
                n = self.openlist_index_refresh_n
            try:
                n = max(1, int(n))
            except Exception:
                n = self.openlist_index_refresh_n
            latest = all_files[:n]
            self._index_merge_files(latest, update_full_scan_ts=False)
            print(f"[index] OpenList首页第一页刷新完成，数量={len(latest)}")
            return len(latest)
        except Exception as e:
            print(f"[index] refresh homepage error: {e}")
            return 0
    def searchOpenlistBestVideoFromIndex(self, keywords):
        if not keywords:
            return None
        if isinstance(keywords, str):
            keywords = [keywords]
        keywords = [str(x).strip() for x in keywords if str(x).strip()]
        if not keywords:
            return None
        records = self._index_all_records()
        if not records:
            return None
        norm_keys = [self.normalizeSearchText(k) for k in keywords if k]
        code_info = self.extractVideoCode(" ".join(keywords))
        candidates = []
        for rec in records:
            name = str(rec.get("name", ""))
            path = str(rec.get("path", ""))
            if not name or not path:
                continue
            text_n = rec.get("text_n") or self.normalizeSearchText(name + " " + path)
            if not text_n:
                continue
            if any(k and k in text_n for k in norm_keys):
                candidates.append(rec)
        if not candidates:
            return None
        if code_info:
            strict = [c for c in candidates if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})]
            if strict:
                strict.sort(key=lambda x: (self.scoreOpenlistCandidate(x, norm_keys), int(x.get("size") or 0)), reverse=True)
                return strict[0]
        candidates.sort(key=lambda x: (self.scoreOpenlistCandidate(x, norm_keys), int(x.get("size") or 0)), reverse=True)
        return candidates[0]

    def _scan_sleep(self):
        gap = max(0, int(self.openlist_scan_sleep_ms)) / 1000.0
        if gap <= 0:
            return
        now = time.time()
        diff = now - self._openlist_last_scan_ts
        if diff < gap:
            time.sleep(gap - diff)
        self._openlist_last_scan_ts = time.time()

    def _cache_get(self, key):
        item = self._openlist_search_cache.get(key)
        if not item:
            return None
        ts, val = item
        if self.openlist_search_cache_ttl > 0 and (time.time() - ts > self.openlist_search_cache_ttl):
            self._openlist_search_cache.pop(key, None)
            return None
        return val

    def _cache_set(self, key, val):
        if self.openlist_search_cache_ttl == 0:
            return
        self._openlist_search_cache[key] = (time.time(), val)

    def scanOpenlistVideosWithSize(self, path, depth=3, budget=None):
        result = []
        if budget is None:
            budget = {"nodes": self.openlist_scan_max_nodes}
        try:
            depth = int(depth)
        except Exception:
            depth = 3
        if depth < 0 or budget["nodes"] <= 0:
            return result
        path = self.openlistNormalizePath(path)
        if not self.isPathUnderOpenlistParent(path):
            return result
        self._scan_sleep()
        items = self.listOpenlistDir(path, refresh=False)
        budget["nodes"] -= 1
        for item in items:
            if budget["nodes"] <= 0:
                break
            name = item.get("name", "")
            if not name:
                continue
            full_path = self.openlistJoinPath(path, name)
            if not self.isPathUnderOpenlistParent(full_path):
                continue
            if self.openlistIsDir(item):
                if depth > 0:
                    result.extend(self.scanOpenlistVideosWithSize(full_path, depth - 1, budget))
            else:
                if self.isOpenlistVideoFile(name):
                    try:
                        size = int(item.get("size") or 0)
                    except Exception:
                        size = 0
                    result.append({
                        "name": name,
                        "path": full_path,
                        "size": size,
                        "time": self.parseOpenlistTime(item),
                        "sign": item.get("sign", ""),
                    })
        return result

    def searchOpenlistByScan(self, keywords, path=None, depth=None, budget=None):
        result = []
        if not keywords:
            return result
        if isinstance(keywords, str):
            keywords = [keywords]
        if budget is None:
            budget = {"nodes": self.openlist_scan_max_nodes}
        parent = self.openlistNormalizePath(self.openlist_parent)
        path = parent if path is None else self.openlistNormalizePath(path)
        if not self.isPathUnderOpenlistParent(path):
            return result
        if depth is None:
            depth = self.openlist_latest_depth
        try:
            depth = int(depth)
        except Exception:
            depth = 3
        if depth < 0 or budget["nodes"] <= 0:
            return result
        norm_keys = [self.normalizeSearchText(k) for k in keywords if k]
        norm_keys = [k for k in norm_keys if k]
        if not norm_keys:
            return result
        self._scan_sleep()
        items = self.listOpenlistDir(path, refresh=False)
        budget["nodes"] -= 1
        for item in items:
            if budget["nodes"] <= 0:
                break
            name = item.get("name", "")
            if not name:
                continue
            full_path = self.openlistJoinPath(path, name)
            if not self.isPathUnderOpenlistParent(full_path):
                continue
            norm_name = self.normalizeSearchText(name)
            norm_path = self.normalizeSearchText(full_path)
            matched = any(k in norm_name or k in norm_path for k in norm_keys)
            if self.openlistIsDir(item):
                if depth > 0:
                    result.extend(self.searchOpenlistByScan(norm_keys, full_path, depth - 1, budget))
                if matched:
                    result.extend(self.scanOpenlistVideosWithSize(full_path, max(1, depth - 1), budget))
            else:
                if matched and self.isOpenlistVideoFile(name):
                    try:
                        size = int(item.get("size") or 0)
                    except Exception:
                        size = 0
                    result.append({
                        "name": name,
                        "path": full_path,
                        "size": size,
                        "time": self.parseOpenlistTime(item),
                        "sign": item.get("sign", ""),
                    })
        return result

    def scoreOpenlistCandidate(self, c, keywords):
        name = self.normalizeSearchText(c.get("name", ""))
        path = self.normalizeSearchText(c.get("path", ""))
        score = 0

        for k in keywords:
            nk = self.normalizeSearchText(k)
            if not nk:
                continue
            if nk in name:
                score += 100
            elif nk in path:
                score += 30

        code_info = self.extractVideoCode(" ".join(keywords))
        if code_info and self.candidateMatchExactCode(c, code_info):
            score += 10000

        # 文件大小评分（修复语法 + 小文件惩罚）
        try:
            size = int(c.get("size", 0) or 0)
            if size < 50 * 1024 * 1024:
                score -= 100
            elif size < 200 * 1024 * 1024:
                score -= 20
            else:
                score += min(size // (500 * 1024 * 1024), 20)
        except Exception:
            pass

        # 时间评分（按新旧）
        try:
            t = int(c.get("time", 0) or 0)
            if t > 0:
                age_days = max(0, (time.time() - t) / 86400)
                if age_days <= 1:
                    score += 10
                elif age_days <= 3:
                    score += 8
                elif age_days <= 7:
                    score += 5
                elif age_days <= 30:
                    score += 2
        except Exception:
            pass

        # 后缀轻量加分
        n = str(c.get("name", "")).lower()
        if n.endswith(".mp4"):
            score += 8
        elif n.endswith(".mkv"):
            score += 6
        elif n.endswith((".ts", ".m2ts")):
            score += 3
        elif n.endswith((".flv", ".wmv", ".avi")):
            score += 1

        return score

    # 番号专线：索引优先 -> 回退扫描

    def searchOpenlistBestVideoByCode(self, code_text):
        """
        番号专线：
        使用 OpenList /api/fs/search。
        番号提取规则 extractVideoCode 原样保留。
        匹配规则 candidateMatchCodeSuffixAllowed 原样保留。

        优先级：
        1. 点击刷新缓存得到的 recent_files
        2. /api/fs/search
        """
        try:
            cache_hit = self.search115CacheBestVideo([code_text])
            if cache_hit:
                return cache_hit
            code_info = self.extractVideoCode(code_text or "")
            if not code_info:
                return None

            keywords = [
                code_info.get("dash", ""),
                code_info.get("nodash", ""),
            ]
            keywords = [x for x in keywords if x]

            if not keywords:
                return None

            cache_key = "api_code|" + "|".join([
                self.openlistNormalizePath(self.openlist_parent)
            ] + [self.normalizeSearchText(x) for x in keywords])

            cached = self._cache_get(cache_key)
            if cached:
                return cached

            norm_keys = [self.normalizeSearchText(x) for x in keywords if x]

            # 1. 优先匹配点击刷新得到的 recent_files
            recent = getattr(self, "_openlist_recent_files", []) or []
            if recent:
                strict_pool = [
                    c for c in recent
                    if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
                ]

                if strict_pool:
                    strict_pool.sort(
                        key=lambda x: (
                            self.scoreOpenlistCandidate(x, norm_keys),
                            int(x.get("size") or 0)
                        ),
                        reverse=True
                    )

                    best = strict_pool[0]
                    self._cache_set(cache_key, best)

                    print(f"[OpenList RECENT CODE] hit={best.get('name')} path={best.get('path')}")

                    return best

            # 2. 再走 /api/fs/search
            candidates = self.searchOpenlistByApi(keywords, max_pages=2, per_page=100)

            if not candidates:
                print(f"[OpenList API CODE] no candidates, keywords={keywords}")
                return None

            strict_pool = [
                c for c in candidates
                if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
            ]

            if not strict_pool:
                print(f"[OpenList API CODE] no strict match, keywords={keywords}")
                return None

            strict_pool.sort(
                key=lambda x: (
                    self.scoreOpenlistCandidate(x, norm_keys),
                    int(x.get("size") or 0)
                ),
                reverse=True
            )

            best = strict_pool[0]
            self._cache_set(cache_key, best)

            print(f"[OpenList API CODE] hit={best.get('name')} path={best.get('path')}")

            return best

        except Exception as e:
            print(f"[OpenList API CODE] error: {e}")
            return None

    def searchOpenlistBestVideo(self, keywords):
        """
        OpenList 搜索线：
        使用 /api/fs/search。
        不再走本地索引。
        不再递归 /api/fs/list 扫描目录。

        保留：
        1. buildOpenlistSearchKeywords 标题提取规则
        2. extractVideoCode 番号提取规则
        3. candidateMatchCodeSuffixAllowed 匹配规则
        4. scoreOpenlistCandidate 排序规则

        优先级：
        1. 点击刷新缓存得到的 recent_files
        2. /api/fs/search
        """
        try:
            cache_hit = self.search115CacheBestVideo(keywords)
            if cache_hit:
                return cache_hit
            if not keywords:
                return None

            if isinstance(keywords, str):
                keywords = [keywords]

            keywords = [self.cleanText(x) for x in keywords if self.cleanText(x)]
            if not keywords:
                return None

            cache_key = "api_search|" + "|".join([
                self.openlistNormalizePath(self.openlist_parent)
            ] + [self.normalizeSearchText(x) for x in keywords])

            cached = self._cache_get(cache_key)
            if cached:
                return cached

            norm_keys = [self.normalizeSearchText(x) for x in keywords if x]
            code_info = self.extractVideoCode(" ".join(keywords))

            # 1. 优先匹配点击刷新得到的 recent_files
            recent = getattr(self, "_openlist_recent_files", []) or []
            if recent:
                recent_candidates = self.filterOpenlistApiCandidates(recent, keywords)

                if recent_candidates:
                    if code_info:
                        strict_pool = [
                            c for c in recent_candidates
                            if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
                        ]

                        if strict_pool:
                            strict_pool.sort(
                                key=lambda x: (
                                    self.scoreOpenlistCandidate(x, norm_keys),
                                    int(x.get("size") or 0)
                                ),
                                reverse=True
                            )

                            best = strict_pool[0]
                            self._cache_set(cache_key, best)

                            print(f"[OpenList RECENT CODE] hit={best.get('name')} path={best.get('path')}")

                            return best

                    recent_candidates.sort(
                        key=lambda x: (
                            self.scoreOpenlistCandidate(x, norm_keys),
                            int(x.get("size") or 0)
                        ),
                        reverse=True
                    )

                    best = recent_candidates[0]
                    self._cache_set(cache_key, best)

                    print(f"[OpenList RECENT] hit={best.get('name')} path={best.get('path')}")

                    return best

            # 2. 再走 /api/fs/search
            candidates = self.searchOpenlistByApi(keywords, max_pages=2, per_page=100)

            if not candidates:
                print(f"[OpenList API SEARCH] no candidates, keywords={keywords}")
                return None

            candidates = self.filterOpenlistApiCandidates(candidates, keywords)

            if not candidates:
                print(f"[OpenList API SEARCH] no filtered candidates, keywords={keywords}")
                return None

            # 有番号时，继续优先严格番号池
            if code_info:
                strict_pool = [
                    c for c in candidates
                    if self.candidateMatchCodeSuffixAllowed(c, code_info, {"", "c", "ch", "uc"})
                ]

                if strict_pool:
                    strict_pool.sort(
                        key=lambda x: (
                            self.scoreOpenlistCandidate(x, norm_keys),
                            int(x.get("size") or 0)
                        ),
                        reverse=True
                    )

                    best = strict_pool[0]
                    self._cache_set(cache_key, best)

                    print(f"[OpenList API SEARCH CODE] hit={best.get('name')} path={best.get('path')}")

                    return best

                return None

            # 无番号时，沿用原 scoreOpenlistCandidate 排序
            candidates.sort(
                key=lambda x: (
                    self.scoreOpenlistCandidate(x, norm_keys),
                    int(x.get("size") or 0)
                ),
                reverse=True
            )

            best = candidates[0]
            self._cache_set(cache_key, best)

            print(f"[OpenList API SEARCH] hit={best.get('name')} path={best.get('path')}")

            return best

        except Exception as e:
            print(f"[OpenList API SEARCH] search best error: {e}")
            return None
    def getLatestFolderLargestVideoInfo(self):
        try:
            parent = self.openlistNormalizePath(self.openlist_parent)
            if not self.isPathUnderOpenlistParent(parent):
                return None
            items = self.listOpenlistDir(parent, refresh=False)
            if not items:
                return None
            folders, parent_videos = [], []
            for item in items:
                name = item.get("name", "")
                if not name:
                    continue
                full_path = self.openlistJoinPath(parent, name)
                if not self.isPathUnderOpenlistParent(full_path):
                    continue
                if self.openlistIsDir(item):
                    folders.append(item)
                elif self.isOpenlistVideoFile(name):
                    try:
                        size = int(item.get("size") or 0)
                    except Exception:
                        size = 0
                    parent_videos.append({
                        "name": name,
                        "path": full_path,
                        "size": size,
                        "time": self.parseOpenlistTime(item),
                        "sign": item.get("sign", ""),
                    })
            candidates = []
            if folders:
                folders.sort(key=lambda x: self.parseOpenlistTime(x), reverse=True)
                budget = {"nodes": self.openlist_scan_max_nodes}
                for folder in folders[:20]:
                    folder_path = self.openlistJoinPath(parent, folder.get("name", ""))
                    videos = self.scanOpenlistVideosWithSize(folder_path, max(1, self.openlist_latest_depth), budget)
                    if videos:
                        videos.sort(key=lambda x: int(x.get("size") or 0), reverse=True)
                        best = videos[0]
                        best["folder_time"] = self.parseOpenlistTime(folder)
                        candidates.append(best)
                        break
            candidates.extend(parent_videos)
            if not candidates:
                return None
            candidates.sort(key=lambda x: (x.get("folder_time", 0), x.get("time", 0), int(x.get("size") or 0)), reverse=True)
            return candidates[0]
        except Exception:
            return None

    def openlistDecodeTitleFromId(self, _id):
        try:
            parts = str(_id or "").split("|")
            if len(parts) >= 2:
                if parts[0] == "__OPENLIST_SEARCH__" and len(parts) >= 3:
                    title_b64 = parts[2]
                else:
                    title_b64 = parts[1]
                return base64.b64decode(title_b64.encode("utf-8")).decode("utf-8")
        except Exception:
            pass
        return ""


    def openlistPlayerContent(self, _id):
        """
        OpenList 播放入口。

        保留：
        1. 刷新缓存按钮
        2. 番号播放
        3. 搜N播放

        删除/停用：
        1. 原本地索引刷新
        2. 原目录递归扫描
        3. 刷新混存
        4. 播放最新
        """
        try:
            _id = str(_id or "")

            if not self.openlist_url or not self.openlist_token:
                return self._returnAck()

            # 点击“刷新缓存”：
            # 只刷新 openlist_parent 最新3个条目到内存 recent_files
            if _id.startswith("__OPENLIST_REFRESH__"):
                title = self.openlistDecodeTitleFromId(_id)
                cnt = self.refreshOpenlistLatest3ToMemory(title)
                print(f"[OpenList REFRESH] clicked, latest videos cached={cnt}")
                return self._returnAck()

            # 兼容旧ID：不再执行任何扫描/索引
            if _id.startswith("__OPENLIST_REFRESH_MIX__"):
                try:
                    self._openlist_search_cache.clear()
                except Exception:
                    pass
                print("[OpenList REFRESH_MIX] disabled, only clear memory cache")
                return self._returnAck()

            # 兼容旧ID：不再播放最新，改为按标题搜索
            if _id.startswith("__OPENLIST_LATEST__"):
                title = self.openlistDecodeTitleFromId(_id)
                keywords = self.buildOpenlistSearchKeywords(title, 5)
                if not keywords:
                    return self._returnAck()

                info = self.searchOpenlistBestVideo(keywords)
                if not info or not info.get("path"):
                    return self._returnAck()

                play_url, headers = self.getPlayableUrlFromOpenlist(info.get("path"))

                if not play_url:
                    return self._returnAck()

                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": play_url,
                    "header": headers
                }

            # 番号专线
            if _id.startswith("__OPENLIST_CODE__"):
                parts = _id.split("|")

                if len(parts) < 2:
                    return self._returnAck()

                try:
                    code_text = base64.b64decode(parts[1].encode("utf-8")).decode("utf-8")
                except Exception:
                    code_text = ""

                if not code_text:
                    return self._returnAck()

                info = self.searchOpenlistBestVideoByCode(code_text)

                if not info or not info.get("path"):
                    return self._returnAck()

                play_url, headers = self.getPlayableUrlFromOpenlist(info.get("path"))

                if not play_url:
                    return self._returnAck()

                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": play_url,
                    "header": headers
                }

            # 搜N线路
            if _id.startswith("__OPENLIST_SEARCH__"):
                parts = _id.split("|")

                try:
                    n = int(parts[1])
                except Exception:
                    n = 5

                title = self.openlistDecodeTitleFromId(_id)
                keywords = self.buildOpenlistSearchKeywords(title, n)

                if not keywords:
                    return self._returnAck()

                info = self.searchOpenlistBestVideo(keywords)

                if not info or not info.get("path"):
                    return self._returnAck()

                play_url, headers = self.getPlayableUrlFromOpenlist(info.get("path"))

                if not play_url:
                    return self._returnAck()

                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": play_url,
                    "header": headers
                }

            return self._returnAck()

        except Exception as e:
            print(f"[OpenList] player error: {e}")
            return self._returnAck()

    # ===================== 115 离线/API 缓存与播放增强 =====================

    def _115_cache_paths(self):
        paths = []
        main = getattr(self, "cache_115_file", "") or ""
        candidates = [
            main,
            "/storage/emulated/0/Download/115api_cache/115_cache.json",
            "/sdcard/Download/115api_cache/115_cache.json",
            "/storage/emulated/0/Download/115_cache.json",
            "/sdcard/Download/115_cache.json",
            "/sdcard/115_cache.json",
            "/tmp/okys_115_offline_cache.json",
        ]
        for x in candidates:
            x = str(x or "").strip()
            if x and x not in paths:
                paths.append(x)
        return paths

    def _115_cache_load(self):
        last_error = ""
        for p in self._115_cache_paths():
            try:
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    if isinstance(d, dict):
                        if "magnets" not in d or not isinstance(d.get("magnets"), dict):
                            d["magnets"] = {}
                        if "files" not in d or not isinstance(d.get("files"), dict):
                            d["files"] = {}
                        self.cache_115_file = p
                        print(f"[115 cache] load ok: {p}")
                        return d
            except Exception as e:
                last_error = f"{p} => {repr(e)}"
                print(f"[115 cache] load error: {last_error}")
        if last_error:
            print(f"[115 cache] load all failed, last: {last_error}")
        return {"magnets": {}, "files": {}}

    def _115_cache_save(self, data):
        errors = []
        for p in self._115_cache_paths():
            try:
                dname = os.path.dirname(p)
                if dname:
                    os.makedirs(dname, exist_ok=True)

                # 先写 tmp，再替换；如果 os.replace 在某些 Android 上失败，再直接写正式文件
                tmp = p + ".tmp"
                try:
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    os.replace(tmp, p)
                except Exception as e1:
                    try:
                        with open(p, "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                    except Exception as e2:
                        raise Exception(f"tmp_write_or_replace={repr(e1)}, direct_write={repr(e2)}")

                self.cache_115_file = p
                print(f"[115 cache] write ok: {p}")
                return True
            except Exception as e:
                err = f"{p} => {repr(e)}"
                errors.append(err)
                print(f"[115 cache] save error: {err}")

        print("[115 cache] save all failed: " + " | ".join(errors))
        return False

    def _115_extract_btih(self, text):
        s = str(text or "")
        m = re.search(r"btih:([a-fA-F0-9]{40})", s, re.I)
        if m:
            return m.group(1).lower()
        m = re.search(r"btih:([A-Z2-7]{32})", s, re.I)
        if m:
            return m.group(1).lower()
        m = re.search(r"\b([a-fA-F0-9]{40})\b", s)
        if m:
            return m.group(1).lower()
        return ""

    def _115_magnet_key(self, magnet):
        h = self._115_extract_btih(magnet)
        if h:
            return h.lower()
        return hashlib.md5(str(magnet or "").encode("utf-8")).hexdigest()

    def _115_headers(self):
        return {
            "User-Agent": self.headers.get("User-Agent", "Mozilla/5.0"),
            "Cookie": self.pan_115_cookie,
            "Origin": "https://115.com",
            "Referer": "https://115.com/web/lixian/",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

    def parse115FileItem(self, item, parent_cid=""):
        try:
            name = (
                item.get("n")
                or item.get("name")
                or item.get("file_name")
                or item.get("fname")
                or ""
            )
            fid = (
                item.get("fid")
                or item.get("file_id")
                or item.get("id")
                or ""
            )
            cid = (
                item.get("cid")
                or item.get("parent_id")
                or parent_cid
                or ""
            )
            pickcode = (
                item.get("pc")
                or item.get("pick_code")
                or item.get("pickcode")
                or item.get("pickCode")
                or ""
            )
            size = int(
                item.get("s")
                or item.get("size")
                or item.get("file_size")
                or 0
            )
            sha1 = (
                item.get("sha")
                or item.get("sha1")
                or item.get("file_sha1")
                or ""
            )
            return {
                "fid": str(fid),
                "cid": str(cid),
                "name": str(name),
                "size": size,
                "pickcode": str(pickcode),
                "sha1": str(sha1),
            }
        except Exception:
            return {
                "fid": "",
                "cid": str(parent_cid or ""),
                "name": "",
                "size": 0,
                "pickcode": "",
                "sha1": "",
            }

    def is115VideoFile(self, name):
        name = str(name or "").lower()
        return name.endswith((
            ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
            ".ts", ".m2ts", ".webm", ".m3u8", ".rmvb",
            ".mpg", ".mpeg", ".3gp", ".m4v", ".vob", ".f4v"
        ))

    def choose115VideoFiles(self, files, min_size=None, parent_cid=""):
        if min_size is None:
            min_size = getattr(self, "min_115_video_size", 100 * 1024 * 1024)

        bad_words = [
            "sample", "trailer", "preview",
            "预告", "样片", "花絮", "广告"
        ]

        out = []
        seen = set()

        for item in files or []:
            info = self.parse115FileItem(item, parent_cid)
            name = info.get("name") or ""
            size = int(info.get("size") or 0)
            low = name.lower()

            if not name:
                continue
            if not self.is115VideoFile(name):
                continue
            if size < min_size:
                continue
            if any(w in low for w in bad_words):
                continue

            k = info.get("fid") or info.get("pickcode") or name
            if k in seen:
                continue
            seen.add(k)
            out.append(info)

        out.sort(key=lambda x: int(x.get("size") or 0), reverse=True)
        return out

    def _115_list_files(self, cid="0", limit=500):
        if not self.pan_115_cookie:
            return []

        headers = self._115_headers()
        url = "https://webapi.115.com/files"

        try:
            limit = max(20, min(500, int(limit)))
        except Exception:
            limit = 500

        params = {
            "cid": str(cid or "0"),
            "offset": 0,
            "limit": limit,
            "show_dir": 1,
            "format": "json"
        }

        try:
            s = Session()
            s.verify = False
            r = s.get(url, headers=headers, params=params, timeout=15)
            data = r.json()

            # ================= 🚀 海关系统 V11：全量大片收割 + 图片格式物理绞杀 =================

            if isinstance(data, dict) and isinstance(data.get("data"), list):

                try:

                    _items = data["data"]

                    _ext_kw = getattr(self, "ext", {}).get("ignore_folders", []) if isinstance(getattr(self, "ext", {}), dict) else []

                    _default_kw = ["论坛", "論壇", "文宣", "台湾uu", "聊天室", "麻豆", "草榴", "杏吧", "抖音", "快手", "91国产", "含羞草", "外围", "约炮", "体验", "app", "地址发布", "获取最新", "4096", "发布器", "网址", "pic", "图片", "广告"]

                    _ignore_kw = [str(k).lower() for k in _ext_kw + _default_kw]

                    

                    # ☠️ 跨界绞杀名单：图片、文档、压缩包、安装包

                    _kill_exts = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".txt", ".chm", ".apk", ".exe", ".zip", ".rar", ".7z", ".html", ".url", ".torrent"]

                    

                    _valid_files = []

                    _valid_folders = []

                    _has_big_video = False

                    

                    for item in _items:

                        if not isinstance(item, dict): continue

                        name = str(item.get("n") or item.get("name") or "").lower()

                        size = int(item.get("s") or item.get("size") or 0)

                        is_file = bool(item.get("fid") or item.get("file_id") or str(item.get("ico", "")))

                        

                        # 斩杀1：文件夹或文件命中垃圾关键词

                        if any(kw in name for kw in _ignore_kw): continue

                        

                        if is_file:

                            # 斩杀2：图片、安装包、文本等非视频格式直接烧毁！

                            if any(name.endswith(ext) for ext in _kill_exts): continue

                            

                            # 斩杀3：低于 50MB 的垃圾视频烧毁！

                            if size < 50 * 1024 * 1024: continue 

                            

                            # 存活下来的必定是真正的视频！

                            _valid_files.append(item)

                            if size >= 100 * 1024 * 1024:

                                _has_big_video = True # 发现了超过100M的正片！

                        else:

                            _valid_folders.append(item) # 文件夹暂存

                            

                    if _has_big_video:

                        # 🎉 发现大片！触发终极防崩溃保护：

                        # 抛弃同目录下的所有文件夹（防止脚本钻进图片文件夹崩溃）

                        # 收割所有 >=100MB 的多集视频！

                        _filtered = [x for x in _valid_files if int(x.get("s") or x.get("size") or 0) >= 100 * 1024 * 1024]

                        # 按体积从大到小排序，保证最清晰、最大的排第一集

                        _filtered.sort(key=lambda x: int(x.get("s") or x.get("size") or 0), reverse=True)

                    else:

                        # 还在外层迷宫，放行经过过滤的文件夹

                        _filtered = _valid_folders

                        

                    data["data"] = _filtered

                    if "count" in data:

                        data["count"] = len(_filtered)

                except Exception:

                    pass

            # ===================================================================
            files = data.get("data") or data.get("files") or []
            if not isinstance(files, list):
                files = []
            print(f"[115 files] cid={cid}, count={len(files)}")
            return files
        except Exception as e:
            print(f"[115 files] error: {e}")
            return []

    def _115_task_list(self, page=1):
        if not self.pan_115_cookie:
            return []

        headers = self._115_headers()
        urls = [
            "https://115.com/web/lixian/?ct=lixian&ac=task_lists",
            "https://115.com/web/lixian/?ct=lixian&ac=task_list",
        ]

        params = {
            "page": int(page or 1),
            "limit": 100
        }

        for url in urls:
            try:
                s = Session()
                s.verify = False
                r = s.get(url, headers=headers, params=params, timeout=15)
                data = r.json()

                tasks = (
                    data.get("tasks")
                    or data.get("data")
                    or data.get("list")
                    or []
                )

                if isinstance(tasks, dict):
                    tasks = tasks.get("tasks") or tasks.get("list") or []

                if isinstance(tasks, list):
                    print(f"[115 task list] count={len(tasks)}")
                    return tasks

            except Exception as e:
                print(f"[115 task list] url={url} error: {e}")

        return []

    def _115_find_task_by_hash(self, btih):
        btih = str(btih or "").lower()
        if not btih:
            return None

        tasks = self._115_task_list(1)

        for t in tasks:
            try:
                raw = json.dumps(t, ensure_ascii=False).lower()
                if btih in raw:
                    return t

                h = (
                    t.get("info_hash")
                    or t.get("hash")
                    or t.get("bt_hash")
                    or t.get("sha1")
                    or ""
                )
                if str(h).lower() == btih:
                    return t
            except Exception:
                pass

        return None

    def _115_task_done(self, task):
        if not task:
            return False

        raw = json.dumps(task, ensure_ascii=False).lower()
        done_words = ["完成", "已完成", "success", "finished", "done"]

        if any(w in raw for w in done_words):
            return True

        status = (
            task.get("status")
            or task.get("state")
            or task.get("percentDone")
            or task.get("percent")
            or task.get("progress")
        )

        try:
            if str(status).lower() in ["2", "100", "done", "success", "finished"]:
                return True
            if float(status) >= 100:
                return True
        except Exception:
            pass

        return False

    def _115_task_failed(self, task):
        if not task:
            return False
        raw = json.dumps(task, ensure_ascii=False).lower()
        bad_words = ["失败", "error", "failed", "fail"]
        if any(w in raw for w in bad_words):
            return True
        status = task.get("status") or task.get("state")
        if str(status).lower() in ["-1", "failed", "error"]:
            return True
        return False

    def _115_task_save_cid(self, task):
        if not task:
            return str(getattr(self, "pan_115_save_cid", "") or "")

        keys = [
            "cid", "save_cid", "wp_path_id", "file_id",
            "to_cid", "target_cid", "parent_id"
        ]

        for k in keys:
            v = task.get(k)
            if v:
                return str(v)

        for k in ["file", "folder", "data", "info"]:
            sub = task.get(k)
            if isinstance(sub, dict):
                for kk in keys:
                    v = sub.get(kk)
                    if v:
                        return str(v)

        return str(getattr(self, "pan_115_save_cid", "") or "")

    def _115_submit_only(self, magnet):
        """
        点击115云下载里的磁力项：
        只提交任务，不等待，不播放。
        """
        key = self._115_magnet_key(magnet)
        btih = self._115_extract_btih(magnet)

        cache = self._115_cache_load()
        rec = cache.get("magnets", {}).get(key)

        if rec:
            print(f"[115 submit] cache exists, status={rec.get('status')}")
            return rec

        task = None
        if btih:
            task = self._115_find_task_by_hash(btih)

        if task:
            status = "done" if self._115_task_done(task) else "downloading"
            rec = {
                "magnet": magnet,
                "key": key,
                "btih": btih,
                "status": status,
                "task": task,
                "cid": self._115_task_save_cid(task),
                "files": [],
                "best": None,
                "update_time": int(time.time())
            }
            cache["magnets"][key] = rec
            self._115_cache_save(cache)
            return rec

        add = self._115_add_task(magnet)

        rec = {
            "magnet": magnet,
            "key": key,
            "btih": btih,
            "status": "submitted" if add.get("state") else "add_failed",
            "task": add.get("task") or add.get("raw") or {},
            "cid": "",
            "files": [],
            "best": None,
            "update_time": int(time.time())
        }

        cache["magnets"][key] = rec
        self._115_cache_save(cache)

        return rec


    def _115_list_files_depth1_safe(self, cid="0", limit=500, max_dirs = 200, sleep_sec=0.2):
        """
        安全扫描 115 离线目录。

        扫描范围：
          当前 cid 目录：       /云下载/a/*
          当前 cid 的一层子目录：/云下载/a/b/*

        最多可以找到：
          /云下载/a/c.mp4
          /云下载/a/b/c.mp4

        不会继续扫描：
          /云下载/a/b/c/d.mp4

        目的：
          1. 避免深度递归造成大量 115 API 请求；
          2. 只在第一层没找到视频时调用；
          3. 最多扫描 max_dirs 个目录；
          4. 请求之间 sleep，降低风控风险。
        """
        all_items = []
        visited = set()
        queue = [(str(cid or "").strip(), 0)]
        scanned_dirs = 0
        max_depth = 15

        def get_pickcode(item):
            if not isinstance(item, dict):
                return ""
            return (
                item.get("pick_code")
                or item.get("pickcode")
                or item.get("pc")
                or ""
            )

        def get_name(item):
            if not isinstance(item, dict):
                return ""
            return str(
                item.get("n")
                or item.get("name")
                or item.get("file_name")
                or ""
            )

        def get_child_cid(item, current_cid):
            try:
                if not isinstance(item, dict):
                    return ""

                # 有 pickcode 一般就是文件，不当目录
                if get_pickcode(item):
                    return ""

                name = get_name(item)

                # 名字像视频文件，不当目录
                if name:
                    try:
                        if self.is115VideoFile(name):
                            return ""
                    except Exception:
                        pass

                child = (
                    item.get("cid")
                    or item.get("file_id")
                    or item.get("fid")
                    or item.get("id")
                    or ""
                )
                child = str(child or "").strip()
                current_cid = str(current_cid or "").strip()

                if not child:
                    return ""
                if child == current_cid:
                    return ""

                return child
            except Exception:
                return ""

        while queue and scanned_dirs < max_dirs:
            cur_cid, level = queue.pop(0)
            cur_cid = str(cur_cid or "").strip()

            if not cur_cid:
                continue
            if cur_cid in visited:
                continue

            visited.add(cur_cid)
            scanned_dirs += 1

            try:
                if sleep_sec and scanned_dirs > 1:
                    time.sleep(float(sleep_sec))
            except Exception:
                pass

            try:
                items = self._115_list_files(cur_cid, limit=limit)
            except Exception as e:
                print(f"[115 depth1] list error cid={cur_cid}: {e}")
                items = []

            if not isinstance(items, list):
                items = []

            print(
                f"[115 depth1] cid={cur_cid}, "
                f"level={level}, count={len(items)}, "
                f"scanned={scanned_dirs}/{max_dirs}"
            )

            # 给文件补 parent cid，避免子目录文件 cid 丢失
            fixed_items = []
            for it in items:
                if not isinstance(it, dict):
                    continue

                x = dict(it)

                if not x.get("_parent_cid"):
                    x["_parent_cid"] = cur_cid

                # 如果文件自身没有 cid，补当前目录 cid
                if not x.get("cid"):
                    x["cid"] = cur_cid

                fixed_items.append(x)

            all_items.extend(fixed_items)

            # level=0 时，只把一层子目录加入队列
            # level=1 时，不再继续进入更深目录
            if level >= max_depth:
                continue

            for it in fixed_items:
                child_cid = get_child_cid(it, cur_cid)
                if child_cid and child_cid not in visited:
                    queue.append((child_cid, level + 1))

        # 去重
        out = []
        seen = set()

        for it in all_items:
            if not isinstance(it, dict):
                continue

            k = str(
                it.get("fid")
                or it.get("file_id")
                or it.get("pick_code")
                or it.get("pickcode")
                or it.get("pc")
                or it.get("sha1")
                or it.get("cid")
                or it.get("id")
                or it.get("name")
                or it.get("n")
                or ""
            ).strip()

            if not k:
                k = str(it)

            if k in seen:
                continue

            seen.add(k)
            out.append(it)

        print(
            f"[115 depth1] total_items={len(out)}, "
            f"root={cid}, scanned_dirs={scanned_dirs}"
        )

        return out


    def _115_resolve_magnet_files(self, magnet, wait=False):
        """
        查询磁力对应115离线状态，并在完成后查询保存目录文件。
        wait=False 时只查一次，不长时间阻塞。
        """
        key = self._115_magnet_key(magnet)
        btih = self._115_extract_btih(magnet)

        cache = self._115_cache_load()
        rec = cache.get("magnets", {}).get(key)

        # 已经缓存到 files/best 时直接返回，避免重复访问 115 API
        try:
            if isinstance(rec, dict) and rec.get("status") == "done" and (rec.get("files") or rec.get("best")):
                print(f"[115 resolve] cache hit key={key}, files={len(rec.get('files') or [])}")
                return rec
        except Exception:
            pass

        task = None
        if btih:
            task = self._115_find_task_by_hash(btih)

        if not task:
            if rec and rec.get("task"):
                task = rec.get("task")
            else:
                rec = rec or {
                    "magnet": magnet,
                    "key": key,
                    "btih": btih,
                    "status": "not_found",
                    "cid": "",
                    "task": {},
                    "files": [],
                    "best": None,
                    "update_time": int(time.time())
                }
                cache["magnets"][key] = rec
                self._115_cache_save(cache)
                return rec

        done = self._115_task_done(task)
        failed = self._115_task_failed(task)

        cid = self._115_task_save_cid(task)
        files_raw = []
        video_files = []

        if done and cid:
            # 先只扫当前磁力保存目录第一层：/云下载/a/*
            files_raw = self._115_list_files(cid, limit=500)
            video_files = self.choose115VideoFiles(
                files_raw,
                self.min_115_video_size,
                parent_cid=cid
            )

            # 第一层没找到大于100M的视频时，才扫描一层子目录：
            # 最多到 /云下载/a/b/c.mp4，不继续往更深层扫描。
            if not video_files:
                files_raw_depth1 = self._115_list_files_depth1_safe(
                    cid,
                    limit=500,
                    max_dirs = 200,
                    sleep_sec=0.2
                )
                video_files = self.choose115VideoFiles(
                    files_raw_depth1,
                    self.min_115_video_size,
                    parent_cid=cid
                )

        if done and not video_files:
            inner_files = (
                task.get("files")
                or task.get("file_list")
                or task.get("filelist")
                or []
            )
            if isinstance(inner_files, list):
                video_files = self.choose115VideoFiles(
                    inner_files,
                    self.min_115_video_size,
                    parent_cid=cid
                )

        best = video_files[0] if video_files else None

        status = "done" if done else ("failed" if failed else "downloading")

        rec = {
            "magnet": magnet,
            "key": key,
            "btih": btih,
            "status": status,
            "cid": cid,
            "task": task or {},
            "files": video_files,
            "best": best,
            "update_time": int(time.time())
        }

        cache["magnets"][key] = rec

        for f in video_files:
            fid = f.get("fid") or ""
            pc = f.get("pickcode") or ""
            fk = fid or pc
            if fk:
                cache["files"][fk] = {
                    "fid": fid,
                    "pickcode": pc,
                    "cid": f.get("cid") or cid,
                    "name": f.get("name"),
                    "size": f.get("size"),
                    "sha1": f.get("sha1"),
                    "magnet_key": key,
                    "btih": btih,
                    "update_time": int(time.time())
                }

        self._115_cache_save(cache)

        print(
            f"[115 resolve] status={status}, cid={cid}, "
            f"videos={len(video_files)}, best={(best or {}).get('name')}"
        )

        return rec

    def build115CachedFilePlayItems(self, magnets):
        """
        播放列表线路：
        根据115离线缓存生成具体视频文件。
        仅列出100MB以上视频文件。
        """
        try:
            if not magnets:
                return ""

            cache = self._115_cache_load()
            items = []
            seen = set()

            for mg in magnets:
                key = self._115_magnet_key(mg)
                rec = cache.get("magnets", {}).get(key)
                if not rec:
                    continue

                files = rec.get("files") or []

                for f in files:
                    name = f.get("name") or ""
                    size = int(f.get("size") or 0)
                    fid = f.get("fid") or ""
                    pc = f.get("pickcode") or ""
                    fk = fid or pc

                    if not name or not fk:
                        continue
                    if not self.is115VideoFile(name):
                        continue
                    if size < self.min_115_video_size:
                        continue
                    if fk in seen:
                        continue

                    seen.add(fk)

                    size_gb = size / 1024 / 1024 / 1024
                    show = f"{name[:50]} [{size_gb:.2f}G]"
                    play_id = f"__115_FILE__|{fk}"

                    items.append(f"{show}${play_id}")

            return "#".join(items)

        except Exception as e:
            print(f"[115 cached list] error: {e}")
            return ""

    def _115StatusAllPlayerContent(self, _id):
        """
        115云下载线路下的“下载状态”。
        查询当前详情页全部磁力任务状态，完成则缓存100MB以上视频文件。
        """
        try:
            parts = str(_id or "").split("|", 1)
            if len(parts) < 2:
                return self._returnAck()

            try:
                magnets_json = base64.b64decode(parts[1].encode("utf-8")).decode("utf-8")
                magnets = json.loads(magnets_json)
            except Exception:
                magnets = []

            if not isinstance(magnets, list) or not magnets:
                return self._returnAck()

            best_file = None
            updated = 0

            for mg in magnets:
                mg = str(mg or "").strip()
                if not mg:
                    continue

                rec = self._115_resolve_magnet_files(mg, wait=False)

                if rec:
                    updated += 1

                best = rec.get("best") if isinstance(rec, dict) else None

                if best:
                    if not best_file:
                        best_file = best
                    else:
                        try:
                            if int(best.get("size") or 0) > int(best_file.get("size") or 0):
                                best_file = best
                        except Exception:
                            pass

            print(f"[115 status all] updated={updated}, best={(best_file or {}).get('name')}")

            if best_file:
                return self._115_play_file_info(best_file)

            return self._returnAck()

        except Exception as e:
            print(f"[115 status all] error: {e}")
            return self._returnAck()

    def _115CachedFilePlayerContent(self, _id):
        try:
            _id = str(_id or "")

            if not _id.startswith("__115_FILE__|"):
                return self._returnAck()

            fk = _id.split("|", 1)[1].strip()
            if not fk:
                return self._returnAck()

            cache = self._115_cache_load()
            f = cache.get("files", {}).get(fk)

            if not f:
                print(f"[115 file] cache miss: {fk}")
                return self._returnAck()

            return self._115_play_file_info(f)

        except Exception as e:
            print(f"[115 cached file player] error: {e}")
            return self._returnAck()

    def search115CacheBestVideo(self, keywords):
        """
        查询线路优先查115 API缓存。
        返回结构兼容OpenList：
        {
          source: "115cache",
          path: "__115CACHE__|fid_or_pickcode",
          name, size, pickcode, fid ...
        }
        """
        try:
            if not keywords:
                return None

            if isinstance(keywords, str):
                keywords = [keywords]

            keywords = [self.cleanText(x) for x in keywords if self.cleanText(x)]
            if not keywords:
                return None

            cache = self._115_cache_load()
            files_map = cache.get("files", {}) or {}

            if not files_map:
                return None

            norm_keys = [self.normalizeSearchText(k) for k in keywords if k]
            norm_keys = [x for x in norm_keys if x]

            code_info = self.extractVideoCode(" ".join(keywords))

            candidates = []

            for fk, f in files_map.items():
                name = f.get("name") or ""
                size = int(f.get("size") or 0)

                if not name:
                    continue
                if not self.is115VideoFile(name):
                    continue
                if size < self.min_115_video_size:
                    continue

                text_n = self.normalizeSearchText(
                    name + " " + str(f.get("cid") or "") + " " + str(f.get("sha1") or "")
                )

                matched = False

                if code_info:
                    temp = {
                        "name": name,
                        "path": name
                    }
                    if self.candidateMatchCodeSuffixAllowed(temp, code_info, {"", "c", "ch", "uc"}):
                        matched = True
                else:
                    if any(k and k in text_n for k in norm_keys):
                        matched = True

                if not matched:
                    continue

                item = dict(f)
                item["source"] = "115cache"
                item["path"] = "__115CACHE__|" + str(fk)
                item["_cache_key"] = str(fk)
                candidates.append(item)

            if not candidates:
                return None

            candidates.sort(
                key=lambda x: (
                    self.score115CacheCandidate(x, norm_keys),
                    int(x.get("size") or 0)
                ),
                reverse=True
            )

            best = candidates[0]
            print(f"[115 cache query] hit={best.get('name')} size={best.get('size')}")
            return best

        except Exception as e:
            print(f"[115 cache query] error: {e}")
            return None

    def score115CacheCandidate(self, f, norm_keys):
        try:
            name_n = self.normalizeSearchText(f.get("name") or "")
            score = 0

            for k in norm_keys or []:
                if k and k in name_n:
                    score += 100

            size = int(f.get("size") or 0)
            if size >= 100 * 1024 * 1024:
                score += 10
            if size >= 500 * 1024 * 1024:
                score += 20
            if size >= 1024 * 1024 * 1024:
                score += 30

            n = str(f.get("name") or "").lower()

            if n.endswith(".mp4"):
                score += 8
            elif n.endswith(".mkv"):
                score += 6
            elif n.endswith((".ts", ".m2ts")):
                score += 3

            return score

        except Exception:
            return 0

    def _json_find_video_urls(self, obj):
        urls = []

        def walk(x):
            if isinstance(x, dict):
                for k, v in x.items():
                    if isinstance(v, str):
                        sv = v.strip()
                        low = sv.lower()
                        if sv.startswith("http://") or sv.startswith("https://"):
                            if any(t in low for t in [".m3u8", ".mp4", ".ts", "download", "video"]):
                                urls.append(sv)
                    walk(v)

            elif isinstance(x, list):
                for i in x:
                    walk(i)

            elif isinstance(x, str):
                sv = x.strip()
                low = sv.lower()
                if sv.startswith("http://") or sv.startswith("https://"):
                    if any(t in low for t in [".m3u8", ".mp4", ".ts", "download", "video"]):
                        urls.append(sv)

        walk(obj)

        out = []
        seen = set()
        for u in urls:
            if u not in seen:
                seen.add(u)
                out.append(u)

        return out

    def _select_best_video_url(self, urls):
        if not urls:
            return ""

        for u in urls:
            if ".m3u8" in u.lower():
                return u

        for u in urls:
            if ".mp4" in u.lower():
                return u

        for u in urls:
            if ".ts" in u.lower():
                return u

        return urls[0]

    def _115_get_play_url_by_pickcode(self, pickcode):
        """
        115 pickcode -> 播放地址。
        说明：
        这是通用探测逻辑，不保证所有115接口版本都能返回真实播放地址。
        如果返回空，说明需要后续针对你的115接口返回做适配。
        """
        if not pickcode or not self.pan_115_cookie:
            return "", {}

        headers = {
            "User-Agent": self.headers.get("User-Agent", "Mozilla/5.0"),
            "Cookie": self.pan_115_cookie,
            "Referer": "https://115.com/",
            "Origin": "https://115.com",
            "Accept": "application/json, text/plain, */*",
        }

        candidate_requests = [
            {
                "url": "https://webapi.115.com/files/video",
                "params": {"pickcode": pickcode}
            },
            {
                "url": "https://webapi.115.com/files/video_info",
                "params": {"pickcode": pickcode}
            },
            {
                "url": "https://webapi.115.com/files/download",
                "params": {"pickcode": pickcode}
            },
            {
                "url": "https://proapi.115.com/android/2.0/ufile/download",
                "params": {"pickcode": pickcode}
            }
        ]

        try:
            s = Session()
            s.verify = False

            for req in candidate_requests:
                try:
                    url = req.get("url")
                    params = req.get("params") or {}

                    r = s.get(
                        url,
                        headers=headers,
                        params=params,
                        timeout=15
                    )

                    text = r.text or ""

                    if r.status_code != 200:
                        print(f"[115 play] {url} HTTP {r.status_code}, text={text[:120]}")
                        continue

                    try:
                        data = r.json()
                    except Exception:
                        if text.startswith("http://") or text.startswith("https://"):
                            return text.strip(), headers
                        continue

                    urls = self._json_find_video_urls(data)
                    play_url = self._select_best_video_url(urls)

                    if play_url:
                        print(f"[115 play] hit api={url}")
                        return play_url, headers

                    print(f"[115 play] no url api={url}")

                except Exception as e:
                    print(f"[115 play] candidate error: {req.get('url')} {e}")

        except Exception as e:
            print(f"[115 play] error: {e}")

        return "", headers

    def _115_play_file_info(self, file_info):
        if not file_info:
            return self._returnAck()

        pickcode = file_info.get("pickcode") or ""
        name = file_info.get("name") or ""

        if pickcode:
            play_url, headers = self._115_get_play_url_by_pickcode(pickcode)
            if play_url:
                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": play_url,
                    "header": headers
                }

        print(f"[115 play] failed name={name}, pickcode={pickcode}")
        return self._returnAck()


    def playerContent(self, flag, id, vipFlags):
        try:
            flag = str(flag or "")
            id = str(id or "")
            pic = self._get_play_pic(id)

            # 提示线路（对齐4k2为 flag=0 或 **ACK**）
            if flag == "0" or flag == "提示" or id == "__ACK__":
                ret = self._returnAck()
                if pic:
                    ret["pic"] = pic
                return ret

            # 115播放（OpenList）
            if flag in ["查询", "115播放"] or id.startswith("__OPENLIST_"):
                if self.openlist_test_stream:
                    ret = {
                        "parse": 0,
                        "playUrl": "",
                        "url": self.test_m3u8,
                        "header": {"User-Agent": self.headers.get("User-Agent", "")},
                    }
                    if pic:
                        ret["pic"] = pic
                    return ret
                ret = self.openlistPlayerContent(id)
                if pic and isinstance(ret, dict):
                    ret["pic"] = ret.get("pic") or pic
                return ret

            # 播放列表：点击115缓存文件播放
            if flag == "播放列表" or id.startswith("__115_FILE__|"):
                ret = self._115CachedFilePlayerContent(id)
                if pic and isinstance(ret, dict):
                    ret["pic"] = ret.get("pic") or pic
                return ret


            # 115云下载
            if flag == "115云下载":
                # 下载状态：查询当前详情页所有磁力任务状态，完成后缓存文件列表
                if id.startswith("__115_STATUS_ALL__|"):
                    ret = self._115StatusAllPlayerContent(id)
                    if pic and isinstance(ret, dict):
                        ret["pic"] = ret.get("pic") or pic
                    return ret

                # 原磁力项：名称不变，点击只提交任务，不等待、不播放
                try:
                    real_mag = base64.b64decode(id.encode("utf-8")).decode("utf-8")
                except Exception:
                    ret = self._returnAck()
                    if pic:
                        ret["pic"] = pic
                    return ret

                if self.confirm_115 and real_mag not in self.confirm_cache:
                    self.confirm_cache.add(real_mag)
                    ret = self._returnAck()
                    if pic:
                        ret["pic"] = pic
                    return ret

                threading.Thread(
                    target=self._115_submit_only,
                    args=(real_mag,),
                    daemon=True
                ).start()

                ret = self._returnAck()
                if pic:
                    ret["pic"] = pic
                return ret

            # 磁力 push
            if id.startswith("ma2gnet:") or id.startswith("magnet:"):
                real = id.replace("ma2gnet:", "magnet:", 1)
                ret = {"parse": 0, "playUrl": "", "url": "push://" + real}
                if pic:
                    ret["pic"] = pic
                return ret

            if id.startswith("ed2k://"):
                ret = {"parse": 0, "playUrl": "", "url": "push://" + id}
                if pic:
                    ret["pic"] = pic
                return ret

            ret = {"parse": 1, "playUrl": "", "url": id, "header": self.headers}
            if pic:
                ret["pic"] = pic
            return ret
        except Exception as e:
            print(f"[playerContent] error: {e}")
            ret = self._returnAck()
            pic = self._get_play_pic(id)
            if pic:
                ret["pic"] = pic
            return ret

    def _returnAck(self):
        ret = {
            "parse": 0,
            "playUrl": "",
            "url": self.ack_mp4,
            "header": {
                "User-Agent": self.headers.get("User-Agent", ""),
                "Referer": self.host + "/",
            },
        }
        if self.last_vod_pic:
            ret["pic"] = self.last_vod_pic
        return ret

    def _115_add_task(self, magnet):
        """
        提交115离线任务。
        返回：
        {
          state: bool,
          btih: "",
          task: {},
          raw: {}
        }
        """
        if not self.pan_115_cookie:
            return {"state": False, "msg": "missing 115 cookie"}

        headers = self._115_headers()

        try:
            s = Session()
            s.verify = False

            sign_rsp = s.get(
                "https://115.com/?ct=offline&ac=space",
                headers=headers,
                timeout=10
            ).json()

            if not sign_rsp.get("state"):
                print(f"[115] sign fail: {sign_rsp}")
                return {"state": False, "msg": "sign fail", "raw": sign_rsp}

            sign = sign_rsp.get("sign", "")
            req_time = sign_rsp.get("time", "")

            uid = ""
            m = re.search(r"UID=(\d+)", self.pan_115_cookie)
            if m:
                uid = m.group(1)

            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

            data = {
                "url": magnet,
                "uid": uid,
                "sign": sign,
                "time": req_time
            }

            if getattr(self, "pan_115_save_cid", ""):
                data["wp_path_id"] = self.pan_115_save_cid

            add_rsp = s.post(
                "https://115.com/web/lixian/?ct=lixian&ac=add_task_url",
                data=data,
                headers=headers,
                timeout=15,
            ).json()

            btih = self._115_extract_btih(magnet)
            ok = bool(add_rsp.get("state") or add_rsp.get("errcode") == 0)

            if ok:
                print(f"[115] add task success, btih={btih}")
            else:
                print(f"[115] add task fail: {add_rsp}")

            return {
                "state": ok,
                "btih": btih,
                "task": add_rsp,
                "raw": add_rsp
            }

        except Exception as e:
            print(f"[115] add task error: {e}")
            return {"state": False, "msg": str(e)}



# ===== COMMON_115_MAGNET_NAME_ONLY_PATCH_BEGIN =====
# 只修正 115云下载 下磁力项名称：
# 优先使用原磁力线路文件名，并把文件大小移动到名称最前面。
# 下载状态名称保持不变。

def _common_115_decode_possible_b64_text(_s):
    try:
        _s = str(_s or "").strip()
        if not _s:
            return ""
        # urlsafe base64
        try:
            _p = _s + "=" * (-len(_s) % 4)
            _v = base64.urlsafe_b64decode(_p.encode("utf-8")).decode("utf-8")
            if _v:
                return _v
        except Exception:
            pass
        # standard base64
        try:
            _p = _s + "=" * (-len(_s) % 4)
            _v = base64.b64decode(_p.encode("utf-8")).decode("utf-8")
            if _v:
                return _v
        except Exception:
            pass
        return _s
    except Exception:
        return ""


def _common_115_normalize_magnet_for_name(self, _v):
    try:
        _v = str(_v or "").strip()
        if not _v:
            return ""
        if _v.startswith("ma2gnet:"):
            _v = _v.replace("ma2gnet:", "magnet:", 1)
        if hasattr(self, "normalizeMagnet"):
            try:
                return self.normalizeMagnet(_v)
            except Exception:
                pass
        if hasattr(self, "_normalize_magnet"):
            try:
                return self._normalize_magnet(_v)
            except Exception:
                pass
        if _v.startswith("magnet:") and "urn:btih:" in _v:
            return _v
    except Exception:
        pass
    return ""


def _common_115_btih_for_name(self, _magnet):
    try:
        if hasattr(self, "_115_extract_btih"):
            _h = self._115_extract_btih(_magnet)
            if _h:
                return _h.lower()
    except Exception:
        pass
    try:
        _m = re.search(r"btih:([a-fA-F0-9]{40})", str(_magnet or ""), re.I)
        if _m:
            return _m.group(1).lower()
        _m = re.search(r"btih:([A-Z2-7]{32})", str(_magnet or ""), re.I)
        if _m:
            return _m.group(1).lower()
    except Exception:
        pass
    return ""


def _common_115_clean_play_name(self, _name, _limit=100):
    try:
        _name = str(_name or "")
        _name = _name.replace("#", "＃").replace("$", "＄")
        _name = re.sub(r"\s+", " ", _name).strip()
        if hasattr(self, "cleanPlayName"):
            try:
                _name = self.cleanPlayName(_name)
            except Exception:
                pass
        elif hasattr(self, "_clean_name"):
            try:
                _name = self._clean_name(_name, _limit)
            except Exception:
                pass
        return _name[:_limit]
    except Exception:
        return str(_name or "")[:_limit]


def _common_115_is_bad_original_name(_name):
    try:
        _n = re.sub(r"\s+", "", str(_name or "")).strip().lower()
        if not _n:
            return True
        bad = {
            "磁力",
            "磁力链接",
            "磁力资源",
            "链接",
            "ed2k链接",
            "下载",
            "资源",
            "magnet",
            "magnetlink",
        }
        if _n in bad:
            return True
        # 纯短 hash 或类似 hash 的名称，认为没有有效文件名
        if re.fullmatch(r"[a-f0-9]{6,40}", _n, re.I):
            return True
        if re.fullmatch(r"磁力[a-f0-9]{4,16}", _n, re.I):
            return True
        return False
    except Exception:
        return True


def _common_115_move_size_to_front(self, _name):
    """
    把大小移动到最前面：
    例如：
    影片名 1080p 2.36GB -> 2.36GB 影片名 1080p
    [2.36G] 影片名 -> 2.36G 影片名
    850MB-影片名 -> 850MB 影片名
    """
    try:
        _name = str(_name or "").strip()
        if not _name:
            return ""

        # 支持 TB/GB/MB/G/M/GiB/MiB/TiB，避免把 4K 当大小
        size_re = re.compile(
            r"(?i)(?:[\[\(（【]?\s*)"
            r"(\d+(?:\.\d+)?)\s*"
            r"(tb|tib|gb|gib|mb|mib|g|m)"
            r"(?:\s*[\]\)）】]?)"
        )

        _m = size_re.search(_name)
        if not _m:
            return self._common_115_clean_play_name(_name, 120)

        _num = _m.group(1)
        _unit = _m.group(2).upper()

        unit_map = {
            "GIB": "GB",
            "MIB": "MB",
            "TIB": "TB",
            "G": "GB",
            "M": "MB",
        }
        _unit = unit_map.get(_unit, _unit)
        _size = f"{_num}{_unit}"

        # 删除名称里所有大小标记
        _rest = size_re.sub(" ", _name)
        _rest = re.sub(r"[\[\]【】()（）]+", " ", _rest)
        _rest = re.sub(r"[-_｜|:：]+", " ", _rest)
        _rest = re.sub(r"\s+", " ", _rest).strip()

        if _rest:
            return self._common_115_clean_play_name(f"{_size} {_rest}", 120)
        return self._common_115_clean_play_name(_size, 120)
    except Exception:
        return self._common_115_clean_play_name(_name, 120)


def _common_115_magnet_name_map_from_playstr(self, _playstr):
    """
    从原磁力线路里提取：
    原名称 -> magnet

    支持：
    name$magnet:
    name$ma2gnet:
    name$base64(magnet)
    """
    _mp = {}
    try:
        for _item in str(_playstr or "").split("#"):
            if not _item:
                continue

            if "$" in _item:
                _name, _val = _item.split("$", 1)
            else:
                _name, _val = "", _item

            _name = self._common_115_clean_play_name(_name, 160)
            _val = str(_val or "").strip()

            _magnet = self._common_115_normalize_magnet_for_name(_val)

            if not _magnet:
                _decoded = _common_115_decode_possible_b64_text(_val)
                _magnet = self._common_115_normalize_magnet_for_name(_decoded)

            if not _magnet:
                continue

            _key = self._common_115_btih_for_name(_magnet) or _magnet.lower()
            if not _key:
                continue

            if _name and not _common_115_is_bad_original_name(_name):
                _mp[_key] = _name
    except Exception as e:
        print(f"[115 name map] error: {e}")
    return _mp


def _common_115_format_magnet_display_name(self, _magnet, _name_map=None):
    """
    115云下载下单个磁力的显示名：
    1. 优先使用原磁力线路名称
    2. 如果名称里有文件大小，则移动到最前面
    3. 没有有效名称时 fallback：磁力XXXXXXXX
    """
    try:
        _name_map = _name_map or {}
        _key = self._common_115_btih_for_name(_magnet) or str(_magnet or "").lower()
        _raw_name = _name_map.get(_key, "")

        if _raw_name and not _common_115_is_bad_original_name(_raw_name):
            return self._common_115_move_size_to_front(_raw_name)

        _btih = self._common_115_btih_for_name(_magnet)
        if _btih:
            return f"磁力{_btih[:8].upper()}"

        _m = str(_magnet or "")
        return f"磁力{_m[20:28]}" if len(_m) > 28 else "磁力链接"
    except Exception:
        return "磁力链接"


def _common_115_build_cloud_items_named(self, _magnets, _name_map=None):
    """
    通用构建 115云下载列表：
    下载状态 名称保持不变；
    其他磁力项用原文件名。
    """
    _items = []
    try:
        _mg_json = json.dumps(_magnets, ensure_ascii=False)
        _mg_b64 = base64.b64encode(_mg_json.encode("utf-8")).decode("utf-8")
        _items.append(f"下载状态$__115_STATUS_ALL__|{_mg_b64}")
    except Exception as e:
        print(f"[115 cloud] build status item error: {e}")

    for _mg in _magnets or []:
        try:
            _name = self._common_115_format_magnet_display_name(_mg, _name_map or {})
            # 七味/qw 原逻辑使用 urlsafe b64；其他脚本使用普通 b64也能被后续解码兼容
            _encoded = base64.urlsafe_b64encode(str(_mg).encode("utf-8")).decode("utf-8").rstrip("=")
            _items.append(f"{self._common_115_clean_play_name(_name, 120)}${_encoded}")
        except Exception as e:
            print(f"[115 cloud] named item error: {e}")

    return "#".join(_items)


# 绑定到 Spider
Spider._common_115_clean_play_name = _common_115_clean_play_name
Spider._common_115_move_size_to_front = _common_115_move_size_to_front
Spider._common_115_btih_for_name = _common_115_btih_for_name
Spider._common_115_normalize_magnet_for_name = _common_115_normalize_magnet_for_name
Spider._common_115_magnet_name_map_from_playstr = _common_115_magnet_name_map_from_playstr
Spider._common_115_format_magnet_display_name = _common_115_format_magnet_display_name
Spider._common_115_build_cloud_items_named = _common_115_build_cloud_items_named

# 兼容七味/qw 补丁里可能调用的 named builder
Spider._build_115_cloud_items_named = _common_115_build_cloud_items_named

# ===== COMMON_115_MAGNET_NAME_ONLY_PATCH_END =====

# ===== 115_ORIGINAL_CACHE_PLAY_PATCH_BEGIN =====
# 115缓存播放线路原画优先补丁
# 只影响：
#   1. 播放列表 -> __115_FILE__|xxx
#   2. 115云下载 -> 下载状态完成后播放 best_file
# 不影响：
#   1. OpenList / 查询线路
#   2. OpenList 的 /api/fs/get / /d/xxx 播放逻辑
#   3. 论坛解析、磁力推送、分类、搜索等逻辑

try:
    import json as _json_115_original_patch
    import re as _re_115_original_patch
    from requests import Session as _Session_115_original_patch
except Exception:
    _json_115_original_patch = None
    _re_115_original_patch = None
    _Session_115_original_patch = None


def _patch_115_original_is_m3u8_url(_url):
    try:
        return ".m3u8" in str(_url or "").lower()
    except Exception:
        return False


def _patch_115_original_is_http_url(_url):
    try:
        _u = str(_url or "").strip()
        return _u.startswith("http://") or _u.startswith("https://")
    except Exception:
        return False


def _patch_115_original_video_exts():
    return [
        ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv",
        ".ts", ".m2ts", ".webm", ".rmvb", ".mpg",
        ".mpeg", ".3gp", ".m4v", ".vob", ".f4v"
    ]


def _patch_115_original_extract_urls_from_json(_obj):
    """
    从 115 接口 JSON 中递归提取可能的直链。
    注意：
        这里只负责收集，不在这里决定是否原画。
    """
    _urls = []

    _important_keys = {
        "url",
        "file_url",
        "fileUrl",
        "download_url",
        "downloadUrl",
        "down_url",
        "downUrl",
        "downurl",
        "origin_url",
        "originUrl",
        "source_url",
        "sourceUrl",
        "raw_url",
        "rawUrl",
        "direct_url",
        "directUrl",
    }

    def _walk(_x, _parent_key=""):
        try:
            if isinstance(_x, dict):
                for _k, _v in _x.items():
                    _key = str(_k or "")
                    _key_low = _key.lower()

                    if isinstance(_v, str):
                        _sv = _v.strip().replace("\\/", "/")
                        if _patch_115_original_is_http_url(_sv):
                            _low = _sv.lower()

                            if (
                                _key in _important_keys
                                or "download" in _key_low
                                or "down" in _key_low
                                or "url" in _key_low
                                or ".m3u8" in _low
                                or any(_ext in _low for _ext in _patch_115_original_video_exts())
                            ):
                                _urls.append(_sv)

                    _walk(_v, _key)

            elif isinstance(_x, list):
                for _i in _x:
                    _walk(_i, _parent_key)

            elif isinstance(_x, str):
                _sv = _x.strip().replace("\\/", "/")
                if _patch_115_original_is_http_url(_sv):
                    _low = _sv.lower()
                    if (
                        ".m3u8" in _low
                        or "download" in _low
                        or "downurl" in _low
                        or any(_ext in _low for _ext in _patch_115_original_video_exts())
                    ):
                        _urls.append(_sv)

        except Exception:
            pass

    _walk(_obj)

    _out = []
    _seen = set()
    for _u in _urls:
        try:
            _u = str(_u or "").strip()
            if not _u:
                continue
            if _u in _seen:
                continue
            _seen.add(_u)
            _out.append(_u)
        except Exception:
            pass

    return _out


def _patch_115_original_select_download_url(_urls):
    """
    从候选 URL 中选择 115 原始下载直链。

    优先级：
        1. 明显下载直链，且不是 m3u8；
        2. 非 m3u8 的真实视频文件 URL；
        3. 任意非 m3u8 HTTP URL；
        4. 不主动返回 m3u8。

    返回：
        原画直链 或 ""
    """
    try:
        if not _urls:
            return ""

        _clean = []
        _seen = set()

        for _u in _urls:
            _u = str(_u or "").strip()
            if not _u:
                continue
            if not _patch_115_original_is_http_url(_u):
                continue
            if _u in _seen:
                continue
            _seen.add(_u)
            _clean.append(_u)

        if not _clean:
            return ""

        _video_exts = _patch_115_original_video_exts()

        # 1. 明显下载直链，排除 m3u8
        _direct_keywords = [
            "download",
            "downurl",
            "down_url",
            "file_url",
            "d.115.com",
            "115cdn",
            "cdnfhnfile",
            "proapi",
            "webapi",
            "oss",
            "object",
        ]

        for _u in _clean:
            _low = _u.lower()
            if ".m3u8" in _low:
                continue
            if any(_k in _low for _k in _direct_keywords):
                return _u

        # 2. 非 m3u8 的真实视频文件地址
        for _u in _clean:
            _low = _u.lower()
            if ".m3u8" in _low:
                continue
            if any(_ext in _low for _ext in _video_exts):
                return _u

        # 3. 任意非 m3u8 链接
        for _u in _clean:
            _low = _u.lower()
            if ".m3u8" not in _low:
                return _u

        # 4. 严格原画：不返回 m3u8
        return ""

    except Exception:
        return ""


def _patch_115_original_headers(self):
    """
    给 OK影视播放器使用的请求头。
    """
    try:
        _ua = self.headers.get("User-Agent", "Mozilla/5.0")
    except Exception:
        _ua = "Mozilla/5.0"

    try:
        _cookie = getattr(self, "pan_115_cookie", "") or ""
    except Exception:
        _cookie = ""

    return {
        "User-Agent": _ua,
        "Cookie": _cookie,
        "Referer": "https://115.com/",
        "Origin": "https://115.com",
        "Accept": "*/*",
    }


def _patch_115_get_original_download_url_by_pickcode(self, pickcode):
    """
    115 pickcode -> 原始下载直链。

    注意：
        这个函数只给 115缓存播放线路使用。
        不替换 self._115_get_play_url_by_pickcode，
        所以不会影响 OpenList 查询线路。
    """
    if not pickcode:
        return "", {}

    try:
        if not getattr(self, "pan_115_cookie", ""):
            print("[115 original] missing pan_115_cookie")
            return "", {}
    except Exception:
        return "", {}

    if _Session_115_original_patch is None:
        print("[115 original] requests.Session unavailable")
        return "", {}

    _headers = _patch_115_original_headers(self)

    # 下载接口优先，video/video_info 只兜底探测，但最终也不会选择 m3u8。
    _candidate_requests = [
        {
            "name": "webapi_files_download",
            "url": "https://webapi.115.com/files/download",
            "method": "GET",
            "params": {"pickcode": pickcode},
        },
        {
            "name": "proapi_android_download",
            "url": "https://proapi.115.com/android/2.0/ufile/download",
            "method": "GET",
            "params": {"pickcode": pickcode},
        },
        {
            "name": "webapi_files_video",
            "url": "https://webapi.115.com/files/video",
            "method": "GET",
            "params": {"pickcode": pickcode},
        },
        {
            "name": "webapi_files_video_info",
            "url": "https://webapi.115.com/files/video_info",
            "method": "GET",
            "params": {"pickcode": pickcode},
        },
    ]

    try:
        _s = _Session_115_original_patch()
        _s.verify = False

        for _req in _candidate_requests:
            _api = _req.get("url")
            _name = _req.get("name") or _api
            _params = _req.get("params") or {}

            try:
                _r = _s.get(
                    _api,
                    headers=_headers,
                    params=_params,
                    timeout=15,
                    allow_redirects=True,
                    verify=False,
                )

                _text = _r.text or ""

                if _r.status_code != 200:
                    print(f"[115 original] {_name} HTTP {_r.status_code}, text={_text[:180]}")
                    continue

                # 有些接口可能直接跳转到真实下载地址
                try:
                    _final_url = str(_r.url or "").strip()
                    if (
                        _patch_115_original_is_http_url(_final_url)
                        and _api not in _final_url
                        and not _patch_115_original_is_m3u8_url(_final_url)
                    ):
                        print(f"[115 original] redirect hit api={_name}")
                        return _final_url, _headers
                except Exception:
                    pass

                # 响应体本身就是 URL
                _text_strip = _text.strip()
                if _patch_115_original_is_http_url(_text_strip):
                    if not _patch_115_original_is_m3u8_url(_text_strip):
                        print(f"[115 original] text url hit api={_name}")
                        return _text_strip, _headers

                # JSON 解析
                try:
                    _data = _r.json()
                except Exception:
                    print(f"[115 original] json parse fail api={_name}, text={_text[:180]}")
                    continue

                _urls = _patch_115_original_extract_urls_from_json(_data)
                _download_url = _patch_115_original_select_download_url(_urls)

                if _download_url:
                    print(f"[115 original] hit api={_name}, url={_download_url[:180]}")
                    return _download_url, _headers

                # 打印少量结构，方便排查
                try:
                    if _json_115_original_patch:
                        print(
                            f"[115 original] no original url api={_name}, "
                            f"json={_json_115_original_patch.dumps(_data, ensure_ascii=False)[:300]}"
                        )
                    else:
                        print(f"[115 original] no original url api={_name}")
                except Exception:
                    print(f"[115 original] no original url api={_name}")

            except Exception as _e:
                print(f"[115 original] api error {_name}: {_e}")

    except Exception as _e:
        print(f"[115 original] error: {_e}")

    return "", _headers


def _patch_115_play_file_info_original_first(self, file_info):
    """
    替换 Spider._115_play_file_info。

    只影响 115缓存播放线路，因为：
        播放列表 -> _115CachedFilePlayerContent -> _115_play_file_info
        下载状态 -> _115StatusAllPlayerContent -> _115_play_file_info

    不影响 OpenList：
        OpenList 的普通文件播放走 getPlayableUrlFromOpenlist。
    """
    try:
        if not file_info:
            return self._returnAck()

        _pickcode = file_info.get("pickcode") or ""
        _name = file_info.get("name") or ""

        if not _pickcode:
            print(f"[115 original play] missing pickcode, name={_name}")
            return self._returnAck()

        _play_url, _headers = _patch_115_get_original_download_url_by_pickcode(self, _pickcode)

        if _play_url and not _patch_115_original_is_m3u8_url(_play_url):
            print(f"[115 original play] ok name={_name}, url={_play_url[:200]}")
            return {
                "parse": 0,
                "playUrl": "",
                "url": _play_url,
                "header": _headers,
            }

        # 默认严格原画：不回退 m3u8。
        # 如果你想拿不到原画时回退旧逻辑，把下面的 strict 改成 False。
        _strict_original = True

        if not _strict_original:
            try:
                _old = getattr(Spider, "_115_play_file_info_before_original_patch", None)
                if _old:
                    print(f"[115 original play] fallback old logic, name={_name}")
                    return _old(self, file_info)
            except Exception as _e:
                print(f"[115 original play] old fallback error: {_e}")

        print(f"[115 original play] no original url, name={_name}, pickcode={_pickcode}")
        return self._returnAck()

    except Exception as _e:
        print(f"[115 original play] error: {_e}")
        try:
            return self._returnAck()
        except Exception:
            return {
                "parse": 0,
                "playUrl": "",
                "url": "",
                "header": {},
            }


try:
    # 保存旧函数，便于必要时 fallback
    if not hasattr(Spider, "_115_play_file_info_before_original_patch"):
        Spider._115_play_file_info_before_original_patch = Spider._115_play_file_info

    # 只替换 115缓存播放使用的 _115_play_file_info
    Spider._115_play_file_info = _patch_115_play_file_info_original_first

    print("[115 original patch] loaded: 115缓存播放线路已设置为原画直链优先，不影响OpenList")

except Exception as _e:
    print(f"[115 original patch] load error: {_e}")

# ===== 115_ORIGINAL_CACHE_PLAY_PATCH_END =====
# ===== OPENLIST_OFFICIAL_INDEX_PRIORITY_169_PATCH_BEGIN =====
# -*- coding: utf-8 -*-
# 169BBS 查询线路修正：
# 1. 优先查 OpenList 缓存 recent_files
# 2. 再查 OpenList 官方索引 /api/fs/search
# 3. 最后才查 115 缓存
#
# 注意：
# - 不建立本地索引
# - 不写 openlist_index_file
# - 不调用 fullScanOpenlistToIndex
# - 不扫描整个 openlist_parent
# - 只在 /api/fs/search 命中目录时，最多向下展开到相对 openlist_parent 的第 4 层


def _ol169_rel_parts(self, path):
    """
    计算 path 相对 openlist_parent 的层级。
    例如：
      openlist_parent = /云下载

      /云下载/视频.mp4
        -> ["视频.mp4"]，1层

      /云下载/x/视频.mp4
        -> ["x", "视频.mp4"]，2层

      /云下载/x/文件夹/视频.mp4
        -> ["x", "文件夹", "视频.mp4"]，3层

      /云下载/a/b/c/视频.mp4
        -> ["a", "b", "c", "视频.mp4"]，4层
    """
    try:
        parent = self.openlistNormalizePath(self.openlist_parent)
        path = self.openlistNormalizePath(path)

        if parent == "/":
            rel = path.lstrip("/")
        elif path == parent:
            rel = ""
        elif path.startswith(parent.rstrip("/") + "/"):
            rel = path[len(parent.rstrip("/")) + 1:]
        else:
            rel = path.lstrip("/")

        rel = rel.strip("/")
        if not rel:
            return []

        return [x for x in rel.split("/") if x]
    except Exception:
        return []


def _ol169_depth_ok(self, path):
    """
    OpenList 官方索引结果层级限制。
    默认最多 4 层。
    """
    try:
        max_depth = int(getattr(self, "openlist_official_index_max_depth", 4) or 4)
    except Exception:
        max_depth = 15

    try:
        parts = self._ol169_rel_parts(path)
        return len(parts) <= max_depth
    except Exception:
        return False


def _ol169_collect_videos_under_dir(self, dir_path, seen=None):
    """
    /api/fs/search 命中目录后，展开该目录找视频。
    注意：
    - 只展开命中的目录
    - 不扫描整个 openlist_parent
    - 不建立本地索引
    - 最多展开到相对 openlist_parent 的第 4 层
    """
    out = []

    if seen is None:
        seen = set()

    try:
        max_depth = int(getattr(self, "openlist_official_index_max_depth", 4) or 4)
    except Exception:
        max_depth = 15

    try:
        dir_path = self.openlistNormalizePath(dir_path)

        if not self.isPathUnderOpenlistParent(dir_path):
            return out

        dir_parts = self._ol169_rel_parts(dir_path)

        # 当前目录已经到达最大层级，不能再往下展开
        if len(dir_parts) >= max_depth:
            return out

        children = self.openlistListDirOnce(
            dir_path,
            per_page=300,
            refresh=False
        )

        for child in children or []:
            try:
                name = str(child.get("name") or "").strip()
                if not name:
                    continue

                child_path = self.openlistNormalizePath(
                    child.get("path") or self.openlistJoinPath(dir_path, name)
                )

                if not self.isPathUnderOpenlistParent(child_path):
                    continue

                child_parts = self._ol169_rel_parts(child_path)

                # 超过 4 层直接忽略
                if len(child_parts) > max_depth:
                    continue

                is_dir = bool(child.get("is_dir")) or self.openlistIsDir(child)

                if is_dir:
                    # 目录未到最大层级，继续展开
                    if len(child_parts) < max_depth:
                        out.extend(
                            self._ol169_collect_videos_under_dir(
                                child_path,
                                seen
                            )
                        )
                    continue

                if not self.isOpenlistVideoFile(name):
                    continue

                if child_path in seen:
                    continue

                seen.add(child_path)

                try:
                    size = int(child.get("size") or 0)
                except Exception:
                    size = 0

                out.append({
                    "name": name,
                    "path": child_path,
                    "size": size,
                    "time": self.parseOpenlistTime(child),
                    "sign": child.get("sign", ""),
                    "parent": dir_path,
                    "is_dir": False,
                    "source": "openlist_official_index_dir_expand",
                })

            except Exception as e:
                print("[OpenList official index dir child] error:", e)

    except Exception as e:
        print("[OpenList official index dir expand] error:", e)

    return out


def _ol169_openlistApiSearchFiles(self, keyword, page=1, per_page=100):
    """
    覆盖原 openlistApiSearchFiles。

    使用 OpenList 官方索引：
      /api/fs/search

    规则：
      1. 搜到视频文件：直接加入候选
      2. 搜到目录：展开该命中目录，最多到相对 openlist_parent 的第 4 层
      3. 不建立本地索引
      4. 不写 openlist_index_file
      5. 不扫描整个 openlist_parent
    """
    results = []

    if not self.openlist_url:
        return results

    keyword = self.cleanText(keyword or "")
    if not keyword:
        return results

    try:
        page = max(1, int(page))
    except Exception:
        page = 1

    try:
        per_page = max(20, min(200, int(per_page)))
    except Exception:
        per_page = 100

    payload = {
        "parent": self.openlistNormalizePath(self.openlist_parent),
        "keywords": keyword,
        "scope": 0,
        "page": page,
        "per_page": per_page,
        "password": ""
    }

    data = self.openlistApiPost("/api/fs/search", payload, 20)

    if data.get("code") != 200:
        return results

    d = data.get("data", {}) or {}
    content = d.get("content") or []

    seen = set()

    for item in content:
        try:
            name = str(item.get("name") or "").strip()
            if not name:
                continue

            parent = str(item.get("parent") or "").strip()
            path = str(item.get("path") or "").strip()

            if path:
                full_path = self.openlistNormalizePath(path)
            else:
                full_path = self.openlistJoinPath(parent, name)

            if not self.isPathUnderOpenlistParent(full_path):
                continue

            # 搜索结果自身超过 4 层，忽略
            if not self._ol169_depth_ok(full_path):
                continue

            is_dir = bool(item.get("is_dir")) or self.openlistIsDir(item)

            # 搜索命中目录：展开这个目录，最多到 4 层
            if is_dir:
                expanded = self._ol169_collect_videos_under_dir(
                    full_path,
                    seen
                )
                results.extend(expanded)
                continue

            # 搜索命中文件：只保留视频文件
            if not self.isOpenlistVideoFile(name):
                continue

            if full_path in seen:
                continue

            seen.add(full_path)

            try:
                size = int(item.get("size") or 0)
            except Exception:
                size = 0

            results.append({
                "name": name,
                "path": full_path,
                "size": size,
                "time": self.parseOpenlistTime(item),
                "sign": item.get("sign", ""),
                "parent": parent,
                "is_dir": False,
                "source": "openlist_official_index",
            })

        except Exception as e:
            print("[OpenList official index item] error:", e)

    print(
        "[OpenList official index search] keyword=%s page=%s count=%s"
        % (keyword, page, len(results))
    )

    return results


def _ol169_searchOpenlistBestVideo(self, keywords):
    """
    覆盖原 searchOpenlistBestVideo。

    新优先级：
      1. OpenList 缓存 recent_files
      2. OpenList 官方索引 /api/fs/search
      3. 115 缓存
    """
    try:
        if not keywords:
            return None

        if isinstance(keywords, str):
            keywords = [keywords]

        keywords = [self.cleanText(x) for x in keywords if self.cleanText(x)]
        if not keywords:
            return None

        cache_key = "ol169_priority_search|" + "|".join([
            self.openlistNormalizePath(self.openlist_parent)
        ] + [self.normalizeSearchText(x) for x in keywords])

        cached = self._cache_get(cache_key)
        if cached:
            return cached

        norm_keys = [self.normalizeSearchText(x) for x in keywords if x]
        norm_keys = [x for x in norm_keys if x]

        code_info = self.extractVideoCode(" ".join(keywords))

        # ==================================================
        # 1. 优先查 OpenList 缓存 recent_files
        # ==================================================
        recent = getattr(self, "_openlist_recent_files", []) or []

        if recent:
            recent_candidates = self.filterOpenlistApiCandidates(
                recent,
                keywords
            )

            recent_candidates = [
                c for c in recent_candidates
                if self._ol169_depth_ok(c.get("path") or "")
            ]

            if recent_candidates:
                if code_info:
                    strict_pool = [
                        c for c in recent_candidates
                        if self.candidateMatchCodeSuffixAllowed(
                            c,
                            code_info,
                            {"", "c", "ch", "uc"}
                        )
                    ]

                    if strict_pool:
                        strict_pool.sort(
                            key=lambda x: (
                                self.scoreOpenlistCandidate(x, norm_keys),
                                int(x.get("size") or 0)
                            ),
                            reverse=True
                        )

                        best = strict_pool[0]
                        self._cache_set(cache_key, best)

                        print(
                            "[OpenList recent first code] hit=%s path=%s"
                            % (best.get("name"), best.get("path"))
                        )

                        return best

                recent_candidates.sort(
                    key=lambda x: (
                        self.scoreOpenlistCandidate(x, norm_keys),
                        int(x.get("size") or 0)
                    ),
                    reverse=True
                )

                best = recent_candidates[0]
                self._cache_set(cache_key, best)

                print(
                    "[OpenList recent first] hit=%s path=%s"
                    % (best.get("name"), best.get("path"))
                )

                return best

        # ==================================================
        # 2. 再查 OpenList 官方索引 /api/fs/search
        # ==================================================
        candidates = self.searchOpenlistByApi(
            keywords,
            max_pages=2,
            per_page=100
        )

        if candidates:
            candidates = [
                c for c in candidates
                if self._ol169_depth_ok(c.get("path") or "")
            ]

            candidates = self.filterOpenlistApiCandidates(
                candidates,
                keywords
            )

            if candidates:
                if code_info:
                    strict_pool = [
                        c for c in candidates
                        if self.candidateMatchCodeSuffixAllowed(
                            c,
                            code_info,
                            {"", "c", "ch", "uc"}
                        )
                    ]

                    if strict_pool:
                        strict_pool.sort(
                            key=lambda x: (
                                self.scoreOpenlistCandidate(x, norm_keys),
                                int(x.get("size") or 0)
                            ),
                            reverse=True
                        )

                        best = strict_pool[0]
                        self._cache_set(cache_key, best)

                        print(
                            "[OpenList official index code] hit=%s path=%s"
                            % (best.get("name"), best.get("path"))
                        )

                        return best

                    print(
                        "[OpenList official index code] no strict match, keywords=%s"
                        % keywords
                    )

                else:
                    candidates.sort(
                        key=lambda x: (
                            self.scoreOpenlistCandidate(x, norm_keys),
                            int(x.get("size") or 0)
                        ),
                        reverse=True
                    )

                    best = candidates[0]
                    self._cache_set(cache_key, best)

                    print(
                        "[OpenList official index] hit=%s path=%s"
                        % (best.get("name"), best.get("path"))
                    )

                    return best

        # ==================================================
        # 3. 最后才查 115 缓存
        # ==================================================
        cache_hit_115 = self.search115CacheBestVideo(keywords)

        if cache_hit_115:
            self._cache_set(cache_key, cache_hit_115)

            print(
                "[115 cache last] hit=%s size=%s"
                % (cache_hit_115.get("name"), cache_hit_115.get("size"))
            )

            return cache_hit_115

        print("[OpenList priority] no hit, keywords=%s" % keywords)
        return None

    except Exception as e:
        print("[OpenList priority] searchOpenlistBestVideo error:", e)
        return None


def _ol169_searchOpenlistBestVideoByCode(self, code_text):
    """
    覆盖原 searchOpenlistBestVideoByCode。

    新优先级：
      1. OpenList 缓存 recent_files
      2. OpenList 官方索引 /api/fs/search
      3. 115 缓存
    """
    try:
        code_info = self.extractVideoCode(code_text or "")
        if not code_info:
            return None

        keywords = [
            code_info.get("dash", ""),
            code_info.get("nodash", ""),
        ]

        keywords = [x for x in keywords if x]
        if not keywords:
            return None

        cache_key = "ol169_priority_code|" + "|".join([
            self.openlistNormalizePath(self.openlist_parent)
        ] + [self.normalizeSearchText(x) for x in keywords])

        cached = self._cache_get(cache_key)
        if cached:
            return cached

        norm_keys = [self.normalizeSearchText(x) for x in keywords if x]

        # ==================================================
        # 1. 优先查 OpenList 缓存 recent_files
        # ==================================================
        recent = getattr(self, "_openlist_recent_files", []) or []

        if recent:
            strict_pool = []

            for c in recent:
                try:
                    path = c.get("path") or ""
                    if not self._ol169_depth_ok(path):
                        continue

                    if self.candidateMatchCodeSuffixAllowed(
                        c,
                        code_info,
                        {"", "c", "ch", "uc"}
                    ):
                        strict_pool.append(c)
                except Exception:
                    pass

            if strict_pool:
                strict_pool.sort(
                    key=lambda x: (
                        self.scoreOpenlistCandidate(x, norm_keys),
                        int(x.get("size") or 0)
                    ),
                    reverse=True
                )

                best = strict_pool[0]
                self._cache_set(cache_key, best)

                print(
                    "[OpenList recent first code] hit=%s path=%s"
                    % (best.get("name"), best.get("path"))
                )

                return best

        # ==================================================
        # 2. 再查 OpenList 官方索引 /api/fs/search
        # ==================================================
        candidates = self.searchOpenlistByApi(
            keywords,
            max_pages=2,
            per_page=100
        )

        if candidates:
            candidates = [
                c for c in candidates
                if self._ol169_depth_ok(c.get("path") or "")
            ]

            strict_pool = [
                c for c in candidates
                if self.candidateMatchCodeSuffixAllowed(
                    c,
                    code_info,
                    {"", "c", "ch", "uc"}
                )
            ]

            if strict_pool:
                strict_pool.sort(
                    key=lambda x: (
                        self.scoreOpenlistCandidate(x, norm_keys),
                        int(x.get("size") or 0)
                    ),
                    reverse=True
                )

                best = strict_pool[0]
                self._cache_set(cache_key, best)

                print(
                    "[OpenList official index code] hit=%s path=%s"
                    % (best.get("name"), best.get("path"))
                )

                return best

            print(
                "[OpenList official index code] no strict match, keywords=%s"
                % keywords
            )

        # ==================================================
        # 3. 最后才查 115 缓存
        # ==================================================
        cache_hit_115 = self.search115CacheBestVideo(keywords)

        if cache_hit_115:
            self._cache_set(cache_key, cache_hit_115)

            print(
                "[115 cache last code] hit=%s size=%s"
                % (cache_hit_115.get("name"), cache_hit_115.get("size"))
            )

            return cache_hit_115

        print("[OpenList priority code] no hit, keywords=%s" % keywords)
        return None

    except Exception as e:
        print("[OpenList priority code] error:", e)
        return None


# 绑定辅助方法
Spider._ol169_rel_parts = _ol169_rel_parts
Spider._ol169_depth_ok = _ol169_depth_ok
Spider._ol169_collect_videos_under_dir = _ol169_collect_videos_under_dir

# 覆盖 OpenList 官方索引搜索方法
Spider.openlistApiSearchFiles = _ol169_openlistApiSearchFiles

# 覆盖查询线路优先级
Spider.searchOpenlistBestVideo = _ol169_searchOpenlistBestVideo
Spider.searchOpenlistBestVideoByCode = _ol169_searchOpenlistBestVideoByCode

print("[OPENLIST OFFICIAL INDEX PRIORITY 169 PATCH] priority: recent -> /api/fs/search -> 115cache")
# ===== OPENLIST_OFFICIAL_INDEX_PRIORITY_169_PATCH_END =====
# ===== FINAL_JAVBUS_OPENLIST_SCORE_PATCH_BEGIN =====
# -*- coding: utf-8 -*-

# ============================================================
# 最终评分规则：
#
# 1. .iso 识别为视频文件
# 2. 同番号命中最高优先，非同番号不能抢同番号
# 3. 同番号且文件 >= 10GB：
#       文件大小最高优先级，谁大选谁
# 4. 同番号且文件 < 10GB：
#       分辨率 > UC/CH/C > 文件大小 > 格式
# 5. UC / CH / C 优先于纯番号
# 6. iso / mp4 / mkv 格式评分相同
# ============================================================

JBF_BIG_FILE_THRESHOLD = 10 * 1024 * 1024 * 1024  # 10GB


# ============================================================
# 让 ISO 也被识别为视频文件
# ============================================================

def _jbf_is_video(self, name):
    try:
        n = str(name or "").lower()
        return n.endswith((
            ".mp4",
            ".mkv",
            ".iso",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
            ".rmvb",
            ".ts",
            ".m2ts",
        ))
    except Exception:
        return False


# ============================================================
# 分辨率评分
# ============================================================

def _jbf_resolution_score_threshold(all_l):
    """
    分辨率辅助分。
    注意：这里只看文件名 + 路径文字，不读取真实视频分辨率。
    """
    try:
        all_l = str(all_l or "").lower()

        if any(x in all_l for x in [
            "4k",
            "4 k",
            "2160p",
            "2160",
            "uhd",
            "ultra hd",
            "ultrahd",
        ]):
            return 50000

        if any(x in all_l for x in [
            "2k",
            "1440p",
            "1440",
        ]):
            return 20000

        if any(x in all_l for x in [
            "1080p",
            "1080",
            "fhd",
            "fullhd",
        ]):
            return 10000

        if any(x in all_l for x in [
            "720p",
            "720",
        ]):
            return 3000

        return 0

    except Exception:
        return 0


# ============================================================
# UC / CH / C 版本评分
# ============================================================

def _jbf_detect_code_variant_priority_threshold(self, c, keywords):
    """
    同番号变体辅助分：

      UC 版：+3000
      CH 版：+2500
      C 版 ：+2000
      纯番号：+0

    支持识别：

      SONE-168UC
      SONE-168-UC
      SONE_168_UC
      SONE.168.UC

      SONE-168CH
      SONE-168-CH

      SONE-168C
      SONE-168-C
      SONE168C
    """
    try:
        name = str(c.get("name", "") or "")
        path = str(c.get("path", "") or "")
        text = (name + " " + path).lower()

        code_info = _jbf_extract_code(self, " ".join(keywords or []))
        if not code_info:
            return 0

        prefix = str(code_info.get("prefix", "") or "").lower()
        num = str(code_info.get("num", "") or "").lower()

        if not prefix or not num:
            return 0

        # 压缩文本，去掉符号：
        # SONE-168-UC -> sone168uc
        # SONE_168_C  -> sone168c
        compact = _jbf_re.sub(r"[^0-9a-zA-Z]+", "", text).lower()
        base = prefix + num

        if base + "uc" in compact:
            return 3000

        if base + "ch" in compact:
            return 2500

        if base + "c" in compact:
            return 2000

        return 0

    except Exception:
        return 0


# ============================================================
# 视频格式评分
# ============================================================

def _jbf_format_score_threshold(name_l):
    """
    格式辅助分：

      mp4 / mkv / iso = +3
      ts / m2ts       = +2
      其他视频格式     = +1
    """
    try:
        name_l = str(name_l or "").lower()

        if name_l.endswith((".mp4", ".mkv", ".iso")):
            return 3

        if name_l.endswith((".ts", ".m2ts")):
            return 2

        if name_l.endswith((
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".rmvb",
            ".m4v",
        )):
            return 1

        return 0

    except Exception:
        return 0


# ============================================================
# 最终候选评分函数
# ============================================================

def _jbf_score_candidate(self, c, keywords):
    try:
        name = str(c.get("name", "") or "")
        path = str(c.get("path", "") or "")
        size = int(c.get("size") or 0)

        name_l = name.lower()
        path_l = path.lower()
        all_l = name_l + " " + path_l

        score = 0

        # ========================================================
        # 判断是否同番号命中
        # ========================================================
        code_hit = False

        try:
            code_info = _jbf_extract_code(self, " ".join(keywords or []))
            if code_info and _jbf_candidate_match_code(self, c, code_info):
                code_hit = True
        except Exception:
            code_hit = False

        # ========================================================
        # 情况一：同番号命中
        # ========================================================
        if code_hit:
            # 同番号基础超大分，确保非同番号无法抢
            score += 10 ** 30

            # ====================================================
            # A. 同番号 且 >= 10GB
            # 文件大小最高优先级
            # ====================================================
            if size >= JBF_BIG_FILE_THRESHOLD:
                # 大文件区基础分
                # 保证 >=10GB 的同番号文件优先于 <10GB 的同番号文件
                score += 10 ** 25

                # 文件大小绝对优先
                # 乘 1000000，确保哪怕只大 1 byte，
                # 也能压过分辨率、UC/C、格式等辅助分
                score += size * 1000000

                minor = 0

                # 大文件区里这些只是辅助分
                minor += _jbf_resolution_score_threshold(all_l)
                minor += _jbf_detect_code_variant_priority_threshold(self, c, keywords)
                minor += _jbf_format_score_threshold(name_l)

                score += minor

                print("[JavBus Final Score] BIG code_hit=%s score=%s size=%s minor=%s name=%s path=%s" % (
                    code_hit,
                    score,
                    size,
                    minor,
                    name,
                    path,
                ))

                return score

            # ====================================================
            # B. 同番号 但 < 10GB
            # 使用之前评分规则：
            # 分辨率 > UC/CH/C > 文件大小 > 格式
            # ====================================================
            else:
                # 小文件区基础分
                score += 10 ** 20

                # 关键词命中基础分
                try:
                    name_n = _jbf_norm_text(self, name)
                    path_n = _jbf_norm_text(self, path)

                    for k in keywords or []:
                        nk = _jbf_norm_text(self, k)
                        if not nk:
                            continue

                        if nk in name_n:
                            score += 100
                        elif nk in path_n:
                            score += 50
                except Exception:
                    pass

                # 分辨率优先
                resolution_score = _jbf_resolution_score_threshold(all_l)
                score += resolution_score

                # UC / CH / C 优先
                variant_score = _jbf_detect_code_variant_priority_threshold(self, c, keywords)
                score += variant_score

                # 文件大小辅助：
                # 每 100MB +1 分，上限 5000
                size_score = 0
                try:
                    size_score = size // (100 * 1024 * 1024)
                    if size_score > 5000:
                        size_score = 5000
                    score += int(size_score)
                except Exception:
                    size_score = 0

                # 格式辅助分
                format_score = _jbf_format_score_threshold(name_l)
                score += format_score

                print("[JavBus Final Score] SMALL code_hit=%s score=%s size=%s resolution=%s variant=%s size_score=%s format=%s name=%s path=%s" % (
                    code_hit,
                    score,
                    size,
                    resolution_score,
                    variant_score,
                    size_score,
                    format_score,
                    name,
                    path,
                ))

                return score

        # ========================================================
        # 情况二：非同番号
        # 只能普通关键词匹配，不能抢同番号
        # ========================================================
        else:
            try:
                name_n = _jbf_norm_text(self, name)
                path_n = _jbf_norm_text(self, path)

                for k in keywords or []:
                    nk = _jbf_norm_text(self, k)
                    if not nk:
                        continue

                    if nk in name_n:
                        score += 10000
                    elif nk in path_n:
                        score += 5000

            except Exception:
                pass

            # 非同番号也给一点大小分
            # 但这个分数远远低于同番号基础分
            score += size

            print("[JavBus Final Score] NONCODE code_hit=%s score=%s size=%s name=%s path=%s" % (
                code_hit,
                score,
                size,
                name,
                path,
            ))

            return score

    except Exception as e:
        print("[JavBus Final Score] error:", e)
        return 0


print("[FINAL JAVBUS OPENLIST SCORE PATCH] loaded")
# ===== FINAL_JAVBUS_OPENLIST_SCORE_PATCH_END =====


# ===== FINAL_169BBS_SITE_IMAGE_PROXY_ONLY_BEGIN =====
# -*- coding: utf-8 -*-
# ============================================================
# 169BBS 最终代理规则：
#
# 走代理：
#   169BBS 主页 / 分类 / 列表 / 搜索 / 详情 / 帖子页 /
#   站内附件解析 / 种子附件解析 / 封面图 / 详情页图片
#
# 不走代理：
#   115云下载 / 115任务查询 / 115文件查询 / 115播放地址获取 /
#   OpenList查询 / OpenList播放 / 磁力push / 最终播放链接
#
# 代理端口：
#   http://127.0.0.1:10172
#
# 配置 JSON 里不要再写：
#   "proxy": "proxy"
# ============================================================

import json as _b169_json
from urllib.parse import quote as _b169_quote
from urllib.parse import unquote as _b169_unquote
from urllib.parse import urljoin as _b169_urljoin
from urllib.parse import urlparse as _b169_urlparse
from urllib.parse import parse_qs as _b169_parse_qs

try:
    from requests import Session as _b169_Session
except Exception:
    _b169_Session = None


# 保存旧方法
try:
    Spider._b169_old_init = Spider.init
except Exception:
    Spider._b169_old_init = None

try:
    Spider._b169_old_getHtml = Spider.getHtml
except Exception:
    Spider._b169_old_getHtml = None

try:
    Spider._b169_old_getImgSrc = Spider.getImgSrc
except Exception:
    Spider._b169_old_getImgSrc = None

try:
    Spider._b169_old_getThreadListPic = Spider.getThreadListPic
except Exception:
    Spider._b169_old_getThreadListPic = None

try:
    Spider._b169_old_localProxy = Spider.localProxy
except Exception:
    Spider._b169_old_localProxy = None


def _b169_default_proxy():
    return "http://127.0.0.1:10172"


def _b169_get_site_proxy(self):
    """
    只给 169BBS 页面、附件、图片使用的代理。
    """
    try:
        p = (
            getattr(self, "site_proxy", "")
            or getattr(self, "bbs_proxy", "")
            or getattr(self, "proxy_url", "")
            or ""
        )
        p = str(p or "").strip()
        if p:
            return p
    except Exception:
        pass
    return _b169_default_proxy()


def _b169_proxies(self):
    p = _b169_get_site_proxy(self)
    if not p:
        return None
    return {
        "http": p,
        "https": p,
    }


def _b169_clean_url(self, url):
    try:
        url = str(url or "").strip().replace("&amp;", "&")
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http://") or url.startswith("https://"):
            return url
        host = getattr(self, "host", "https://169bbs.com").rstrip("/")
        return _b169_urljoin(host + "/", url.lstrip("/"))
    except Exception:
        return str(url or "")


def _b169_is_local_proxy_url(url):
    try:
        u = str(url or "")
        return (
            "/proxy?" in u
            and "url=" in u
            and (
                "127.0.0.1" in u
                or "localhost" in u
                or ":9978" in u
            )
        )
    except Exception:
        return False


def _b169_unwrap_proxy_url(url):
    """
    防止图片代理套娃。
    """
    try:
        url = str(url or "").strip()
        if not url:
            return ""
        for _ in range(10):
            url = _b169_unquote(url)
            if not _b169_is_local_proxy_url(url):
                break
            up = _b169_urlparse(url)
            qs = _b169_parse_qs(up.query)
            inner = ""
            if "url" in qs and qs["url"]:
                inner = qs["url"][0]
            if not inner:
                break
            inner = _b169_unquote(inner)
            if inner == url:
                break
            url = inner
        return url
    except Exception:
        return str(url or "")


def _b169_is_img(url):
    try:
        u = str(url or "").lower()
        if u.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")):
            return True
        if "img" in u and any(x in u for x in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
            return True
        if "image" in u and any(x in u for x in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
            return True
        if "attachment" in u and any(x in u for x in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
            return True
        return False
    except Exception:
        return False


def _b169_guess_ctype(url, content=None, rsp=None):
    try:
        if rsp is not None:
            ctype = rsp.headers.get("Content-Type") or ""
            if ctype and "text/html" not in ctype.lower():
                return ctype

        if content:
            if content[:3] == b"\xff\xd8\xff":
                return "image/jpeg"
            if content[:8] == b"\x89PNG\r\n\x1a\n":
                return "image/png"
            if content[:4] == b"RIFF" and b"WEBP" in content[:20]:
                return "image/webp"
            if content[:6] in [b"GIF87a", b"GIF89a"]:
                return "image/gif"

        low = str(url or "").lower()
        if low.endswith(".png"):
            return "image/png"
        if low.endswith(".webp"):
            return "image/webp"
        if low.endswith(".gif"):
            return "image/gif"
        if low.endswith(".avif"):
            return "image/avif"
        return "image/jpeg"
    except Exception:
        return "image/jpeg"


def _b169_get_param(params, key):
    try:
        if not isinstance(params, dict):
            return ""
        v = params.get(key, "")
        if isinstance(v, list):
            return v[0] if v else ""
        return v
    except Exception:
        return ""


def _b169_site_headers(self, accept_image=False):
    try:
        ua = ""
        try:
            ua = getattr(self, "headers", {}).get("User-Agent", "")
        except Exception:
            ua = ""

        if not ua:
            ua = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )

        host = getattr(self, "host", "https://169bbs.com").rstrip("/")

        if accept_image:
            accept = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        else:
            accept = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"

        headers = {
            "User-Agent": ua,
            "Accept": accept,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": host + "/",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        ck = ""
        try:
            ck = getattr(self, "site_cookie", "") or getattr(self, "headers", {}).get("Cookie", "")
        except Exception:
            ck = ""

        if ck:
            headers["Cookie"] = ck

        return headers
    except Exception:
        return {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://169bbs.com/",
        }


def _b169_to_img_proxy(self, url):
    """
    把图片地址转成本地图片代理地址。
    图片实际下载在 localProxy 里走 10172。
    """
    try:
        url = _b169_unwrap_proxy_url(url)
        url = _b169_clean_url(self, url)

        if not url:
            return ""

        if not _b169_is_img(url):
            return url

        # 默认开启图片代理
        if not getattr(self, "use_img_proxy", True):
            return url

        try:
            if hasattr(self, "getProxyUrl"):
                proxy = self.getProxyUrl()
                if proxy:
                    sep = "&" if "?" in proxy else "?"
                    return proxy + sep + "type=img&url=" + _b169_quote(url, safe="")
        except Exception as e:
            print("[169BBS FINAL PROXY img getProxyUrl] error:", e)

        return url
    except Exception as e:
        print("[169BBS FINAL PROXY to_img_proxy] error:", e)
        return str(url or "")


def _b169_init(self, extend=""):
    """
    最终 init：
    1. 先执行原 init，保留你原来的 115/OpenList 配置；
    2. 再设置 169BBS 页面/图片代理；
    3. 115/OpenList 仍保持直连。
    """
    if getattr(Spider, "_b169_old_init", None):
        Spider._b169_old_init(self, extend)

    # 默认 PG 内置代理
    self.proxy_url = getattr(self, "proxy_url", "") or _b169_default_proxy()
    self.site_proxy = getattr(self, "site_proxy", "") or self.proxy_url
    self.bbs_proxy = getattr(self, "bbs_proxy", "") or self.site_proxy

    # 图片需要走代理
    self.use_img_proxy = True

    # 支持 ext 覆盖：
    # {
    #   "site_proxy": "http://127.0.0.1:10172",
    #   "bbs_proxy": "http://127.0.0.1:10172",
    #   "proxy_url": "http://127.0.0.1:10172"
    # }
    try:
        if extend:
            ext = _b169_json.loads(extend)
            if isinstance(ext, dict):
                p = str(
                    ext.get("site_proxy", "")
                    or ext.get("bbs_proxy", "")
                    or ext.get("proxy_url", "")
                    or ""
                ).strip()
                if p:
                    self.proxy_url = p
                    self.site_proxy = p
                    self.bbs_proxy = p

                if str(ext.get("image_proxy", "true")).lower() in ["0", "false", "no"]:
                    self.use_img_proxy = False
                else:
                    self.use_img_proxy = True
    except Exception as e:
        print("[169BBS FINAL PROXY init ext] error:", e)

    # 169BBS 站点 session 走代理
    try:
        if hasattr(self, "session") and self.session:
            self.session.trust_env = False
            self.session.verify = False
            self.session.headers.update(_b169_site_headers(self, False))
            self.session.proxies.clear()
            self.session.proxies.update(_b169_proxies(self) or {})
    except Exception as e:
        print("[169BBS FINAL PROXY session setup] error:", e)

    # OpenList session 明确直连，不使用代理
    try:
        if hasattr(self, "openlist_session") and self.openlist_session:
            self.openlist_session.trust_env = False
            self.openlist_session.proxies.clear()
    except Exception:
        pass

    print("[169BBS FINAL PROXY] site/page/attachment/image proxy=%s image_proxy=%s" % (
        _b169_get_site_proxy(self),
        bool(getattr(self, "use_img_proxy", True)),
    ))
    print("[169BBS FINAL PROXY] 115/OpenList/query/play keep direct")


def _b169_getHtml(self, url):
    """
    169BBS 页面请求统一走代理。

    影响：
      主页 / 分类 / 列表 / 搜索 / 详情 / 帖子页

    不影响：
      115 / OpenList / 播放地址
    """
    url = _b169_clean_url(self, url)

    if not url:
        return ""

    try:
        sess = getattr(self, "session", None)

        if sess is None and _b169_Session:
            sess = _b169_Session()
            sess.verify = False
            sess.trust_env = False
            sess.headers.update(_b169_site_headers(self, False))
            sess.proxies.update(_b169_proxies(self) or {})
            self.session = sess

        if sess is None:
            old = getattr(Spider, "_b169_old_getHtml", None)
            if old:
                return old(self, url)
            return ""

        rsp = sess.get(
            url,
            headers=_b169_site_headers(self, False),
            timeout=30,
            allow_redirects=True,
            verify=False,
            proxies=_b169_proxies(self),
        )

        if rsp.encoding and rsp.encoding.lower() in ["iso-8859-1", "ascii"]:
            rsp.encoding = rsp.apparent_encoding or "utf-8"
        elif not rsp.encoding:
            rsp.encoding = rsp.apparent_encoding or "utf-8"

        text = rsp.text or ""

        print("[169BBS FINAL PROXY GET] %s => %s final=%s len=%s proxy=%s" % (
            url,
            rsp.status_code,
            rsp.url,
            len(text),
            _b169_get_site_proxy(self),
        ))

        if any(k in text for k in [
            "请先登录",
            "您需要登录",
            "登录后",
            "會員登錄",
            "会员登录",
            "验证码",
            "安全验证",
            "访问受限",
            "抱歉",
            "您无权进行当前操作",
        ]):
            print("[169BBS FINAL PROXY WARN] 页面可能需要登录 Cookie、验证码，或当前账号权限不足")

        if rsp.status_code == 200:
            return text

    except Exception as e:
        print("[169BBS FINAL PROXY getHtml] error:", e, url)

    return ""


def _b169_getImgSrc(self, img):
    """
    详情图 / 帖子图 / 普通图片：
    先用旧逻辑取真实图片地址，再转本地图片代理。
    """
    try:
        old = getattr(Spider, "_b169_old_getImgSrc", None)
        if old:
            raw = old(self, img)
        else:
            raw = ""

        raw = _b169_unwrap_proxy_url(raw)
        raw = _b169_clean_url(self, raw)

        if not raw:
            return ""

        return _b169_to_img_proxy(self, raw)
    except Exception as e:
        print("[169BBS FINAL PROXY getImgSrc] error:", e)
        return ""


def _b169_getThreadListPic(self, row):
    """
    列表封面：
    先用旧逻辑取真实封面，再转本地图片代理。
    """
    try:
        old = getattr(Spider, "_b169_old_getThreadListPic", None)
        if old:
            raw = old(self, row)
        else:
            raw = ""

        raw = _b169_unwrap_proxy_url(raw)
        raw = _b169_clean_url(self, raw)

        if not raw:
            return ""

        return _b169_to_img_proxy(self, raw)
    except Exception as e:
        print("[169BBS FINAL PROXY getThreadListPic] error:", e)
        return ""


def _b169_localProxy(self, params):
    """
    只接管图片代理。
    图片请求走 127.0.0.1:10172。
    其他 localProxy 请求交给旧逻辑。
    """
    try:
        ptype = str(_b169_get_param(params, "type") or "").strip()
        action = str(_b169_get_param(params, "action") or "").strip()
        do_val = str(_b169_get_param(params, "do") or "").strip()

        is_img = False
        if ptype == "img" or action == "img" or do_val == "img":
            is_img = True

        if not is_img:
            old = getattr(Spider, "_b169_old_localProxy", None)
            if old:
                return old(self, params)
            return [404, "text/plain", "Not Found"]

        raw_url = str(_b169_get_param(params, "url") or "").strip()

        if not raw_url:
            return [404, "text/plain", "No Image Url"]

        raw_url = _b169_unquote(raw_url)
        fixed = _b169_clean_url(self, _b169_unwrap_proxy_url(raw_url))

        if not fixed:
            return [404, "text/plain", "Bad Image Url"]

        sess = getattr(self, "b169_image_session", None)

        if sess is None and _b169_Session:
            sess = _b169_Session()
            sess.verify = False
            sess.trust_env = False
            self.b169_image_session = sess

        if sess is None:
            return [404, "text/plain", "No Session"]

        rsp = sess.get(
            fixed,
            headers=_b169_site_headers(self, True),
            timeout=30,
            allow_redirects=True,
            verify=False,
            proxies=_b169_proxies(self),
        )

        content = rsp.content or b""
        ctype = rsp.headers.get("Content-Type") or ""

        print("[169BBS FINAL PROXY IMG] status=%s ctype=%s len=%s url=%s proxy=%s" % (
            rsp.status_code,
            ctype,
            len(content),
            fixed,
            _b169_get_site_proxy(self),
        ))

        if rsp.status_code == 200 and content:
            if "text/html" not in ctype.lower():
                return [200, _b169_guess_ctype(fixed, content, rsp), content]

            # 有些站 Content-Type 给错，按文件头判断
            if (
                content[:3] == b"\xff\xd8\xff"
                or content[:8] == b"\x89PNG\r\n\x1a\n"
                or (content[:4] == b"RIFF" and b"WEBP" in content[:20])
                or content[:6] in [b"GIF87a", b"GIF89a"]
            ):
                return [200, _b169_guess_ctype(fixed, content, rsp), content]

        try:
            print("[169BBS FINAL PROXY IMG body head]", content[:160])
        except Exception:
            pass

        return [404, "text/plain", "Image Not Found"]

    except Exception as e:
        print("[169BBS FINAL PROXY localProxy] error:", e)
        return [404, "text/plain", "Image Request Error"]


# 绑定最终方法
Spider.init = _b169_init
Spider.getHtml = _b169_getHtml
Spider.getImgSrc = _b169_getImgSrc
Spider.getThreadListPic = _b169_getThreadListPic
Spider.localProxy = _b169_localProxy

print("[FINAL 169BBS SITE/IMAGE PROXY ONLY] loaded")
# ===== FINAL_169BBS_SITE_IMAGE_PROXY_ONLY_END =====

# ===== ZERO_LINE_AUTO_PLAY_PATCH_BEGIN =====
# -*- coding: utf-8 -*-
# ============================================================
# 0线路自动播放补丁
#
# 作用：
#   1. 详情页 vod_play_from / vod_play_url 中，0线路永远排第一；
#   2. 如果原详情页已有0线路，移动到最前面；
#   3. 如果原详情页没有0线路，新增0线路到最前面；
#   4. 0线路默认播放本地路径：
#      /storage/emulated/0/Download/2026/太阳之子
#   5. 可通过 ext 配置 wait_video_url 覆盖：
#      {
#        "wait_video_url": "/storage/emulated/0/Download/2026/太阳之子"
#      }
#      或：
#      {
#        "wait_video_url": "https://example.com/demo.mp4"
#      }
#
# 注意：
#   - 这个补丁放在文件末尾，通过 monkey patch 方式覆盖；
#   - 不破坏原来的 115云下载 / 播放列表 / 查询 / 磁力链接线路；
#   - 只强制 0 线路排第一，解决壳自动播放会跳到首线路的问题。
# ============================================================

try:
    import json as _zero_line_json
except Exception:
    _zero_line_json = None

_ZERO_LINE_DEFAULT_WAIT_VIDEO_URL = "/storage/emulated/0/Download/2026/太阳之子"


def _zero_line_clean_play_name(_name, _limit=80):
    try:
        _name = str(_name or "").replace("#", "＃").replace("$", "＄")
        _name = " ".join(_name.split()).strip()
        return _name[:_limit] if _name else "默认播放"
    except Exception:
        return "默认播放"


def _zero_line_get_wait_video_url(self):
    """
    获取 0线路 默认播放地址。
    优先级：
      1. self.wait_video_url
      2. 固定默认路径
    """
    try:
        _url = str(getattr(self, "wait_video_url", "") or "").strip()
        if _url:
            return _url
    except Exception:
        pass
    return _ZERO_LINE_DEFAULT_WAIT_VIDEO_URL


def _zero_line_build_play_url(self):
    """
    构造 0线路播放项。
    格式：
      名称$id
    """
    try:
        _url = _zero_line_get_wait_video_url(self)
        _name = _zero_line_clean_play_name("默认播放")
        return "%s$%s" % (_name, _url)
    except Exception:
        return "默认播放$%s" % _ZERO_LINE_DEFAULT_WAIT_VIDEO_URL


def _zero_line_parse_extend_wait_url(self, extend):
    """
    从 ext 中读取 wait_video_url。
    """
    try:
        if not extend:
            return ""
        if isinstance(extend, dict):
            ext = extend
        else:
            if _zero_line_json is None:
                return ""
            ext = _zero_line_json.loads(str(extend))
        if not isinstance(ext, dict):
            return ""
        val = str(ext.get("wait_video_url", "") or "").strip()
        return val
    except Exception as e:
        try:
            print("[ZERO LINE PATCH] parse wait_video_url error:", e)
        except Exception:
            pass
        return ""


def _zero_line_fix_vod_play_lines(self, vod):
    """
    修正单个 vod 的播放线路：
      - 0线路置顶
      - 0线路播放地址统一为 wait_video_url
      - 其他线路原样保留
    """
    try:
        if not isinstance(vod, dict):
            return vod

        play_from_raw = str(vod.get("vod_play_from", "") or "")
        play_url_raw = str(vod.get("vod_play_url", "") or "")

        play_from = play_from_raw.split("$$$") if play_from_raw else []
        play_url = play_url_raw.split("$$$") if play_url_raw else []

        # 对齐长度，避免 from/url 数量不一致导致线路错位
        max_len = max(len(play_from), len(play_url))
        if max_len <= 0:
            play_from = []
            play_url = []
        else:
            while len(play_from) < max_len:
                play_from.append("")
            while len(play_url) < max_len:
                play_url.append("")

        # 移除原来的所有 0 线路，后面统一重建到最前面
        new_from = []
        new_url = []
        for f, u in zip(play_from, play_url):
            f2 = str(f or "").strip()
            if f2 == "0":
                continue
            # 空线路名没有意义，跳过
            if not f2:
                continue
            new_from.append(f2)
            new_url.append(str(u or ""))

        # 新的 0 线路永远第一
        zero_from = "0"
        zero_url = _zero_line_build_play_url(self)

        vod["vod_play_from"] = "$$$".join([zero_from] + new_from)
        vod["vod_play_url"] = "$$$".join([zero_url] + new_url)

        return vod
    except Exception as e:
        try:
            print("[ZERO LINE PATCH] fix vod play lines error:", e)
        except Exception:
            pass
        return vod


# 保存旧 init
try:
    if not hasattr(Spider, "_zero_line_old_init"):
        Spider._zero_line_old_init = Spider.init
except Exception:
    pass


def _zero_line_init(self, extend=""):
    """
    包装 init：
      - 先调用旧 init，保留原配置；
      - 再读取 ext.wait_video_url；
      - 没设置则使用默认本地路径。
    """
    try:
        old = getattr(Spider, "_zero_line_old_init", None)
        if old:
            old(self, extend)
    except Exception as e:
        try:
            print("[ZERO LINE PATCH] old init error:", e)
        except Exception:
            pass

    try:
        self.wait_video_url = _ZERO_LINE_DEFAULT_WAIT_VIDEO_URL
        ext_url = _zero_line_parse_extend_wait_url(self, extend)
        if ext_url:
            self.wait_video_url = ext_url
        print("[ZERO LINE PATCH] wait_video_url=%s" % self.wait_video_url)
    except Exception as e:
        try:
            print("[ZERO LINE PATCH] init wait_video_url error:", e)
        except Exception:
            pass


# 保存旧 detailContent
try:
    if not hasattr(Spider, "_zero_line_old_detailContent"):
        Spider._zero_line_old_detailContent = Spider.detailContent
except Exception:
    pass


def _zero_line_detailContent(self, ids):
    """
    包装 detailContent：
      - 调用原详情；
      - 对返回 vod 的播放线路做 0线路置顶修正。
    """
    try:
        old = getattr(Spider, "_zero_line_old_detailContent", None)
        if not old:
            return {"list": []}

        ret = old(self, ids)

        try:
            if not isinstance(ret, dict):
                return ret
            lst = ret.get("list") or []
            if not isinstance(lst, list):
                return ret

            for vod in lst:
                _zero_line_fix_vod_play_lines(self, vod)

            return ret
        except Exception as e:
            try:
                print("[ZERO LINE PATCH] detail ret fix error:", e)
            except Exception:
                pass
            return ret

    except Exception as e:
        try:
            print("[ZERO LINE PATCH] detailContent error:", e)
        except Exception:
            pass
        return {"list": []}


# 保存旧 playerContent
try:
    if not hasattr(Spider, "_zero_line_old_playerContent"):
        Spider._zero_line_old_playerContent = Spider.playerContent
except Exception:
    pass


def _zero_line_playerContent(self, flag, id, vipFlags):
    """
    包装 playerContent：
      - flag == "0" 时，不再走原来的提示逻辑；
      - 直接播放 wait_video_url 或 0线路 item 里的 id。
    """
    try:
        flag_s = str(flag or "").strip()
        id_s = str(id or "").strip()

        if flag_s == "0":
            play_url = id_s if id_s and id_s != "__ACK__" else _zero_line_get_wait_video_url(self)

            header = {}
            try:
                if play_url.startswith("http://") or play_url.startswith("https://"):
                    header = {
                        "User-Agent": getattr(self, "headers", {}).get("User-Agent", "Mozilla/5.0"),
                        "Referer": getattr(self, "host", "") + "/" if getattr(self, "host", "") else "",
                    }
            except Exception:
                header = {}

            ret = {
                "parse": 0,
                "playUrl": "",
                "url": play_url,
                "header": header,
            }

            # 保留封面
            try:
                pic = ""
                if hasattr(self, "_get_play_pic"):
                    pic = self._get_play_pic(id_s)
                if not pic:
                    pic = getattr(self, "last_vod_pic", "") or ""
                if pic:
                    ret["pic"] = pic
            except Exception:
                pass

            return ret

        old = getattr(Spider, "_zero_line_old_playerContent", None)
        if old:
            return old(self, flag, id, vipFlags)

        return {
            "parse": 0,
            "playUrl": "",
            "url": id_s,
            "header": {},
        }

    except Exception as e:
        try:
            print("[ZERO LINE PATCH] playerContent error:", e)
        except Exception:
            pass

        try:
            return {
                "parse": 0,
                "playUrl": "",
                "url": _zero_line_get_wait_video_url(self),
                "header": {},
            }
        except Exception:
            return {
                "parse": 0,
                "playUrl": "",
                "url": _ZERO_LINE_DEFAULT_WAIT_VIDEO_URL,
                "header": {},
            }


try:
    Spider.init = _zero_line_init
    Spider.detailContent = _zero_line_detailContent
    Spider.playerContent = _zero_line_playerContent
    print("[ZERO LINE PATCH] loaded: 0线路已置顶，默认播放 wait_video_url")
except Exception as e:
    try:
        print("[ZERO LINE PATCH] load error:", e)
    except Exception:
        pass
# ===== ZERO_LINE_AUTO_PLAY_PATCH_END =====
# ===== 169BBS_ADD_115_ORIGINAL_PLAY_ALWAYS_PATCH_BEGIN =====
# -*- coding: utf-8 -*-
# ============================================================
# 169BBS 新增“115原画播放”线路补丁
#
# 功能：
#   1. 不改变原有 0 / 115云下载 / 播放列表 / 查询 / 磁力链接逻辑；
#   2. 始终显示“115原画播放”线路；
#   3. 如果存在“115云下载”，则插入到“115云下载”之后；
#   4. 如果不存在“115云下载”，则插入到“0”线路之后；
#   5. 115原画播放线路复用“播放列表”里的 __115_FILE__|xxx；
#   6. 没有缓存文件时也显示占位项；
#   7. 点击“115原画播放”时，才构造 Go 代理 type=dwnz 原画播放地址；
#   8. 其他代码和逻辑不改。
# ============================================================

import json as _b169op_json
import base64 as _b169op_base64
import re as _b169op_re
from urllib.parse import urlencode as _b169op_urlencode
from urllib.parse import quote as _b169op_quote

# ------------------------------------------------------------
# 保存当前最终方法
# ------------------------------------------------------------
try:
    Spider._b169op_old_init = Spider.init
except Exception:
    Spider._b169op_old_init = None

try:
    Spider._b169op_old_detailContent = Spider.detailContent
except Exception:
    Spider._b169op_old_detailContent = None

try:
    Spider._b169op_old_playerContent = Spider.playerContent
except Exception:
    Spider._b169op_old_playerContent = None


# ------------------------------------------------------------
# 默认配置
# ------------------------------------------------------------
_B169OP_DEFAULT_HOST = "127.0.0.1"
_B169OP_DEFAULT_OK_PORT = "10078"
_B169OP_DEFAULT_GO_PORT = "9978"
_B169OP_DEFAULT_REFERER = "https://anxia.com/"
_B169OP_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)


# ------------------------------------------------------------
# init 包装：只新增 115原画播放配置项
# ------------------------------------------------------------
def _b169op_init(self, extend=""):
    try:
        old = getattr(Spider, "_b169op_old_init", None)
        if old:
            old(self, extend)
    except Exception as e:
        try:
            print("[169BBS 115原画播放 init] old init error:", e)
        except Exception:
            pass

    try:
        self.b169op_host = getattr(self, "b169op_host", "") or _B169OP_DEFAULT_HOST
        self.b169op_ok_port = getattr(self, "b169op_ok_port", "") or _B169OP_DEFAULT_OK_PORT
        self.b169op_go_port = getattr(self, "b169op_go_port", "") or _B169OP_DEFAULT_GO_PORT
        self.b169op_referer = getattr(self, "b169op_referer", "") or _B169OP_DEFAULT_REFERER
        self.b169op_ua = getattr(self, "b169op_ua", "") or _B169OP_DEFAULT_UA
    except Exception:
        pass

    # 可选 extend 覆盖：
    # {
    #   "b169op_host": "127.0.0.1",
    #   "b169op_ok_port": "10078",
    #   "b169op_go_port": "9978",
    #   "b169op_referer": "https://anxia.com/",
    #   "b169op_ua": "Mozilla/5.0 ... Chrome/138.0.0.0 ..."
    # }
    try:
        if extend:
            ext = _b169op_json.loads(str(extend))
            if isinstance(ext, dict):
                if ext.get("b169op_host"):
                    self.b169op_host = str(ext.get("b169op_host")).strip()
                if ext.get("b169op_ok_port"):
                    self.b169op_ok_port = str(ext.get("b169op_ok_port")).strip()
                if ext.get("b169op_go_port"):
                    self.b169op_go_port = str(ext.get("b169op_go_port")).strip()
                if ext.get("b169op_referer"):
                    self.b169op_referer = str(ext.get("b169op_referer")).strip()
                if ext.get("b169op_ua"):
                    self.b169op_ua = str(ext.get("b169op_ua")).strip()

                # 兼容参考代码里的配置名
                if ext.get("jb115op_host"):
                    self.b169op_host = str(ext.get("jb115op_host")).strip()
                if ext.get("jb115op_ok_port"):
                    self.b169op_ok_port = str(ext.get("jb115op_ok_port")).strip()
                if ext.get("jb115op_go_port"):
                    self.b169op_go_port = str(ext.get("jb115op_go_port")).strip()
                if ext.get("jb115op_referer"):
                    self.b169op_referer = str(ext.get("jb115op_referer")).strip()
                if ext.get("jb115op_ua"):
                    self.b169op_ua = str(ext.get("jb115op_ua")).strip()
    except Exception as e:
        try:
            print("[169BBS 115原画播放 init] extend parse error:", e)
        except Exception:
            pass

    # 强制使用验证成功 UA
    try:
        if "Chrome/138.0.0.0" not in str(getattr(self, "b169op_ua", "")):
            self.b169op_ua = _B169OP_DEFAULT_UA
    except Exception:
        self.b169op_ua = _B169OP_DEFAULT_UA

    try:
        print("[169BBS 115原画播放 init] host=%s ok_port=%s go_port=%s" % (
            getattr(self, "b169op_host", _B169OP_DEFAULT_HOST),
            getattr(self, "b169op_ok_port", _B169OP_DEFAULT_OK_PORT),
            getattr(self, "b169op_go_port", _B169OP_DEFAULT_GO_PORT),
        ))
    except Exception:
        pass


# ------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------
def _b169op_ack(self):
    try:
        if hasattr(self, "_returnAck"):
            return self._returnAck()
    except Exception:
        pass
    return {
        "parse": 0,
        "playUrl": "",
        "url": "",
        "header": {},
    }


def _b169op_get_pic(self, pid=""):
    try:
        if hasattr(self, "_get_play_pic"):
            pic = self._get_play_pic(pid)
            if pic:
                return pic
    except Exception:
        pass
    try:
        return getattr(self, "last_vod_pic", "") or ""
    except Exception:
        return ""


def _b169op_set_pic(self, pid, pic):
    try:
        if not pid or not pic:
            return
        if hasattr(self, "_set_play_pic"):
            self._set_play_pic(pid, pic)
            return
        if not hasattr(self, "play_pic_map"):
            self.play_pic_map = {}
        self.play_pic_map[str(pid)] = pic
    except Exception:
        pass


def _b169op_clean_name(name, limit=120):
    try:
        name = str(name or "")
        name = name.replace("#", "＃").replace("$", "＄")
        name = name.replace("\r", " ").replace("\n", " ").replace("\t", " ")
        name = _b169op_re.sub(r"\s+", " ", name).strip()
        return name[:limit] if name else "115原画"
    except Exception:
        return "115原画"


def _b169op_get_cookie(self):
    try:
        ck = str(getattr(self, "pan_115_cookie", "") or "").strip()
        if ck:
            return ck
    except Exception:
        pass

    for attr in [
        "cookie_115",
        "pan115_cookie",
        "jb115_cookie",
        "jbo_final_cookie",
        "cookie",
        "_cookie",
    ]:
        try:
            v = str(getattr(self, attr, "") or "").strip()
            if v and "UID=" in v:
                return v
        except Exception:
            pass
    return ""


def _b169op_uid_from_cookie(cookie):
    try:
        cookie = str(cookie or "")
        m = _b169op_re.search(r"(?:^|;\s*)UID=([^;]+)", cookie)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return ""


def _b169op_ext(name):
    try:
        name = str(name or "").strip()
        if "." in name:
            ext = name.rsplit(".", 1)[-1].strip().lower()
            if ext:
                return ext
    except Exception:
        pass
    return "mp4"


def _b169op_load_cache(self):
    try:
        if hasattr(self, "_115_cache_load"):
            return self._115_cache_load()
    except Exception as e:
        try:
            print("[169BBS 115原画播放 cache] load by _115_cache_load error:", e)
        except Exception:
            pass
    return {
        "magnets": {},
        "files": {},
    }


def _b169op_load_file_from_cache(self, fk):
    """
    从 115_cache.json 读取文件信息。
    支持：
      __115_FILE__|fid
      __115_FILE__|pickcode
    """
    fk = str(fk or "").strip()
    if not fk:
        return None

    try:
        cache = _b169op_load_cache(self)
        files_map = cache.get("files", {}) or {}
        if not isinstance(files_map, dict):
            return None

        # 1. 直接 key 命中
        f = files_map.get(fk)
        if isinstance(f, dict):
            return f

        # 2. fid / pickcode 反查
        for _, v in files_map.items():
            if not isinstance(v, dict):
                continue
            fid = str(
                v.get("fid")
                or v.get("file_id")
                or v.get("id")
                or ""
            ).strip()
            pc = str(
                v.get("pickcode")
                or v.get("pick_code")
                or v.get("pickCode")
                or v.get("pc")
                or ""
            ).strip()
            if fk == fid or fk == pc:
                return v
    except Exception as e:
        try:
            print("[169BBS 115原画播放 cache] lookup error:", e)
        except Exception:
            pass
    return None


def _b169op_is_valid_115_file_item(play_item):
    try:
        s = str(play_item or "")
        if "$" not in s:
            return False
        _, pid = s.split("$", 1)
        pid = pid.strip()
        return pid.startswith("__115_FILE__|")
    except Exception:
        return False


def _b169op_filter_valid_115_items(source_url):
    """
    从原“播放列表”线路中提取 __115_FILE__ 项。
    不改变原播放列表，只复制有效项到“115原画播放”。
    """
    out = []
    try:
        for it in str(source_url or "").split("#"):
            it = str(it or "").strip()
            if not it:
                continue
            if _b169op_is_valid_115_file_item(it):
                out.append(it)
    except Exception:
        pass
    return "#".join(out)


def _b169op_find_line(flags, name):
    try:
        for i, f in enumerate(flags or []):
            if str(f or "").strip() == name:
                return i
    except Exception:
        pass
    return -1


def _b169op_get_playlist_items(flags, urls):
    try:
        idx = _b169op_find_line(flags, "播放列表")
        if idx < 0 or idx >= len(urls):
            return ""
        return _b169op_filter_valid_115_items(urls[idx])
    except Exception:
        return ""


# ------------------------------------------------------------
# 构造 115 原画播放地址
# ------------------------------------------------------------
def _b169op_build_original_url(self, file_info):
    """
    构造 OK/PG + Go 代理原画播放地址。

    外层：
      http://127.0.0.1:10078/p/32/null/{base64}/{ext}?header={HeaderJSON}

    内层 Base64 解码后：
      http://127.0.0.1:9978/proxy?do=115&type=dwnz&file_id=...&share_id=self&share_pwd=...&file_size=...&content_hash=...&file_name=mp4

    关键：
      type 固定为 dwnz
    """
    try:
        if not isinstance(file_info, dict):
            return "", {}

        fid = str(
            file_info.get("fid")
            or file_info.get("file_id")
            or file_info.get("id")
            or ""
        ).strip()

        pickcode = str(
            file_info.get("pickcode")
            or file_info.get("pick_code")
            or file_info.get("pickCode")
            or file_info.get("pc")
            or ""
        ).strip()

        name = str(
            file_info.get("name")
            or file_info.get("file_name")
            or file_info.get("fname")
            or ""
        ).strip()

        size = str(
            file_info.get("size")
            or file_info.get("file_size")
            or file_info.get("s")
            or "0"
        ).strip()

        sha1 = str(
            file_info.get("sha1")
            or file_info.get("sha")
            or file_info.get("file_sha1")
            or file_info.get("content_hash")
            or ""
        ).strip().upper()

        if not fid or not pickcode:
            print("[169BBS 115原画播放] missing fid/pickcode:", file_info)
            return "", {}

        ext = _b169op_ext(name)

        host = str(
            getattr(self, "b169op_host", _B169OP_DEFAULT_HOST)
            or _B169OP_DEFAULT_HOST
        ).strip()

        ok_port = str(
            getattr(self, "b169op_ok_port", _B169OP_DEFAULT_OK_PORT)
            or _B169OP_DEFAULT_OK_PORT
        ).strip()

        go_port = str(
            getattr(self, "b169op_go_port", _B169OP_DEFAULT_GO_PORT)
            or _B169OP_DEFAULT_GO_PORT
        ).strip()

        referer = str(
            getattr(self, "b169op_referer", _B169OP_DEFAULT_REFERER)
            or _B169OP_DEFAULT_REFERER
        ).strip()

        ua = str(
            getattr(self, "b169op_ua", _B169OP_DEFAULT_UA)
            or _B169OP_DEFAULT_UA
        ).strip()

        if "Chrome/138.0.0.0" not in ua:
            ua = _B169OP_DEFAULT_UA

        cookie = _b169op_get_cookie(self)
        uid = _b169op_uid_from_cookie(cookie)

        if not cookie:
            print("[169BBS 115原画播放] warning: pan_115_cookie empty")

        # ========================================================
        # 关键：type=dwnz
        # ========================================================
        inner_params = [
            ("do", "115"),
            ("type", "dwnz"),
            ("file_id", fid),
            ("share_id", "self"),
            ("share_pwd", pickcode),
            ("file_size", size),
            ("content_hash", sha1),
            ("file_name", ext),
        ]

        inner_url = "http://%s:%s/proxy?%s" % (
            host,
            go_port,
            _b169op_urlencode(inner_params),
        )

        inner_b64 = _b169op_base64.b64encode(
            inner_url.encode("utf-8")
        ).decode("utf-8").rstrip("=")

        header_obj = {
            "cookie": cookie,
            "User-Agent": ua,
            "Referer": referer,
            "p115uid": uid,
            "SPEEDLIMIT": "0",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        header_json = _b169op_json.dumps(
            header_obj,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        header_encoded = _b169op_quote(header_json, safe="()")

        final_url = (
            "http://%s:%s/p/32/null/%s/%s"
            "?header=%s"
            % (
                host,
                ok_port,
                inner_b64,
                ext,
                header_encoded,
            )
        )

        try:
            self._b169op_last_inner = inner_url
            self._b169op_last_url = final_url
            self._b169op_last_header = header_obj
        except Exception:
            pass

        print("[169BBS 115原画播放] build ok")
        print("[169BBS 115原画播放] file name=%s" % name)
        print("[169BBS 115原画播放] fid=%s" % fid)
        print("[169BBS 115原画播放] pickcode=%s" % pickcode)
        print("[169BBS 115原画播放] size=%s" % size)
        print("[169BBS 115原画播放] sha1=%s" % sha1)
        print("[169BBS 115原画播放] ext=%s" % ext)
        print("[169BBS 115原画播放] inner=%s" % inner_url)
        print("[169BBS 115原画播放] final=%s" % final_url)
        print("[169BBS 115原画播放] header=%s" % header_obj)

        return final_url, header_obj

    except Exception as e:
        print("[169BBS 115原画播放] build url error:", e)
        return "", {}


# ------------------------------------------------------------
# 详情页包装：始终新增“115原画播放”线路
# ------------------------------------------------------------
def _b169op_detailContent(self, ids):
    try:
        old = getattr(Spider, "_b169op_old_detailContent", None)
        if old:
            ret = old(self, ids)
        else:
            ret = {"list": []}

        if not ret or not isinstance(ret, dict):
            return ret

        lst = ret.get("list") or []
        if not lst:
            return ret

        vod = lst[0]
        if not isinstance(vod, dict):
            return ret

        play_from_raw = str(vod.get("vod_play_from", "") or "")
        play_url_raw = str(vod.get("vod_play_url", "") or "")

        flags = play_from_raw.split("$$$") if play_from_raw else []
        urls = play_url_raw.split("$$$") if play_url_raw else []

        max_len = max(len(flags), len(urls))
        while len(flags) < max_len:
            flags.append("")
        while len(urls) < max_len:
            urls.append("")

        # 已存在则不重复添加
        if "115原画播放" in [str(x or "").strip() for x in flags]:
            return ret

        # 从原“播放列表”复制 __115_FILE__ 项
        original_url = _b169op_get_playlist_items(flags, urls)

        # 始终显示：没有缓存文件也显示占位项
        if not original_url:
            original_url = "暂无115原画缓存，请先点115云下载-下载状态$__ACK__"

        # 插入位置：
        #   1. 优先放在 115云下载 后面；
        #   2. 没有 115云下载，则放在 0 后面；
        #   3. 再没有，则放到最前面。
        cloud_idx = _b169op_find_line(flags, "115云下载")
        zero_idx = _b169op_find_line(flags, "0")

        if cloud_idx >= 0:
            insert_idx = cloud_idx + 1
        elif zero_idx >= 0:
            insert_idx = zero_idx + 1
        else:
            insert_idx = 0

        flags.insert(insert_idx, "115原画播放")
        urls.insert(insert_idx, original_url)

        vod["vod_play_from"] = "$$$".join(flags)
        vod["vod_play_url"] = "$$$".join(urls)

        # 绑定封面
        try:
            pic = vod.get("vod_pic") or getattr(self, "last_vod_pic", "") or ""
            if pic:
                for it in original_url.split("#"):
                    if "$" not in it:
                        continue
                    _, pid = it.split("$", 1)
                    pid = pid.strip()
                    if pid:
                        _b169op_set_pic(self, pid, pic)
        except Exception:
            pass

        print("[169BBS 115原画播放] line added, insert_idx=%s, has_file=%s" % (
            insert_idx,
            "__115_FILE__|" in original_url,
        ))

        return ret

    except Exception as e:
        try:
            print("[169BBS 115原画播放] detailContent error:", e)
        except Exception:
            pass

        try:
            old = getattr(Spider, "_b169op_old_detailContent", None)
            if old:
                return old(self, ids)
        except Exception:
            pass

        return {"list": []}


# ------------------------------------------------------------
# playerContent 包装：
#   只接管 flag == "115原画播放"
#   其他全部交回旧逻辑
# ------------------------------------------------------------
def _b169op_playerContent(self, flag, id, vipFlags):
    try:
        flag_s = str(flag or "").strip()
        pid = str(id or "").strip()

        if flag_s == "115原画播放":
            pic = _b169op_get_pic(self, pid)

            if not pid.startswith("__115_FILE__|"):
                print("[169BBS 115原画播放] invalid pid:", pid)
                ret = _b169op_ack(self)
                if pic and isinstance(ret, dict):
                    ret["pic"] = ret.get("pic") or pic
                return ret

            fk = pid.split("|", 1)[1].strip()
            if not fk:
                ret = _b169op_ack(self)
                if pic and isinstance(ret, dict):
                    ret["pic"] = ret.get("pic") or pic
                return ret

            f = _b169op_load_file_from_cache(self, fk)
            if not f:
                print("[169BBS 115原画播放] cache miss:", fk)
                ret = _b169op_ack(self)
                if pic and isinstance(ret, dict):
                    ret["pic"] = ret.get("pic") or pic
                return ret

            final_url, header_obj = _b169op_build_original_url(self, f)
            if not final_url:
                ret = _b169op_ack(self)
                if pic and isinstance(ret, dict):
                    ret["pic"] = ret.get("pic") or pic
                return ret

            ret = {
                "parse": 0,
                "playUrl": "",
                "url": final_url,
                "header": header_obj,
            }

            if pic:
                ret["pic"] = pic

            print("[169BBS 115原画播放] player ret url=%s" % final_url)
            print("[169BBS 115原画播放] player ret header=%s" % header_obj)

            return ret

        # 其他所有线路完全交回旧逻辑
        old = getattr(Spider, "_b169op_old_playerContent", None)
        if old:
            return old(self, flag, id, vipFlags)

        return {
            "parse": 1,
            "playUrl": "",
            "url": pid,
            "header": getattr(self, "headers", {}),
        }

    except Exception as e:
        try:
            print("[169BBS 115原画播放] playerContent error:", e)
        except Exception:
            pass

        try:
            old = getattr(Spider, "_b169op_old_playerContent", None)
            if old:
                return old(self, flag, id, vipFlags)
        except Exception:
            pass

        return _b169op_ack(self)


# ------------------------------------------------------------
# 绑定
# ------------------------------------------------------------
try:
    Spider.init = _b169op_init
    Spider.detailContent = _b169op_detailContent
    Spider.playerContent = _b169op_playerContent

    # 调试方法
    Spider._b169op_build_original_url = _b169op_build_original_url
    Spider._b169op_load_file_from_cache = _b169op_load_file_from_cache

    print("[169BBS ADD 115 ORIGINAL PLAY ALWAYS PATCH] loaded")
    print("[169BBS ADD 115 ORIGINAL PLAY ALWAYS PATCH] 新增线路：115原画播放")
    print("[169BBS ADD 115 ORIGINAL PLAY ALWAYS PATCH] 显示规则：始终显示")
    print("[169BBS ADD 115 ORIGINAL PLAY ALWAYS PATCH] 位置：优先在115云下载之后，否则在0线路之后")
    print("[169BBS ADD 115 ORIGINAL PLAY ALWAYS PATCH] 仅 flag=115原画播放 时走 type=dwnz")

except Exception as e:
    try:
        print("[169BBS ADD 115 ORIGINAL PLAY ALWAYS PATCH] load error:", e)
    except Exception:
        pass

# ===== 169BBS_ADD_115_ORIGINAL_PLAY_ALWAYS_PATCH_END =====

# ===== 169BBS_AUTO_PATCH_BEGIN =====
# -*- coding: utf-8 -*-

import os as _b169_os
import re as _b169_re
import json as _b169_json
import time as _b169_time
import threading as _b169_threading
from datetime import datetime as _b169_datetime, timedelta as _b169_timedelta
from urllib.parse import quote as _b169_quote, urljoin as _b169_urljoin

try:
    from pyquery import PyQuery as _b169_pq
except Exception:
    _b169_pq = None


# -----------------------------
# 保存旧方法，避免破坏原逻辑
# -----------------------------
try:
    if not hasattr(Spider, "_b169_old_init"):
        Spider._b169_old_init = Spider.init
except Exception:
    pass

try:
    if not hasattr(Spider, "_b169_old_homeContent"):
        Spider._b169_old_homeContent = Spider.homeContent
except Exception:
    pass

try:
    if not hasattr(Spider, "_b169_old_searchContent"):
        Spider._b169_old_searchContent = Spider.searchContent
except Exception:
    pass

try:
    if not hasattr(Spider, "_b169_old_homeVideoContent") and hasattr(Spider, "homeVideoContent"):
        Spider._b169_old_homeVideoContent = Spider.homeVideoContent
except Exception:
    pass


# -----------------------------
# 通用工具
# -----------------------------
def _b169_today():
    return _b169_datetime.now().strftime("%Y-%m-%d")


def _b169_today_num():
    return _b169_datetime.now().strftime("%Y%m%d")


def _b169_now_text():
    return _b169_datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _b169_clean_text(self, s):
    try:
        if hasattr(self, "cleanText"):
            return self.cleanText(s)
    except Exception:
        pass
    s = str(s or "")
    s = s.replace("\xa0", " ").replace("&nbsp;", " ")
    s = _b169_re.sub(r"<[^>]+>", " ", s)
    s = _b169_re.sub(r"\s+", " ", s)
    return s.strip()


def _b169_fix_url(self, url):
    try:
        if hasattr(self, "fixUrl"):
            return self.fixUrl(url)
    except Exception:
        pass

    url = str(url or "").strip().replace("&amp;", "&")
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://") or url.startswith("https://"):
        return url

    host = getattr(self, "host", "https://169bbs.com").rstrip("/")
    return _b169_urljoin(host + "/", url)


def _b169_remove_mobile(self, url):
    try:
        if hasattr(self, "removeUrlParam"):
            return self.removeUrlParam(url, ["mobile"])
    except Exception:
        pass
    return url


def _b169_dedupe(self, arr):
    try:
        if hasattr(self, "dedupeVodList"):
            return self.dedupeVodList(arr)
    except Exception:
        pass

    out = []
    seen = set()
    for x in arr or []:
        k = x.get("vod_id") or x.get("vod_name")
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out


def _b169_get_html(self, url, headers=None):
    try:
        if hasattr(self, "getHtml"):
            return self.getHtml(url)
    except Exception:
        pass

    sess = getattr(self, "session", None)
    if sess is None:
        return ""
    try:
        r = sess.get(
            url,
            headers=headers or getattr(self, "headers", {}),
            timeout=30,
            allow_redirects=True,
            verify=False,
        )
        return r.text or ""
    except Exception as e:
        print("[169BBS get html] error:", e)
        return ""


def _b169_formhash_from_html(html):
    html = html or ""
    pats = [
        r'name=["\']formhash["\']\s+value=["\']([^"\']+)["\']',
        r'value=["\']([^"\']+)["\']\s+name=["\']formhash["\']',
        r'formhash=([0-9a-fA-F]+)',
        r'formhash["\']?\s*[:=]\s*["\']([0-9a-fA-F]+)["\']',
    ]
    for p in pats:
        m = _b169_re.search(p, html, _b169_re.I)
        if m:
            return m.group(1).strip()
    return ""


def _b169_get_formhash(self):
    try:
        host = getattr(self, "host", "https://169bbs.com").rstrip("/")
        html = _b169_get_html(self, host + "/")
        fh = _b169_formhash_from_html(html)
        if fh:
            return fh
        html = _b169_get_html(self, host + "/search.php")
        return _b169_formhash_from_html(html)
    except Exception:
        return ""


# -----------------------------
# 缓存
# -----------------------------
def _b169_cache_file(self):
    p = str(getattr(self, "checkin_cache_file", "") or "").strip()
    if p:
        return p
    return "/tmp/169bbs_checkin_cache.json"


def _b169_load_cache(self):
    p = _b169_cache_file(self)
    try:
        if _b169_os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                d = _b169_json.load(f)
            if isinstance(d, dict):
                return d
    except Exception as e:
        print("[169BBS cache] load error:", e)
    return {}


def _b169_save_cache(self, data):
    p = _b169_cache_file(self)
    try:
        dn = _b169_os.path.dirname(p)
        if dn and not _b169_os.path.exists(dn):
            _b169_os.makedirs(dn, exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _b169_json.dump(data or {}, f, ensure_ascii=False, indent=2)
        _b169_os.replace(tmp, p)
        return True
    except Exception as e:
        print("[169BBS cache] save error:", e)
        return False


def _b169_checkin_from_cache(self):
    try:
        d = _b169_load_cache(self)
        rec = d.get(_b169_today())
        if isinstance(rec, dict):
            return rec
    except Exception:
        pass
    return None


def _b169_set_checkin_cache(self, status, msg="", raw=""):
    rec = {
        "date": _b169_today(),
        "status": status,
        "msg": msg,
        "raw": str(raw or "")[:800],
        "update_time": int(_b169_time.time()),
        "update_time_text": _b169_now_text(),
    }
    try:
        d = _b169_load_cache(self)
        d[_b169_today()] = rec
        _b169_save_cache(self, d)
    except Exception:
        pass
    self._b169_checkin_status = rec
    return rec


# -----------------------------
# 登录
# -----------------------------
def _b169_is_logged_in_html(html):
    html = html or ""

    if any(x in html for x in [
        "member.php?mod=logging&amp;action=logout",
        "member.php?mod=logging&action=logout",
        "退出",
        "访问我的空间",
        "home.php?mod=spacecp",
    ]):
        return True

    if any(x in html for x in [
        "member.php?mod=logging&action=login",
        "member.php?mod=logging&amp;action=login",
        "请先登录",
        "您需要登录",
        "會員登錄",
        "会员登录",
    ]):
        return False

    return False


def _b169_login(self, force=False):
    """
    账号密码登录。
    配置字段兼容：
      username / site_username / user
      password / site_password / pass
    如果未配置账号密码，则使用已有 cookie。
    """
    try:
        if getattr(self, "_b169_logged", False) and not force:
            return True

        host = getattr(self, "host", "https://169bbs.com").rstrip("/")
        sess = getattr(self, "session", None)

        # 先用当前 cookie 访问首页判断
        html0 = _b169_get_html(self, host + "/")
        if _b169_is_logged_in_html(html0):
            self._b169_logged = True
            return True

        username = str(
            getattr(self, "site_username", "zw110708") or
            getattr(self, "username", "") or
            getattr(self, "user", "") or
            ""
        ).strip()

        password = str(
            getattr(self, "site_password", "Zw110708#") or
            getattr(self, "password", "") or
            getattr(self, "pass_word", "") or
            ""
        ).strip()

        if not username or not password or sess is None:
            self._b169_logged = False
            print("[169BBS login] no username/password or session, use cookie only")
            return False

        login_page = host + "/member.php?mod=logging&action=login"
        html = _b169_get_html(self, login_page)
        formhash = _b169_formhash_from_html(html) or _b169_get_formhash(self)

        login_url = host + "/member.php?mod=logging&action=login&loginsubmit=yes&loginhash=L169&inajax=1"

        headers = dict(getattr(self, "headers", {}) or {})
        headers.update({
            "Referer": login_page,
            "Origin": host,
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": headers.get("User-Agent", "Mozilla/5.0"),
        })

        data = {
            "formhash": formhash,
            "referer": host + "/",
            "loginfield": "username",
            "username": username,
            "password": password,
            "questionid": "0",
            "answer": "",
            "cookietime": "2592000",
        }

        r = sess.post(
            login_url,
            data=data,
            headers=headers,
            timeout=30,
            allow_redirects=True,
            verify=False,
        )

        print("[169BBS login] post status=%s len=%s" % (r.status_code, len(r.text or "")))

        html2 = _b169_get_html(self, host + "/")
        ok = _b169_is_logged_in_html(html2)

        try:
            ck = sess.cookies.get_dict()
            if ck:
                cookie_str = "; ".join(["%s=%s" % (k, v) for k, v in ck.items()])
                if cookie_str:
                    self.site_cookie = cookie_str
                    if hasattr(self, "headers"):
                        self.headers["Cookie"] = cookie_str
                    sess.headers.update({"Cookie": cookie_str})
        except Exception:
            pass

        self._b169_logged = ok
        print("[169BBS login] ok=%s" % ok)
        return ok

    except Exception as e:
        print("[169BBS login] error:", e)
        return False


# -----------------------------
# 打卡
# -----------------------------
def _b169_cookie_has_today_sign(self):
    """
    检查 Cookie 中是否有：
      SlDj_2132_zqlj_sign_493890=20260529
    """
    try:
        today = _b169_today_num()
        cookie_text = ""

        sess = getattr(self, "session", None)
        if sess is not None and hasattr(sess, "cookies"):
            cd = sess.cookies.get_dict()
            if cd:
                cookie_text = "; ".join(["%s=%s" % (k, v) for k, v in cd.items()])

        if not cookie_text:
            cookie_text = str(
                getattr(self, "site_cookie", "") or
                getattr(self, "headers", {}).get("Cookie", "") or
                ""
            )

        if not cookie_text:
            return False

        return _b169_re.search(r"zqlj_sign_\d+=" + _b169_re.escape(today), cookie_text) is not None
    except Exception:
        return False


def _b169_do_checkin(self, force=False):
    """
    169BBS 实测打卡：
      GET /qiandao.php
      解析 qiandao.php?sign=xxxx
      GET /qiandao.php?sign=xxxx
    """
    try:
        if not force:
            cached = _b169_checkin_from_cache(self)
            if cached:
                self._b169_checkin_status = cached
                print("[169BBS checkin] cache hit:", cached)
                return cached

        try:
            _b169_login(self, force=False)
        except Exception as e:
            print("[169BBS checkin] login error:", e)

        if _b169_cookie_has_today_sign(self):
            return _b169_set_checkin_cache(self, "done", "今日已打卡，Cookie 已有打卡标记", "")

        host = getattr(self, "host", "https://169bbs.com").rstrip("/")
        sess = getattr(self, "session", None)
        if sess is None:
            return _b169_set_checkin_cache(self, "error", "session 不存在")

        headers = dict(getattr(self, "headers", {}) or {})
        headers.update({
            "User-Agent": headers.get("User-Agent", "Mozilla/5.0"),
            "Referer": host + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        })

        page_url = host + "/qiandao.php"
        r = sess.get(
            page_url,
            headers=headers,
            timeout=30,
            allow_redirects=True,
            verify=False,
        )

        html = r.text or ""
        final_url = r.url or page_url

        print("[169BBS checkin] open page status=%s final=%s len=%s" % (
            r.status_code,
            final_url,
            len(html),
        ))

        done_words = [
            "您今天已经打过卡",
            "今天已经打过卡",
            "已经打过卡",
            "請勿重複操作",
            "请勿重复操作",
            "今日已打卡",
            "已打卡",
            "已签到",
            "今日已签到",
            "已簽到",
        ]

        if any(x in html for x in done_words):
            return _b169_set_checkin_cache(self, "done", "今日已打卡", html)

        if _b169_cookie_has_today_sign(self):
            return _b169_set_checkin_cache(self, "done", "今日已打卡，Cookie 已有打卡标记", html)

        sign_url = ""

        m = _b169_re.search(
            r'["\']([^"\']*qiandao\.php\?sign=[0-9a-zA-Z]+[^"\']*)["\']',
            html,
            _b169_re.I
        )
        if m:
            sign_url = m.group(1).replace("&amp;", "&").strip()

        if not sign_url:
            m = _b169_re.search(
                r'(qiandao\.php\?sign=[0-9a-zA-Z]+)',
                html,
                _b169_re.I
            )
            if m:
                sign_url = m.group(1).replace("&amp;", "&").strip()

        if not sign_url and "qiandao.php?sign=" in final_url:
            sign_url = final_url

        if not sign_url:
            return _b169_set_checkin_cache(self, "unknown", "未找到 qiandao.php?sign=xxxx", html)

        sign_url = _b169_fix_url(self, sign_url)

        headers["Referer"] = page_url

        r2 = sess.get(
            sign_url,
            headers=headers,
            timeout=30,
            allow_redirects=True,
            verify=False,
        )

        text = r2.text or ""

        print("[169BBS checkin] sign url=%s status=%s final=%s len=%s" % (
            sign_url,
            r2.status_code,
            r2.url,
            len(text),
        ))

        success_words = [
            "打卡成功",
            "签到成功",
            "簽到成功",
            "成功打卡",
            "恭喜",
            "您今天已经打过卡",
            "今天已经打过卡",
            "已经打过卡",
            "请勿重复操作",
            "請勿重複操作",
            "今日已打卡",
            "已打卡",
            "已签到",
            "今日已签到",
        ]

        if any(x in text for x in success_words):
            return _b169_set_checkin_cache(self, "done", "今日已打卡", text)

        if _b169_cookie_has_today_sign(self):
            return _b169_set_checkin_cache(self, "done", "今日已打卡，Cookie 已有打卡标记", text)

        login_words = [
            "请先登录",
            "您需要登录",
            "登录后",
            "會員登錄",
            "会员登录",
            "member.php?mod=logging",
        ]

        if any(x in text for x in login_words):
            return _b169_set_checkin_cache(self, "error", "打卡失败：未登录", text)

        return _b169_set_checkin_cache(self, "unknown", "已请求打卡 URL，但未能确认是否成功", text)

    except Exception as e:
        print("[169BBS checkin] error:", e)
        return _b169_set_checkin_cache(self, "error", str(e))


def _b169_schedule_midnight(self):
    """
    每天 0 点 5 秒自动打卡。
    注意：只有 py 进程持续运行时才有效。
    """
    try:
        now = _b169_datetime.now()
        nxt = (now + _b169_timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
        sec = max(5, int((nxt - now).total_seconds()))

        def _run():
            try:
                _b169_do_checkin(self, force=False)
            except Exception as e:
                print("[169BBS checkin timer] error:", e)
            try:
                _b169_schedule_midnight(self)
            except Exception:
                pass

        t = _b169_threading.Timer(sec, _run)
        t.daemon = True
        t.start()
        self._b169_checkin_timer = t
        print("[169BBS checkin timer] next after %s seconds" % sec)
    except Exception as e:
        print("[169BBS checkin timer] schedule error:", e)


def _b169_checkin_card(self):
    rec = None
    try:
        rec = getattr(self, "_b169_checkin_status", None) or _b169_checkin_from_cache(self)
    except Exception:
        rec = None

    if not rec:
        rec = {
            "date": _b169_today(),
            "status": "unknown",
            "msg": "未查询",
            "update_time_text": "",
        }

    status = str(rec.get("status") or "unknown")
    msg = str(rec.get("msg") or "")
    date = str(rec.get("date") or _b169_today())
    ut = str(rec.get("update_time_text") or "")

    if status == "done":
        name = "✅ 今日已打卡"
        remarks = ut or date
    elif status == "error":
        name = "❌ 打卡失败"
        remarks = msg or date
    else:
        name = "⚠️ 打卡状态未知"
        remarks = msg or date

    return {
        "vod_id": "__169BBS_CHECKIN_STATUS__",
        "vod_name": name,
        "vod_pic": "",
        "vod_remarks": remarks,
        "vod_content": "169BBS 打卡状态：%s；%s" % (status, msg),
    }


# -----------------------------
# init 包装
# -----------------------------
def _b169_init(self, extend=""):
    try:
        old = getattr(Spider, "_b169_old_init", None)
        if old:
            old(self, extend)
    except Exception as e:
        print("[169BBS init patch] old init error:", e)

    try:
        self.site_username = getattr(self, "site_username", "")
        self.site_password = getattr(self, "site_password", "")
        self.checkin_cache_file = getattr(self, "checkin_cache_file", "/tmp/169bbs_checkin_cache.json")

        if extend:
            ext = _b169_json.loads(str(extend))
            if isinstance(ext, dict):
                self.site_username = str(
                    ext.get("username", "") or
                    ext.get("site_username", "") or
                    ext.get("user", "") or
                    getattr(self, "site_username", "") or
                    ""
                ).strip()

                self.site_password = str(
                    ext.get("password", "") or
                    ext.get("site_password", "") or
                    ext.get("pass", "") or
                    getattr(self, "site_password", "") or
                    ""
                ).strip()

                if ext.get("checkin_cache_file"):
                    self.checkin_cache_file = str(ext.get("checkin_cache_file")).strip()
    except Exception as e:
        print("[169BBS init patch] parse extend error:", e)

    # 启动后台登录 + 打卡
    try:
        def _bg():
            try:
                _b169_login(self, force=False)
            except Exception as e:
                print("[169BBS bg login] error:", e)
            try:
                _b169_do_checkin(self, force=False)
            except Exception as e:
                print("[169BBS bg checkin] error:", e)

        t = _b169_threading.Thread(target=_bg, daemon=True)
        t.start()
    except Exception as e:
        print("[169BBS init patch] bg start error:", e)

    try:
        _b169_schedule_midnight(self)
    except Exception:
        pass

    print("[169BBS_AUTO_PATCH] init ok username=%s cache=%s" % (
        bool(getattr(self, "site_username", "")),
        getattr(self, "checkin_cache_file", ""),
    ))


# -----------------------------
# 首页固定打卡卡片
# -----------------------------
def _b169_homeContent(self, filter):
    try:
        old = getattr(Spider, "_b169_old_homeContent", None)
        if old:
            ret = old(self, filter)
        else:
            ret = {"class": []}

        if not isinstance(ret, dict):
            ret = {"class": []}

        old_list = ret.get("list") or []
        if not isinstance(old_list, list):
            old_list = []

        old_list = [
            x for x in old_list
            if str(x.get("vod_id", "")) != "__169BBS_CHECKIN_STATUS__"
        ]

        ret["list"] = [_b169_checkin_card(self)] + old_list
        return ret
    except Exception as e:
        print("[169BBS homeContent patch] error:", e)
        return {"class": [], "list": [_b169_checkin_card(self)]}


def _b169_homeVideoContent(self):
    """
    有些壳首页视频使用 homeVideoContent，而不是 homeContent['list']。
    """
    try:
        old = getattr(Spider, "_b169_old_homeVideoContent", None)
        if old:
            ret = old(self)
        else:
            ret = {"list": []}

        if not isinstance(ret, dict):
            ret = {"list": []}

        old_list = ret.get("list") or []
        if not isinstance(old_list, list):
            old_list = []

        old_list = [
            x for x in old_list
            if str(x.get("vod_id", "")) != "__169BBS_CHECKIN_STATUS__"
        ]

        ret["list"] = [_b169_checkin_card(self)] + old_list
        return ret
    except Exception as e:
        print("[169BBS homeVideoContent patch] error:", e)
        return {"list": [_b169_checkin_card(self)]}


# -----------------------------
# 搜索解析
# -----------------------------
def _b169_parse_search_html(self, html):
    vlist = []
    seen = set()

    try:
        if not html:
            return []

        if _b169_pq is None:
            print("[169BBS search] pyquery not available")
            return []

        data = _b169_pq(html)

        selectors = [
            # 169BBS 实测结构
            "#threadlist li.pbw h3.xs3 a[href*='viewthread']",
            ".slst li.pbw h3.xs3 a[href*='viewthread']",
            "li.pbw h3.xs3 a[href*='viewthread']",

            # Discuz 兼容
            ".slst li h3 a[href*='viewthread']",
            ".slst li a[href*='viewthread']",
            ".xs3 a[href*='viewthread']",
            ".pbw a[href*='viewthread']",

            # 兜底
            "a[href*='forum.php?mod=viewthread'][href*='tid=']",
            "a[href*='mod=viewthread'][href*='tid=']",
            "a[href^='thread-']",
        ]

        for sel in selectors:
            for a in data(sel).items():
                href = a.attr("href") or ""
                title = _b169_clean_text(self, a.text())

                if not href or not title:
                    continue

                link = _b169_fix_url(self, href)

                if "viewthread" not in link and not _b169_re.search(r"thread-\d+", link):
                    continue

                if any(x in title for x in [
                    "上一页", "下一页", "返回", "高级搜索", "搜索", "发帖"
                ]):
                    continue

                link = _b169_remove_mobile(self, link)

                uniq = link or title
                if uniq in seen:
                    continue
                seen.add(uniq)

                row = a.parents("li.pbw").eq(0)
                if len(row) == 0:
                    row = a.parents("li").eq(0)

                replies_views = ""
                desc = ""
                meta = ""

                try:
                    replies_views = _b169_clean_text(self, row("p.xg1").eq(0).text())
                except Exception:
                    replies_views = ""

                try:
                    desc = _b169_clean_text(self, row("p.byg_message_p").eq(0).text())
                except Exception:
                    desc = ""

                try:
                    ps = list(row("p").items())
                    if ps:
                        meta = _b169_clean_text(self, ps[-1].text())
                except Exception:
                    meta = ""

                remarks_parts = []
                if replies_views:
                    remarks_parts.append(replies_views)
                if meta:
                    remarks_parts.append(meta)

                remarks = " | ".join(remarks_parts)
                if not remarks and desc:
                    remarks = desc[:100]

                vlist.append({
                    "vod_id": link,
                    "vod_name": title,
                    "vod_pic": "",       # 关键：不带图，壳通常会按列表显示
                    "vod_remarks": remarks[:120],
                })

            if vlist:
                break

    except Exception as e:
        print("[169BBS parse search] error:", e)

    return vlist


def _b169_searchContent(self, key, quick):
    """
    169BBS 搜索修复：
    实测页面：
      /search.php?mod=forum&searchid=1641&orderby=lastpost&ascdesc=desc&searchsubmit=yes&kw=4k

    表单：
      method=post
      action=search.php?mod=forum
      formhash=xxxx
      srchtxt=关键词
      searchsubmit=yes

    返回结构：
      #threadlist li.pbw h3.xs3 a[href*='viewthread']
    """
    try:
        key = str(key or "").strip()
        if not key:
            return {"list": []}

        try:
            _b169_login(self, force=False)
        except Exception as e:
            print("[169BBS search] login error:", e)

        host = getattr(self, "host", "https://169bbs.com").rstrip("/")
        sess = getattr(self, "session", None)

        vlist = []

        # 1. 优先 GET srchtxt，让站点自己生成 searchid 并跳转
        urls = [
            host + "/search.php?mod=forum&srchtxt=%s&searchsubmit=yes" % _b169_quote(key),
            host + "/search.php?mod=forum&searchsubmit=yes&srchtxt=%s" % _b169_quote(key),
            host + "/search.php?mod=forum&orderby=lastpost&ascdesc=desc&searchsubmit=yes&kw=%s" % _b169_quote(key),
        ]

        for url in urls:
            try:
                html = _b169_get_html(self, url)
                print("[169BBS search GET] url=%s len=%s" % (url, len(html or "")))

                if not html:
                    continue

                if any(x in html for x in [
                    "请先登录",
                    "您需要登录",
                    "登录后",
                    "會員登錄",
                    "会员登录",
                ]):
                    print("[169BBS search GET] maybe need login")
                    continue

                vlist = _b169_parse_search_html(self, html)
                if vlist:
                    break

                # 如果页面是“正在跳转”，尝试抓跳转地址
                m = _b169_re.search(
                    r'href=["\']([^"\']*search\.php\?mod=forum[^"\']+)["\']',
                    html,
                    _b169_re.I
                )
                if m:
                    jump = _b169_fix_url(self, m.group(1).replace("&amp;", "&"))
                    html2 = _b169_get_html(self, jump)
                    vlist = _b169_parse_search_html(self, html2)
                    if vlist:
                        break

            except Exception as e:
                print("[169BBS search GET] error:", e)

        # 2. 兜底 POST 表单
        if not vlist and sess is not None:
            try:
                formhash = _b169_get_formhash(self)
                post_url = host + "/search.php?mod=forum"

                headers = dict(getattr(self, "headers", {}) or {})
                headers.update({
                    "Referer": host + "/",
                    "Origin": host,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": headers.get("User-Agent", "Mozilla/5.0"),
                })

                data = {
                    "formhash": formhash,
                    "srchtxt": key,
                    "searchsubmit": "yes",
                }

                r = sess.post(
                    post_url,
                    data=data,
                    headers=headers,
                    timeout=30,
                    allow_redirects=True,
                    verify=False,
                )

                html = r.text or ""

                print("[169BBS search POST] status=%s final=%s len=%s" % (
                    r.status_code,
                    r.url,
                    len(html),
                ))

                vlist = _b169_parse_search_html(self, html)

                if not vlist:
                    m = _b169_re.search(
                        r'href=["\']([^"\']*search\.php\?mod=forum[^"\']+)["\']',
                        html,
                        _b169_re.I
                    )
                    if m:
                        jump = _b169_fix_url(self, m.group(1).replace("&amp;", "&"))
                        html2 = _b169_get_html(self, jump)
                        vlist = _b169_parse_search_html(self, html2)

            except Exception as e:
                print("[169BBS search POST] error:", e)

        vlist = _b169_dedupe(self, vlist)

        # 搜索结果强制清空图片，尽量列表显示
        for x in vlist:
            x["vod_pic"] = ""

        print("[169BBS search] key=%s count=%s" % (key, len(vlist)))
        return {"list": vlist}

    except Exception as e:
        print("[169BBS search] error:", e)
        return {"list": []}


# -----------------------------
# 绑定补丁
# -----------------------------
try:
    Spider.init = _b169_init
    Spider.homeContent = _b169_homeContent
    Spider.homeVideoContent = _b169_homeVideoContent
    Spider.searchContent = _b169_searchContent

    Spider._b169_lcs_login = _b169_login
    Spider._b169_lcs_do_checkin = _b169_do_checkin
    Spider._b169_lcs_load_cache = _b169_load_cache
    Spider._b169_lcs_save_cache = _b169_save_cache

    print("[169BBS_AUTO_PATCH] loaded: login + qiandao + cache + home card + search")
except Exception as e:
    print("[169BBS_AUTO_PATCH] load error:", e)

# ===== 169BBS_AUTO_PATCH_END =====

# ===== 169BBS_SEARCH_FIX_BEGIN =====
# -*- coding: utf-8 -*-

import re as _b169sf_re
from urllib.parse import quote as _b169sf_quote, urljoin as _b169sf_urljoin

try:
    from pyquery import PyQuery as _b169sf_pq
except Exception:
    _b169sf_pq = None


def _b169sf_clean_text(self, s):
    try:
        if hasattr(self, "cleanText"):
            return self.cleanText(s)
    except Exception:
        pass
    s = str(s or "")
    s = s.replace("\xa0", " ").replace("&nbsp;", " ")
    s = _b169sf_re.sub(r"<[^>]+>", " ", s)
    s = _b169sf_re.sub(r"\s+", " ", s)
    return s.strip()


def _b169sf_fix_url(self, url):
    try:
        if hasattr(self, "fixUrl"):
            return self.fixUrl(url)
    except Exception:
        pass

    url = str(url or "").strip().replace("&amp;", "&")
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://") or url.startswith("https://"):
        return url

    host = getattr(self, "host", "https://169bbs.com").rstrip("/")
    return _b169sf_urljoin(host + "/", url)


def _b169sf_dedupe(self, arr):
    try:
        if hasattr(self, "dedupeVodList"):
            return self.dedupeVodList(arr)
    except Exception:
        pass

    out = []
    seen = set()
    for x in arr or []:
        k = x.get("vod_id") or x.get("vod_name")
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out


def _b169sf_formhash(html):
    html = html or ""
    pats = [
        r'name=["\']formhash["\']\s+value=["\']([^"\']+)["\']',
        r'value=["\']([^"\']+)["\']\s+name=["\']formhash["\']',
        r'formhash=([0-9a-fA-F]+)',
        r'formhash["\']?\s*[:=]\s*["\']([0-9a-fA-F]+)["\']',
    ]
    for p in pats:
        m = _b169sf_re.search(p, html, _b169sf_re.I)
        if m:
            return m.group(1).strip()
    return ""


def _b169sf_session_get(self, url, referer=None):
    host = getattr(self, "host", "https://169bbs.com").rstrip("/")
    sess = getattr(self, "session", None)

    headers = dict(getattr(self, "headers", {}) or {})
    headers.update({
        "User-Agent": headers.get("User-Agent", "Mozilla/5.0"),
        "Referer": referer or host + "/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })

    if sess is not None:
        r = sess.get(
            url,
            headers=headers,
            timeout=30,
            allow_redirects=True,
            verify=False,
        )
        return r.text or "", r.url or url, r.status_code

    # 没有 session 时才尝试原 getHtml
    try:
        if hasattr(self, "getHtml"):
            return self.getHtml(url), url, 0
    except Exception:
        pass

    return "", url, 0


def _b169sf_session_post(self, url, data, referer=None):
    host = getattr(self, "host", "https://169bbs.com").rstrip("/")
    sess = getattr(self, "session", None)
    if sess is None:
        return "", url, 0

    headers = dict(getattr(self, "headers", {}) or {})
    headers.update({
        "User-Agent": headers.get("User-Agent", "Mozilla/5.0"),
        "Referer": referer or host + "/search.php?mod=forum",
        "Origin": host,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })

    r = sess.post(
        url,
        data=data,
        headers=headers,
        timeout=30,
        allow_redirects=True,
        verify=False,
    )
    return r.text or "", r.url or url, r.status_code


def _b169sf_parse_by_pyquery(self, html):
    vlist = []
    seen = set()

    if not html or _b169sf_pq is None:
        return []

    try:
        data = _b169sf_pq(html)

        selectors = [
            "#threadlist li.pbw h3.xs3 a[href*='viewthread']",
            ".slst li.pbw h3.xs3 a[href*='viewthread']",
            "li.pbw h3.xs3 a[href*='viewthread']",
            ".slst li h3 a[href*='viewthread']",
            ".xs3 a[href*='viewthread']",
            ".pbw a[href*='viewthread']",
            "a[href*='forum.php?mod=viewthread'][href*='tid=']",
            "a[href*='mod=viewthread'][href*='tid=']",
        ]

        for sel in selectors:
            for a in data(sel).items():
                title = _b169sf_clean_text(self, a.text())
                href = a.attr("href") or ""
                if not title or not href:
                    continue

                link = _b169sf_fix_url(self, href)
                if "viewthread" not in link and "thread-" not in link:
                    continue

                if any(x in title for x in ["上一页", "下一页", "高级搜索", "搜索", "返回"]):
                    continue

                if link in seen:
                    continue
                seen.add(link)

                row = a.parents("li.pbw").eq(0)
                if len(row) == 0:
                    row = a.parents("li").eq(0)

                replies_views = ""
                desc = ""
                meta = ""

                try:
                    replies_views = _b169sf_clean_text(self, row("p.xg1").eq(0).text())
                except Exception:
                    pass

                try:
                    desc = _b169sf_clean_text(self, row("p.byg_message_p").eq(0).text())
                except Exception:
                    pass

                try:
                    ps = list(row("p").items())
                    if ps:
                        meta = _b169sf_clean_text(self, ps[-1].text())
                except Exception:
                    pass

                remarks = " | ".join([x for x in [replies_views, meta] if x])
                if not remarks and desc:
                    remarks = desc[:100]

                vlist.append({
                    "vod_id": link,
                    "vod_name": title,
                    "vod_pic": "",
                    "vod_remarks": remarks[:120],
                })

            if vlist:
                break

    except Exception as e:
        print("[169BBS_SEARCH_FIX] pyquery parse error:", e)

    return vlist


def _b169sf_parse_by_regex(self, html):
    """
    正则兜底，直接匹配：
    <li class="pbw z" id="3736012">
      <h3 class="xs3">
        <a href="forum.php?mod=viewthread&amp;tid=3736012...">标题</a>
    """
    vlist = []
    seen = set()

    if not html:
        return []

    try:
        blocks = _b169sf_re.findall(
            r'<li[^>]+class=["\'][^"\']*pbw[^"\']*["\'][^>]*>(.*?)</li>',
            html,
            _b169sf_re.I | _b169sf_re.S
        )

        print("[169BBS_SEARCH_FIX] regex blocks:", len(blocks))

        for block in blocks:
            m = _b169sf_re.search(
                r'<h3[^>]+class=["\'][^"\']*xs3[^"\']*["\'][^>]*>.*?<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                block,
                _b169sf_re.I | _b169sf_re.S
            )

            if not m:
                m = _b169sf_re.search(
                    r'<a[^>]+href=["\']([^"\']*forum\.php\?mod=viewthread[^"\']*tid=\d+[^"\']*)["\'][^>]*>(.*?)</a>',
                    block,
                    _b169sf_re.I | _b169sf_re.S
                )

            if not m:
                continue

            href = m.group(1).replace("&amp;", "&")
            title_html = m.group(2)
            title = _b169sf_clean_text(self, title_html)

            if not href or not title:
                continue

            link = _b169sf_fix_url(self, href)
            if link in seen:
                continue
            seen.add(link)

            rv = ""
            dm = ""

            mrv = _b169sf_re.search(r'<p[^>]+class=["\'][^"\']*xg1[^"\']*["\'][^>]*>(.*?)</p>', block, _b169sf_re.I | _b169sf_re.S)
            if mrv:
                rv = _b169sf_clean_text(self, mrv.group(1))

            md = _b169sf_re.search(r'<p[^>]+class=["\'][^"\']*byg_message_p[^"\']*["\'][^>]*>(.*?)</p>', block, _b169sf_re.I | _b169sf_re.S)
            if md:
                dm = _b169sf_clean_text(self, md.group(1))[:80]

            remarks = rv or dm

            vlist.append({
                "vod_id": link,
                "vod_name": title,
                "vod_pic": "",
                "vod_remarks": remarks[:120],
            })

    except Exception as e:
        print("[169BBS_SEARCH_FIX] regex parse error:", e)

    return vlist


def _b169sf_parse_search_html(self, html):
    arr = _b169sf_parse_by_pyquery(self, html)
    if arr:
        return arr
    return _b169sf_parse_by_regex(self, html)


def _b169sf_searchContent(self, key, quick):
    """
    二次修复版：
    1. 强制使用 session.get/session.post，不优先走原 getHtml；
    2. POST search.php?mod=forum 优先；
    3. 支持 formhash；
    4. pyquery + 正则双解析；
    5. 打印详细日志方便确认。
    """
    try:
        key = str(key or "").strip()
        if not key:
            return {"list": []}

        host = getattr(self, "host", "https://169bbs.com").rstrip("/")

        # 先尝试调用前面补丁里的登录函数
        try:
            if hasattr(self, "_b169_lcs_login"):
                self._b169_lcs_login(force=False)
        except Exception as e:
            print("[169BBS_SEARCH_FIX] login error:", e)

        vlist = []

        # 1. 打开搜索页拿 formhash
        search_page = host + "/search.php?mod=forum"
        html0, final0, code0 = _b169sf_session_get(self, search_page, host + "/")
        fh = _b169sf_formhash(html0)

        print("[169BBS_SEARCH_FIX] open search page code=%s final=%s len=%s formhash=%s" % (
            code0, final0, len(html0 or ""), bool(fh)
        ))

        # 2. POST 搜索，最符合你抓到的页面结构
        post_url = host + "/search.php?mod=forum"
        post_data = {
            "formhash": fh,
            "srchtxt": key,
            "searchsubmit": "yes",
        }

        html1, final1, code1 = _b169sf_session_post(self, post_url, post_data, search_page)

        print("[169BBS_SEARCH_FIX] POST code=%s final=%s len=%s" % (
            code1, final1, len(html1 or "")
        ))

        if html1:
            vlist = _b169sf_parse_search_html(self, html1)
            print("[169BBS_SEARCH_FIX] POST parse count=%s" % len(vlist))

        # 3. 如果 POST 返回跳转页，尝试找 searchid 地址
        if not vlist and html1:
            m = _b169sf_re.search(
                r'(search\.php\?mod=forum[^"\']*searchid=\d+[^"\']*)',
                html1,
                _b169sf_re.I
            )
            if m:
                jump = _b169sf_fix_url(self, m.group(1).replace("&amp;", "&"))
                htmlj, finalj, codej = _b169sf_session_get(self, jump, search_page)
                print("[169BBS_SEARCH_FIX] jump code=%s final=%s len=%s url=%s" % (
                    codej, finalj, len(htmlj or ""), jump
                ))
                vlist = _b169sf_parse_search_html(self, htmlj)
                print("[169BBS_SEARCH_FIX] jump parse count=%s" % len(vlist))

        # 4. GET srchtxt 兜底
        if not vlist:
            get_urls = [
                host + "/search.php?mod=forum&srchtxt=%s&searchsubmit=yes" % _b169sf_quote(key),
                host + "/search.php?mod=forum&searchsubmit=yes&srchtxt=%s" % _b169sf_quote(key),
                host + "/search.php?mod=forum&orderby=lastpost&ascdesc=desc&searchsubmit=yes&kw=%s" % _b169sf_quote(key),
            ]

            for url in get_urls:
                htmlg, finalg, codeg = _b169sf_session_get(self, url, host + "/")
                print("[169BBS_SEARCH_FIX] GET code=%s final=%s len=%s url=%s" % (
                    codeg, finalg, len(htmlg or ""), url
                ))

                vlist = _b169sf_parse_search_html(self, htmlg)
                print("[169BBS_SEARCH_FIX] GET parse count=%s" % len(vlist))

                if vlist:
                    break

        vlist = _b169sf_dedupe(self, vlist)

        for x in vlist:
            x["vod_pic"] = ""

        print("[169BBS_SEARCH_FIX] final key=%s count=%s" % (key, len(vlist)))
        return {"list": vlist}

    except Exception as e:
        print("[169BBS_SEARCH_FIX] search error:", e)
        return {"list": []}


try:
    Spider.searchContent = _b169sf_searchContent
    print("[169BBS_SEARCH_FIX] loaded")
except Exception as e:
    print("[169BBS_SEARCH_FIX] load error:", e)

# ===== 169BBS_SEARCH_FIX_END =====

# ===== 169BBS_FORCE_SEARCH_BEGIN =====
# -*- coding: utf-8 -*-

import os as _b169fs_os
import re as _b169fs_re
import time as _b169fs_time
from urllib.parse import quote as _b169fs_quote, urljoin as _b169fs_urljoin

try:
    from pyquery import PyQuery as _b169fs_pq
except Exception:
    _b169fs_pq = None


_B169FS_LOG = "/tmp/169bbs_debug.log"


def _b169fs_log(*args):
    msg = " ".join([str(x) for x in args])
    line = "[169BBS_FORCE_SEARCH] " + msg
    try:
        print(line)
    except Exception:
        pass
    try:
        with open(_B169FS_LOG, "a", encoding="utf-8") as f:
            f.write(time_str() + " " + line + "\n")
    except Exception:
        pass


def time_str():
    try:
        return _b169fs_time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _b169fs_clean(s):
    s = str(s or "")
    s = s.replace("&nbsp;", " ").replace("\xa0", " ")
    s = s.replace("&amp;", "&")
    s = _b169fs_re.sub(r"<script[\s\S]*?</script>", " ", s, flags=_b169fs_re.I)
    s = _b169fs_re.sub(r"<style[\s\S]*?</style>", " ", s, flags=_b169fs_re.I)
    s = _b169fs_re.sub(r"<[^>]+>", " ", s)
    s = _b169fs_re.sub(r"\s+", " ", s)
    return s.strip()


def _b169fs_fix_url(self, url):
    url = str(url or "").strip().replace("&amp;", "&")
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    host = getattr(self, "host", "https://169bbs.com").rstrip("/")
    return _b169fs_urljoin(host + "/", url)


def _b169fs_formhash(html):
    html = html or ""
    pats = [
        r'name=["\']formhash["\']\s+value=["\']([^"\']+)["\']',
        r'value=["\']([^"\']+)["\']\s+name=["\']formhash["\']',
        r'formhash=([0-9a-fA-F]+)',
        r'formhash["\']?\s*[:=]\s*["\']([0-9a-fA-F]+)["\']',
    ]
    for p in pats:
        m = _b169fs_re.search(p, html, _b169fs_re.I)
        if m:
            return m.group(1).strip()
    return ""


def _b169fs_get_session(self):
    sess = getattr(self, "session", None)
    if sess is not None:
        return sess

    try:
        import requests
        sess = requests.Session()
        self.session = sess
        return sess
    except Exception as e:
        _b169fs_log("create session error:", e)
        return None


def _b169fs_headers(self, referer=None):
    host = getattr(self, "host", "https://169bbs.com").rstrip("/")
    h = dict(getattr(self, "headers", {}) or {})
    h.update({
        "User-Agent": h.get("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": referer or host + "/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    return h


def _b169fs_get(self, url, referer=None):
    sess = _b169fs_get_session(self)
    if sess is None:
        return "", url, 0

    try:
        r = sess.get(
            url,
            headers=_b169fs_headers(self, referer),
            timeout=30,
            allow_redirects=True,
            verify=False,
        )
        return r.text or "", r.url or url, r.status_code
    except Exception as e:
        _b169fs_log("GET error:", url, e)
        return "", url, 0


def _b169fs_post(self, url, data, referer=None):
    sess = _b169fs_get_session(self)
    if sess is None:
        return "", url, 0

    host = getattr(self, "host", "https://169bbs.com").rstrip("/")
    h = _b169fs_headers(self, referer)
    h.update({
        "Origin": host,
        "Content-Type": "application/x-www-form-urlencoded",
    })

    try:
        r = sess.post(
            url,
            data=data,
            headers=h,
            timeout=30,
            allow_redirects=True,
            verify=False,
        )
        return r.text or "", r.url or url, r.status_code
    except Exception as e:
        _b169fs_log("POST error:", url, e)
        return "", url, 0


def _b169fs_parse(html, self=None):
    arr = []
    seen = set()

    if not html:
        return arr

    # 先用 pyquery
    if _b169fs_pq is not None:
        try:
            doc = _b169fs_pq(html)
            selectors = [
                "#threadlist li.pbw h3.xs3 a[href*='viewthread']",
                ".slst li.pbw h3.xs3 a[href*='viewthread']",
                "li.pbw h3.xs3 a[href*='viewthread']",
                ".xs3 a[href*='viewthread']",
                ".pbw a[href*='viewthread']",
                "a[href*='forum.php?mod=viewthread'][href*='tid=']",
                "a[href*='mod=viewthread'][href*='tid=']",
            ]

            for sel in selectors:
                for a in doc(sel).items():
                    href = a.attr("href") or ""
                    title = _b169fs_clean(a.text())
                    if not href or not title:
                        continue

                    link = _b169fs_fix_url(self, href) if self else href

                    if "viewthread" not in link:
                        continue

                    if link in seen:
                        continue
                    seen.add(link)

                    row = a.parents("li.pbw").eq(0)
                    if len(row) == 0:
                        row = a.parents("li").eq(0)

                    remarks = ""
                    try:
                        rv = _b169fs_clean(row("p.xg1").eq(0).text())
                        ps = list(row("p").items())
                        meta = _b169fs_clean(ps[-1].text()) if ps else ""
                        remarks = " | ".join([x for x in [rv, meta] if x])
                    except Exception:
                        remarks = ""

                    arr.append({
                        "vod_id": link,
                        "vod_name": title,
                        "vod_pic": "",
                        "vod_remarks": remarks[:120],
                    })

                if arr:
                    _b169fs_log("pyquery selector hit:", sel, "count:", len(arr))
                    return arr

        except Exception as e:
            _b169fs_log("pyquery parse error:", e)

    # 正则兜底：直接按你发的 HTML 结构抓
    try:
        blocks = _b169fs_re.findall(
            r'<li[^>]+class=["\'][^"\']*pbw[^"\']*["\'][^>]*>([\s\S]*?)</li>',
            html,
            _b169fs_re.I
        )
        _b169fs_log("regex li.pbw blocks:", len(blocks))

        for block in blocks:
            m = _b169fs_re.search(
                r'<h3[^>]+class=["\'][^"\']*xs3[^"\']*["\'][^>]*>[\s\S]*?<a[^>]+href=["\']([^"\']*forum\.php\?mod=viewthread[^"\']*tid=\d+[^"\']*)["\'][^>]*>([\s\S]*?)</a>',
                block,
                _b169fs_re.I
            )
            if not m:
                m = _b169fs_re.search(
                    r'<a[^>]+href=["\']([^"\']*forum\.php\?mod=viewthread[^"\']*tid=\d+[^"\']*)["\'][^>]*>([\s\S]*?)</a>',
                    block,
                    _b169fs_re.I
                )
            if not m:
                continue

            href = m.group(1).replace("&amp;", "&")
            title = _b169fs_clean(m.group(2))
            if not href or not title:
                continue

            link = _b169fs_fix_url(self, href) if self else href
            if link in seen:
                continue
            seen.add(link)

            remarks = ""
            rv = _b169fs_re.search(
                r'<p[^>]+class=["\'][^"\']*xg1[^"\']*["\'][^>]*>([\s\S]*?)</p>',
                block,
                _b169fs_re.I
            )
            if rv:
                remarks = _b169fs_clean(rv.group(1))

            arr.append({
                "vod_id": link,
                "vod_name": title,
                "vod_pic": "",
                "vod_remarks": remarks[:120],
            })

    except Exception as e:
        _b169fs_log("regex parse error:", e)

    return arr


def _b169fs_do_search(self, key, pg="1"):
    key = str(key or "").strip()
    pg = str(pg or "1").strip()

    _b169fs_log("do_search called key=", key, "pg=", pg)

    if not key:
        return {"list": []}

    host = getattr(self, "host", "https://169bbs.com").rstrip("/")

    # 尝试调用之前补丁里的登录/打卡登录
    try:
        if hasattr(self, "_b169_lcs_login"):
            _b169fs_log("call _b169_lcs_login")
            self._b169_lcs_login(force=False)
    except Exception as e:
        _b169fs_log("_b169_lcs_login error:", e)

    result = []

    # 1. 打开搜索页拿 formhash
    search_page = host + "/search.php?mod=forum"
    html0, final0, code0 = _b169fs_get(self, search_page, host + "/")
    fh = _b169fs_formhash(html0)

    _b169fs_log("open search page code=", code0, "final=", final0, "len=", len(html0 or ""), "formhash=", bool(fh))

    # 2. 按网页表单 POST。这个最符合你发的 HTML。
    post_url = host + "/search.php?mod=forum"

    post_data = {
        "formhash": fh,
        "srchtxt": key,
        "searchsubmit": "yes",
    }

    html1, final1, code1 = _b169fs_post(post_url, post_data, search_page)

    _b169fs_log("POST search code=", code1, "final=", final1, "len=", len(html1 or ""))

    if html1:
        result = _b169fs_parse(html1, self)
        _b169fs_log("POST parse count=", len(result))

    # 3. 如果 POST 后 final_url 已经是 searchid，但解析不到，重新 GET final_url
    if not result and final1 and "search.php" in final1:
        html2, final2, code2 = _b169fs_get(self, final1, search_page)
        _b169fs_log("GET final_url code=", code2, "final=", final2, "len=", len(html2 or ""))
        result = _b169fs_parse(html2, self)
        _b169fs_log("GET final_url parse count=", len(result))

    # 4. 从跳转页里找 searchid
    if not result and html1:
        m = _b169fs_re.search(
            r'(search\.php\?mod=forum[^"\']*searchid=\d+[^"\']*)',
            html1,
            _b169fs_re.I
        )
        if m:
            jump = _b169fs_fix_url(self, m.group(1).replace("&amp;", "&"))
            htmlj, finalj, codej = _b169fs_get(self, jump, search_page)
            _b169fs_log("GET jump code=", codej, "final=", finalj, "len=", len(htmlj or ""), "jump=", jump)
            result = _b169fs_parse(htmlj, self)
            _b169fs_log("GET jump parse count=", len(result))

    # 5. GET 兜底。网页会跳转，requests 会跟随。
    if not result:
        urls = [
            host + "/search.php?mod=forum&srchtxt=%s&searchsubmit=yes" % _b169fs_quote(key),
            host + "/search.php?mod=forum&searchsubmit=yes&srchtxt=%s" % _b169fs_quote(key),
            host + "/search.php?mod=forum&orderby=lastpost&ascdesc=desc&searchsubmit=yes&kw=%s" % _b169fs_quote(key),
        ]

        for url in urls:
            htmlg, finalg, codeg = _b169fs_get(self, url, host + "/")
            _b169fs_log("GET fallback code=", codeg, "final=", finalg, "len=", len(htmlg or ""), "url=", url)
            result = _b169fs_parse(htmlg, self)
            _b169fs_log("GET fallback parse count=", len(result))
            if result:
                break

    # 去重
    out = []
    seen = set()
    for x in result:
        k = x.get("vod_id") or x.get("vod_name")
        if not k or k in seen:
            continue
        seen.add(k)
        x["vod_pic"] = ""
        out.append(x)

    _b169fs_log("final search count=", len(out), "key=", key)

    return {
        "list": out,
        "page": int(pg) if pg.isdigit() else 1,
        "pagecount": 1,
        "limit": len(out),
        "total": len(out),
    }


# 保存旧方法
try:
    if not hasattr(Spider, "_b169fs_old_homeContent"):
        Spider._b169fs_old_homeContent = Spider.homeContent
except Exception:
    pass

try:
    if not hasattr(Spider, "_b169fs_old_searchContent"):
        Spider._b169fs_old_searchContent = Spider.searchContent
except Exception:
    pass


def _b169fs_homeContent(self, filter):
    _b169fs_log("homeContent called, force searchable")

    try:
        old = getattr(Spider, "_b169fs_old_homeContent", None)
        if old:
            ret = old(self, filter)
        else:
            ret = {"class": []}
    except Exception as e:
        _b169fs_log("old homeContent error:", e)
        ret = {"class": []}

    if not isinstance(ret, dict):
        ret = {"class": []}

    classes = ret.get("class") or []
    if isinstance(classes, list):
        for c in classes:
            if isinstance(c, dict):
                c["searchable"] = 1
                c["filterable"] = c.get("filterable", 0)

    ret["class"] = classes
    return ret


def _b169fs_searchContent(self, key, quick):
    _b169fs_log("searchContent called key=", key, "quick=", quick)
    return _b169fs_do_search(self, key, "1")


def _b169fs_searchContentPage(self, key, quick, pg):
    _b169fs_log("searchContentPage called key=", key, "quick=", quick, "pg=", pg)
    return _b169fs_do_search(self, key, pg)


def _b169fs_search(self, key, quick=False):
    _b169fs_log("search called key=", key, "quick=", quick)
    return _b169fs_do_search(self, key, "1")


try:
    Spider.homeContent = _b169fs_homeContent
    Spider.searchContent = _b169fs_searchContent
    Spider.searchContentPage = _b169fs_searchContentPage
    Spider.search = _b169fs_search

    _b169fs_log("loaded ok, log file:", _B169FS_LOG)
except Exception as e:
    _b169fs_log("load error:", e)

# ===== 169BBS_FORCE_SEARCH_END =====

# ===== 169BBS_RUNTIME_LOG_PATH_FIX_BEGIN =====
# -*- coding: utf-8 -*-

import os as _b169rl_os
import json as _b169rl_json
import time as _b169rl_time


def _b169_runtime_now():
    try:
        return _b169rl_time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _b169_get_debug_log_file(self=None):
    """
    运行环境日志文件路径：
    1. 优先使用 ext 里的 debug_log_file；
    2. 其次使用 checkin_cache_file 同目录；
    3. 其次使用 /tmp/169bbs_debug.log；
    4. 如果都不可写，则返回空字符串。
    """
    candidates = []

    try:
        if self is not None:
            p = str(getattr(self, "debug_log_file", "") or "").strip()
            if p:
                candidates.append(p)

            c = str(getattr(self, "checkin_cache_file", "") or "").strip()
            if c:
                d = _b169rl_os.path.dirname(c)
                if d:
                    candidates.append(_b169rl_os.path.join(d, "169bbs_debug.log"))
    except Exception:
        pass

    candidates.extend([
        "/storage/emulated/0/Download/169bbs_debug.log",
        "/sdcard/Download/169bbs_debug.log",
        "/tmp/169bbs_debug.log",
        "169bbs_debug.log",
    ])

    for p in candidates:
        try:
            if not p:
                continue
            d = _b169rl_os.path.dirname(p)
            if d and not _b169rl_os.path.exists(d):
                _b169rl_os.makedirs(d, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write("")
            return p
        except Exception:
            continue

    return ""


def _b169_runtime_log(self, *args):
    msg = " ".join([str(x) for x in args])
    line = "[169BBS_RUNTIME] " + msg

    try:
        print(line)
    except Exception:
        pass

    try:
        p = _b169_get_debug_log_file(self)
        if p:
            with open(p, "a", encoding="utf-8") as f:
                f.write(_b169_runtime_now() + " " + line + "\n")
    except Exception:
        pass


# 补强 init：从 ext 读取 debug_log_file
try:
    if not hasattr(Spider, "_b169rl_old_init"):
        Spider._b169rl_old_init = Spider.init
except Exception:
    pass


def _b169rl_init(self, extend=""):
    try:
        old = getattr(Spider, "_b169rl_old_init", None)
        if old:
            old(self, extend)
    except Exception as e:
        try:
            print("[169BBS_RUNTIME] old init error:", e)
        except Exception:
            pass

    try:
        if extend:
            ext = _b169rl_json.loads(str(extend))
            if isinstance(ext, dict):
                if ext.get("debug_log_file"):
                    self.debug_log_file = str(ext.get("debug_log_file")).strip()

                if ext.get("checkin_cache_file"):
                    self.checkin_cache_file = str(ext.get("checkin_cache_file")).strip()
    except Exception as e:
        try:
            print("[169BBS_RUNTIME] parse ext error:", e)
        except Exception:
            pass

    try:
        _b169_runtime_log(
            self,
            "init ok",
            "debug_log_file=" + str(_b169_get_debug_log_file(self)),
            "checkin_cache_file=" + str(getattr(self, "checkin_cache_file", "")),
        )
    except Exception:
        pass


try:
    Spider.init = _b169rl_init
    Spider._b169_runtime_log = _b169_runtime_log
    Spider._b169_get_debug_log_file = _b169_get_debug_log_file
    print("[169BBS_RUNTIME] log path fix loaded")
except Exception as e:
    try:
        print("[169BBS_RUNTIME] log path fix load error:", e)
    except Exception:
        pass

# ===== 169BBS_RUNTIME_LOG_PATH_FIX_END =====
