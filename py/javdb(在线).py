# -*- coding: utf-8 -*-
# by @汤圆
# 在“尽量不改动原始结构/字段名”的前提下修复：无码 / FC2 / 动漫 分类加载为空
# 根因：这三类未登录会跳 /login，必须带登录 Cookie。
# 做法：保留原 self.headers（不给公开分类强塞 cookie），仅在受限分类请求时临时追加 Cookie。
#
# ✅ 本次改造：参考 bad.news 的代理实现，为 javdb 增加同款代理能力
# - extend 支持 JSON：{"proxy": {...}, "proxy_prefix": "...", "host":"...", "cookie":"..."}
# - 增加 self.proxies / self.proxy_prefix / fetch()（requests.get(..., proxies=..., timeout=10).text）
# - 封面图 vod_pic 在列表/详情统一加 proxy_prefix

import re
import sys
import json
import requests
from urllib.parse import urlparse
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def __init__(self):
        self.name = "DB563"
        self.host = "https://javdb.com"

        # 与 bad.news 对齐：requests 代理配置
        self.proxies = {}  # 代理配置（requests proxies dict）
        # 与 bad.news 对齐：封面代理前缀（默认空）
        self.proxy_prefix = ''  # 例如: 'http://127.0.0.1:10079/p/0/127.0.0.1:10172/'

        # 原始 headers 保持不变（Accept 改成 */* 更标准）
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 15; 23113RKC6C Build/AQ3A.240912.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/140.0.7339.207 Mobile Safari/537.36',
            'Cookie': '',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }

        # 你提供的登录 cookie（也可以通过 init(extend) 覆盖）
        self.cookie = (
            'list_mode=h; theme=auto; locale=zh; _ym_uid=1769941480238786950; _ym_d=1769941480; _ym_isad=1; over18=1; redirect_to=%2Ffc2; _rucaptcha_session_id=1f7e214432e43815b3c1ca62b55ee47c; hide_app_banner=1; remember_me_token=eyJfcmFpbHMiOnsibWVzc2FnZSI6IklrMUhNMUU0ZVVRMWRtZGZNMnBIV1V4TU1qUnFJZz09IiwiZXhwIjoiMjAyNi0wMi0wOFQxMjowNDowNy4wMDBaIiwicHVyIjoiY29va2llLnJlbWVtYmVyX21lX3Rva2VuIn19--1b6fe5c7934486cdfd52559d5117ac499ef57f68; _jdb_session=qUIm47Qg7xT75KGtmYvYwDaNa4broCQSME7W8AyjEfWWS44KTLXYjIgsZEeAjcRS7s52XNPac7EO06I2eX0On%2Bcur%2BG9r%2BpzvV8jWNwpvBehnds06YBfuxVl7ikFgFtpKUFJ1TEBbOznpmKtaL9pUJfXcDJvgqi7RrnlD8m34kB0VVs%2FWj8973lzvCGSAaaRFKmjyaqvNlgqQ0fKWQ1YtvDKniqgSjtuvbKXefBZPkqrYgjUezR8vbGq70hPSZcNP6HYH7Q1Zp1xwnToGKuNAagSUTAIv%2FUgO%2B8ak9JBE%2Fv0djEn%2FVOliPbHkpBk11i6PevSQui9%2Bj5WyMQA%2BWWsOFI3X%2FGCE2W%2Fgzrpfb6pbGEV5s4M7EKLvLUWIIive0iMoHQ%3D--VgnX3zv21E%2BtBoE2--6cZEq%2BkxSpo98LJk%2FBfIvg%3D%3D'
        )

    def init(self, extend=""):
        """
        ✅ 支持两种 extend：
        1) 旧格式（原来那套）："host=...; cookie=..." 或直接传 cookie 串
        2) bad.news 同款 JSON：
           {
             "host": "https://javdb.com",
             "cookie": "...",
             "proxy": {"http":"http://127.0.0.1:7890","https":"http://127.0.0.1:7890"},
             "proxy_prefix": "http://127.0.0.1:10079/p/0/127.0.0.1:10172/"
           }
        """
        ext = (extend or "").strip()
        if not ext:
            return

        # 优先尝试 JSON（对齐 bad.news）
        if ext.startswith('{') and ext.endswith('}'):
            try:
                obj = json.loads(ext)
                if isinstance(obj, dict):
                    if obj.get('host'):
                        self.host = str(obj.get('host')).rstrip('/')
                    if obj.get('cookie'):
                        self.cookie = str(obj.get('cookie')).strip()

                    p = obj.get('proxy')
                    if isinstance(p, dict):
                        self.proxies = p

                    if obj.get('proxy_prefix'):
                        self.proxy_prefix = str(obj.get('proxy_prefix')).strip()
                return
            except Exception:
                # JSON 失败则继续走旧格式
                pass

        # 旧格式兼容（你原来的逻辑）
        m = re.search(r'(?:^|[;\s])host\s*=\s*(https?://[^;\s]+)', ext, re.I)
        if m:
            self.host = m.group(1).rstrip('/')

        m = re.search(r'(?:^|[;\s])cookie\s*=\s*(.+)$', ext, re.I)
        if m:
            self.cookie = m.group(1).strip()
        else:
            # 看起来就是 cookie
            if '=' in ext and 'http' not in ext.lower():
                self.cookie = ext

        # 可选：旧格式也允许传 proxy_prefix=...
        m = re.search(r'(?:^|[;\s])proxy_prefix\s*=\s*(https?://[^;\s]+)', ext, re.I)
        if m:
            self.proxy_prefix = m.group(1).strip()

        # 可选：旧格式也允许传 proxy={...}
        m = re.search(r'(?:^|[;\s])proxy\s*=\s*({.*})', ext, re.I)
        if m:
            try:
                p = json.loads(m.group(1))
                if isinstance(p, dict):
                    self.proxies = p
            except Exception:
                pass

    def getName(self):
        return self.name

    # =========================
    # 与 bad.news 对齐：fetch
    # =========================
    def fetch(self, url, headers=None, params=None):
        """对齐 bad.news 的代理思路：所有请求走 self.proxies。

        注意：这里返回 Response（而不是 .text），以兼容原 javdb 的解析逻辑（rsp.content / rsp.text / rsp.url）。
        """
        try:
            if headers is None:
                headers = self.headers
            return requests.get(
                url,
                headers=headers,
                params=params,
                proxies=self.proxies,
                timeout=10,
                allow_redirects=True
            )
        except Exception:
            return None

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return

    def _fix_mojibake(self, s):
        if not s:
            return s
        try:
            if re.search(r'[ÃÂäåæçèéìíòóùúÄÅÆÇÈÉÌÍÒÓÙÚ]', s):
                return s.encode('latin1', 'ignore').decode('utf-8', 'ignore')
        except Exception:
            pass
        return s

    # =========================
    # 封面代理：对齐 bad.news
    # =========================
    def _proxy_pic(self, pic: str) -> str:
        if not pic:
            return pic or ''
        pic = str(pic).strip()
        pic = pic.split('?', 1)[0]
        if not self.proxy_prefix:
            return pic
        return self.proxy_prefix + pic

    def homeContent(self, filter):
        data = self.getpq("/")
        result = {}

        classes = [
            {'type_name': '全部', 'type_id': '?vft=4&vst=1'},
            {'type_name': '有码', 'type_id': 'censored?vft=4&vst=1'},
            {'type_name': '无码', 'type_id': 'uncensored?vft=4&vst=1'},
            {'type_name': '欧美', 'type_id': 'western?vft=4&vst=1'},
            {'type_name': 'FC2', 'type_id': 'fc2?vft=4&vst=1'},
            {'type_name': '动漫', 'type_id': 'anime?vft=4&vst=1'}
        ]

        result['class'] = classes
        result['list'] = self.getlist(data)
        return result

    def homeVideoContent(self):
        return {}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg)

        if tid == '' or tid is None:
            url = "/" if pg == 1 else f"/?page={pg}"
        else:
            if pg == 1:
                url = f"/{tid}"
            else:
                url = f"/{tid}&page={pg}" if ('?' in tid) else f"/{tid}?page={pg}"

        data = self.getpq(url)
        result = {}
        result['list'] = self.getlist(data)
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def detailContent(self, ids):
        data = self.getpq(ids[0])

        title = data('.video-title strong').text() or data('h1').text()
        title = self._fix_mojibake((title or '').strip())

        vod_pic = data('.cover img').attr('src')
        vod_pic = self._proxy_pic(vod_pic)

        vod = {
            'vod_id': ids[0],
            'vod_name': title,
            'vod_pic': vod_pic,
            'vod_year': self._fix_mojibake((data('.meta').text() or '').strip()),
            'vod_remarks': self._fix_mojibake((data('.score .value').text() or '').strip()),
            'vod_content': self._fix_mojibake((data('.video-title').text() or '').strip())
        }

        # 直链播放：从详情页封面区域提取 /v/xxx/play?... 链接
        play_url = data('a.video-play-container').attr('href') or ''

        # 兜底：任意包含 /play 的链接（避免 class 变更）
        if not play_url:
            play_url = data('a[href*="/v/"][href*="/play"]').attr('href') or ''

        # 兜底：对整页 HTML 正则抽取
        if not play_url:
            full_html = ''
            try:
                full_html = data('html').outer_html()  # 某些版本支持
            except Exception:
                pass
            if not full_html:
                try:
                    full_html = data('html').html() or ''
                except Exception:
                    full_html = ''
            if not full_html:
                try:
                    full_html = data('body').html() or ''
                except Exception:
                    full_html = ''
            if not full_html:
                full_html = str(data)

            m = re.search(r'href="(/v/[^\"]+/play\?[^\"]+)"', full_html)
            if not m:
                m = re.search(r'href="(/v/[^\"]+/play[^\"]*)"', full_html)
            play_url = m.group(1) if m else ''

        # 统一成绝对路径
        if play_url and not play_url.startswith('http'):
            play_url = self.host.rstrip('/') + play_url

        # 给 play_url 加时间戳，降低缓存影响
        try:
            import time
            if play_url:
                sep = '&' if ('?' in play_url) else '?'
                play_url = f"{play_url}{sep}tvbox={int(time.time()*1000)}"
        except Exception:
            pass

        vod["vod_play_from"] = "直链播放"
        vod["vod_play_url"] = f"正片${play_url}" if play_url else f"正片${ids[0]}"

        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        search_url = f"/search?q={key}"
        if str(pg) != "1":
            search_url += f"&page={pg}"

        data = self.getpq(search_url)
        result = {}
        result['list'] = self.getlist(data)
        result['page'] = int(pg)
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def _decode_vurl(self, vurl: str) -> str:
        """play页里 data-vurl 是 urlsafe base64 + gzip 的 JSON。"""
        import base64
        import gzip
        import json

        if not vurl:
            return ''
        try:
            raw = base64.urlsafe_b64decode(vurl)
            if raw[:2] == b'\x1f\x8b':
                raw = gzip.decompress(raw)
            obj = json.loads(raw.decode('utf-8', 'ignore'))
            # 取最高画质
            best_url = ''
            best_q = -1
            for k, v in obj.items():
                if not isinstance(v, dict):
                    continue
                u = v.get('url') or ''
                m = re.search(r'(\d+)', str(k))
                q = int(m.group(1)) if m else 0
                if u and q > best_q:
                    best_q = q
                    best_url = u
            # 兜底：取任意一个
            if not best_url:
                for v in obj.values():
                    if isinstance(v, dict) and v.get('url'):
                        best_url = v.get('url')
                        break
            return best_url or ''
        except Exception:
            return ''

    def playerContent(self, flag, id, vipFlags):
        """id 传入的是 /v/xxx/play?... 这类页面；在里面解析出 m3u8 直链返回。"""
        data = self.getpq(id)
        vurl = data('#player-container').attr('data-vurl') or ''
        m3u8 = self._decode_vurl(vurl)
        if m3u8:
            # 给 m3u8 加时间戳降低缓存
            try:
                import time
                sep = '&' if ('?' in m3u8) else '?'
                m3u8 = f"{m3u8}{sep}tvbox={int(time.time()*1000)}"
            except Exception:
                pass

            # m3u8/ts 拉流需要带 Cookie + Referer + UA
            h = dict(self.headers)
            if (self.cookie or '').strip():
                h['Cookie'] = self.cookie.strip()
            try:
                if not str(id).startswith('http'):
                    referer = self.host.rstrip('/') + str(id)
                else:
                    referer = str(id)
                h['Referer'] = referer
                u = urlparse(self.host)
                h['Origin'] = f"{u.scheme}://{u.netloc}" if u.scheme and u.netloc else self.host
            except Exception:
                pass

            return {'parse': 0, 'url': m3u8, 'header': h, 'headers': h}

        return {'parse': 0, 'url': id, 'header': self.headers, 'headers': self.headers}

    def localProxy(self, param):
        return None

    def getlist(self, data):
        videos = []
        items = data('.movie-list .item')

        for item in items.items():
            link_elem = item('a.box')
            href = link_elem.attr('href')
            if not href:
                continue

            title = self._fix_mojibake((link_elem.attr('title') or '').strip())
            img_src = item('.cover img').attr('src') or item('img').attr('src')
            img_src = self._proxy_pic(img_src)
            meta_text = self._fix_mojibake((item('.meta').text() or '').strip())

            videos.append({
                'vod_id': href,
                'vod_name': title,
                'vod_pic': img_src,
                'vod_remarks': meta_text,
                'vod_year': meta_text
            })

        return videos

    def _need_cookie(self, url_or_path: str) -> bool:
        p = (url_or_path or '')
        # 无码/FC2/动漫 分类页需要登录；播放页 /v/xxxx/play 同样需要登录才能拿到 data-vurl
        return (
            ('/uncensored' in p)
            or ('/fc2' in p)
            or ('/anime' in p)
            or ('/play' in p)
            or ('/v/' in p)
        )

    def getpq(self, path=''):
        url = f"{self.host}{path}" if not str(path).startswith('http') else path

        # 仅在受限页面带 Cookie
        headers = dict(self.headers)
        if self._need_cookie(url) and (self.cookie or '').strip():
            headers['Cookie'] = self.cookie.strip()

        rsp = self.fetch(url, headers=headers)
        if not rsp:
            return pq('')

        # 跟随重定向域名，避免偶发域名切换
        try:
            final_url = getattr(rsp, 'url', None)
            if final_url:
                u = urlparse(final_url)
                if u.scheme and u.netloc:
                    self.host = f"{u.scheme}://{u.netloc}"
        except Exception:
            pass

        content = rsp.content
        try:
            return pq(content)
        except Exception as e:
            print(f"解析错误: {str(e)}")
            try:
                return pq(content.decode('utf-8', 'ignore'))
            except Exception:
                return pq(rsp.text)
