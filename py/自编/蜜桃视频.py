import json
import re
import sys
from urllib.parse import quote, urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    """蜜桃视频(mitao2026.com)站点专属极简版（无 pyquery 依赖）"""

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        elif isinstance(extend, dict):
            cfg = extend

        self.host = (cfg.get('host') or 'https://mitao2026.com').rstrip('/')
        self.proxies = cfg.get('proxies') or {          "http": "http://127.0.0.1:10172",

          "https": "http://127.0.0.1:10172"}

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Referer': f'{self.host}/',
        }

        # 首页脚本里给的CDN线路（直链播放、直链图片）
        self.cdn_candidates = [
            'https://wefa.pkqus.com',
            'https://otgbdf.pkqus.com',
            'https://d38dp2kzhjhhs.cloudfront.net',
            'https://diik3zzrxh4hj.cloudfront.net',
            'https://di6qbkqrsodg9.cloudfront.net',
        ]

        # 复用连接 + 失败重试（提升翻页/图片/详情请求稳定性）
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        if self.proxies:
            self.session.proxies.update(self.proxies)

        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        # home 缓存：避免 homeContent/homeVideoContent 连续调用重复请求
        self._home_cache = None

    def getName(self):
        return "蜜桃视频-极简直链"

    def isVideoFormat(self, url):
        u = (url or '').lower()
        return '.m3u8' in u or '.mp4' in u

    def manualVideoCheck(self):
        return False

    # -----------------------------
    # helpers
    # -----------------------------
    def _get(self, url, *, timeout=(10, 20)):
        """统一 GET：Session + 重试 + 超时。失败返回 None。"""
        try:
            r = self.session.get(url, timeout=timeout)
            r.encoding = r.apparent_encoding
            return r
        except Exception:
            return None

    def _abs(self, href: str):
        if not href:
            return ''
        href = href.strip()
        if href.startswith('http'):
            return href
        if href.startswith('//'):
            return 'https:' + href
        # 首页推荐列表里封面常见：/image/xxxx（真实资源在CDN，不在主站域名）
        if href.startswith('/image/'):
            return self.cdn_candidates[0] + href
        return urljoin(self.host + '/', href)

    def _pick_cdn(self, raw_path: str):
        """不做探测，直接使用固定CDN前缀，避免额外请求导致失败。"""
        raw_path = (raw_path or '').strip()
        if not raw_path:
            return ''
        if raw_path.startswith('http'):
            return raw_path
        if raw_path.startswith('//'):
            return 'https:' + raw_path
        # 站点当前最常用的直链域名
        return self.cdn_candidates[0] + raw_path

    def _unescape(self, s: str):
        if not s:
            return ''
        # 处理 \u0026 以及 \/
        try:
            s = s.encode('utf-8').decode('unicode_escape')
        except Exception:
            pass
        return s.replace('\\/', '/')

    def _parse_menu_classes_and_filters(self, html: str):
        """参考 rsp.py 的一级/二级分类做法（更稳的匹配方式）。

        一级：
        - 分组型：a[href="#menuSubXX"]（例如：性巴克/原创/亚洲/AV...）
        - 直链型：a.menu-item-link[href^="/category/"]（例如：嫩妹）

        二级：
        - 分组型对应的 div#menuSubXX 里的 ul.mobile-menu-subs 下 /category/... 链接
        - 写入 filters[type_id]，key 使用 type
        """
        classes = []
        filters = {}
        group_default = {}
        seen = set()

        # 1) 分组型一级（href="#menuSub27"）
        for m in re.finditer(
            r'<a[^>]*class="menu-item(?![^\"]*menu-item-link)[^\"]*"[^>]*href="#(menuSub\d+)"[^>]*>([\s\S]*?)<img',
            html,
        ):
            gid = m.group(1)
            name_raw = m.group(2)
            name = re.sub(r'<[^>]+>', '', name_raw)
            name = re.sub(r'\s+', ' ', name).strip()
            if not name:
                continue

            type_id = f'group:{gid}'
            if type_id in seen:
                continue
            seen.add(type_id)

            # 找到该分组的子分类列表
            subs_m = re.search(
                rf'<div class="collapse"\s+id="{re.escape(gid)}"[\s\S]*?<ul class="mobile-menu-subs">([\s\S]*?)</ul>',
                html,
            )
            subs_html = subs_m.group(1) if subs_m else ''

            sub_values = []
            for href, sub_name in re.findall(r'href="(/category/[^\"]+/)"[\s\S]*?>([^<]{1,60})</a>', subs_html):
                sub_name = re.sub(r'\s+', ' ', sub_name).strip()
                if sub_name:
                    sub_values.append({'n': sub_name, 'v': href})

            classes.append({'type_name': name, 'type_id': type_id})
            if sub_values:
                filters[type_id] = [{'key': 'type', 'name': '类型', 'value': sub_values}]
                group_default[type_id] = sub_values[0]['v']

        # 2) 直链型一级（嫩妹等）
        for m in re.finditer(
            r'<a[^>]*class="menu-item[^\"]*menu-item-link[^\"]*"[^>]*href="(/category/[^\"]+/)"[\s\S]*?>\s*([\s\S]*?)\s*<img',
            html,
        ):
            href = m.group(1).strip()
            name_raw = m.group(2)
            name = re.sub(r'<[^>]+>', '', name_raw)
            name = re.sub(r'\s+', ' ', name).strip()
            if not name:
                continue
            if href in seen:
                continue
            seen.add(href)
            classes.append({'type_name': name, 'type_id': href})

        return classes, filters, group_default

    def _parse_videos(self, html: str):
        # 列表卡片：a href="/video/ID/" ... <img ... data-src="..." ... alt="标题" ... <h3>标题</h3>
        out = []
        seen = set()

        # 优先抓 section-content__item 结构（更准、更少误匹配）
        blocks = re.findall(r'<li class="section-content__item"[\s\S]*?</li>', html)
        if not blocks:
            # 兜底：直接从整页匹配 a[href^=/video/]
            blocks = re.findall(r'<a[^>]+href="/video/\d+/"[\s\S]*?</a>', html)

        for b in blocks:
            m = re.search(r'href="(/video/\d+/)"', b)
            if not m:
                continue
            href = m.group(1)
            if href in seen:
                continue

            title = ''
            m = re.search(r'<h3[^>]*>([^<]+)</h3>', b)
            if m:
                title = m.group(1)
            if not title:
                m = re.search(r'alt="([^"]+)"', b)
                if m:
                    title = m.group(1)
            if not title:
                m = re.search(r'aria-label="([^"]+)"', b)
                if m:
                    title = m.group(1).rsplit('-', 1)[0]

            title = re.sub(r'\s+', ' ', title).strip()
            if not title:
                continue

            img = ''
            m = re.search(r'data-src="([^"]+)"', b)
            if m:
                img = m.group(1)

            # 推荐区很多 img 的 src 是 blob:，不能用；优先 data-src，兜底 src
            if (not img) or img.startswith('blob:'):
                m = re.search(r'src="([^"]+)"', b)
                if m:
                    img = m.group(1)
            if img.startswith('blob:'):
                img = ''

            remark = ''
            m = re.search(r'class="cover-duration">([^<]+)</span>', b)
            if m:
                remark = m.group(1).strip()

            out.append({
                'vod_id': href,  # 相对路径，交给壳拼 host
                'vod_name': title,
                'vod_pic': self._abs(img),
                'vod_remarks': remark,
            })
            seen.add(href)

        return out

    def _build_click(self, href: str, name: str):
        """统一生成可点击文本（壳里 a=cr 才能点击）。"""
        href = (href or '').strip()
        name = (name or '').strip()
        if not href or not name:
            return ''
        return f'[a=cr:{json.dumps({"id": href, "name": name})}/]{name}[/a]'

    # -----------------------------
    # Spider API
    # -----------------------------
    def homeContent(self, filter):
        r = self._get(self.host + '/')
        html = r.text if r else ''
        if not html:
            return {'class': [], 'filters': {}, 'list': []}

        classes, filters, group_default = self._parse_menu_classes_and_filters(html)
        # 保存给 categoryContent 默认使用
        self._group_default = group_default

        videos = self._parse_videos(html)
        self._home_cache = {'videos': videos}
        return {'class': classes, 'filters': filters, 'list': videos}

    def homeVideoContent(self):
        if isinstance(getattr(self, '_home_cache', None), dict) and self._home_cache.get('videos') is not None:
            return {'list': self._home_cache.get('videos') or []}
        return {'list': self.homeContent(None).get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        # 参考 rsp.py：如果选择了二级分类，则 extend['type'] 直接替换 tid
        if isinstance(extend, dict) and extend.get('type'):
            tid = extend['type']
        elif isinstance(tid, str) and tid.startswith('group:'):
            # 未选择二级时，默认取该分组的第一个子类
            default_map = getattr(self, '_group_default', {}) or {}
            tid = default_map.get(tid) or tid

        pg = int(pg) if str(pg).isdigit() else 1
        base = tid if isinstance(tid, str) and tid.startswith('http') else self._abs(tid)
        base = base.rstrip('/') + '/'
        url = base if pg == 1 else f'{base}{pg}/'

        r = self._get(url)
        html = r.text if r else ''
        videos = self._parse_videos(html) if html else []
        return {'list': videos, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}

    def detailContent(self, ids):
        detail_url = ids[0]
        if not detail_url.startswith('http'):
            detail_url = self._abs(detail_url)

        r = self._get(detail_url)
        html = r.text if r else ''
        if not html:
            return {'list': []}

        title = ''
        m = re.search(r'<h1[^>]*class="only-pc"[^>]*>([^<]+)</h1>', html)
        if m:
            title = m.group(1)
        if not title:
            m = re.search(r'<title>([^<]+)</title>', html)
            if m:
                title = m.group(1).replace(' - 蜜桃视频', '').strip()
        title = re.sub(r'\s+', ' ', title).strip()

        pic = ''
        m = re.search(r'property="og:image"\s+content="([^"]+)"', html)
        if m:
            pic = m.group(1).strip()

        m = re.search(r'window\.__ARCHIVE_PLAYER__\s*=\s*(\{.*?\});', html, re.S)
        if not m:
            return {'list': []}

        try:
            obj = json.loads(m.group(1))
        except Exception:
            return {'list': []}

        raw = self._unescape(obj.get('rawPath') or '')
        play = self._pick_cdn(raw)

        # tags（详情页简介显示）
        tags = []
        span_m = re.search(r'<span[^>]*class="tags"[^>]*>([\s\S]*?)</span>', html)
        span_html = span_m.group(1) if span_m else ''
        for href, name in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', span_html):
            name = re.sub(r'\s+', ' ', (name or '')).strip()
            href = (href or '').strip()
            click = self._build_click(href, name)
            if click:
                tags.append(click)

        vod_content = ''
        if tags:
            # “标签:”为普通文本，仅标签链接可点击
            vod_content = '标签： ' + ' '.join(tags)

        vod = {
            'vod_id': ids[0],
            'vod_name': title,
            'vod_pic': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{pic}',
            'vod_content': vod_content,
            'vod_play_from': '直链',
            'vod_play_url': f'播放${play}',
        }
        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        base = f'{self.host}/search/{quote(key, safe="")}/'
        url = base if pg == 1 else f'{base}{pg}/'

        r = self._get(url)
        html = r.text if r else ''
        videos = self._parse_videos(html) if html else []
        return {'list': videos, 'page': pg, 'pagecount': 9999}

    def playerContent(self, flag, id, vipFlags):
        return {'parse': 0, 'url': f'http://127.0.0.1:10079/p/0/127.0.0.1:10172/{id}', 'header': self.headers}
