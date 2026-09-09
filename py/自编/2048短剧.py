# -*- coding: utf-8 -*-
# OK影视 spider - 2048AI短剧（AI短剧 + 视频）
import json, re, base64
import requests
from urllib.parse import quote, urljoin, urlparse
from base.spider import Spider


class Spider(Spider):
    def init(self, extend="{}"):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        # 站点用 http（https 在 plp 转发时 SSL 易失败）
        self.host = config.get('site', 'http://2048ai.vip').rstrip('/')
        # 代理三行（由 extend 传，没传就直连）
        self.plp = config.get('plp', '')
        self.proxy = config.get('proxy', {})
        # 不带 Origin（否则 403 Invalid CORS request）
        self.headers = {
            'referer': self.host + '/media/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 16; 2211133C) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9',
        }
        self._menus = []   # 菜单缓存
        self._cats = []    # 分类缓存

    def getName(self):
        return '2048AI短剧'

    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(m3u8|mp4|ts)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ---- 内部请求：一律走 self.proxy ----
    def _get(self, url, timeout=20, extra_headers=None):
        headers = dict(self.headers)
        if extra_headers:
            headers.update(extra_headers)
        return requests.get(url, headers=headers, proxies=self.proxy, timeout=timeout, verify=False)

    def _json(self, r):
        try:
            data = r.json()
        except Exception:
            return {}
        if isinstance(data, dict) and data.get('code') == 200:
            return data.get('data', data)
        return data

    def _text(self, r):
        try:
            return r.content.decode('utf-8')
        except Exception:
            return r.content.decode('utf-8', 'ignore')

    def _abs(self, u):
        if not u:
            return ''
        if u.startswith('http'):
            return u
        if u.startswith('//'):
            return 'http:' + u
        return urljoin(self.host + '/', u)

    # ---- 封面：明文，加 size=thumbnail 缩略图（原图 2.4MB 加载慢）----
    def _cover(self, cover):
        if not cover:
            return ''
        t = cover
        if not t.startswith('http://') and not t.startswith('https://') and not t.startswith('/'):
            t = 'https://d3t4z7ziql7nr5.cloudfront.net/' + t
        if '/api/v1/image/proxy' in t:
            if 'size=' not in t:
                t += '&size=thumbnail' if '?' in t else '?size=thumbnail'
        elif 'd3t4z7ziql7nr5.cloudfront.net' in t:
            t = '/api/v1/image/proxy?path=' + quote(t.replace('https://d3t4z7ziql7nr5.cloudfront.net/', ''), safe='') + '&size=thumbnail'
        return self._abs(t)

    def _pic_url(self, cover):
        """封面走 localProxy：Python 层带 Referer 请求并返回图片二进制（image/proxy 复杂 query 走 plp 会失败）"""
        full = self._cover(cover)
        if not full:
            return ''
        return self.getProxyUrl() + '&type=img&url=' + base64.b64encode(full.encode('utf-8')).decode()

    # ---- 菜单/分类（动态，匹配网站结构）----
    def _load_cats(self):
        if self._menus:
            return
        try:
            self._menus = self._json(self._get(self.host + '/api/v1/menus?productId=1'))
            if not isinstance(self._menus, list):
                self._menus = []
        except Exception:
            self._menus = []
        try:
            d = self._json(self._get(self.host + '/api/v1/categories?type=video'))
            self._cats = [c for c in d if c.get('enabled') and c.get('type') == 'video'] if isinstance(d, list) else []
        except Exception:
            self._cats = []

    def _subs(self, menu_id):
        return sorted([(c.get('sortOrder', 0), c['id'], c['name']) for c in self._cats if c.get('menuId') == menu_id])

    def homeContent(self, filter):
        result = {'class': [], 'filters': {}, 'list': []}
        try:
            self._load_cats()
            result['class'].append({'type_id': 'drama', 'type_name': 'AI短剧'})
            for m in sorted(self._menus, key=lambda x: x.get('sortOrder', 0)):
                if m.get('type') != 'video':
                    continue
                mid = m['id']
                tid = 'recent' if mid == 6 else 'menu_' + str(mid)
                result['class'].append({'type_id': tid, 'type_name': m.get('name', '')})
                subs = self._subs(mid)
                if subs:
                    result['filters'][tid] = [{
                        'key': 'type', 'name': '分类',
                        'value': [{'n': name, 'v': str(cid)} for _, cid, name in subs],
                    }]
            data = self._json(self._get(self.host + '/api/v1/videos?page=1&size=20'))
            result['list'] = self._format_video(data.get('items', [])) if isinstance(data, dict) else []
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'page': int(pg or 1), 'pagecount': 9999, 'limit': 20, 'total': 999999}
        try:
            page = int(pg or 1)
            if tid == 'drama':
                data = self._json(self._get('{}/api/v1/short-dramas?productId=1&sortBy=heat&page={}&size=20'.format(self.host, page)))
                if isinstance(data, dict):
                    result['list'] = self._format_drama(data.get('items', []))
                    result['page'], result['pagecount'], result['total'] = data.get('page', page), data.get('totalPages', 1), data.get('total', 0)
            else:
                cid = ''
                if tid.startswith('menu_'):
                    cid = (extend or {}).get('type', '') if isinstance(extend, dict) else ''
                    if not cid:
                        subs = self._subs(int(tid[5:]))
                        cid = str(subs[0][1]) if subs else ''
                q = ('&categoryId=' + cid) if cid else ''
                data = self._json(self._get('{}/api/v1/videos?page={}&size=20{}'.format(self.host, page, q)))
                if isinstance(data, dict):
                    result['list'] = self._format_video(data.get('items', []))
                    result['page'], result['pagecount'], result['total'] = data.get('page', page), data.get('totalPages', 1), data.get('total', 0)
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0] if isinstance(ids, list) else ids)
            vod = self._drama_detail(vid[6:]) if vid.startswith('drama_') else self._video_detail(vid[6:] if vid.startswith('video_') else vid)
        except Exception:
            pass
        return {'list': [vod]} if vod else {'list': []}

    def _video_detail(self, vid):
        data = self._json(self._get('{}/api/v1/videos/{}'.format(self.host, vid)))
        if not isinstance(data, dict) or not data.get('id'):
            return {}
        vurl = data.get('videoUrl', '')
        play = ('正片$' + self._m3u8(vurl)) if vurl else ''
        return {
            'vod_id': 'video_' + str(data['id']),
            'vod_name': data.get('title', ''),
            'vod_pic': self._pic_url(data.get('coverUrl', '')),
            'vod_remarks': self._dur(data.get('durationSec', 0)),
            'vod_content': data.get('description', '') or '',
            'vod_play_from': '2048AI',
            'vod_play_url': play,
        }

    def _drama_detail(self, did):
        data = self._json(self._get('{}/api/v1/short-dramas/{}?productId=1'.format(self.host, did)))
        if not isinstance(data, dict) or not data.get('id'):
            return {}
        plays = []
        for ep in data.get('episodes', []):
            vurl = ep.get('videoUrl', '')
            if vurl:
                plays.append('第%s集$%s' % (ep.get('episodeNo', ''), self._m3u8(vurl)))
        rating = data.get('rating')
        remark = ('★ %s ' % rating if rating is not None else '') + '全%d集' % data.get('episodeCount', 0)
        heat = data.get('heatCount', 0)
        if heat:
            remark += ' 热度%.1f万' % (heat / 10000.0)
        return {
            'vod_id': 'drama_' + str(data['id']),
            'vod_name': data.get('title', ''),
            'vod_pic': self._pic_url(data.get('coverUrl', '')),
            'vod_remarks': remark,
            'vod_content': data.get('description', '') or '',
            'vod_play_from': 'AI短剧',
            'vod_play_url': '#'.join(plays) if plays else '',
        }

    def _m3u8(self, vurl):
        """m3u8 相对路径 → 完整 m3u8 代理 URL"""
        if not vurl:
            return ''
        return '{}/api/v1/m3u8/proxy?path={}'.format(self.host, quote(vurl, safe=''))

    def searchContent(self, key, quick, pg="1"):
        result = {'list': [], 'page': int(pg or 1)}
        try:
            page = int(pg or 1)
            url = '{}/api/v1/videos/search?q={}&page={}&size=20'.format(self.host, quote(str(key)), page)
            data = self._json(self._get(url, extra_headers={'referer': '{}/media/search?q={}'.format(self.host, quote(str(key)))}))
            if isinstance(data, dict):
                result['list'] = self._format_video(data.get('items', []))
        except Exception:
            pass
        return result

    def playerContent(self, flag, id, vipFlags):
        """播放：m3u8 走 localProxy，改写 ts 分片走 plp 代理"""
        if '.m3u8' in id:
            if '/api/v1/m3u8/proxy' in id:
                m3u8_url = id
            else:
                path = id
                if path.startswith('http'):
                    path = urlparse(path).path.lstrip('/')
                m3u8_url = '{}/api/v1/m3u8/proxy?path={}'.format(self.host, quote(path, safe=''))
            return {'parse': 0, 'url': self.getProxyUrl() + '&type=m3u8&url=' + base64.b64encode(m3u8_url.encode('utf-8')).decode(), 'header': self.headers}
        if '.mp4' in id:
            return {'parse': 0, 'url': self.plp + id, 'header': self.headers}
        return {'parse': 1, 'url': id, 'header': self.headers}

    def localProxy(self, param):
        """处理封面图片和 m3u8 改写（内部请求走 self.proxy）"""
        try:
            if not isinstance(param, dict):
                return [404, 'text/plain', b'']
            ptype = param.get('type', '')
            url = base64.b64decode(param.get('url', '')).decode('utf-8')
            if ptype == 'img':
                r = self._get(url)
                mime = r.headers.get('Content-Type', 'image/jpeg')
                return [200, mime, r.content]
            if ptype == 'm3u8':
                r = self._get(url)
                text = self._text(r)
                text = self._rewrite_m3u8(text)
                return [200, 'application/vnd.apple.mpegurl', text.encode('utf-8')]
        except Exception:
            pass
        return [404, 'text/plain', b'']

    def _rewrite_m3u8(self, text):
        """把 m3u8 里的 ts 分片和 AES key 绝对 URL 改写成 plp 前缀（走本地代理）"""
        lines = text.split('\n')
        out = []
        for line in lines:
            line = line.rstrip('\r\n')
            if line.startswith('http'):
                line = self.plp + line
            elif 'URI="' in line and ('http://' in line or 'https://' in line):
                line = re.sub(r'URI="(https?://[^"]+)"', lambda m: 'URI="' + self.plp + m.group(1) + '"', line)
            out.append(line)
        return '\n'.join(out)

    # ---- 列表格式化 ----
    def _format_video(self, items):
        out, seen = [], set()
        for it in items:
            try:
                vid = str(it.get('id', ''))
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                out.append({
                    'vod_id': 'video_' + vid,
                    'vod_name': it.get('title', '') or '',
                    'vod_pic': self._pic_url(it.get('coverUrl', '')),
                    'vod_remarks': self._dur(it.get('durationSec', 0)),
                })
            except Exception:
                continue
        return out

    def _format_drama(self, items):
        out, seen = [], set()
        for it in items:
            try:
                did = str(it.get('id', ''))
                if not did or did in seen:
                    continue
                seen.add(did)
                rating = it.get('rating')
                remark = ('★ %s ' % rating if rating is not None else '') + '全%d集' % it.get('episodeCount', 0)
                out.append({
                    'vod_id': 'drama_' + did,
                    'vod_name': it.get('title', '') or '',
                    'vod_pic': self._pic_url(it.get('coverUrl', '')),
                    'vod_remarks': remark,
                })
            except Exception:
                continue
        return out

    def _dur(self, seconds):
        try:
            seconds = int(seconds or 0)
        except Exception:
            seconds = 0
        if seconds <= 0:
            return ''
        m, s = divmod(seconds, 60)
        if m >= 60:
            h, m = divmod(m, 60)
            return '%d:%02d:%02d' % (h, m, s)
        return '%d:%02d' % (m, s)
