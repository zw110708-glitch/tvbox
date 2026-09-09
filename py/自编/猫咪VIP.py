"""
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: '猫咪VIP',
  lang: 'hipy',
})
"""

# -*- coding: utf-8 -*-
"""
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: '猫咪VIP',
  lang: 'hipy',
})
"""

import json, time, re, sys, base64, hashlib, threading, traceback
from urllib.parse import urljoin, urlencode, urlsplit, quote, unquote
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from concurrent.futures import ThreadPoolExecutor
import requests
from requests.adapters import HTTPAdapter
import urllib3

# ========== 新增导入：OK影视基类 ==========
from base.spider import Spider as BaseSpider

urllib3.disable_warnings()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

SEARCH_SIGN_KEY = "JkI2OG1AJXpnMzJfJXUqdkhVbEU0V2tTJjFKNiUleG1VQGZO"
PLAY_SIGN_KEY = "D7hGKHnWThaECaQ3ji4XyAF3MfYKJ53M"

# 严格过滤仅保留有效视频频道（排除 topic / adv 等 403 频道）
ALLOWED_CHANNELS = ("vip", "media_video", "remen", "remen2", "remen3", "shipin")

# ==================== 日志输出 ====================
def _log(msg):
    try:
        sys.stderr.write(f"[猫咪VIP-LOG] {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass

# ==================== 全局高性能图片连接池与预热机制 ====================
_img_session = requests.Session()
_img_adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=1, pool_block=False)
_img_session.mount("http://", _img_adapter)
_img_session.mount("https://", _img_adapter)
_img_session.verify = False

_IMG_CACHE = {}
_IMG_CACHE_LOCK = threading.Lock()
_PREFETCH_POOL = ThreadPoolExecutor(max_workers=16)

# ==================== AES 加解密辅助 ====================
def _aes_decrypt(key, data, iv=None):
    if not data or len(data) < 16:
        return data
    try:
        from Crypto.Cipher import AES
        cipher = AES.new(key, AES.MODE_CBC, iv) if iv else AES.new(key, AES.MODE_ECB)
        raw = cipher.decrypt(data)
        pad = raw[-1] if raw else 0
        if 0 < pad <= 16 and raw.endswith(bytes([pad]) * pad):
            return raw[:-pad]
        return raw
    except Exception:
        pass

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv) if iv else modes.ECB(), backend=default_backend())
        decryptor = cipher.decryptor()
        raw = decryptor.update(data) + decryptor.finalize()
        pad = raw[-1] if raw else 0
        if 0 < pad <= 16 and raw.endswith(bytes([pad]) * pad):
            return raw[:-pad]
        return raw
    except Exception:
        pass

    return data

def _aes_encrypt(key, data, iv=None):
    pad = 16 - len(data) % 16
    padded = data + bytes([pad]) * pad
    try:
        from Crypto.Cipher import AES
        cipher = AES.new(key, AES.MODE_CBC, iv) if iv else AES.new(key, AES.MODE_ECB)
        return cipher.encrypt(padded)
    except Exception:
        pass

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv) if iv else modes.ECB(), backend=default_backend())
        encryptor = cipher.encryptor()
        return encryptor.update(padded) + encryptor.finalize()
    except Exception:
        pass

    return padded

# ==================== 图片下载与解密核心 ====================
def _fetch_and_cache_img(url, host="https://r0hiexcmqu1o.cc"):
    if not url or not url.startswith("http"):
        return None
    if "@" in url:
        url = url.split("@")[0]

    with _IMG_CACHE_LOCK:
        if url in _IMG_CACHE:
            return _IMG_CACHE[url]

    try:
        req_headers = {
            "Referer": host + "/",
            "User-Agent": UA,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        }
        r = _img_session.get(url, headers=req_headers, timeout=(3.0, 5.0), verify=False, allow_redirects=True)
        if r.status_code != 200:
            return None

        content = r.content
        dec = Spider._decrypt_image_fast(content)
        mime = Spider._detect_image_mime(dec)

        with _IMG_CACHE_LOCK:
            if len(_IMG_CACHE) > 1000:
                _IMG_CACHE.clear()
            _IMG_CACHE[url] = (mime, dec)

        return (mime, dec)
    except Exception:
        return None

# ==================== 内置轻量代理 ====================
_proxy_port = 0
_proxy_started = False

class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class _ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            real_url = unquote(self.path[1:])
            if not real_url or not real_url.startswith("http"):
                self.send_response(404); self.end_headers(); return
            
            res = _fetch_and_cache_img(real_url)
            if res:
                mime, dec = res
                self.send_response(200)
                self.send_header("Content-Type", f"image/{mime}")
                self.send_header("Content-Length", str(len(dec)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(dec)
            else:
                self.send_response(404); self.end_headers()
        except Exception:
            self.send_response(404); self.end_headers()

    def log_message(self, format, *args):
        pass

def _find_free_port():
    import socket
    sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sk.bind(("127.0.0.1", 0))
    port = sk.getsockname()[1]
    sk.close()
    return port

def _start_proxy():
    global _proxy_port, _proxy_started
    if _proxy_started:
        return
    try:
        _proxy_port = _find_free_port()
        server = _ThreadedHTTPServer(("127.0.0.1", _proxy_port), _ProxyHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        _proxy_started = True
    except Exception as e:
        _log(f"内置代理启动失败: {e}")

# ==================== 主爬虫类（继承自 OK 影视基类） ====================
class Spider(BaseSpider):  # 修改：继承 BaseSpider
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.t4_api = kwargs.get("t4_api", "")
        self.session = requests.Session()
        self.session.mount("http://", _img_adapter)
        self.session.mount("https://", _img_adapter)
        self.extend = {}
        self.host = "https://r0hiexcmqu1o.cc"
        self.json_host = "https://kfsoahubdsjson.qxdlawyer.com/"
        self.image_host = "https://wzzqlm.erbaiwulaoge.com"
        self.search_api = "https://ma0m1ss3a5chap.621g3uxa.com/search"
        self.timeout = 8
        self.verify = False
        self._key = base64.b64decode("SWRUSnEwSGtscHVJNm11OGlCJU9PQCF2ZF40SyZ1WFc=")
        self._iv_prefix = base64.b64decode("JDB2QGtySDdWMg==").decode("utf-8")
        self._cache = {}
        self._menus = None
        self._cached_img_host = None

    # ---------------- 基础 ----------------
    def getName(self):
        return "猫咪VIP"

    def getProxyUrl(self, flag=False):
        return getattr(self, "t4_api", "")

    def init(self, extend=""):
        # 调用基类 init（若有）
        super().init(extend)
        self.setExtendInfo(extend)
        if not getattr(self, "t4_api", ""):
            _start_proxy()
        _log(f"Spider 初始化完毕, t4_api={self.t4_api}")

    def setExtendInfo(self, extend=""):
        value = extend if isinstance(extend, dict) else {}
        if not value and extend:
            try:
                value = json.loads(str(extend))
            except Exception:
                value = {}
        self.extend = value if isinstance(value, dict) else {}
        self.host = str(self.extend.get("host") or self.host).rstrip("/")
        self.json_host = str(self.extend.get("json_host") or self.json_host).rstrip("/") + "/"
        self.image_host = str(self.extend.get("image_host") or self.image_host).rstrip("/")
        self.search_api = str(self.extend.get("search_api") or self.search_api)
        try:
            self.timeout = max(1, float(self.extend.get("timeout", self.timeout)))
        except Exception:
            pass
        verify = self.extend.get("verify", False)
        self.verify = verify if isinstance(verify, bool) else str(verify).lower() not in ("0", "false", "no")
        headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
        if self.extend.get("cookie"):
            headers["Cookie"] = str(self.extend["cookie"])
        if self.extend.get("authorization"):
            headers["Authorization"] = str(self.extend["authorization"])
        if self.extend.get("token"):
            token = str(self.extend["token"])
            headers["X-Token"] = token
            headers.setdefault("Authorization", "Bearer " + token)
        self.session.headers.clear()
        self.session.headers.update(headers)
        self._menus = None
        self._cache.clear()
        self._cached_img_host = None

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(?:m3u8|mp4|flv|mkv|ts)(?:\?|$)", str(url), re.I))

    def manualVideoCheck(self):
        return False

    def homeLayout(self):
        return 0

    def getHomeContent(self, filter=False):
        return self.homeContent(filter)

    # ---------------- 智能图片识别与高速解密 ----------------
    @staticmethod
    def _is_valid_image(data):
        if not data or len(data) < 12:
            return False
        if data.startswith(b"\xff\xd8") or data.startswith(b"\x89PNG\r\n\x1a\n"):
            return True
        if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
            return True
        if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
            return True
        if data.startswith(b"BM"):
            return True
        if len(data) >= 12 and data[4:8] == b"ftyp":
            return True
        return False

    @staticmethod
    def _detect_image_mime(data):
        if data.startswith(b"\xff\xd8"):
            return "jpeg"
        if data.startswith(b"\x89PNG"):
            return "png"
        if data.startswith(b"GIF"):
            return "gif"
        if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
            return "webp"
        if data.startswith(b"BM"):
            return "bmp"
        if len(data) >= 12 and data[4:8] == b"ftyp":
            return "avif"
        return "jpeg"

    @classmethod
    def _decrypt_image_fast(cls, data):
        if not data or len(data) < 16 or cls._is_valid_image(data):
            return data

        try:
            if data.startswith(b"data:image") or data.startswith(b"/9j/") or data.startswith(b"iVBOR"):
                b64_str = data.split(b",", 1)[-1] if b"," in data else data
                decoded = base64.b64decode(b64_str)
                if cls._is_valid_image(decoded):
                    return decoded
                data = decoded
        except Exception:
            pass

        site_key = base64.b64decode("SWRUSnEwSGtscHVJNm11OGlCJU9PQCF2ZF40SyZ1WFc=")
        iv_prefix = "$0v@krH7V2"

        fast_candidates = [
            (site_key, (iv_prefix + "123456").encode("utf-8")),
            (b"f5d965df75336270", b"97b60394abc2fbe1"),
            (site_key, (iv_prefix + "000000").encode("utf-8")),
            (b"0123456789abcdef", b"0123456789abcdef"),
        ]

        align_len = len(data) - (len(data) % 16)
        chunk = data[:align_len]

        for k, iv in fast_candidates:
            try:
                dec = _aes_decrypt(k, chunk, iv)
                if cls._is_valid_image(dec):
                    return dec
            except Exception:
                pass

        if len(data) >= 32:
            data_iv = data[:16]
            chunk_body = data[16: 16 + ((len(data) - 16) - (len(data) - 16) % 16)]
            for k, _ in fast_candidates:
                try:
                    dec = _aes_decrypt(k[:16], chunk_body, data_iv)
                    if cls._is_valid_image(dec):
                        return dec
                except Exception:
                    pass

        return data

    def localProxy(self, param):
        t_start = time.time()
        url = param.get("url") or param.get("img") or ""
        if isinstance(url, list):
            url = url[0] if url else ""
        if not url:
            return [400, "text/plain", b""]

        url = unquote(str(url)).strip()
        if "@" in url:
            url = url.split("@")[0]

        res = _fetch_and_cache_img(url, self.host)
        if res:
            mime, dec = res
            _log(f"图片就绪: mime={mime}, 耗时={round((time.time()-t_start)*1000, 1)}ms, url={url}")
            return [200, f"image/{mime}", dec]
        else:
            _log(f"图片获取超时或失败: url={url}")
            return [404, "text/plain", b""]

    def proxy(self, param):
        return self.localProxy(param)

    # ---------------- 接口通信 ----------------
    def _crypt_iv(self, suffix):
        raw = (self._iv_prefix + str(suffix)).encode("utf-8")
        if len(raw) != 16:
            raise ValueError("invalid suffix")
        return raw

    def _decrypt_wrapper(self, wrapper):
        if not isinstance(wrapper, dict):
            raise ValueError(f"bad wrapper: {type(wrapper)}")
        suffix = wrapper.get("suffix", "")
        ciphertext = wrapper.get("data", "")
        dec_bytes = _aes_decrypt(self._key, base64.b64decode(ciphertext), self._crypt_iv(suffix))
        return json.loads(dec_bytes.decode("utf-8"))

    def _api_url(self, path):
        return self.json_host + base64.b64encode(("gt6ikshg458mns4f" + path).encode("utf-8")).decode("ascii")

    def _request_json(self, method, url, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", self.verify)
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    def _api(self, path):
        key = ("api", path)
        if key not in self._cache:
            raw_url = self._api_url(path)
            t_start = time.time()
            try:
                wrapper = self._request_json("GET", raw_url)
                dec_data = self._decrypt_wrapper(wrapper)
                self._cache[key] = dec_data
                _log(f"API 解密成功: {path}, 耗时={round((time.time()-t_start)*1000, 1)}ms")
            except Exception as e:
                _log(f"API 解密失败: path={path}, error={e}")
                raise e
        return self._cache[key]

    # ---------------- 分类（严格保留有效 6 个频道） ----------------
    def _get_menus(self):
        if self._menus is None:
            try:
                data = self._api("/data/category/base-2.js")
                self._menus = data.get("menus", {}) if isinstance(data, dict) else {}
            except Exception as e:
                _log(f"获取 menus 失败: {e}")
                self._menus = {}
        return self._menus

    def _flat_categories(self):
        out = []
        menus = self._get_menus()
        if not isinstance(menus, dict):
            return out
        for ch_key, entry in menus.items():
            if not isinstance(entry, dict):
                continue
            channel = str(entry.get("channel") or ch_key or "").strip()
            # 严格过滤非视频频道，避免 403
            if channel not in ALLOWED_CHANNELS:
                continue
            children = entry.get("data") or []
            if not isinstance(children, list):
                continue
            for child in children:
                if not isinstance(child, dict):
                    continue
                tid = child.get("id")
                name = str(child.get("name") or "").strip()
                jump = str(child.get("jump_name") or tid).strip()
                if tid is None or not name:
                    continue
                out.append((str(tid), name, channel, jump))
        return out

    def homeContent(self, filter=False):
        cats = self._flat_categories()
        _log(f"homeContent 完成, 共下发 {len(cats)} 个有效分类")
        return {"class": [{"type_name": name, "type_id": tid} for tid, name, _, _ in cats], "filters": {}}

    def homeVideoContent(self):
        try:
            # 首页固定加载第 1 个推荐分类 58
            return {"list": self.categoryContent("58", "1", False, {}).get("list", [])}
        except Exception as e:
            _log(f"homeVideoContent 异常: {e}")
            return {"list": []}

    def _resolve(self, tid):
        cats = self._flat_categories()
        str_tid = str(tid).strip()
        for cid, name, channel, jump in cats:
            if cid == str_tid:
                _log(f"解析分类匹配: tid={str_tid} -> 分类名={name}, 频道={channel}, jump={jump}")
                return (channel, jump, cid)
        
        for cid, name, channel, jump in cats:
            if jump == str_tid or channel == str_tid:
                _log(f"解析分类 jump 匹配: tid={str_tid} -> 分类名={name}, 频道={channel}, jump={jump}")
                return (channel, jump, cid)

        _log(f"解析分类未匹配, 默认回退 vip: tid={str_tid}")
        return ("vip", str_tid, str_tid)

    def categoryContent(self, tid, pg, filter=False, extend=None):
        t_start = time.time()
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        
        try:
            channel, jump, cid = self._resolve(tid)
            if channel == "media_video":
                path = f"/data/mediaVideo/list-{cid}-{page}-16.js"
            else:
                path = f"/data/list/base-{channel}-{jump}-{page}.js"

            try:
                payload = self._api(path)
            except Exception as e:
                _log(f"拉取分类接口失败: path={path}, error={e}")
                return {"list": [], "page": page, "pagecount": 0, "limit": 0, "total": 0}

            root = payload.get("list", {}) if isinstance(payload, dict) else {}
            rows = root.get("data", []) if isinstance(root, dict) else []
            
            if not rows and isinstance(payload, dict):
                if isinstance(payload.get("data"), list):
                    rows = payload.get("data")
                elif isinstance(payload.get("list"), list):
                    rows = payload.get("list")

            items = []
            raw_img_urls = []
            for x in rows:
                if not isinstance(x, dict):
                    continue
                raw_pic = self._raw_image_url(x)
                if raw_pic:
                    raw_img_urls.append(raw_pic)

                vod = self._vod(x)
                if channel == "media_video":
                    vid = str(vod.get("vod_id") or "")
                    if vid:
                        vod["vod_id"] = "mv_" + vid
                items.append(vod)

            # 立即异步后台预热当前页前 25 张图片
            for img_u in raw_img_urls[:25]:
                _PREFETCH_POOL.submit(_fetch_and_cache_img, img_u, self.host)

            res = {
                "list": items,
                "page": int(root.get("current_page") or page),
                "pagecount": int(root.get("last_page") or (page + 1 if len(items) >= 10 else page)),
                "limit": int(root.get("per_page") or len(rows)),
                "total": int(root.get("total") or len(rows)),
            }
            _log(f"categoryContent 成功: tid={tid}, page={page}, 数量={len(items)}, 触发预热={len(raw_img_urls[:25])}张, 耗时={round((time.time()-t_start)*1000, 1)}ms")
            return res
        except Exception as e:
            _log(f"categoryContent 异常: tid={tid}, page={page}, error={e}\n{traceback.format_exc()}")
            return {"list": [], "page": page, "pagecount": 0, "limit": 0, "total": 0}

    # ---------------- 列表项与全字段图片提取 ----------------
    def _config_image_host(self):
        if self._cached_img_host:
            return self._cached_img_host
        try:
            cfg = self._api("/data/config/base-2.js")
            if isinstance(cfg, dict):
                target = cfg.get("config") if isinstance(cfg.get("config"), dict) else (cfg.get("data") if isinstance(cfg.get("data"), dict) else cfg)
                for k in ("mm_web_image_domain", "ai_image_domain", "face_domain", "image_domain", "img_domain", "cover_domain", "oss_domain", "pic_domain"):
                    v = target.get(k) if isinstance(target, dict) else None
                    if v:
                        if isinstance(v, (list, tuple)) and v:
                            v = v[0]
                        if isinstance(v, dict):
                            v = v.get("domain") or v.get("host") or ""
                        host = str(v).strip().rstrip("/")
                        if host:
                            if host.startswith("//"):
                                host = "https:" + host
                            elif not host.startswith("http://") and not host.startswith("https://"):
                                host = "https://" + host.lstrip("/")
                            self._cached_img_host = host
                            return host
        except Exception as e:
            _log(f"获取图片域名失败: {e}")
        self._cached_img_host = self.image_host
        return self._cached_img_host

    def _raw_image_url(self, item):
        if isinstance(item, str):
            path = item
        elif isinstance(item, dict):
            # 完整覆盖包括换脸AI等所有字段
            path = (item.get("thumb") or item.get("cover") or item.get("ai_cover")
                    or item.get("face_cover") or item.get("target_img") or item.get("source_img")
                    or item.get("img_url") or item.get("thumb_url") or item.get("cover_url")
                    or item.get("pic") or item.get("img") or item.get("video_cover")
                    or item.get("thumb_ori") or item.get("cover_webp") or item.get("poster")
                    or item.get("vod_pic") or item.get("pic_url") or item.get("image")
                    or item.get("preview") or item.get("cover_img") or item.get("thumbnail") or "")
            if not path and isinstance(item.get("cover"), dict):
                path = item.get("cover", {}).get("url") or item.get("cover", {}).get("path") or ""
            if not path and isinstance(item.get("images"), list) and item.get("images"):
                path = item.get("images")[0]
        else:
            path = ""

        if not path:
            return ""
        path = str(path).strip()
        if not path.startswith("http://") and not path.startswith("https://"):
            if path.startswith("//"):
                path = "https:" + path
            else:
                img_host = self._config_image_host().rstrip("/")
                path = urljoin(img_host + "/", re.sub(r"/{2,}", "/", path).lstrip("/"))
        return path

    def _fix_pic(self, pic):
        if not pic:
            return ""
        pic_url = self._raw_image_url(pic) if not str(pic).startswith("http") else str(pic).strip()
        
        base = getattr(self, "t4_api", "") or self.getProxyUrl()
        if base and pic_url.startswith("http"):
            sep = "&" if "?" in base else "?"
            return f"{base}{sep}type=img&url={quote(pic_url, safe='')}"

        if _proxy_started and _proxy_port > 0 and pic_url.startswith("http"):
            return f"http://127.0.0.1:{_proxy_port}/{quote(pic_url, safe='')}"

        return pic_url

    def _image(self, item):
        raw_url = self._raw_image_url(item)
        if not raw_url:
            return ""
        return self._fix_pic(raw_url)

    def _vod(self, item):
        vid = str(item.get("id") or item.get("vod_id") or "")
        title = str(item.get("title") or item.get("name") or item.get("vod_name") or "")
        remarks = ""
        dur = item.get("duration") or item.get("duration_seconds")
        if dur:
            try:
                minutes, sec = divmod(int(dur), 60)
                remarks = "%02d:%02d" % (minutes, sec)
            except Exception:
                remarks = str(dur)
        return {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": self._image(item),
            "vod_remarks": remarks,
        }

    # ---------------- 详情 ----------------
    def detailContent(self, ids):
        t_start = time.time()
        try:
            vid = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
            if vid.startswith("mv_"):
                real_id = vid[3:]
                detail_path = f"/data/mediaVideo/detail-{real_id}.js"
            else:
                real_id = vid
                detail_path = f"/data/shipin/detail-{vid}.js"
            
            payload = self._api(detail_path)
            data = payload.get("data", payload) if isinstance(payload, dict) else {}
            info = data.get("info", {}) or {}
            source = data.get("source", {}) or {}
            ad = data.get("ad", {}) or {}
            play_data = {
                "video_url": source.get("video_url") or info.get("video_url") or "",
                "m3u8_host": (source.get("m3u8_host") or source.get("m3u8_host1")
                              or source.get("m3u8_host2") or info.get("m3u8_host") or ""),
                "site": ad.get("site") or info.get("site") or "",
            }
            play_id = base64.urlsafe_b64encode(json.dumps(play_data, separators=(",", ":")).encode()).decode()
            vod = self._vod(dict(info, id=info.get("id", real_id)))
            vod.update({
                "vod_content": str(info.get("description") or ""),
                "vod_tag": str(info.get("tags") or ""),
                "vod_play_from": "猫咪",
                "vod_play_url": "播放$" + play_id,
            })
            _log(f"detailContent 成功: id={vid}, name={vod.get('vod_name')}, 耗时={round((time.time()-t_start)*1000, 1)}ms")
            return {"list": [vod]}
        except Exception as e:
            _log(f"detailContent 异常: ids={ids}, error={e}")
            return {"list": []}

    # ---------------- 搜索 ----------------
    def _has_authorized_session(self):
        return any(self.extend.get(k) for k in ("cookie", "authorization", "token"))

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        if not self._has_authorized_session():
            return {"list": [], "page": page, "pagecount": 0, "limit": 0, "total": 0}
        try:
            params = {"page": str(page), "q": str(key), "system": 2,
                      "timestamp": int(time.time()), "device": "mobile"}
            canonical = "".join("%s=%s&" % (k, params[k]) for k in sorted(params))
            params["encode_sign"] = hashlib.md5(
                (canonical + SEARCH_SIGN_KEY).encode("utf-8")
            ).hexdigest()
            suffix = "123456"
            wrapper = self._request_json("POST", self.search_api,
                json={"post-data": self._encrypt(params, suffix)}, headers={"suffix": suffix})
            payload = self._decrypt_wrapper(wrapper)
            raw_list = payload.get("list", []) if isinstance(payload, dict) else []
            if isinstance(raw_list, list):
                rows = raw_list
                root = payload
            else:
                root = raw_list if isinstance(raw_list, dict) else {}
                rows = root.get("data", root.get("list", []))
            if not isinstance(rows, list):
                rows = []
            return {"list": [self._vod(x) for x in rows if isinstance(x, dict)],
                    "page": page,
                    "pagecount": int(root.get("last_page") or page),
                    "limit": int(root.get("per_page") or len(rows)),
                    "total": int(root.get("total") or len(rows))}
        except Exception as e:
            _log(f"searchContent 异常: {e}")
            return {"list": [], "page": page, "pagecount": 0, "limit": 0, "total": 0}

    # ---------------- 播放 ----------------
    @staticmethod
    def _normalize_path(value):
        parts = urlsplit(str(value or ""))
        path = parts.path if parts.scheme or parts.netloc else str(value or "").split("?", 1)[0]
        return "/" + re.sub(r"/{2,}", "/", path).lstrip("/")

    def _config_host(self):
        try:
            cfg = self._api("/data/config/base-2.js")
            return str(cfg.get("m3u8_host_encrypt") or "") if isinstance(cfg, dict) else ""
        except Exception:
            return ""

    def playerContent(self, flag, id, vipFlags=None):
        safe = {"parse": 0, "playUrl": "", "url": "", "header": {}}
        try:
            raw = str(id)
            raw += "=" * (-len(raw) % 4)
            play = json.loads(base64.urlsafe_b64decode(raw.encode()).decode("utf-8"))
            video_url = play.get("video_url") or ""
            play_domain = self._config_host() or play.get("m3u8_host") or ""
            if not video_url or not play_domain:
                return safe
            path = self._normalize_path(video_url)
            expires = int(time.time()) + 300
            secret = hashlib.md5((PLAY_SIGN_KEY + path + str(expires)).encode("utf-8")).hexdigest()
            query = urlencode({"wsSecret": secret, "wsTime": expires})
            url = urljoin(str(play_domain).rstrip("/") + "/", path.lstrip("/")) + "?" + query
            return {"parse": 0, "playUrl": "", "url": url, "header": {"Referer": self.host + "/"}}
        except Exception as e:
            _log(f"playerContent 异常: {e}")
            return safe

    # ---------------- 加密辅助 ----------------
    def _encrypt(self, obj, suffix):
        plain = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        enc = _aes_encrypt(self._key, plain, self._crypt_iv(suffix))
        return base64.b64encode(enc).decode("ascii")