# -*- coding: utf-8 -*-
# R星精选 视频源 —— 由海阔视界规则转换而来（只保留「视频」一项）
# 接口：cofXX.bahfn.cn/jbapi/  （token + enc 加密，cof 节点自动探测）
import json, re, base64, urllib.parse
import requests
from base.spider import Spider

requests.packages.urllib3.disable_warnings()


class Spider(Spider):
    def init(self, extend="{}"):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}

        # ---- 代理三行（照抄，由 extend 传，没传就直连）----
        self.plp = config.get('plp', '')       # 播放器/封面/播放地址 URL 前缀
        self.proxy = config.get('proxy', {})   # 内部请求代理

        # cof 节点池（cof03 当前稳定节点优先，其余兜底探测）
        self.host_pool = ['cof03.bahfn.cn', 'cof02.bahfn.cn', 'cof01.bahfn.cn'] + \
            ['cof%02d.bahfn.cn' % i for i in range(4, 26)]

        self.api_base = ''   # 探测后填充 'https://cofXX.bahfn.cn/jbapi/'
        self.h5_host = ''    # 'https://cofXX.bahfn.cn'
        self.h5_base = ''    # 'https://cofXX.bahfn.cn/h5/'
        self.token = ''
        self.cates = []      # 分类缓存
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }

    def getName(self):
        return 'R星精选'

    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(m3u8|mp4|ts)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ---- enc 解密：base64 -> 反转 -> base64 -> urldecode ----
    def _decode(self, data):
        step1 = base64.b64decode(data).decode('utf-8', 'ignore')
        step2 = step1[::-1]
        step3 = base64.b64decode(step2).decode('utf-8', 'ignore')
        return json.loads(urllib.parse.unquote(step3))

    def _parse_res(self, res):
        data = res.get('data')
        if res.get('enc') is True and isinstance(data, str):
            try:
                data = self._decode(data)
            except Exception:
                data = None
        return data

    # ---- 域名探测 + 拿 token（惰性，失败不固化）----
    def _ensure(self, force=False):
        if not force and self.api_base and self.token:
            return True
        for d in self.host_pool:
            base = 'https://%s/jbapi/' % d
            try:
                r = requests.get(base + 'user/autoUser/null/td/null', headers=self.headers, proxies=self.proxy, timeout=6, verify=False)
                if r.status_code == 200:
                    res = r.json()
                    data = self._parse_res(res)
                    if isinstance(data, dict) and data.get('token'):
                        self.api_base = base
                        self.h5_host = 'https://%s' % d
                        self.h5_base = 'https://%s/h5/' % d
                        self.token = data['token']
                        return True
            except Exception:
                continue
        # 兜底 cof03（不覆盖已探测成功的 base）
        if not self.api_base:
            self.api_base = 'https://cof03.bahfn.cn/jbapi/'
            self.h5_host = 'https://cof03.bahfn.cn'
            self.h5_base = 'https://cof03.bahfn.cn/h5/'
        return False

    # ---- 内部 GET/POST（带 token，401/302 自动换 token 重试）----
    def _api_get(self, url):
        if not self._ensure():
            return None
        h = dict(self.headers)
        h['token'] = self.token
        r = requests.get(self.api_base + url, headers=h, proxies=self.proxy, timeout=15, verify=False)
        res = r.json()
        if res.get('code') in (401, 302):
            if self._ensure(True):
                h['token'] = self.token
                r = requests.get(self.api_base + url, headers=h, proxies=self.proxy, timeout=15, verify=False)
                res = r.json()
        return self._parse_res(res)

    def _api_post(self, url, body):
        if not self._ensure():
            return None
        h = dict(self.headers)
        h['token'] = self.token
        h['Content-Type'] = 'application/json'
        r = requests.post(self.api_base + url, headers=h, data=body, proxies=self.proxy, timeout=15, verify=False)
        res = r.json()
        if res.get('code') in (401, 302):
            if self._ensure(True):
                h['token'] = self.token
                r = requests.post(self.api_base + url, headers=h, data=body, proxies=self.proxy, timeout=15, verify=False)
                res = r.json()
        return self._parse_res(res)

    # ---- 分类（惰性缓存）----
    def _get_cates(self):
        if not self.cates:
            data = self._api_get('movie/fenglei/hjm.ojbk')
            if isinstance(data, list):
                self.cates = data
        return self.cates

    def _find_cate(self, tid):
        for c in self.cates:
            if str(c.get('id')) == str(tid):
                return c
        return None

    # ---- 封面走本地代理解密（图片 XOR 加密）----
    def _img_proxy(self, url):
        return self.getProxyUrl() + '&type=img&url=' + base64.b64encode(url.encode('utf-8')).decode('ascii')

    # ---- 可点击标签封装 ----
    def _cr(self, href, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': href, 'name': name}, ensure_ascii=False), name)

    # ---- item -> OK影视 列表项 ----
    def _to_videos(self, items):
        videos = []
        seen = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            mv = it.get('movie') or it
            if not isinstance(mv, dict):
                continue
            title = (mv.get('title') or '').strip()
            url = mv.get('movieurl') or mv.get('movieurlSk') or ''
            if not title or not url:
                continue
            if url in seen:
                continue
            seen.append(url)

            pic = mv.get('imgurl') or ''
            dur = (mv.get('duration') or '').strip()

            # 标签 marks（JSON 数组字符串）
            marks = mv.get('marks') or ''
            tag_list = []
            if isinstance(marks, str) and marks.strip():
                try:
                    tag_list = json.loads(marks)
                except Exception:
                    tag_list = [x.strip() for x in marks.strip('[]').replace('"', '').split(',') if x.strip()]
            tags = []
            seen_tag = []
            for t in tag_list or []:
                t = (str(t) or '').strip()
                if t and t not in seen_tag:
                    seen_tag.append(t)
                    tags.append(t)

            # 简介
            miaoshu = (mv.get('miaoshu') or '').strip()

            # 演员/博主
            user = it.get('movieUser') or {}
            user_name = (user.get('name') or '').strip()
            user_id = str(user.get('id') or '')

            # 详情信息打包进 vod_id（json+base64，最安全）
            info = {
                'u': url,
                't': title,
                'p': pic,
                'g': tags,
                'd': miaoshu,
                'n': user_name,
                'id': user_id,
            }
            vod_id = base64.b64encode(json.dumps(info, ensure_ascii=False).encode('utf-8')).decode('ascii')

            videos.append({
                'vod_id': vod_id,
                'vod_name': title,
                'vod_pic': self._img_proxy(pic) if pic else '',
                'vod_remarks': dur,  # 只保留时长
            })
        return videos

    def homeContent(self, filter):
        result = {'class': [], 'filters': {}, 'list': []}
        try:
            cates = self._get_cates()
            for c in cates:
                cid = str(c.get('id'))
                result['class'].append({'type_id': cid, 'type_name': c.get('name', '')})
                result['filters'][cid] = [{'key': 'sort', 'name': '排序', 'value': [
                    {'n': '最新', 'v': 'zx'}, {'n': '推荐', 'v': 'tj'}, {'n': '随机', 'v': 'rand'}
                ]}]
            # 首页列表：取第一个 isFirst=1（推荐）分类的前若干条
            first_cate = None
            for c in cates:
                if c.get('isFirst') == 1:
                    first_cate = c
                    break
            if first_cate:
                data = self._api_get('movie/fengleidata/%s/hjm.ojbk' % first_cate.get('id')) or {}
                sections = data.get('movieList') or []
                items = []
                for s in sections:
                    if isinstance(s, dict):
                        items.extend(s.get('list') or [])
                result['list'] = self._to_videos(items[:20])
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return {'list': []}

    # ---- 搜索（关键词 base64）----
    def _search_movies(self, key, pg):
        kw = base64.b64encode(key.encode('utf-8')).decode('ascii')
        data = self._api_post('movie/searchv2/%s/15/zx' % pg, json.dumps({'name': kw})) or {}
        items = data.get('records') or data.get('list') or []
        return self._to_videos(items)

    # ---- 演员作品列表 ----
    def _user_movies(self, uid, pg):
        data = self._api_get('movieUser/moredata/%s/%s/15/zx' % (uid, pg)) or {}
        items = data.get('list') or []
        return self._to_videos(items)

    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'page': int(pg or 1), 'pagecount': 9999, 'limit': 90, 'total': 999999}
        pg = int(pg or 1)
        sort = 'zx'
        if extend and isinstance(extend, dict):
            sort = extend.get('sort', 'zx')
        if sort not in ('zx', 'tj', 'rand'):
            sort = 'zx'
        try:
            tid = str(tid or '')
            # 演员作品（user_ 前缀）
            if tid.startswith('user_'):
                result['list'] = self._user_movies(tid[5:], pg)
                return result
            # 纯数字 = 分类
            if tid.isdigit():
                self._get_cates()
                cate = self._find_cate(tid)
                is_first = (cate.get('isFirst') == 1) if cate else False
                if is_first:
                    data = self._api_get('movie/fengleidata/%s/hjm.ojbk' % tid) or {}
                    sections = data.get('movieList') or []
                    all_items = []
                    for s in sections:
                        if isinstance(s, dict):
                            all_items.extend(s.get('list') or [])
                    start = (pg - 1) * 60
                    items = all_items[start:start + 60]
                else:
                    data = self._api_get('movie/fengleidataShow/%s/%s/15/%s/hjm.ojbk' % (tid, pg, sort)) or {}
                    items = data.get('movieList') or []
                result['list'] = self._to_videos(items)
                return result
            # 其他 = 搜索
            result['list'] = self._search_movies(tid, pg)
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, list) else ids
        info = {}
        try:
            info = json.loads(base64.b64decode(vod_id).decode('utf-8'))
        except Exception:
            info = {}
        url = info.get('u', '')
        name = info.get('t', '在线播放')
        pic = info.get('p', '')
        tags = info.get('g', [])
        miaoshu = info.get('d', '')
        user_name = info.get('n', '')
        user_id = info.get('id', '')

        # 演员/博主 -> vod_actor（可点击进作品列表）
        actor = ''
        if user_name:
            actor = self._cr('user_' + user_id, user_name) if user_id else user_name

        # 标签 -> vod_content 可点击（点击搜索）
        tag_str = ''
        for t in tags or []:
            tag_str += self._cr(t, t) + ' '

        # 简介拼接（可点击标签在前，简介在后）
        content = tag_str.strip()
        if miaoshu:
            content = (content + '\n' + miaoshu) if content else miaoshu

        vod = {
            'vod_id': vod_id,
            'vod_name': name,
            'vod_pic': self._img_proxy(pic) if pic else '',
            'type_name': '视频',
            'vod_actor': actor,
            'vod_director': '',
            'vod_content': content,
            'vod_play_from': 'R星精选',
            'vod_play_url': '高清$' + url,
        }
        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        result = {'list': [], 'page': int(pg or 1)}
        try:
            result['list'] = self._search_movies(key, pg)
        except Exception:
            pass
        return result

    def _play_headers(self):
        h = dict(self.headers)
        if self.h5_base:
            h['Referer'] = self.h5_base
        if self.h5_host:
            h['Origin'] = self.h5_host
        return h

    def playerContent(self, flag, id, vipFlags):
        if '.m3u8' in id or '.mp4' in id:
            return {'parse': 0, 'url': self.plp + id, 'header': self._play_headers()}
        return {'parse': 1, 'url': id, 'header': self._play_headers()}

    # ---- 图片解密：封面为 XOR(前100字节) 加密的 WebP ----
    def _guess_mime(self, data):
        if data[:4] == b'\x89PNG':
            return 'image/png'
        if data[:2] == b'\xff\xd8':
            return 'image/jpeg'
        if data[:6] in (b'GIF87a', b'GIF89a'):
            return 'image/gif'
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return 'image/webp'
        return 'image/jpeg'

    def _dec_img(self, url, data):
        if '.html' in url:
            try:
                return base64.b64decode(data)
            except Exception:
                return data
        # 默认 XOR 前 100 字节
        key = b'2019ysapp7527'
        bb = bytearray(data)
        limit = min(100, len(bb))
        for i in range(limit):
            bb[i] ^= key[i % len(key)]
        return bytes(bb)

    def localProxy(self, param):
        try:
            if param.get('type') == 'img':
                url = base64.b64decode(param.get('url', '')).decode('utf-8', 'ignore')
                r = requests.get(url, headers=self.headers, proxies=self.proxy, timeout=20, verify=False)
                data = r.content
                if not data:
                    return [404, 'text/plain', b'']
                data = self._dec_img(url, data)
                mime = self._guess_mime(data)
                return [200, mime, data]
        except Exception:
            pass
        return [404, 'text/plain', b'']
