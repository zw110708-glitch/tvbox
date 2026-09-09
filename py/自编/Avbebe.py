# -*- coding: utf-8 -*-
# Avbebe 爬虫源（WordPress/JNews 主题，繁体中文成人动漫/AV 聚合站）
# 适配 OK影视（pg.jar + Chaquopy Python 3.8）
import json
import re
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from base.spider import Spider

# 关闭 verify=False 的证书告警噪音
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass


class Spider(Spider):

    # hgcloud 播放器真实域名池（动态轮换，硬编码候选，失败自动降级）
    HG_HOSTS = ['hanerix.com', 'audinifer.com', 'vibuxer.com']

    # 站点分类（显示名, slug）。子分类（華語AV-素人/片商、綜合漫畫）平铺为一级分类
    CATEGORIES = [
        ('新番', 'new'),
        ('動畫卡通', 'h動畫影片'),
        ('3D動畫', '3d動畫'),
        ('泡麵番', '泡麵番'),
        ('綜合漫畫', '成人h漫畫'),
        ('高清中字', '高清中字'),
        ('高清素人', '高清素人'),
        ('馬賽克破解', '馬賽克破解'),
        ('華語AV', '華語av'),
        ('華語AV-素人', '華語av/華語av-素人'),
        ('華語AV-片商', '華語av/華語av-片商'),
        ('綜合AV', '綜合av'),
    ]

    # Dean Edwards Packer base62 数字表
    _DIGITS = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'

    def init(self, extend="{}"):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}

        self.host = (config.get('site') or 'https://avbebe.com').rstrip('/')
        # ---- 代理三行（由 extend 传，没传就直连）----
        self.plp = config.get('plp', '')       # 播放器/封面/播放地址 URL 前缀
        self.proxy = config.get('proxy', {})   # 内部请求代理

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.host + '/',
        }

    def getName(self):
        return 'Avbebe'

    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(m3u8|mp4|ts)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ------------------------- http -------------------------
    def _get(self, url, referer=None, timeout=15):
        headers = dict(self.headers)
        if referer:
            headers['Referer'] = referer
        return requests.get(url, headers=headers, proxies=self.proxy, timeout=timeout, verify=False)

    def _text(self, r):
        try:
            ctype = (r.headers or {}).get('Content-Type', '')
            m = re.search(r'charset\s*=\s*([\w\-]+)', ctype, re.I)
            if m:
                return r.content.decode(m.group(1), errors='ignore')
        except Exception:
            pass
        for enc in ('utf-8', 'gb18030'):
            try:
                return r.content.decode(enc)
            except Exception:
                pass
        return r.content.decode('utf-8', 'ignore')

    def _soup(self, html):
        return BeautifulSoup(html, 'lxml')

    def _abs(self, u):
        if not u:
            return ''
        if u.startswith('http'):
            return u
        if u.startswith('//'):
            return 'https:' + u
        return urljoin(self.host + '/', u)

    # ------------------------- 可点击标签 -------------------------
    def _cr(self, href, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': href, 'name': name}, ensure_ascii=False), name)

    # ------------------------- 列表解析 -------------------------
    def _parse_vod_list(self, soup):
        items = []
        seen = []
        for art in soup.select('article.jeg_post, article.elementor-post'):
            a = (art.select_one('h3.jeg_post_title a')
                 or art.select_one('h2 a')
                 or art.select_one('h3 a')
                 or art.select_one('.elementor-post__title a'))
            if not a:
                continue
            href = a.get('href') or ''
            title = a.get_text(strip=True)
            if not href or not title:
                continue
            href = self._abs(href)
            if href in seen:
                continue
            seen.append(href)

            img = art.select_one('img')
            pic = ''
            if img:
                pic = (img.get('data-src') or img.get('src') or '').strip()
                if pic.startswith('data:'):
                    pic = (img.get('data-src') or '').strip()
                pic = self._abs(pic)

            date_el = art.select_one('.jeg_meta_date') or art.select_one('.elementor-post__date')
            remark = date_el.get_text(' ', strip=True) if date_el else ''

            items.append({
                'vod_id': href,
                'vod_name': title,
                'vod_pic': self.plp + pic if pic else '',
                'vod_remarks': remark,
            })
        return items

    # ------------------------- 分类列表 -------------------------
    def _categories(self):
        result = []
        for name, slug in self.CATEGORIES:
            url = self.host + '/archives/category/' + quote(slug, safe='/')
            result.append({'type_id': url, 'type_name': name})
        return result

    # ------------------------- spider api -------------------------
    def homeContent(self, filter):
        result = {'class': self._categories(), 'list': []}
        try:
            r = self._get(self.host + '/')
            soup = self._soup(self._text(r))
            result['list'] = self._parse_vod_list(soup)
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        result = {'list': []}
        try:
            r = self._get(self.host + '/')
            soup = self._soup(self._text(r))
            result['list'] = self._parse_vod_list(soup)
        except Exception:
            pass
        return result

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        result = {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}
        tid = str(tid or '')
        try:
            if tid.startswith('rec_'):
                result['list'] = self._rec_list(tid[4:])
                return result
            base = tid if tid.startswith('http') else self._abs(tid)
            url = base if pg <= 1 else base.rstrip('/') + '/page/%d/' % pg
            r = self._get(url)
            soup = self._soup(self._text(r))
            result['list'] = self._parse_vod_list(soup)
        except Exception:
            pass
        return result

    # 詳情页「熱門觀看中」二级推荐列表
    def _rec_list(self, vid):
        try:
            url = self.host + '/archives/' + vid
            r = self._get(url)
            soup = self._soup(self._text(r))
            for h in soup.find_all(['h2', 'h3']):
                if '熱門觀看中' in h.get_text() or '熱門' in h.get_text():
                    sec = h.find_parent('section')
                    if sec:
                        for sib in sec.find_all_next('section'):
                            if sib.select('article.elementor-post'):
                                return self._parse_vod_list(sib)
        except Exception:
            pass
        return []

    def detailContent(self, ids):
        url = ids[0] if str(ids[0]).startswith('http') else self._abs(ids[0])
        result = {'list': []}
        try:
            r = self._get(url)
            html = self._text(r)
            soup = self._soup(html)

            # 标题
            h1 = soup.select_one('h1.jeg_post_title')
            title = h1.get_text(strip=True) if h1 else ''
            if not title:
                og = soup.select_one('meta[property="og:title"]')
                title = og.get('content', '').strip() if og else ''
            if not title:
                t = soup.title.get_text(strip=True) if soup.title else ''
                title = t.split('|')[0].strip() if t else url

            # 封面
            pic = ''
            ogimg = soup.select_one('meta[property="og:image"]')
            if ogimg:
                pic = self._abs(ogimg.get('content', ''))
            if not pic:
                img = soup.select_one('.jeg_featured img, .entry-content img, article img')
                if img:
                    pic = self._abs(img.get('data-src') or img.get('src') or '')

            # 可点击 Tags（放在简介前面，须先于简介提取，因简介会剔除 tags 节点）
            tags = []
            for a in soup.select('.jeg_post_tags a'):
                name = a.get_text(strip=True)
                href = self._abs(a.get('href') or '')
                if name and href:
                    tags.append(self._cr(href, name))
            tag_str = ' '.join(tags)

            # 播放地址：m3u8 直链 + iframe 分流（须先于简介提取，因简介会剔除播放器节点）
            m3u8_list = self._extract_m3u8(html)
            iframe_list = self._extract_iframes(soup)
            play_from, play_url = self._build_play(m3u8_list, iframe_list)

            # 简介（视频介绍文本）
            intro = self._extract_intro(soup)

            # 内容：标签在前（加「标签：」前缀），视频介绍紧跟其后（不隔行）
            content = ''
            if tag_str:
                content = '标签：' + tag_str
            if intro:
                content = (content + '\n' + intro) if content else intro

            # 备注：日期 + 熱門觀看中 可点击标签
            remarks = []
            date_el = soup.select_one('.jeg_meta_date')
            if date_el:
                remarks.append(date_el.get_text(' ', strip=True))
            m = re.search(r'/archives/(\d+)', url)
            if m:
                remarks.append(self._cr('rec_' + m.group(1), '熱門觀看中'))

            vod = {
                'vod_id': url,
                'vod_name': title,
                'vod_pic': self.plp + pic if pic else '',
                'vod_content': content,
                'vod_remarks': ' '.join(remarks),
                'vod_play_from': play_from,
                'vod_play_url': play_url,
            }
            result['list'] = [vod]
        except Exception:
            pass
        return result

    # 提取简介文本（兼容动漫类 h6 正文 / AV 旧布局 p 段落 / AV 新布局「簡介：」文本）
    def _extract_intro(self, soup):
        ci = soup.select_one('.content-inner') or soup.select_one('.entry-content')
        if not ci:
            return ''
        # 剔除 tags / 播放器 / 脚本 / tab 标题节点
        for bad in ci.select('.jeg_post_tags, iframe, video, .flowplayer, .aiovg-player-container, script, noscript, .elementor-tab-title, .elementor-tab-mobile-title'):
            bad.decompose()
        parts = []
        seen = []
        for el in ci.find_all(['h6', 'h5', 'h4', 'p']):
            t = el.get_text(' ', strip=True)
            if not t or len(t) < 15:
                continue
            if t in seen:
                continue
            seen.append(t)
            parts.append(t)
        # 过滤纯标题（短且无中文标点），正文通常含。！？，
        filtered = [t for t in parts if ('。' in t or '！' in t or '？' in t or '，' in t) or len(t) >= 50]
        if filtered:
            return '\n'.join(filtered)
        if parts:
            return '\n'.join(parts)
        # 兜底：AV 类（「簡介：」开头文本节点）
        txt = ci.get_text('\n', strip=True)
        txt = re.sub(r'簡介\s*[:：]\s*', '', txt)
        txt = re.sub(r'Tags?\s*[:：]\s*', '', txt)
        lines = [l.strip() for l in txt.split('\n') if l.strip()]
        return '\n'.join(lines)

    # 提取页面所有 m3u8 直链（覆盖 video-js source / flowplayer data-item / 转义 JSON）
    def _extract_m3u8(self, html):
        urls = []
        seen = []
        # 先还原转义斜杠（flowplayer data-item 里是 https:\/\/xxx\/video.m3u8）
        unescaped = html.replace('\\/', '/')
        for m in re.finditer(r'https?://[^"\s\'<>]+?\.m3u8', unescaped):
            u = m.group(0).strip()
            if u not in seen:
                seen.append(u)
                urls.append(u)
        return urls

    # 提取 iframe（排除广告）
    def _extract_iframes(self, soup):
        urls = []
        seen = []
        for f in soup.select('iframe'):
            src = f.get('src') or f.get('data-src') or ''
            if not src:
                continue
            src = self._abs(src)
            if not src.startswith('http'):
                continue
            if any(k in src for k in ('whitetrafsa', 'creative.', 'google', 'cloudflare', 'yandex')):
                continue
            if src not in seen:
                seen.append(src)
                urls.append(src)
        return urls

    # 组装播放线路：$$$ 分线路、# 分集、$ 分集名和地址
    def _build_play(self, m3u8_list, iframe_list):
        play_from = []
        play_url = []
        if m3u8_list:
            play_from.append('Avbebe')
            parts = []
            for i, u in enumerate(m3u8_list):
                name = '高清' if len(m3u8_list) == 1 else '源%d' % (i + 1)
                parts.append('%s$%s' % (name, u))
            play_url.append('#'.join(parts))
        if iframe_list:
            play_from.append('分流')
            parts = []
            for i, u in enumerate(iframe_list):
                name = '线路%d' % (i + 1)
                parts.append('%s$%s' % (name, u))
            play_url.append('#'.join(parts))
        return '$$$'.join(play_from), '$$$'.join(play_url)

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg or 1)
        result = {'list': [], 'page': pg, 'pagecount': 9999}
        try:
            if pg <= 1:
                url = self.host + '/?s=' + quote(key)
            else:
                url = self.host + '/page/%d/?s=%s' % (pg, quote(key))
            r = self._get(url)
            soup = self._soup(self._text(r))
            result['list'] = self._parse_vod_list(soup)
        except Exception:
            pass
        return result

    def playerContent(self, flag, id, vipFlags):
        id = id or ''
        # m3u8/mp4 直链
        if self.isVideoFormat(id):
            return {'parse': 0, 'url': self.plp + id, 'header': self.headers}
        # iframe 二次解析
        if id.startswith('http'):
            m3u8 = self._resolve(id)
            if m3u8:
                return {'parse': 0, 'url': self.plp + m3u8, 'header': self.headers}
        # 兜底：webview 打开
        return {'parse': 1, 'url': id, 'header': self.headers}

    # iframe 地址 → 真实 m3u8
    def _resolve(self, url):
        if 'hgcloud.to' in url:
            return self._parse_hgcloud(url)
        # turbovidhls 等：请求页面直接搜 m3u8
        try:
            r = self._get(url, referer='https://avbebe.com/')
            html = self._text(r)
            arr = self._extract_m3u8(html)
            if arr:
                return arr[0]
        except Exception:
            pass
        return None

    # hgcloud.to/e/{id} → 域名池 → packer 解码 → m3u8
    def _parse_hgcloud(self, url):
        m = re.search(r'/e/([A-Za-z0-9]+)', url)
        if not m:
            return None
        vid = m.group(1)
        for host in self.HG_HOSTS:
            try:
                eu = 'https://%s/e/%s' % (host, vid)
                r = self._get(eu, referer='https://hgcloud.to/')
                html = self._text(r)
                decoded = self._decode_packed(html)
                if not decoded:
                    continue
                hm = re.search(r'["\']hls4["\']\s*:\s*["\']([^"\']+)["\']', decoded)
                if hm:
                    hls = hm.group(1)
                    if hls.startswith('/'):
                        return 'https://%s%s' % (host, hls)
                    if hls.startswith('http'):
                        return hls
                hm2 = re.search(r'["\']hls2["\']\s*:\s*["\']([^"\']+)["\']', decoded)
                if hm2:
                    return hm2.group(1)
                hm3 = re.search(r'["\']hls3["\']\s*:\s*["\']([^"\']+)["\']', decoded)
                if hm3:
                    return hm3.group(1)
            except Exception:
                continue
        return None

    # Dean Edwards Packer 解码
    def _decode_packed(self, html):
        m = re.search(r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\((.*?),(\d+),(\d+),'(.*?)'\.split\('\|'\)", html, re.S)
        if not m:
            return None
        p = m.group(1).strip("'")
        a = int(m.group(2))
        c = int(m.group(3))
        words = m.group(4).split('|')
        return self._unpack(p, a, c, words)

    def _b(self, n, base):
        if n == 0:
            return '0'
        s = ''
        while n > 0:
            s = self._DIGITS[n % base] + s
            n //= base
        return s

    def _unpack(self, p, a, c, k):
        for i in range(c - 1, -1, -1):
            if k[i]:
                p = re.sub(r'\b' + re.escape(self._b(i, a)) + r'\b', k[i], p)
        return p
