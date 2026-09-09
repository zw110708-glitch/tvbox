# coding=utf-8
import json, time, ssl, re, base64, random
from base.spider import Spider
import requests
from urllib.parse import quote, unquote

try:
    from Crypto.Cipher import AES
except Exception:
    AES = None


class Spider(Spider):

    def getName(self):
        return "抖阴小说"

    def init(self, extend=""):
        # ---- 代理三行（由 extend 传，没传就直连）----
        try:
            config = json.loads(extend) if isinstance(extend, str) else (extend or {})
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        self.plp = config.get('plp', '')
        self.proxy = config.get('proxy', {})

        self.publish_url = "https://18dyw.net/"
        self.ua = "Mozilla/5.0 (Linux; Android 16; 2510DRK44C Build/BP2A.250605.031.A3) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/143.0.7499.192 Mobile Safari/537.36"
        self.headers = {
            "User-Agent": self.ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.session = requests.Session()
        try:
            ssl._create_default_https_context = ssl._create_unverified_context
        except Exception:
            pass
        self.aes_key = b"f5d965df75336270"
        self.aes_iv = b"97b60394abc2fbe1"
        self.host = ""
        self._host_cache_time = 0
        self._resolve_domain()

    def _get_host(self):
        if self.host and self._host_cache_time and time.time() - self._host_cache_time < 1800:
            return self.host
        self._resolve_domain()
        return self.host

    def _resolve_domain(self):
        headers = {"User-Agent": self.ua}
        try:
            r = requests.get("https://dys18.com/", headers=headers, timeout=8, verify=False, proxies=self.proxy)
            if r.status_code == 200 and len(r.text) > 1000:
                self.host = "https://dys18.com"
                self._host_cache_time = time.time()
                self.headers.update({"Referer": f"{self.host}/", "Origin": self.host})
                return
        except Exception:
            pass
        main_domain = ""
        backup_domain = ""
        try:
            r = requests.get(self.publish_url, headers=headers, timeout=10, verify=False, proxies=self.proxy)
            if r.status_code == 200:
                m = re.search(r"var\s+mainDomain\s*=\s*'([^']+)'", r.text)
                if m:
                    main_domain = m.group(1)
                m = re.search(r"var\s+backupDomain\s*=\s*'([^']+)'", r.text)
                if m:
                    backup_domain = m.group(1)
        except Exception:
            pass
        chars = "abcdefghjkmnpqrstuvwxy23456789"
        for _ in range(10):
            prefix = ''.join(random.choices(chars, k=4))
            for suffix in (main_domain, backup_domain):
                if not suffix:
                    continue
                domain = f"https://{prefix}.{suffix}"
                try:
                    r = requests.get(domain, headers=headers, timeout=5, verify=False, proxies=self.proxy)
                    if r.status_code == 200 and len(r.text) > 1000:
                        self.host = domain.rstrip('/')
                        self._host_cache_time = time.time()
                        self.headers.update({"Referer": f"{self.host}/", "Origin": self.host})
                        return
                except Exception:
                    continue

    def _req(self, url):
        self._get_host()
        if not self.host and not url.startswith("http"):
            return ""
        try:
            r = self.session.get(url, headers=self.headers, timeout=15, verify=False, proxies=self.proxy)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
        return ""

    # 小说分类（实测 /novel 导航，14 类）
    CATS = {
        "cyzs": "穿越重生",
        "dfxh": "东方玄幻",
        "dsjq": "都市激情",
        "jdwx": "经典武侠",
        "jtll": "家庭乱伦",
        "kxhx": "科学幻想",
        "lsjk": "历史架空",
        "trgb": "同人改编",
        "xcaq": "乡村爱情",
        "xfmh": "西方魔幻",
        "xtyn": "系统异能",
        "xycs": "校园春色",
        "xzxs": "贤者小说",
        "ylmx": "娱乐明星",
    }
    SORTS = [
        {"n": "最新", "v": "newest"},
        {"n": "热门", "v": "hot"},
    ]

    def _cr(self, cid, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': cid, 'name': name}, ensure_ascii=False), name)

    def _parse_novel_list(self, html):
        result = []
        for m in re.finditer(r'<li>\s*<a href="/novel/detail/(\d+)"[^>]*>(.*?)</li>', html, re.DOTALL):
            nid = m.group(1)
            inner = m.group(2)
            name = ""
            nm = re.search(r'<h3>([^<]+)</h3>', inner)
            if nm:
                name = nm.group(1).strip()
            if not name:
                am = re.search(r'alt="([^"]*)"', inner)
                if am:
                    name = am.group(1).strip()
            if not name:
                name = nid
            img = ""
            im = re.search(r'data-src="([^"]+)"', inner)
            if im:
                img = self._img_proxy(im.group(1))
            remarks = ""
            rm = re.search(r'<span>([^<]+)</span>', inner)
            if rm:
                remarks = rm.group(1).strip()
            result.append({
                "vod_id": nid,
                "vod_name": name,
                "vod_pic": img,
                "vod_remarks": remarks,
            })
        seen = set()
        out = []
        for r in result:
            if r["vod_id"] not in seen:
                seen.add(r["vod_id"])
                out.append(r)
        return out

    def _extract_max_page(self, html):
        total_m = re.search(r'data-rec-total="(\d+)"', html)
        per_page_m = re.search(r'data-rec-per-page="(\d+)"', html)
        if total_m and per_page_m:
            total = int(total_m.group(1))
            per_page = int(per_page_m.group(1))
            if per_page > 0:
                return (total + per_page - 1) // per_page
        if re.search(r'<link rel="next"', html):
            return 999
        return 1

    def _parse_ext(self, ext):
        if not ext:
            return {}
        if isinstance(ext, dict):
            return ext
        if isinstance(ext, str):
            ext = ext.strip()
            if not ext or ext in ("{}", "null", "undefined"):
                return {}
            try:
                return json.loads(ext)
            except Exception:
                result = {}
                for part in ext.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        result[k] = v
                return result
        return {}

    def homeContent(self, filter):
        classes = []
        filters = {}
        for cid, cname in self.CATS.items():
            classes.append({"type_id": cid, "type_name": cname})
            filters[cid] = [{"key": "by", "name": "排序", "value": self.SORTS}]
        html = self._req(f"{self.host}/novel")
        vods = self._parse_novel_list(html)
        return {"class": classes, "list": vods, "filters": filters}

    def homeVideoContent(self):
        html = self._req(f"{self.host}/novel")
        return {"list": self._parse_novel_list(html)}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        ext = self._parse_ext(extend)
        # 标签跳转：novel_tag/{标签}
        if str(tid).startswith("novel_tag/"):
            tag = unquote(str(tid)[10:])
            html = self._req(f"{self.host}/novel/tag/{quote(tag, safe='')}/{pg}")
            vods = self._parse_novel_list(html)
            pc = self._extract_max_page(html)
            return {"list": vods, "page": pg, "pagecount": pc, "limit": 24, "total": pc * 24}
        # 分类：/{slug}/{sort}/{pg}
        by = ext.get("by", "newest")
        if by not in ("newest", "hot"):
            by = "newest"
        html = self._req(f"{self.host}/novel/{tid}/{by}/{pg}")
        vods = self._parse_novel_list(html)
        pc = self._extract_max_page(html)
        return {"list": vods, "page": pg, "pagecount": pc, "limit": 24, "total": pc * 24}

    def detailContent(self, ids):
        nid = str(ids[0]).strip()
        html = self._req(f"{self.host}/novel/detail/{nid}")
        if not html:
            return {"list": []}

        # 书名
        title = ""
        hm = re.search(r'"headline"\s*:\s*"([^"]+)"', html)
        if hm:
            title = hm.group(1)
        if not title:
            h1_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if h1_m:
                title = re.sub(r'<[^>]+>', '', h1_m.group(1)).strip()

        # 封面（走本地代理）
        img = ""
        m = re.search(r'"image"\s*:\s*\[\s*"([^"]+)"', html)
        if m:
            img = self._img_proxy(m.group(1))
        if not img:
            m = re.search(r'data-src="([^"]+\.(?:jpe?g|png|webp)[^"]*)"', html)
            if m:
                img = self._img_proxy(m.group(1))

        # 作者 / 观看 / 更新时间（详情页 HTML 交叉嵌套，用不闭合正则）
        author = ""
        m = re.search(r'作者：.{0,20}?<strong>([^<]+)', html, re.DOTALL)
        if m:
            author = m.group(1).strip()
        views = ""
        m = re.search(r'观看：.{0,20}?<span>([\d,]+)', html, re.DOTALL)
        if m:
            views = m.group(1).strip()
        update = ""
        m = re.search(r'最新：\s*([^<]+)', html)
        if m:
            update = m.group(1).strip()

        # 简介
        desc = ""
        m = re.search(r'"description"\s*:\s*"([^"]+)"', html)
        if m:
            desc = m.group(1).strip()
        if desc.startswith("简介"):
            desc = desc.lstrip("简介：").lstrip("简介:").strip()

        # 标签（可点击，跳 novel_tag）
        tags = []
        for tm in re.finditer(r'href="/novel/tag/([^"]+)"', html):
            tag = unquote(tm.group(1)).strip()
            if tag and tag not in tags:
                tags.append(tag)

        # 章节列表（/novel/read/{cid}，跳过"开始阅读"按钮，按 cid 去重）
        chapters = {}
        order = []
        for cm in re.finditer(r'href="/novel/read/(\d+)"[^>]*>(.*?)</a>', html, re.DOTALL):
            cid = cm.group(1)
            ctitle = re.sub(r'<[^>]+>', '', cm.group(2)).strip()
            if not ctitle:
                continue
            if cid in chapters:
                if chapters[cid] == "开始阅读" and ctitle != "开始阅读":
                    chapters[cid] = ctitle
                continue
            order.append(cid)
            chapters[cid] = ctitle
        play_url = ""
        if order:
            segs = []
            for cid in order:
                ct = chapters[cid]
                if ct == "开始阅读":
                    ct = "正文"
                segs.append(f"{ct}${self.host}/novel/read/{cid}")
            play_url = "#".join(segs)

        remarks = " ".join(filter(None, ["作者：" + author if author else "", "观看：" + views if views else "", update]))
        vod_actor = " ".join([self._cr("novel_tag/" + quote(t, safe=''), t) for t in tags[:8]]) if tags else ""

        return {"list": [{
            "vod_id": nid,
            "vod_name": title or nid,
            "vod_pic": img,
            "type_name": "小说",
            "vod_actor": vod_actor,
            "vod_remarks": remarks,
            "vod_content": desc or title,
            "vod_play_from": "正文" if play_url else "",
            "vod_play_url": play_url,
        }]}

    def searchContent(self, key, quick, pg="1"):
        key = (key or "").strip()
        if not key:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 24, "total": 0}
        kq = quote(key, safe='')
        # 站点 bug：/novel/search/{key}/{pg} 分页 404，只抓第一页
        html = self._req(f"{self.host}/novel/search/{kq}")
        vods = self._parse_novel_list(html)
        return {"list": vods, "page": 1, "pagecount": 1, "limit": 24, "total": len(vods)}

    def playerContent(self, flag, id, vipFlags):
        url = id
        if url.startswith("/"):
            url = f"{self.host}{url}"
        elif not url.startswith("http"):
            url = f"{self.host}/{url}"
        if "/novel/read/" in url:
            # 默影视小说：请求章节页，提取标题+正文，走 novel:// 协议进阅读模块
            html = self._req(url)
            if not html:
                return {"parse": 0, "playUrl": "", "url": "", "header": ""}
            title = "正文"
            tm = re.search(r'<h1[^>]*>\s*([^<]+)', html)
            if tm:
                title = tm.group(1).strip()
            content = ""
            bm = re.search(r'<article class="text-xl whitespace-pre-line">(.*?)</article>', html, re.DOTALL)
            if bm:
                content = bm.group(1).strip()
            data = {"title": title, "content": content}
            return {"parse": 0, "playUrl": "", "url": "novel://" + json.dumps(data, ensure_ascii=False), "header": ""}
        return {"parse": 0, "playUrl": "", "url": "", "header": ""}

    def localProxy(self, param):
        if param.get("type") == "img":
            try:
                url = self._d64(param.get("url", ""))
                if not url:
                    return [404, "text/plain", "", ""]
                res = requests.get(url, headers=self.headers, timeout=10, verify=False, proxies=self.proxy)
                if res.status_code == 200:
                    data = self.decrypt_image(res.content)
                    ext = self.detect_extension(data)
                    mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif', 'webp': 'image/webp'}
                    return [200, mime.get(ext, 'image/jpeg'), data, ""]
            except Exception as e:
                print(f"[抖阴小说] localProxy img error: {e}")
            return [404, "text/plain", "", ""]
        return [404, "text/plain", "", ""]

    def _img_proxy(self, img_url):
        if not img_url:
            return ""
        return f"{self.getProxyUrl()}&url={self._e64(img_url)}&type=img"

    def decrypt_image(self, encrypted_data):
        if AES is None:
            return encrypted_data
        dec = AES.new(self.aes_key, AES.MODE_CBC, self.aes_iv).decrypt(encrypted_data)
        pad = dec[-1] if dec else 0
        if 1 <= pad <= 16 and dec[-pad:] == bytes([pad]) * pad:
            dec = dec[:-pad]
        else:
            dec = dec.rstrip(b'\x00')
        return dec

    def detect_extension(self, data):
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return 'png'
        if data[:3] == b'\xff\xd8\xff':
            return 'jpg'
        if data[:6] in (b'GIF87a', b'GIF89a'):
            return 'gif'
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return 'webp'
        return 'bin'

    def _e64(self, text):
        try:
            return base64.b64encode(text.encode("utf-8")).decode("utf-8")
        except Exception:
            return ""

    def _d64(self, text):
        try:
            return base64.b64decode(text.encode("utf-8")).decode("utf-8")
        except Exception:
            return ""
