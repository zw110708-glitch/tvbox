# -*- coding: utf-8 -*-
# OK影视 爬虫源 —— 合集(视频+小说)
# 站点 API: https://api.736136.com/api/video  (聚合采集站 spjk.iosh5md.com)
# 结构: get/menu(视频源站) -> get/nav?id=(子分类,link) -> link(视频列表,address解析接口) -> address(真实m3u8)
#        novelType/index(小说分类) -> novel/titleList(小说列表) -> novel/info(正文)
import json, re, base64
import requests
from base.spider import Spider


class Spider(Spider):

    def init(self, extend="{}"):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}

        self.host = config.get('site', 'https://api.736136.com/api/video')
        # ---- 代理三行（照抄，由 extend 传，没传就直连）----
        self.plp = config.get('plp', '')       # 播放器/封面/播放地址 URL 前缀
        self.proxy = config.get('proxy', {})   # 内部请求代理

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        # 子分类缓存: {源站id: {子分类id: (name, link)}}
        self._subs = {}

    def getName(self):
        return '合集视频'

    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(m3u8|mp4|ts)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ---- 内部请求：一律走 self.proxy ----
    def _get(self, url, timeout=15):
        return requests.get(url, headers=self.headers, proxies=self.proxy, timeout=timeout, verify=False)

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

    def _json_get(self, url, timeout=15):
        r = self._get(url, timeout=timeout)
        return json.loads(self._text(r))

    # ---- vod_id 编码/解码（携带标题+播放地址，详情页可还原）----
    def _encode_id(self, title, addr):
        try:
            return base64.urlsafe_b64encode(json.dumps({'t': title, 'u': addr}, ensure_ascii=False).encode('utf-8')).decode().rstrip('=')
        except Exception:
            return addr

    def _decode_id(self, vid):
        try:
            pad = '=' * (-len(vid) % 4)
            return json.loads(base64.urlsafe_b64decode(vid + pad).decode('utf-8'))
        except Exception:
            return {'t': vid, 'u': vid}

    # ---- 拿某源站的子分类 link（惰性缓存）----
    def _get_subs(self, sid):
        if sid not in self._subs:
            try:
                nav = self._json_get(self.host + '/get/nav?id=' + str(sid), timeout=10)
                self._subs[sid] = {}
                for s in nav.get('data', []):
                    if s.get('link'):
                        self._subs[sid][str(s.get('id'))] = (s.get('name') or '', s.get('link'))
            except Exception:
                self._subs[sid] = {}
        return self._subs[sid]

    def _sub_name(self, sid, kid):
        try:
            return self._subs.get(sid, {}).get(kid, ('', ''))[0]
        except Exception:
            return ''

    def homeContent(self, filter):
        result = {'class': [], 'filters': {}}
        # 视频源站
        try:
            menu = self._json_get(self.host + '/get/menu', timeout=10)
            for site in menu.get('data', []):
                sid = str(site.get('id'))
                tid = 'v' + sid
                result['class'].append({'type_id': tid, 'type_name': site.get('name', '') or '源站'})
                subs = self._get_subs(sid)
                if subs:
                    result['filters'][tid] = [{
                        'key': 'type', 'name': '分类',
                        'value': [{'n': self._sub_name(sid, k), 'v': k} for k in subs]
                    }]
        except Exception as e:
            self.log('homeContent menu err: %s' % e)
        # 小说
        result['class'].append({'type_id': 'novel', 'type_name': '小说'})
        try:
            nt = self._json_get(self.host + '/novelType/index', timeout=10)
            nlist = nt.get('data', {}).get('data', [])
            result['filters']['novel'] = [{
                'key': 'type', 'name': '分类',
                'value': [{'n': n.get('name', ''), 'v': str(n.get('id'))} for n in nlist]
            }]
        except Exception as e:
            self.log('homeContent novel err: %s' % e)
        return result

    def homeVideoContent(self):
        return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'page': int(pg or 1), 'pagecount': 9999, 'limit': 90, 'total': 999999}
        sub = ''
        if isinstance(extend, dict):
            sub = str(extend.get('type') or '')
        try:
            # 小说
            if tid == 'novel':
                return self._novel_list(sub, pg)
            # 视频源站
            sid = tid[1:] if tid.startswith('v') else str(tid)
            subs = self._get_subs(sid)
            link = subs.get(sub, ('', ''))[1] if sub else ''
            if not link and subs:
                link = list(subs.values())[0][1]  # 兜底：第一个子分类
            if not link:
                return result
            items = self._json_get(link, timeout=20)
            if isinstance(items, list):
                for block in items:
                    if not isinstance(block, dict):
                        continue
                    for it in block.get('data', []):
                        self._push_video(result['list'], it)
        except Exception as e:
            self.log('categoryContent err: %s' % e)
        return result

    def _push_video(self, out, it):
        addr = (it.get('address') or '').strip()
        title = (it.get('title') or '').strip()
        if not addr:
            return
        vid = self._encode_id(title, addr)
        out.append({
            'vod_id': vid,
            'vod_name': title or '视频',
            'vod_pic': self.plp + (it.get('img') or ''),
            'vod_remarks': (it.get('time') or ''),
        })

    def _novel_list(self, sub, pg):
        result = {'list': [], 'page': int(pg or 1), 'pagecount': 9999, 'limit': 90, 'total': 999999}
        t = sub or '8'
        data = self._json_get(self.host + '/novel/titleList?type_id=' + t + '&page=' + str(pg), timeout=20)
        d = data.get('data', {})
        for it in d.get('data', []):
            result['list'].append({
                'vod_id': 'n' + str(it.get('id')),
                'vod_name': it.get('title', '') or '小说',
                'vod_pic': '',
            })
        return result

    def detailContent(self, ids):
        if not ids:
            return {'list': []}
        vid = ids[0]
        # 小说正文
        if vid.startswith('n'):
            return {'list': [{
                'vod_id': vid,
                'vod_name': '小说',
                'vod_play_from': '小说',
                'vod_play_url': '正文$' + vid,
            }]}
        # 视频
        v = self._decode_id(vid)
        title = v.get('t', '') or '视频'
        addr = v.get('u', '') or vid
        return {'list': [{
            'vod_id': vid,
            'vod_name': title,
            'vod_play_from': '默认线路',
            'vod_play_url': '正片$' + addr,
        }]}

    def searchContent(self, key, quick, pg="1"):
        return {'list': [], 'page': int(pg or 1)}

    def playerContent(self, flag, id, vipFlags):
        sid = str(id)
        # 小说
        if sid.startswith('n'):
            try:
                info = self._json_get(self.host + '/novel/info?id=' + sid[1:], timeout=20)
                d = info.get('data', {})
                content = (d.get('content') or '')
                content = re.sub(r'<(p|/p|br|/br)[^>]*>', '\n', content)
                content = re.sub(r'<[^>]+>', '', content)
                content = content.replace('&nbsp;', ' ').strip()
                return {'parse': 0, 'playUrl': '', 'url': 'novel://' + json.dumps({'title': d.get('title', ''), 'content': content}, ensure_ascii=False), 'header': ''}
            except Exception as e:
                self.log('novel player err: %s' % e)
                return {'parse': 1, 'url': self.plp + sid, 'header': self.headers}
        # 解析接口（sw.php / xj.php，含 pay= 参数），请求拿真实 m3u8
        if 'pay=' in sid or 'sw.php' in sid or 'xj.php' in sid:
            try:
                r = self._get(sid, timeout=20)
                real = self._text(r).strip()
                m = re.search(r'(https?://[^\s"\'<>]+)', real)
                if m:
                    real = m.group(1).rstrip('"\'')
                if real.lower().startswith('http'):
                    return {'parse': 0, 'url': self.plp + real, 'header': self.headers}
            except Exception as e:
                self.log('player parse err: %s' % e)
        # m3u8/mp4 直链
        if re.search(r'\.(m3u8|mp4)(\?|$)', sid, re.I):
            return {'parse': 0, 'url': self.plp + sid, 'header': self.headers}
        return {'parse': 1, 'url': self.plp + sid, 'header': self.headers}

    def localProxy(self, param):
        return [404, 'text/plain', b'']
