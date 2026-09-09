# -*- coding: utf-8 -*-
import base64, json, re, sys
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    NAV_SCRIPT_URLS = [
        'https://6180067.xyz/cdn-tentm-Div/react-jsx-dev-runtime.js?kk=2495955t6683'
    ]

    ZONES = [
        {
            'type_name': '一区',
            'js_idx': 0,
            'module': 'vod',
            'type_id': 1,
            'subcats': [
                ('香蕉精品', 13), ('制服诱惑', 22), ('国产视频', 6), ('清纯少女', 8), ('辣妹大奶', 9), ('女同专属', 10),
                ('素人出演', 11), ('角色扮演', 12), ('人妻熟女', 20), ('日韩剧情', 23), ('经典伦理', 21), ('成人动漫', 7),
                ('精品二区', 14), ('精品三区', 40),
            ],
        },
        {
            'type_name': '二区',
            'js_idx': 1,
            'module': 'vod',
            'type_id': 1,
            'subcats': [
                ('热门', 5), ('推荐', 6), ('字幕', 7), ('欧美', 8), ('动漫', 9), ('传媒', 10), ('黑料', 31),
                ('网黄', 55), ('无码', 56), ('JK', 57), ('国产', 54),
            ],
        },
        {
            'type_name': '五区',
            'js_idx': 4,
            'module': 'vod',
            'type_id': 2,
            'subcats': [
                ('热门', 13), ('字幕', 14), ('国产', 15), ('无码', 16), ('直播', 23), ('探花', 34), ('网黄', 32),
                ('欧美', 11), ('韩国', 12), ('传媒', 58), ('JK', 61),
            ],
        },
        {
            'type_name': '六区',
            'js_idx': 5,
            'module': 'vod',
            'type_id': 44,
            'subcats': [('二区', 35), ('JK', 45), ('中文', 46), ('精品', 47), ('韩国', 48), ('网黄', 59), ('国产', 60)],
        },
        {
            'type_name': '七区',
            'js_idx': 6,
            'module': 'vod',
            'type_id': 40,
            'subcats': [
                ('精品二区', 13), ('P站', 25), ('国产AV', 37), ('欧美', 38), ('字幕', 39), ('福利姬', 41), ('主播直播', 42),
                ('探花AV', 43), ('国产传媒', 44), ('水果π', 45), ('性爱教学', 46), ('动漫', 47), ('三级', 48), ('绿帽淫妻', 49), ('FC2', 66),
            ],
        },
              {
            'type_name': '八区',
            'js_idx': 7,
            'module': 'vod',
            'type_id': 66,
            'subcats': [
                ('一区', 1), ('日欧', 63), ('动漫', 64), ('无码', 65), ('JK', 67), ('厂牌', 68), ('字幕', 69), ('P站', 70),
                ('网黄', 71), ('国产', 72), ('热门', 73),
            ],
        },
    ]

    CARD_SEL = 'a.module-poster-item, a.module-item-pic, a.vodlist_thumb, a.stui-vodlist__thumb, a.myui-vodlist__thumb, a.vodbox'
    REMARK_SEL = '.module-item-note, .pic-text, .remarks, .text-right'
    DETAIL_CONTENT_SEL = '.module-info-introduction, .vod_content, .content, .detail-content'
    PLAY_LINK_SEL_1 = 'a[href*="/vod/play/"]'
    PLAY_LINK_SEL_2 = 'a[href*="vod/play"]'
    BAD_HREF_PARTS = ('/vod/type/', '/vod/search', '/vod/show', '/label/', '/topic/')

    def init(self, extend=''):
        cfg = {}
        if isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        elif isinstance(extend, dict):
            cfg = extend
        self.plp = cfg.get('plp', '')
        self.proxy = cfg.get('proxy') if 'proxy' in cfg else {}
        self.s = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=50, max_retries=0)
        self.s.mount('http://', adapter)
        self.s.mount('https://', adapter)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
        }
        self.image_key = '2019ysapp7527'
        self.STATIC_CLASSES = []
        self.STATIC_SUBCATS = {}
        self._ensure_static()

    def _ensure_static(self):
        # 惰性重建：代理未启动时 init 里探测域名会失败，STATIC_CLASSES 为空；
        # 刷新时若还是空，就重试探测 + 重建分类，避免一直空。
        if self.STATIC_CLASSES:
            return
        try:
            self._build_static_entries_by_one_y(self._pick_y_from_sources(self.NAV_SCRIPT_URLS))
        except Exception:
            self.STATIC_CLASSES = []
            self.STATIC_SUBCATS = {}

    def getName(self):
        return '618导航(极简直链版)'

    def manualVideoCheck(self):
        return False

    def _probe_host(self, host: str) -> bool:
        try:
            base = (host or '').strip().rstrip('/')
            if not base.startswith('http'):
                return False
            url = base + '/index.php/vod/type/id/1.html'
            r = self.s.get(url, headers=self.headers, timeout=4, verify=False, proxies=self.proxy, allow_redirects=True)
            if r.status_code != 200:
                return False
            txt = r.text or ''
            return len(txt) >= 500
        except Exception:
            return False

    def _extract_zuArr(self, js_text: str):
        if not js_text:
            return None
        s = js_text
        k = s.find('const zuArr=')
        if k < 0:
            return None
        s2 = s[k + len('const zuArr='):]
        j = s2.find('];')
        if j < 0:
            return None
        raw = s2[:j + 1]
        raw = raw.replace("'", '"')
        try:
            arr = json.loads(raw)
        except Exception:
            return None
        if not isinstance(arr, list) or not arr:
            return None
        return arr

    def _fetch_zuArr_from_sources(self, urls):
        srcs = []
        for u in (urls or []):
            u = (u or '').strip()
            if u and u.startswith('http') and u not in srcs:
                srcs.append(u)
        if not srcs:
            raise RuntimeError('未配置可用的导航脚本来源 URL')
        last_err = ''
        for js_url in srcs:
            try:
                r = self.s.get(js_url, headers=self.headers, timeout=6, verify=False, proxies=self.proxy)
                if r.status_code != 200:
                    last_err = f'{js_url} 状态码 {r.status_code}'
                    continue
                arr = self._extract_zuArr(r.text or '')
                if arr:
                    return arr
                last_err = f'{js_url} 未解析到 zuArr'
            except Exception as e:
                last_err = f'{js_url} 获取失败: {e}'
        raise RuntimeError(f'所有导航脚本来源均不可用或解析失败: {last_err}')

    def _pick_y_from_sources(self, urls) -> int:
        zuArr = self._fetch_zuArr_from_sources(urls)
        m = max((len(x) for x in zuArr if isinstance(x, list)), default=0)
        if m <= 0:
            raise RuntimeError('zuArr 数据无效')
        idxs = list(range(m))
        try:
            import random
            random.SystemRandom().shuffle(idxs)
        except Exception:
            pass
        for y in idxs:
            ok = True
            for z in self.ZONES:
                js_idx = int(z['js_idx'])
                if js_idx < 0 or js_idx >= len(zuArr):
                    ok = False
                    break
                row = zuArr[js_idx]
                if y < 0 or y >= len(row):
                    ok = False
                    break
                n = str(row[y]).strip()
                if not n:
                    ok = False
                    break
                host = f'https://618{n}.xyz'
                if not self._probe_host(host):
                    ok = False
                    break
            if ok:
                return y
        raise RuntimeError('未检测到可用的 618 域名组合（来源已兜底，但域名不兜底）')

    def _build_static_entries_by_one_y(self, y: int):
        zuArr = self._fetch_zuArr_from_sources(self.NAV_SCRIPT_URLS)
        classes = []
        subcats = {}
        for z in self.ZONES:
            js_idx = int(z['js_idx'])
            n = str((zuArr[js_idx] or [])[y]).strip()
            host = f'https://618{n}.xyz'
            tid = f"{host}/index.php/{z['module']}/type/id/{int(z['type_id'])}.html"
            classes.append({'type_name': z['type_name'], 'type_id': tid})
            items = []
            for name, sid in (z.get('subcats') or []):
                items.append({'n': str(name), 'v': str(int(sid))})
            if items:
                subcats[tid] = items
        self.STATIC_CLASSES = classes
        self.STATIC_SUBCATS = subcats

    def get_filters(self, classes):
        out = {}
        for c in classes:
            tid = c.get('type_id')
            vals = [{'n': '全部', 'v': tid}]
            seen = {tid}
            for it in self.STATIC_SUBCATS.get(tid) or []:
                v = (it.get('v') or '').strip()
                if v and v not in seen:
                    seen.add(v)
                    vals.append({'n': (it.get('n') or '').strip(), 'v': v})
            out[tid] = [{'key': 'type', 'name': '子分类', 'value': vals}]
        return out

    def homeContent(self, filter):
        self._ensure_static()
        classes = list(self.STATIC_CLASSES)
        self._home_classes = classes
        if not filter:
            return {'class': classes, 'filters': {}, 'list': []}
        return {'class': classes, 'filters': self.get_filters(classes), 'list': []}

    def homeVideoContent(self):
        return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg) if pg else 1
            base_url = tid
            sub_id = ''
            if isinstance(extend, dict):
                sub_id = str(extend.get('type') or '').strip()
            if sub_id and sub_id.isdigit() and int(sub_id) > 0:
                p = urlparse(base_url)
                host = f'{p.scheme}://{p.netloc}'
                m = re.search(r"/index\.php/([^/]+)/type/id/\d+\.html", p.path or '')
                module = (m.group(1) if m else 'vod')
                base_url = f'{host}/index.php/{module}/type/id/{int(sub_id)}.html'
            url = self._page_url(base_url, pg)
            html = self._get(url)
            base = base_url.split('/index.php/')[0] + '/'
            return {'list': self._parse_video_cards(html, base=base, referer=url, limit=90), 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}
        except Exception:
            return {'list': [], 'page': int(pg or 1), 'pagecount': 9999, 'limit': 90, 'total': 0}

    def _any_host(self):
        try:
            if self.STATIC_CLASSES:
                p = urlparse(self.STATIC_CLASSES[0]['type_id'])
                return f'{p.scheme}://{p.netloc}'
        except Exception:
            pass
        return ''

    def detailContent(self, ids):
        try:
            detail_url = self._norm_url(ids[0])
            qs = parse_qs(urlparse(detail_url).query)
            plist = [f'播放${detail_url}'] if (qs.get('v') or [''])[0] or (qs.get('url') or [''])[0] else []
            title = self._decode_title_from_url(detail_url)
            content = ''
            pic = ''
            try:
                html = self._get(detail_url)
                doc = pq(html)
                title = self._normalize_title((doc('h1').text() or doc('title').text() or '').strip()) or title
                content = (doc(self.DETAIL_CONTENT_SEL).text() or '').strip()
                pic = self._clean_src((doc('img').eq(0).attr('data-original') or doc('img').eq(0).attr('src') or '').strip())
                if pic and (not pic.startswith('http')):
                    pic = self._abs_url(detail_url, pic)
                if pic:
                    pic = self._img_proxy(pic, referer=detail_url)
                if not plist:
                    links = doc(self.PLAY_LINK_SEL_1)
                    if not len(links):
                        links = doc(self.PLAY_LINK_SEL_2)
                    seen = set()
                    for a in links.items():
                        href = (a.attr('href') or '').strip()
                        if (not href) or href.startswith(('javascript:', '#')):
                            continue
                        play = self._abs_url(detail_url, href)
                        if play in seen:
                            continue
                        seen.add(play)
                        ep = (a.text() or '').strip() or f'播放{len(plist) + 1}'
                        plist.append(f'{ep}${play}')
            except Exception:
                pass
            vod = {'vod_id': detail_url, 'vod_name': title or detail_url, 'vod_pic': pic, 'vod_content': content, 'vod_play_from': '直链播放页', 'vod_play_url': '#'.join(plist) if plist else f'播放${detail_url}'}
            return {'list': [vod]}
        except Exception:
            return {'list': []}

    def playerContent(self, flag, id, vipFlags):
        try:
            play_page_url = self._norm_url(id)
            if self._is_direct_video(play_page_url):
                p = urlparse(play_page_url)
                return {'parse': 0, 'url': play_page_url, 'header': self._play_headers(f'{p.scheme}://{p.netloc}/')}
            qs = parse_qs(urlparse(play_page_url).query)
            ref = f'{urlparse(play_page_url).scheme}://{urlparse(play_page_url).netloc}/'
            mk_api = (qs.get('m') or [''])[0].strip()
            if mk_api:
                u = self._fetch_mk_url(mk_api)
                if u:
                    return {'parse': 0, 'url': u, 'header': self._play_headers(ref)}
            html = self._get(play_page_url)
            kk = self._restore_8zone_url_from_script(html, qs)
            if kk:
                return {'parse': 0, 'url': kk, 'header': self._play_headers(ref)}
            if "get('id')" in html and 'const edUrl' in html and (qs.get('id') or [''])[0]:
                raw_id = (qs.get('id') or [''])[0]
                m_rep = re.search(r"edUrl\s*=\s*url\.replace\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)", html)
                m_token = re.search(r"url:\s*edUrl\s*\+\s*'([^']+)'", html)
                if m_rep and m_token:
                    src, dst = m_rep.group(1), m_rep.group(2)
                    token = m_token.group(1)
                    ed = raw_id.replace(src, dst)
                    if ed.startswith('//'):
                        ed = 'https:' + ed
                    return {'parse': 0, 'url': ed + token, 'header': self._play_headers(ref)}
            if 'jwplayer' in html and 'eval(function' in html:
                unpacked = self._unpack_packer(html)
                if unpacked:
                    u = self._extract_jwplayer_source(unpacked, play_page_url)
                    if u:
                        return {'parse': 0, 'url': u, 'header': self._play_headers(ref)}
            return {'parse': 1, 'url': play_page_url, 'header': self.headers}
        except Exception:
            return {'parse': 1, 'url': id, 'header': self.headers}

    def searchContent(self, key, quick, pg='1'):
        try:
            pg = int(pg) if pg else 1
            key = (key or '').strip()
            if not key:
                return {'list': [], 'page': pg, 'pagecount': 1}
            classes = getattr(self, '_home_classes', None) or self.homeContent(False).get('class', [])
            zones = len(classes)
            if not zones:
                return {'list': [], 'page': pg, 'pagecount': 1}
            ppz = 4
            total = zones * ppz
            idx0 = pg - 1
            if idx0 < 0 or idx0 >= total:
                return {'list': [], 'page': pg, 'pagecount': total}
            zone_idx, zone_pg = idx0 // ppz, idx0 % ppz + 1
            type_url = classes[zone_idx]['type_id']
            wd = requests.utils.quote(key)
            base_part = type_url[:-5] if type_url.endswith('.html') else type_url.rstrip('/')
            url = f'{base_part}/wd/{wd}/page/{zone_pg}.html'
            html = self._get(url)
            base = type_url.split('/index.php/')[0] + '/'
            return {'list': self._parse_video_cards(html, base=base, referer=base, limit=60), 'page': pg, 'pagecount': total}
        except Exception:
            return {'list': [], 'page': int(pg or 1), 'pagecount': 1}

    def localProxy(self, param):
        try:
            if (param or {}).get('type') != 'img' or not (param or {}).get('url'):
                return [404, 'text/plain', b'']
            real = self.d64((param or {}).get('url'))
            ref = self.d64((param or {}).get('ref')) if (param or {}).get('ref') else ''
            if not real:
                return [404, 'text/plain', b'']
            hdr = dict(self.headers)
            hdr.pop('Origin', None)
            hdr.pop('Referer', None)
            if ref:
                p = urlparse(ref)
                ref = f'{p.scheme}://{p.netloc}/'
            else:
                p = urlparse(real)
                ref = f'{p.scheme}://{p.netloc}/'
            h = dict(hdr)
            h.update({'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8', 'Referer': ref})
            h.setdefault('Accept-Encoding', 'identity')
            r = self.s.get(real, headers=h, timeout=15, verify=False, proxies=self.proxy)
            data = r.content or b''
            data, guessed = self._maybe_decrypt_image(data, real)
            ct = (r.headers.get('Content-Type') or '').split(';')[0].strip()
            if (not ct) or ct == 'application/octet-stream':
                ct = guessed or self._guess_image_mime(data, real) or 'image/jpeg'
            return [200 if r.status_code == 200 else r.status_code, ct, data]
        except Exception:
            return [404, 'text/plain', b'']

    def _get(self, url: str) -> str:
        url = self._norm_url(url)
        h = dict(self.headers)
        try:
            p = urlparse(url)
            h['Referer'] = f'{p.scheme}://{p.netloc}/'
        except Exception:
            pass
        r = self.s.get(url, headers=h, timeout=10, verify=False, proxies=self.proxy)
        if r.status_code != 200:
            raise ValueError
        r.encoding = r.apparent_encoding
        return r.text

    def _page_url(self, base_url: str, pg: int) -> str:
        if pg <= 1:
            return base_url
        if re.search('/page/\\d+\\.html', base_url):
            return re.sub('/page/\\d+\\.html', f'/page/{pg}.html', base_url)
        if base_url.endswith('.html'):
            return base_url.replace('.html', f'/page/{pg}.html')
        return base_url.rstrip('/') + f'/page/{pg}.html'

    def _parse_video_cards(self, html: str, base: str, referer: str, limit: int):
        doc = pq(html)
        out, seen = [], set()
        cards = doc(self.CARD_SEL)
        if not len(cards):
            cards = doc('a:has(img)')
        for a in cards.items():
            href = (a.attr('href') or '').strip()
            if (not href) or href.startswith(('javascript:', '#', 'mailto:')) or any(x in href for x in self.BAD_HREF_PARTS):
                continue
            detail_url = self._abs_url(base, href)
            if not detail_url or detail_url in seen:
                continue
            seen.add(detail_url)
            title = (a.attr('title') or '').strip() or (a.find('img').attr('alt') or a.find('img').attr('title') or (a.text() or '')).strip()
            title = self._normalize_title(title) or self._decode_title_from_url(detail_url)
            if not title:
                continue
            img = self._clean_src((a.attr('data-original') or a.attr('data-src') or a.find('img').attr('data-original') or a.find('img').attr('data-src') or a.find('img').attr('src') or '').strip())
            if img and (not img.startswith('http')):
                img = self._abs_url(base, img)
            if img:
                img = self._img_proxy(img, referer=referer)
            remark = (a.find(self.REMARK_SEL).text() or '').strip()
            out.append({'vod_id': detail_url, 'vod_name': title, 'vod_pic': img, 'vod_remarks': remark, 'style': {'type': 'rect', 'ratio': 1.33}})
            if len(out) >= limit:
                break
        return out

    def _clean_src(self, src: str) -> str:
        s = (src or '').strip().replace('\\/', '/').replace('\\', '')
        return '' if s.startswith('blob:') or s.startswith('data:') else s

    def _norm_url(self, url: str) -> str:
        u = (url or '').strip()
        if not u:
            return ''
        u = u.replace('\xa0', '').replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')
        u = re.sub(r"%C2%A0|%c2%a0", "", u)
        try:
            return requests.utils.requote_uri(u)
        except Exception:
            return u

    def _abs_url(self, base_url: str, href: str) -> str:
        h = (href or '').strip()
        if not h:
            return ''
        return self._norm_url(h if h.startswith('http') else urljoin(base_url, h))

    def _is_direct_video(self, url: str) -> bool:
        u = (url or '').strip()
        if not u.startswith('http'):
            return False
        path = (urlparse(u).path or '').lower()
        return ('.m3u8' in path) or ('.mp4' in path) or ('/m3u8' in path) or path.endswith('m3u8')

    def e64(self, text: str) -> str:
        return base64.urlsafe_b64encode(str(text).encode('utf-8')).decode('utf-8').rstrip('=')

    def d64(self, text: str) -> str:
        s = str(text).strip()
        if not s:
            return ''
        pad = '=' * ((4 - len(s) % 4) % 4)
        return base64.urlsafe_b64decode((s + pad).encode('utf-8')).decode('utf-8', 'ignore')

    def _img_proxy(self, img_url: str, referer: str='') -> str:
        proxy = self.getProxyUrl()
        if not proxy:
            return img_url
        if referer:
            p = urlparse(referer)
            referer = f'{p.scheme}://{p.netloc}/'
            return f'{proxy}&type=img&url={self.e64(img_url)}&ref={self.e64(referer)}'
        return f'{proxy}&type=img&url={self.e64(img_url)}'

    def _play_headers(self, referer: str='') -> dict:
        h = dict(self.headers)
        if referer:
            h['Referer'] = referer
            p = urlparse(referer)
            h['Origin'] = f'{p.scheme}://{p.netloc}'
        return h

    def _fetch_mk_url(self, mk: str) -> str:
        try:
            api = f'https://h5.xxoo168.org/api/v2/vod/reqplay/{mk}'
            j = self.s.get(api, headers=self.headers, timeout=10, verify=False, proxies=self.proxy).json()
            data = (j or {}).get('data') or {}
            vod_url = data.get('httpurl_preview') if (j or {}).get('retcode') == 3 else data.get('httpurl')
            return (vod_url or '').replace('?300', '')
        except Exception:
            return ''

    def _decode_title_from_url(self, url: str) -> str:
        try:
            seg = (urlparse(url).path or '').rsplit('/', 1)[-1]
            seg = seg[:-5] if seg.endswith('.html') else seg
            seg = unquote(seg)
            return ''.join(chr(ord(c) ^ 128) for c in seg)
        except Exception:
            return ''

    def _normalize_title(self, title: str) -> str:
        t = (title or '').strip()
        if not t:
            return ''
        dec = ''.join(chr(ord(c) ^ 128) for c in t)
        cjk = sum(1 for ch in dec if '一' <= ch <= '鿿')
        return dec.strip() if cjk >= 2 else t

    def _restore_8zone_url_from_script(self, html: str, qs: dict) -> str:
        try:
            mk = (qs.get('url') or [''])[0] or ''
            fixed = ''
            if mk:
                if mk.startswith('kk7-') or mk.startswith('kk8-'):
                    fixed = 'https://m2cdn.playergo.top/' + mk[4:] + '/playlist.m3u8'
                else:
                    mk1 = mk.replace('%20', '+').replace(' ', '+')
                    try:
                        fixed = requests.utils.unquote(mk1)
                    except Exception:
                        fixed = mk1
            v = (qs.get('v') or [''])[0] or ''
            stream = ''
            if v:
                m = re.search(r"streamUrlFromV\s*=\s*v\s*\+\s*'([^']*)'", html)
                stream = v + (m.group(1) if m else '')
            return fixed if fixed else stream
        except Exception:
            return ''

    def _unpack_packer(self, html: str) -> str:
        try:
            idx = html.find('eval(function')
            if idx < 0:
                return ''
            tail = html[idx:]
            j = tail.find("}('")
            if j < 0:
                return ''
            s = tail[j + 1:]

            def readq(src: str, start: int):
                i = start + 1
                buf = []
                while i < len(src):
                    ch = src[i]
                    if ch == '\\' and i + 1 < len(src):
                        buf.append(src[i:i + 2])
                        i += 2
                        continue
                    if ch == "'":
                        return ''.join(buf), i + 1
                    buf.append(ch)
                    i += 1
                return '', -1

            if not s.startswith("('"):
                return ''
            p_raw, pos = readq(s, 1)
            if pos < 0:
                return ''
            m = re.search(r"\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'", s[pos:])
            if not m:
                return ''
            a, c = int(m.group(1)), int(m.group(2))
            k_start = pos + m.end() - 1
            k_raw, k_end = readq(s, k_start)
            if k_end < 0:
                return ''
            try:
                p_str = bytes(p_raw, 'utf-8').decode('unicode_escape', 'ignore')
            except Exception:
                p_str = p_raw
            try:
                k_str = bytes(k_raw, 'utf-8').decode('unicode_escape', 'ignore')
            except Exception:
                k_str = k_raw
            k = k_str.split('|')

            def base_n(num: int, base: int) -> str:
                chars = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
                if num == 0:
                    return '0'
                out = ''
                while num:
                    num, r = divmod(num, base)
                    out = chars[r] + out
                return out

            out = p_str
            for i in range(c - 1, -1, -1):
                if i < len(k) and k[i]:
                    out = re.sub(r"\b" + re.escape(base_n(i, a)) + r"\b", k[i], out)
            return out
        except Exception:
            return ''

    def _extract_jwplayer_source(self, js: str, base_url: str) -> str:
        try:
            m3u8s = re.findall(r"https?://[^\s\"']+?\.m3u8[^\s\"']*", js, flags=re.I)
            if m3u8s:
                return m3u8s[0]
            mp4s = re.findall(r"https?://[^\s\"']+?\.mp4[^\s\"']*", js, flags=re.I)
            if mp4s:
                return mp4s[0]
            return ''
        except Exception:
            return ''

    def _decrypt_image_data(self, data: bytes) -> bytes:
        key = str(getattr(self, 'image_key', '') or '').encode('utf-8')
        if not key:
            return data
        n = min(100, len(data))
        buf = bytearray(data)
        for i in range(n):
            buf[i] ^= key[i % len(key)]
        return bytes(buf)

    def _guess_image_mime(self, data: bytes, url: str='') -> str:
        if not data:
            return 'image/png' if (url or '').lower().endswith('.png') else 'image/jpeg'
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'image/png'
        if data[:3] == b'GIF':
            return 'image/gif'
        if data.startswith(b'RIFF') and b'WEBP' in data[:16]:
            return 'image/webp'
        if data.startswith(b'\xff\xd8'):
            return 'image/jpeg'
        return ''

    def _maybe_decrypt_image(self, data: bytes, url: str=''):
        m0 = self._guess_image_mime(data, url)
        if m0:
            return data, m0
        dec = self._decrypt_image_data(data)
        m1 = self._guess_image_mime(dec, url)
        return (dec, m1) if m1 else (data, m0 or 'application/octet-stream')
