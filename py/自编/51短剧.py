# -*- coding: utf-8 -*-
# 51短剧 (永久地址 https://51hub.com/) OK影视爬虫
import json, base64
import requests
from urllib.parse import unquote, quote
from Crypto.Cipher import AES
from base.spider import Spider


class Spider(Spider):

    def init(self, extend="{}"):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        # 代理三行（照抄，由 extend 传，没传就直连）
        self.plp = config.get('plp', '')
        self.proxy = config.get('proxy', {})
        # 51hub 永久地址对应的 API 域名
        self.host = config.get('site', 'https://api.51dj1.com/api.php')
        # AES 解密参数（站点前端写死）
        self._key = b'2acf7e91e9864673'
        self._iv = b'1c29882d3ddfcfd6'
        # 图片 AES 解密参数
        self._img_key = b'f5d965df75336270'
        self._img_iv = b'97b60394abc2fbe1'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        }

    def getName(self):
        return '51短剧'

    # 请求接口并 AES 解密返回 data
    def _api(self, path, params=None):
        r = requests.post(self.host + path, data=params or {}, headers=self.headers,
                          proxies=self.proxy, timeout=20, verify=False)
        obj = json.loads(r.text)
        enc = obj.get('data')
        if isinstance(enc, str) and enc:
            ct = base64.b64decode(enc.replace(' ', '+'))
            cipher = AES.new(self._key, AES.MODE_CBC, self._iv)
            pt = cipher.decrypt(ct)
            pt = pt[:-pt[-1]]  # PKCS7 去填充
            obj = json.loads(pt.decode('utf-8', 'ignore'))
        d = obj.get('data', {}) if isinstance(obj, dict) else {}
        return d if isinstance(d, dict) else {}

    # 图片走 localProxy 图片代理（type=tbr_img，getProxyUrl 已带 /proxy）
    def _pic(self, url):
        if not url:
            return ''
        try:
            b = base64.b64encode(url.encode('utf-8')).decode()
            base = self.getProxyUrl()
            if not base:
                return url
            if '?' in base:
                return base + '&type=tbr_img&url=' + quote(b, safe='')
            return base + '?type=tbr_img&url=' + quote(b, safe='')
        except Exception:
            return url

    # 万/播放量格式化
    def _w(self, n):
        try:
            n = int(n)
        except Exception:
            return ''
        return '%.1fW' % (n / 10000.0) if n >= 10000 else str(n)

    # 批量拿集数（详情接口），缓存 {video_id: (episode_count, status)}
    def _fill_episodes(self, items):
        cache = getattr(self, '_epcache', None)
        if cache is None:
            cache = {}
            self._epcache = cache
        ids = []
        for it in items:
            vid = str(it.get('video_id') or it.get('id') or '')
            if vid and vid not in cache:
                ids.append(vid)
        if ids:
            def fetch(vid):
                try:
                    d = self._api('/api/playlet/detail', {'id': vid})
                    return vid, d.get('episode_count'), d.get('serialize_status_text') or ''
                except Exception:
                    return vid, None, ''
            try:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=12) as ex:
                    results = list(ex.map(fetch, ids))
            except Exception:
                results = [fetch(vid) for vid in ids]
            for vid, ep, st in results:
                if ep:
                    cache[vid] = (ep, st)
        return cache

    def _remark(self, it, cache=None):
        st = it.get('serialize_status_text') or ''
        vid = str(it.get('video_id') or it.get('id') or '')
        if cache and vid in cache:
            ep, st2 = cache[vid]
            st = st2 or st
            return '全%d集' % ep if st == '完结' else '已更新至%d集' % ep
        return st

    # 列表项 → vod
    def _vod(self, it, cache=None):
        pic = it.get('cover') or ''
        return {
            'vod_id': str(it.get('video_id') or it.get('id') or ''),
            'vod_name': it.get('title') or '',
            'vod_pic': self._pic(pic),
            'vod_remarks': self._remark(it, cache),
        }

    # 可点击标签
    def _cr(self, id, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': id, 'name': name}, ensure_ascii=False), name)

    def homeContent(self, filter):
        result = {'class': [], 'filters': {}, 'list': []}
        try:
            home = self._api('/api/home/homePage')
            result['class'] = [{'type_id': 'explore', 'type_name': '全部短剧'}]
            result['class'].extend([
                {'type_id': 'rank_week', 'type_name': '剧集周榜'},
                {'type_id': 'rank_month', 'type_name': '剧集月榜'},
            ])
            modules = home.get('modules', {}).get('list', []) if isinstance(home.get('modules'), dict) else []
            for m in modules:
                result['class'].append({'type_id': 'm%d' % m.get('id'), 'type_name': m.get('title', '')})
            result['class'].append({'type_id': 'actor', 'type_name': '演员'})
            seen = []
            items = list(home.get('top_list', []))
            explore = self._api('/api/theater/exploreList', {'page': 1})
            items += explore.get('list', [])
            cache = self._fill_episodes(items)
            for it in items:
                v = self._vod(it, cache)
                if v['vod_id'] and v['vod_id'] not in seen:
                    seen.append(v['vod_id'])
                    result['list'].append(v)
        except Exception:
            pass
        try:
            opt = self._api('/api/home/contentOptions')
            vf = opt.get('video_filter', {})
            if isinstance(vf, dict):
                fl = []
                for key, g in vf.items():
                    if isinstance(g, dict):
                        fl.append({'key': key, 'name': g.get('title', key),
                                   'value': [{'n': '全部', 'v': ''}] + [{'n': i.get('name', ''), 'v': str(i.get('value', ''))} for i in g.get('list', [])]})
                if fl:
                    result['filters']['explore'] = fl
            af = opt.get('actor_filter', [])
            if isinstance(af, list) and af:
                result['filters']['actor'] = [{'key': 'sort', 'name': '分类',
                                               'value': [{'n': i.get('name', ''), 'v': str(i.get('value', ''))} for i in af]}]
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        try:
            home = self._api('/api/home/homePage')
            items = list(home.get('top_list', []))
            explore = self._api('/api/theater/exploreList', {'page': 1})
            items += explore.get('list', [])
            cache = self._fill_episodes(items)
            seen = []
            result = []
            for it in items:
                v = self._vod(it, cache)
                if v['vod_id'] and v['vod_id'] not in seen:
                    seen.append(v['vod_id'])
                    result.append(v)
            return {'list': result}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'page': int(pg or 1), 'pagecount': 9999, 'limit': 30, 'total': 999999}
        try:
            pg = int(pg or 1)
            if tid == 'actor':
                data = self._api('/api/actor/list', {'page': pg, 'sort': extend.get('sort', '0') or '0'})
                result['list'] = [self._actor(it) for it in data.get('list', [])]
            elif tid == 'rank_week' or tid == 'rank_month':
                data = self._api('/api/theater/videoRank', {'type': 'week' if tid == 'rank_week' else 'month', 'page': pg})
                items = data.get('list', [])
                cache = self._fill_episodes(items)
                result['list'] = [self._vod(it, cache) for it in items]
            elif tid.startswith('m'):
                data = self._api('/api/home/recommendDetail', {'module_id': tid[1:], 'page': pg})
                items = data.get('list', [])
                cache = self._fill_episodes(items)
                result['list'] = [self._vod(it, cache) for it in items]
            else:  # explore 全部短剧
                p = {'page': pg}
                for k in ('theme', 'setting', 'background', 'audience', 'time', 'recommend'):
                    v = extend.get(k)
                    if v:
                        p[k] = v
                data = self._api('/api/theater/exploreList', p)
                items = data.get('list', [])
                cache = self._fill_episodes(items)
                result['list'] = [self._vod(it, cache) for it in items]
            result['total'] = data.get('total', result['total'])
        except Exception:
            pass
        return result

    def _actor(self, it):
        pic = it.get('avatar') or ''
        fans = self._w(it.get('fans_count') or it.get('collect_count'))
        return {
            'vod_id': 'actor_%s' % it.get('actor_id'),
            'vod_name': it.get('name', ''),
            'vod_pic': self._pic(pic),
            'vod_remarks': '作品%s · 粉丝%s' % (it.get('works', ''), fans),
            'vod_tag': 'folder',
            'style': {'type': 'oval'},
        }

    def detailContent(self, ids):
        vid = (ids[0] if isinstance(ids, list) else ids) or ''
        if vid.startswith('actor_'):
            return self._actor_detail(vid[6:])
        try:
            data = self._api('/api/playlet/detail', {'id': vid})
            tags = data.get('tags') or []
            actors = data.get('actor_list') or []
            content = []
            if data.get('type_text'):
                content.append('类型：%s' % data['type_text'])
            if tags:
                content.append('标签：%s' % ' '.join([self._cr(t, t) for t in tags]))
            if data.get('description'):
                content.append(data['description'])
            episodes = data.get('episodes') or []
            play_url = '#'.join(['第%02d集$%s_%s' % (int(ep.get('sort', i + 1)), vid, ep.get('id')) for i, ep in enumerate(episodes)])
            ep_count = data.get('episode_count')
            status = data.get('serialize_status_text') or ''
            if ep_count:
                remarks = '全%d集' % ep_count if status == '完结' else '已更新至%d集' % ep_count
            else:
                remarks = status
            vod = {
                'vod_id': vid,
                'vod_name': data.get('title') or '',
                'vod_pic': self._pic(data.get('cover') or ''),
                'vod_content': '\n'.join(content),
                'vod_actor': ' '.join([a.get('name', '') for a in actors]),
                'vod_remarks': remarks,
                'vod_play_from': '51短剧',
                'vod_play_url': play_url,
            }
            return {'list': [vod]}
        except Exception:
            return {'list': []}

    def _actor_detail(self, aid):
        try:
            data = self._api('/api/actor/actorDetail', {'actor_id': aid})
            info = data.get('info', {}) or {}
            lst = data.get('list', {}) or {}
            items = lst.get('list', []) if isinstance(lst, dict) else []
            cache = self._fill_episodes(items)
            vods = [self._vod(it, cache) for it in items]
            return {'list': vods}
        except Exception:
            return {'list': []}

    def searchContent(self, key, quick, pg="1"):
        result = {'list': [], 'page': int(pg or 1)}
        try:
            data = self._api('/api/search/result', {'keyword': key, 'tab': 'video', 'page': int(pg or 1)})
            items = data.get('list', [])
            cache = self._fill_episodes(items)
            result['list'] = [self._vod(it, cache) for it in items]
        except Exception:
            pass
        return result

    def playerContent(self, flag, id, vipFlags):
        try:
            if '_' in id and '.m3u8' not in id and '.mp4' not in id:
                vid, eid = id.split('_', 1)
                data = self._api('/api/playlet/play', {'video_id': vid, 'episode_id': eid})
                url = data.get('video_url') or ''
                if url:
                    return {'parse': 0, 'url': self.plp + url, 'header': self.headers}
        except Exception:
            pass
        if '.m3u8' in id or '.mp4' in id:
            return {'parse': 0, 'url': self.plp + id, 'header': self.headers}
        return {'parse': 1, 'url': id, 'header': self.headers}

    def localProxy(self, params):
        try:
            qs = params if isinstance(params, dict) else {}
            if not isinstance(params, dict):
                for p in str(params).split('&'):
                    if '=' in p:
                        k, v = p.split('=', 1)
                        qs[k] = unquote(v)
            if qs.get('type') != 'tbr_img':
                return [404, 'text/plain', b'not found']
            img_b64 = unquote(qs.get('url', ''))
            pad = 4 - len(img_b64) % 4
            if pad != 4:
                img_b64 += '=' * pad
            url = base64.b64decode(img_b64).decode('utf-8', 'ignore')
            h = {'User-Agent': self.headers.get('User-Agent', ''), 'Referer': self.host + '/'}
            r = requests.get(url, headers=h, proxies=self.proxy, timeout=20, verify=False)
            if r.status_code != 200:
                return [404, 'text/plain', b'image not found']
            data = r.content
            # 明文图片直接返回
            if data[:3] == b'\xff\xd8\xff':
                return [200, 'image/jpeg', data, {'Content-Length': str(len(data))}]
            if data[:4] == b'\x89PNG':
                return [200, 'image/png', data, {'Content-Length': str(len(data))}]
            if data[:4] == b'GIF8':
                return [200, 'image/gif', data, {'Content-Length': str(len(data))}]
            # 否则 AES-CBC 解密
            cipher = AES.new(self._img_key, AES.MODE_CBC, self._img_iv)
            dec = cipher.decrypt(data)
            p = dec[-1]
            if 1 <= p <= 16:
                dec = dec[:-p]
            if dec[:3] == b'\xff\xd8\xff':
                return [200, 'image/jpeg', dec, {'Content-Length': str(len(dec))}]
            if dec[:4] == b'\x89PNG':
                return [200, 'image/png', dec, {'Content-Length': str(len(dec))}]
            if dec[:4] == b'GIF8':
                return [200, 'image/gif', dec, {'Content-Length': str(len(dec))}]
            if len(dec) > 12 and dec[:4] == b'RIFF' and dec[8:12] == b'WEBP':
                return [200, 'image/webp', dec, {'Content-Length': str(len(dec))}]
            return [200, 'image/jpeg', dec, {'Content-Length': str(len(dec))}]
        except Exception:
            return [500, 'text/plain', b'decryption failed']
