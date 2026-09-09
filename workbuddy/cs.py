# -*- coding: utf-8 -*-
# //@name:Catemby
# //@id:catemby_multi
# //@version:30_hot_fix_sort_talist

import base64
import json
import re
import time
import hashlib

import requests
from urllib.parse import quote, unquote
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    name = "Catemby"
    # 主数据 API（jdforrepam.com，Cloudflare 被墙，走 proxy）
    API = "https://jdforrepam.com/api"
    # 播放 resolve（JavDB Web UI）
    RESOLVE = "https://catembylegacy.fastcdn.dpdns.org"
    TOKEN = "lpw6vgqzsp"
    SALT = "71cf27bb3c0bcdf207b64abecddc970098c7421ee7203b9cdae54478478a199e7d5a6e1a57691123c1a931c057842fb73ba3b3c83bcd69c17ccf174081e3d8aa"

    # (type_id, 名称, API type 编号)；hot 是排行榜特殊分类，无 type_no
    CATS = (
        ("hot", "热播", ""),
        ("censored", "有码", "0"),
        ("uncensored", "无码", "1"),
        ("western", "欧美", "2"),
        ("fc2", "FC2", "3"),
    )
    TYPE_MAP = {k: v for k, _, v in CATS if v}
    AREA_MAP = {"0": "日本", "1": "日本", "2": "欧美", "3": "FC2"}
    # filter_by 固定分段顺序：main(资源状态) / year / duration / month
    FILTER_KEYS = ("main", "year", "month", "duration")
    # 资源状态 -> filter_by main 段的值（与前端 cK 一致）
    AVAIL_MAP = {"p": "可播放", "m": "可下载", "c": "含字幕"}

    def init(self, extend=""):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        # ---- 代理三行（照抄，由源配置 extend 传入）----
        self.plp = config.get('plp', '')       # 播放器 URL 前缀（10079 转发，仅原始直连播放地址用）
        self.proxy = config.get('proxy', {})   # 内部请求代理（10172，spider 下载封面/分片/数据用）
        self.headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        self._hls = {}  # HLS m3u8 缓存 {token: 文本}

    def getName(self):
        return self.name

    def destroy(self):
        pass

    # ==================== 基础设施 ====================

    def _sign(self):
        ts = str(int(time.time()))
        return ts + '.' + self.TOKEN + '.' + hashlib.md5((ts + self.SALT).encode()).hexdigest()

    def _get(self, url, params=None, headers=None, timeout=20):
        h = dict(self.headers)
        if headers:
            h.update(headers)
        return requests.get(url, params=params, headers=h, proxies=self.proxy, timeout=timeout, verify=False)

    def _api(self, path, query=None, timeout=20):
        h = {'jdsignature': self._sign()}
        r = self._get(self.API + '/' + path.lstrip('/'), query or {}, h, timeout)
        data = r.json()
        if data.get('success') != 1:
            raise RuntimeError(data.get('message') or 'API error')
        return data.get('data') or {}

    @staticmethod
    def _b64e(s):
        return base64.urlsafe_b64encode(str(s or '').encode('utf-8')).decode().rstrip('=')

    @staticmethod
    def _b64d(s):
        s = str(s or '').strip()
        try:
            return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4)).decode('utf-8')
        except Exception:
            return ''

    def _cr(self, name, route):
        """可点击标签 -> 点击后走 categoryContent(route)"""
        name = re.sub(r'\s+', ' ', str(name or '')).strip()
        route = str(route or '').strip()
        if not name or not route:
            return ''
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': route, 'name': name}, ensure_ascii=False), name)

    # ==================== 首页 / 分类 ====================

    def homeContent(self, filter=False):
        result = {'class': [{'type_id': k, 'type_name': n} for k, n, _ in self.CATS], 'filters': {}}
        for tid, _, tno in self.CATS:
            if not tno:  # 热播无筛选
                continue
            rows = [
                {'key': 'sort', 'name': '排序', 'value': [
                    {'n': '最新', 'v': 'released'}, {'n': '磁链更新', 'v': 'magnet-updated'}]},
                {'key': 'main', 'name': '资源', 'value': [
                    {'n': '全部', 'v': ''}, {'n': '可播放', 'v': 'p'}, {'n': '可下载', 'v': 'm'}, {'n': '含字幕', 'v': 'c'}]},
            ]
            try:
                groups = self._api('/v2/tags', {'type': tno}, timeout=8).get('tags') or []
            except Exception:
                groups = []
            order = {k: i for i, k in enumerate(self.FILTER_KEYS)}
            groups = sorted(groups, key=lambda g: (order.get(str(g.get('category_id') or ''), 99), str(g.get('category_id') or '')))
            for g in groups:
                gid = str(g.get('category_id') or '').strip()
                if gid == 'main':  # 资源状态已硬编码，跳过
                    continue
                vals = [{'n': '全部', 'v': ''}]
                for tag in g.get('tags') or []:
                    tid2 = str((tag or {}).get('id') or '').strip()
                    nm = str((tag or {}).get('name') or '').strip()
                    if tid2 and nm and re.match(r'^[A-Za-z0-9._:-]{1,80}$', tid2):
                        vals.append({'n': nm, 'v': tid2})
                if gid and len(vals) > 1:
                    rows.append({'key': gid, 'name': str(g.get('category') or gid), 'value': vals[:240]})
            result['filters'][tid] = rows
        return result

    def homeVideoContent(self):
        try:
            return {'list': self._movies(self._api('/v1/movies/latest', {'page': 1, 'filter_by': 'all'}).get('movies'))}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        page = self._page(pg)
        text = str(tid or '').strip()
        if text == 'hot':
            return self._hot_page()
        # 二级列表路由（可点击标签）
        if text.startswith('search/'):
            return self._search_page(unquote(text[len('search/'):]), page)
        if text.startswith('actor/'):
            return self._related_page(text[len('actor/'):], 'actor_movies')
        if text.startswith('related/'):
            return self._related_page(text[len('related/'):], 'relative_movies')
        if text.startswith('list/'):
            return self._list_page(text[len('list/'):], page)
        type_no = self.TYPE_MAP.get(text)
        if type_no is None:
            return self._empty(page)
        ext = self._dict(extend)
        # 排序：默认最新；用户选了 magnet-updated 才用
        sort = ext.get('sort') if str(ext.get('sort') or '') in ('released', 'magnet-updated') else 'released'
        sort_by, order_by = ('update', 'desc') if sort == 'magnet-updated' else ('release', 'desc')
        # 资源状态 main：首页默认可下载(m)，用户选了才变
        main = ext.get('main', 'm') if ext.get('main', 'm') in ('', 'p', 'm', 'c') else 'm'
        vals = {k: str(ext.get(k) or '').strip() for k in ('year', 'month', 'duration')}
        extra = [str(ext.get(k) or '').strip() for k in sorted(ext) if k not in ('sort', 'main', 'year', 'month', 'duration')]
        extra = [x for x in extra if x]
        filter_by = '%s:t:%s:%s:%s:%s:%s' % (type_no, main, ','.join(extra), vals['year'], vals['duration'], vals['month'])
        try:
            data = self._api('/v1/movies/tags', {'filter_by': filter_by, 'sort_by': sort_by, 'order_by': order_by, 'page': page, 'limit': 24})
            return self._page_result(data.get('movies'), page)
        except Exception as e:
            return self._empty(page, self._clean(e))

    def searchContent(self, key, quick=False, pg='1'):
        page = self._page(pg)
        q = self._clean(key)
        if not q:
            return self._empty(page)
        return self._search_page(q, page)

    def _search_page(self, q, page):
        q = self._clean(q)
        if not q:
            return self._empty(page)
        try:
            data = self._api('/v2/search', {'q': q, 'page': page, 'type': 'movie', 'limit': 24})
            return self._page_result(data.get('movies'), page)
        except Exception as e:
            return self._empty(page, self._clean(e))

    def _hot_page(self):
        """热播 = 播放排行榜（/v1/rankings/playback，无分页）"""
        try:
            data = self._api('/v1/rankings/playback', {'filter_by': 'all', 'period': 'daily'})
            rows = self._page_result(data.get('movies'), 1).get('list') or []
            return {'list': rows, 'page': 1, 'pagecount': 1, 'limit': len(rows) or 24, 'total': len(rows)}
        except Exception as e:
            return self._empty(1, self._clean(e))

    def _related_page(self, movie_id, field):
        """TA还出演过(actor_movies) / 相关推荐(relative_movies) 二级列表"""
        try:
            movie = self._api('/v4/movies/' + quote(movie_id, safe='')).get('movie') or {}
            rows = self._page_result(movie.get(field), 1).get('list') or []
            return {'list': rows, 'page': 1, 'pagecount': 1, 'limit': len(rows) or 24, 'total': len(rows)}
        except Exception as e:
            return self._empty(1, self._clean(e))

    def _list_page(self, list_id, page):
        """清单 -> 清单内影片列表"""
        try:
            info = self._api('/v1/lists/' + quote(list_id, safe='')).get('list') or {}
            tno = str(info.get('type') or '0')
            data = self._api('/v1/movies/tags', {'filter_by': tno + ':l:' + list_id + ':', 'sort_by': 'release', 'order_by': 'desc', 'page': page, 'limit': 24})
            return self._page_result(data.get('movies'), page)
        except Exception as e:
            return self._empty(page, self._clean(e))

    # ==================== 详情 ====================

    def detailContent(self, ids):
        movie_id = str(ids[0] if isinstance(ids, (list, tuple)) and ids else ids).strip()
        if not re.match(r'^[A-Za-z0-9._:-]{1,120}$', movie_id):
            return {'list': []}
        try:
            movie = self._api('/v4/movies/' + quote(movie_id, safe='')).get('movie') or {}
        except Exception as e:
            return {'list': [self._detail_error(movie_id, e)]}
        if not movie:
            return {'list': [self._detail_error(movie_id, '详情为空')]}

        number = self._clean(movie.get('number') or movie.get('number_letter') or movie_id)
        title = self._clean(movie.get('title') or number)
        pic = self._img_proxy(movie.get('cover_url') or movie.get('thumb_url') or '') or (self.RESOLVE + '/favicon.ico')

        # 播放线路
        play_from = ['在线播放']
        play_url = ['在线播放$' + number]
        magnets = []
        if float(movie.get('magnets_count') or 0) > 0:
            try:
                magnets = self._magnets(self._api('/v1/movies/%s/magnets' % quote(movie_id, safe='')).get('magnets'))
            except Exception:
                magnets = []
        if magnets:
            play_from.append('磁力')
            play_url.append('#'.join('%s$%s' % (self._magnet_label(m), m['hash']) for m in magnets))

        # ---- 详情信息放置 ----
        # 演员 -> vod_actor
        actors = ' '.join(x for x in [self._cr(a.get('name'), 'search/' + quote(str(a.get('name') or ''), safe=''))
                                      for a in (movie.get('actors') or []) if isinstance(a, dict) and a.get('name')] if x)
        # 导演 -> vod_director
        director_name = self._fld(movie, 'director_name', 'director')
        vod_director = self._cr(director_name, 'search/' + quote(director_name, safe=''))

        # 片商、系列 -> vod_remarks（可点击）
        remarks = []
        maker_name = self._fld(movie, 'maker_name', 'maker')
        if maker_name:
            remarks.append(self._cr(maker_name, 'search/' + quote(maker_name, safe='')))
        series_name = self._fld(movie, 'series_name', 'series')
        if series_name:
            remarks.append(self._cr(series_name, 'search/' + quote(series_name, safe='')))
        if magnets:
            remarks.append('磁力%d' % len(magnets))
        if movie.get('has_cnsub'):
            remarks.append('中字')

        # 内容块：类别 + 三个二级列表 + 简介（最后）
        content = []
        tags = [self._cr(x, 'search/' + quote(x, safe='')) for x in self._tag_names(movie.get('tags'))]
        if tags:
            content.append('类别: ' + ' '.join(tags))
        if movie.get('actor_movies'):
            content.append('TA还出演过: ' + self._cr('TA还出演过', 'actor/' + quote(movie_id, safe='')))
        if movie.get('relative_movies'):
            content.append('相关推荐: ' + self._cr('相关推荐', 'related/' + quote(movie_id, safe='')))
        lists = self._list_links(movie_id)
        if lists:
            content.append('相关清单: ' + ' '.join(lists))
        summary = self._clean(movie.get('summary'))
        if summary:
            content.append('')
            content.append('简介: ' + summary)

        return {'list': [{
            'vod_id': movie_id,
            'vod_name': ('%s %s' % (number, title)).strip(),
            'vod_pic': pic,
            'vod_remarks': ' · '.join(remarks) or number,
            'vod_content': '\n'.join(content),
            'vod_actor': actors,
            'vod_director': vod_director,
            'vod_year': str(movie.get('release_date') or '')[:10],
            'vod_area': self.AREA_MAP.get(str(movie.get('type') or ''), ''),
            'vod_duration': self._duration(movie.get('duration')),
            'vod_score': float(movie.get('score') or 0),
            'vod_play_from': '$$$'.join(play_from),
            'vod_play_url': '$$$'.join(play_url),
        }]}

    def _list_links(self, movie_id):
        """相关清单 -> 每个清单一个可点击标签，点击进清单影片列表"""
        rows = []
        try:
            rows = self._api('/v1/lists/related', {'movie_id': movie_id}, timeout=8).get('lists') or []
        except Exception:
            rows = []
        out = []
        for item in rows or []:
            if not isinstance(item, dict):
                continue
            lid = str(item.get('id') or '').strip()
            name = self._clean(item.get('name') or item.get('title'))
            if lid and name:
                out.append(self._cr(name, 'list/' + quote(lid, safe='')))
        return out

    # ==================== 播放 ====================

    def playerContent(self, flag, id, vipFlags=None):
        code = str(id or '').strip()
        if flag == '磁力':
            if re.match(r'^[A-Z0-9]{40}$', code, re.I):
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': 'push://magnet:?xt=urn:btih:' + code.upper(), 'header': {}}
            return self._player_error('磁力地址无效')
        if not code:
            return self._player_error('缺少番号')
        try:
            data = self._get(self.RESOLVE + '/api/v/resolve', {'code': code, 'lang': 'zh'},
                             {'Referer': self.RESOLVE + '/'}).json()
        except Exception as e:
            return self._player_error(e)
        variants = [v for v in (data.get('variants') or []) if isinstance(v, dict) and (v.get('sourceUrl') or v.get('url'))]
        if not variants:
            return self._player_error(data.get('error') or data.get('message') or '无可用播放源')
        v = self._pick_variant(variants)
        url = str(v.get('sourceUrl') or v.get('url') or '').strip()
        if url.startswith('data:'):
            return self._hls_player(url)
        if not (url.startswith('http://') or url.startswith('https://')):
            return self._player_error('媒体地址无效')
        # 原始直连播放地址 -> self.plp 前缀（播放器请求走 10079）
        return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': self.plp + url, 'header': {}}

    def _pick_variant(self, variants):
        for v in variants:
            if str(v.get('variant') or '').lower() == 'original':
                return v
        return max(variants, key=lambda x: x.get('quality') or 0)

    def _hls_player(self, data_uri):
        body = self._decode_playlist(data_uri)
        # 分片走本地代理（spider 用 proxies=self.proxy 下载转发），不用 self.plp
        out = []
        for line in body.splitlines():
            s = line.strip()
            if s and not s.startswith('#') and (s.startswith('http://') or s.startswith('https://')):
                out.append(self.getProxyUrl() + '&type=raw&url=' + self._b64e(s))
            else:
                out.append(line)
        m3u8 = '\n'.join(out)
        token = hashlib.md5(m3u8.encode('utf-8')).hexdigest()
        self._hls[token] = m3u8
        return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': self.getProxyUrl() + '&type=hls&key=' + token, 'header': {}}

    def _decode_playlist(self, value):
        text = str(value or '')
        pos = text.find(',')
        if pos <= 0:
            raise RuntimeError('HLS data URI 缺少 payload')
        meta, payload = text[:pos].lower(), text[pos + 1:]
        raw = base64.b64decode(payload) if ';base64' in meta else unquote(payload).encode('utf-8')
        body = raw.decode('utf-8', 'replace')
        if not body.lstrip().startswith('#EXTM3U'):
            raise RuntimeError('HLS 缺少 EXTM3U')
        return body

    # ==================== 本地代理（localProxy）====================

    def localProxy(self, param):
        data = param if isinstance(param, dict) else {}
        typ = str(data.get('type') or '')
        try:
            if typ == 'img':
                raw, mime = self._fetch_image(self._b64d(data.get('url')))
                return [200, mime, raw, {'Access-Control-Allow-Origin': '*', 'Content-Length': str(len(raw))}]
            if typ == 'hls':
                body = self._hls.get(data.get('key'))
                if body:
                    return [200, 'application/vnd.apple.mpegurl', body.encode('utf-8'), {'Access-Control-Allow-Origin': '*'}]
            if typ == 'raw':
                raw, ctype = self._fetch_raw(self._b64d(data.get('url')))
                return [200, ctype, raw, {'Access-Control-Allow-Origin': '*', 'Content-Length': str(len(raw))}]
        except Exception:
            pass
        return [404, 'text/plain', b'']

    def _fetch_image(self, url):
        """封面下载：spider 走 proxies=self.proxy + Referer，兼容简单 XOR 解密"""
        if not url:
            raise RuntimeError('图片地址无效')
        r = requests.get(url, headers={
            'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
            'Referer': self.RESOLVE + '/',
            'User-Agent': 'Mozilla/5.0',
        }, proxies=self.proxy, timeout=20, verify=False)
        raw = r.content
        mime = self._image_mime(raw)
        if mime:
            return raw, mime
        cands = []
        if raw:
            cands.append(bytes(v ^ raw[0] for v in raw[1:]))
        for i in (0, 1, 2):
            if len(raw) > i:
                cands.append(bytes(v ^ 0x7F for v in raw[i:]))
        for c in cands:
            mime = self._image_mime(c)
            if mime:
                return c, mime
        return raw, 'image/jpeg'

    def _fetch_raw(self, url):
        """分片/任意资源下载：spider 走 proxies=self.proxy 转发"""
        if not url:
            raise RuntimeError('资源地址无效')
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': self.RESOLVE + '/'},
                         proxies=self.proxy, timeout=20, verify=False)
        ctype = r.headers.get('Content-Type') or 'application/octet-stream'
        return r.content, ctype

    @staticmethod
    def _image_mime(raw):
        if raw.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        if raw.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'image/png'
        if raw.startswith((b'GIF87a', b'GIF89a')):
            return 'image/gif'
        if raw.startswith(b'BM'):
            return 'image/bmp'
        if len(raw) >= 12 and raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
            return 'image/webp'
        return ''

    # ==================== 列表映射 ====================

    def _page_result(self, movies, page):
        rows, seen = [], set()
        for m in (movies or []):
            if not isinstance(m, dict):
                continue
            mid = str(m.get('id') or '').strip()
            if not mid or mid in seen:
                continue
            seen.add(mid)
            number = self._clean(m.get('number') or m.get('number_letter') or mid)
            title = self._clean(m.get('title') or number)
            remarks = []
            mc = int(float(m.get('magnets_count') or 0))
            if mc:
                remarks.append('磁力%d' % mc)
            if m.get('has_cnsub'):
                remarks.append('中字')
            if m.get('can_play'):
                remarks.append('可播放')
            rows.append({
                'vod_id': mid,
                'vod_name': ('%s %s' % (number, title)).strip(),
                'vod_pic': self._img_proxy(m.get('cover_url') or m.get('thumb_url') or ''),
                'vod_remarks': ' · '.join(remarks) or self._duration(m.get('duration')),
                'vod_year': str(m.get('release_date') or '')[:10],
            })
        more = 1 if len(rows) >= 24 else 0
        return {'list': rows, 'page': page, 'pagecount': page + more, 'limit': 24, 'total': (page + more) * 24}

    def _movies(self, movies):
        return self._page_result(movies, 1).get('list') or []

    def _img_proxy(self, url):
        url = str(url or '').strip()
        if not (url.startswith('http://') or url.startswith('https://')):
            return ''
        return self.getProxyUrl() + '&type=img&url=' + self._b64e(url)

    def _magnets(self, items):
        rows, seen = [], set()
        for m in (items or []):
            if not isinstance(m, dict):
                continue
            h = str(m.get('hash') or '').strip().upper()
            if not re.match(r'^[A-Z0-9]{40}$', h) or h in seen:
                continue
            seen.add(h)
            name = self._clean(m.get('name'))
            rows.append({
                'hash': h,
                'name': name,
                'sub': bool(m.get('cnsub')) or bool(re.search(r'中文字幕|简体|繁体|中字|字幕|CHS|CHT|SUB', name, re.I)),
                'hd': bool(m.get('hd')) or bool(re.search(r'(?:^|[^A-Z0-9])(HD|FHD|UHD|4K|1080P|720P)(?:[^A-Z0-9]|$)', name, re.I)),
                'size': float(m.get('size') or 0),
            })
        rows.sort(key=lambda x: (0 if x['sub'] else 1, 0 if x['hd'] else 1, -(x['size'] or 0)))
        return rows

    def _magnet_label(self, m):
        marks = []
        if m.get('sub'):
            marks.append('中字')
        if m.get('hd'):
            marks.append('HD')
        size = m.get('size') or 0
        stxt = '%.2fGB' % (size / 1024) if size >= 1024 else ('%dMB' % int(size) if size > 0 else '')
        name = self._clean(m.get('name') or '磁力').replace('#', ' ').replace('$', ' ')[:100]
        prefix = ' '.join('[%s]' % x for x in marks)
        return ' | '.join(x for x in [prefix, stxt, name] if x)

    def _tag_names(self, tags):
        out = []
        for t in tags or []:
            n = t if isinstance(t, str) else (t or {}).get('name') if isinstance(t, dict) else ''
            n = self._clean(n)
            if n:
                out.append(n)
        return out

    # ==================== 工具 ====================

    def _empty(self, page, msg=''):
        d = {'list': [], 'page': page, 'pagecount': page, 'limit': 24, 'total': 0}
        if msg:
            d['msg'] = self._clean(msg)
        return d

    def _detail_error(self, movie_id, msg):
        return {'vod_id': movie_id or 'error', 'vod_name': '详情读取失败', 'vod_content': self._clean(msg)}

    def _player_error(self, msg):
        text = self._clean(msg) or '播放失败'
        return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'msg': text}

    @staticmethod
    def _clean(v):
        return re.sub(r'\s+', ' ', str(v or '')).strip()

    def _fld(self, movie, *names):
        """从 movie 取第一个非空字段（兼容 _name 后缀和裸字段，dict 取 name/title）"""
        for n in names:
            v = movie.get(n)
            if isinstance(v, dict):
                v = v.get('name') or v.get('title') or ''
            v = self._clean(v)
            if v:
                return v
        return ''

    @staticmethod
    def _dict(v):
        if isinstance(v, dict):
            return v
        if not v:
            return {}
        try:
            d = json.loads(str(v))
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _page(v):
        try:
            return max(1, int(v))
        except Exception:
            return 1

    @staticmethod
    def _duration(v):
        try:
            n = float(v or 0)
            return '%d分钟' % int(round(n)) if n > 0 else ''
        except Exception:
            return ''
