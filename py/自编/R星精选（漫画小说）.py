# -*- coding: utf-8 -*-
# R星精选 源 —— 由海阔视界规则转换而来（视频 + 漫画 + 小说 + 书库 + 色图）
# 接口：cofXX.bahfn.cn/jbapi/  （token + enc 加密，cof 节点自动探测）
import json, re, base64, urllib.parse
import requests
from base.spider import Spider

requests.packages.urllib3.disable_warnings()

try:
    from Crypto.Cipher import AES
except Exception:
    AES = None


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
        self.video_cates = []   # 视频分类
        self.manhua_cates = []  # 漫画分类
        self.book_cates = []    # 小说分类（book/fenglei/1）
        self.novel_cates = []   # 书库分类（book/fenglei/2，兜底）
        self.pic_cates = []     # 色图分类（兜底）
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

    # ---- 封面/图片走本地代理解密 ----
    def _img_proxy(self, url):
        return self.getProxyUrl() + '&type=img&url=' + base64.b64encode(url.encode('utf-8')).decode('ascii')

    # ---- 可点击标签封装 ----
    def _cr(self, href, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': href, 'name': name}, ensure_ascii=False), name)

    # ---- marks JSON 数组字符串 -> 去重列表 ----
    def _parse_marks(self, marks):
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
        return tags

    # ---- 分类缓存 ----
    def _get_video_cates(self):
        if not self.video_cates:
            data = self._api_get('movie/fenglei/hjm.ojbk')
            if isinstance(data, list):
                self.video_cates = data
        return self.video_cates

    def _get_manhua_cates(self):
        if not self.manhua_cates:
            data = self._api_get('manhua/fenglei')
            if isinstance(data, list):
                self.manhua_cates = data
        return self.manhua_cates

    def _get_book_cates(self):
        if not self.book_cates:
            data = self._api_get('book/fenglei/1')
            if isinstance(data, list):
                self.book_cates = data
        return self.book_cates

    def _get_novel_cates(self):
        if not self.novel_cates:
            self.novel_cates = [{'id': 61, 'name': '书库', 'onetab': 0}]
        return self.novel_cates

    def _get_pic_cates(self):
        if not self.pic_cates:
            self.pic_cates = [
                {'id': 73, 'name': 'COS图集', 'source': 'comic'},
                {'id': 72, 'name': 'PIXIV图集', 'source': 'comic'},
                {'id': 61, 'name': 'AI图集', 'source': 'comic'},
                {'id': 59, 'name': '最新图集', 'source': 'comic'},
            ]
        return self.pic_cates

    def _find_cate(self, cates, tid):
        for c in cates:
            if str(c.get('id')) == str(tid):
                return c
        return None

    def _first_video_cate(self):
        for c in self._get_video_cates():
            if c.get('isFirst') == 1:
                return str(c.get('id'))
        cates = self._get_video_cates()
        return str(cates[0].get('id')) if cates else ''

    def _first_pic_cate(self):
        cates = self._get_pic_cates()
        return str(cates[0].get('id')) if cates else ''

    # 漫画每日更新
    def _manhua_everyday(self, pg):
        data = self._api_get('manhua/everyday/%s/15/time/hjm.ojbk' % pg) or {}
        items = data.get('records') or []
        return self._to_manhua(items)

    # 小说每日更新
    def _book_everyday(self, pg):
        data = self._api_get('book/everyday/%s/15/time' % pg) or {}
        items = data.get('records') or []
        return self._to_book(items)

    # ---- 打包/解包 vod_id ----
    def _pack(self, info):
        return base64.b64encode(json.dumps(info, ensure_ascii=False).encode('utf-8')).decode('ascii')

    def _unpack(self, vod_id):
        try:
            return json.loads(base64.b64decode(vod_id).decode('utf-8'))
        except Exception:
            return {}

    # ================= 视频 =================
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
            tags = self._parse_marks(mv.get('marks'))
            miaoshu = (mv.get('miaoshu') or '').strip()
            user = it.get('movieUser') or {}
            user_name = (user.get('name') or '').strip()
            user_id = str(user.get('id') or '')
            info = {'type': 'video', 'u': url, 't': title, 'p': pic, 'g': tags, 'd': miaoshu, 'n': user_name, 'id': user_id}
            videos.append({
                'vod_id': self._pack(info),
                'vod_name': title,
                'vod_pic': self._img_proxy(pic) if pic else '',
                'vod_remarks': dur,
            })
        return videos

    def _video_list(self, tid, pg, sort):
        cates = self._get_video_cates()
        cate = self._find_cate(cates, tid)
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
        return self._to_videos(items)

    # ================= 漫画 =================
    def _to_manhua(self, items, typ='manhua'):
        videos = []
        seen = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            title = (it.get('title') or '').strip()
            mid = it.get('id')
            if not title or mid is None:
                continue
            if str(mid) in seen:
                continue
            seen.append(str(mid))
            pic = it.get('imgurl') or ''
            zjnum = it.get('zhangjieNum') or ''
            info = {'type': typ, 'id': str(mid), 't': title, 'p': pic}
            videos.append({
                'vod_id': self._pack(info),
                'vod_name': title,
                'vod_pic': self._img_proxy(pic) if pic else '',
                'vod_remarks': ('共%s话' % zjnum) if zjnum else '',
            })
        return videos

    def _manhua_list(self, tid, pg, sort):
        cates = self._get_manhua_cates()
        cate = self._find_cate(cates, tid)
        onetab = (cate.get('onetab') == 1) if cate else False
        if onetab:
            data = self._api_get('manhua/fengleidata/%s' % tid) or []
            items = []
            for s in data:
                if isinstance(s, dict):
                    items.extend(s.get('list') or [])
        else:
            data = self._api_get('manhua/onetab/%s/%s/15/%s/hjm.ojbk' % (tid, pg, sort)) or []
            items = data if isinstance(data, list) else []
        return self._to_manhua(items)

    def _pic_list(self, tid, pg, sort):
        data = self._api_get('manhua/onetab/%s/%s/15/%s/hjm.ojbk' % (tid, pg, sort)) or []
        items = data if isinstance(data, list) else []
        return self._to_manhua(items, 'pic')

    # ================= 小说 =================
    def _to_book(self, items):
        videos = []
        seen = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            title = (it.get('title') or '').strip()
            bid = it.get('id')
            if not title or bid is None:
                continue
            if str(bid) in seen:
                continue
            seen.append(str(bid))
            pic = it.get('imgurl') or ''
            zjnum = it.get('zhangjieNum') or ''
            info = {'type': 'book', 'id': str(bid), 't': title, 'p': pic}
            videos.append({
                'vod_id': self._pack(info),
                'vod_name': title,
                'vod_pic': self._img_proxy(pic) if pic else '',
                'vod_remarks': ('共%s章' % zjnum) if zjnum else '',
            })
        return videos

    def _book_list(self, tid, pg, sort):
        data = self._api_get('book/md/xsmoredata/%s/%s/15/%s/hjm.ojbk' % (tid, pg, sort)) or {}
        items = data.get('records') or []
        return self._to_book(items)

    # ================= 搜索 =================
    def _search_videos(self, key, pg):
        kw = base64.b64encode(key.encode('utf-8')).decode('ascii')
        data = self._api_post('movie/searchv2/%s/15/zx' % pg, json.dumps({'name': kw})) or {}
        items = data.get('records') or data.get('list') or []
        return self._to_videos(items)

    def _user_movies(self, uid, pg):
        data = self._api_get('movieUser/moredata/%s/%s/15/zx' % (uid, pg)) or {}
        items = data.get('list') or []
        return self._to_videos(items)

    # ================= homeContent =================
    def homeContent(self, filter):
        result = {'class': [], 'filters': {}, 'list': []}
        try:
            result['class'] = [
                {'type_id': 'video', 'type_name': '视频'},
                {'type_id': 'manhua', 'type_name': '漫画'},
                {'type_id': 'book', 'type_name': '小说'},
                {'type_id': 'novel', 'type_name': '书库'},
                {'type_id': 'pic', 'type_name': '色图'},
            ]
            vc = self._get_video_cates()
            result['filters']['video'] = [
                {'key': 'type', 'name': '分类', 'value': [{'n': c.get('name', ''), 'v': str(c.get('id'))} for c in vc]},
                {'key': 'sort', 'name': '排序', 'value': [{'n': '最新', 'v': 'zx'}, {'n': '推荐', 'v': 'tj'}, {'n': '随机', 'v': 'rand'}]},
            ]
            mc = self._get_manhua_cates()
            result['filters']['manhua'] = [
                {'key': 'type', 'name': '分类', 'value': [{'n': c.get('name', ''), 'v': str(c.get('id'))} for c in mc]},
            ]
            bc = self._get_book_cates()
            result['filters']['book'] = [
                {'key': 'type', 'name': '分类', 'value': [{'n': c.get('name', ''), 'v': str(c.get('id'))} for c in bc]},
            ]
            nc = self._get_novel_cates()
            result['filters']['novel'] = [
                {'key': 'type', 'name': '分类', 'value': [{'n': c.get('name', ''), 'v': str(c.get('id'))} for c in nc]},
            ]
            pc = self._get_pic_cates()
            result['filters']['pic'] = [
                {'key': 'type', 'name': '分类', 'value': [{'n': c.get('name', ''), 'v': str(c.get('id'))} for c in pc]},
            ]
            # 首页列表：视频推荐
            first_cate = None
            for c in vc:
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

    # ================= categoryContent =================
    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'page': int(pg or 1), 'pagecount': 9999, 'limit': 90, 'total': 999999}
        pg = int(pg or 1)
        sort = 'zx'
        if extend and isinstance(extend, dict):
            sort = extend.get('sort', 'zx')
        if sort not in ('zx', 'tj', 'rand', 'time', 'look', 'like'):
            sort = 'zx'
        try:
            tid = str(tid or '')
            sub = ''
            if extend and isinstance(extend, dict):
                sub = str(extend.get('type', '') or '')
            if tid.startswith('user_'):
                result['list'] = self._user_movies(tid[5:], pg)
                return result
            if tid == 'video' or tid.isdigit():
                if tid == 'video' and not sub:
                    sub = self._first_video_cate()
                result['list'] = self._video_list(sub or tid, pg, sort)
                return result
            if tid == 'manhua':
                if sub:
                    result['list'] = self._manhua_list(sub, pg, 'time')
                else:
                    result['list'] = self._manhua_everyday(pg)
                return result
            if tid in ('book', 'novel'):
                if sub:
                    result['list'] = self._book_list(sub, pg, sort)
                else:
                    result['list'] = self._book_everyday(pg)
                return result
            if tid == 'pic':
                if not sub:
                    sub = self._first_pic_cate()
                result['list'] = self._pic_list(sub, pg, 'time')
                return result
            result['list'] = self._search_videos(tid, pg)
        except Exception:
            pass
        return result

    # ================= detailContent =================
    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, list) else ids
        info = self._unpack(vod_id)
        typ = info.get('type', 'video')
        if typ == 'video':
            return self._video_detail(info, vod_id)
        if typ == 'manhua':
            return self._manhua_detail(info, vod_id)
        if typ == 'book':
            return self._book_detail(info, vod_id)
        if typ == 'pic':
            return self._manhua_detail(info, vod_id, pic=True)
        return {'list': []}

    def _video_detail(self, info, vod_id):
        url = info.get('u', '')
        name = info.get('t', '在线播放')
        pic = info.get('p', '')
        tags = info.get('g', [])
        miaoshu = info.get('d', '')
        user_name = info.get('n', '')
        user_id = info.get('id', '')
        actor = ''
        if user_name:
            actor = self._cr('user_' + user_id, user_name) if user_id else user_name
        tag_str = ''
        for t in tags or []:
            tag_str += self._cr(t, t) + ' '
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

    def _manhua_detail(self, info, vod_id, pic=False):
        mid = info.get('id', '')
        data = self._api_get('manhua/data/%s' % mid) or {}
        manhua = data.get('manhua') or {}
        zhangjie = data.get('zhangjie') or []
        title = manhua.get('title') or info.get('t', '')
        cover = manhua.get('imgurl') or info.get('p', '')
        marks = manhua.get('marks') or ''
        miaoshu = manhua.get('miaoshu') or ''
        parts = []
        for z in zhangjie or []:
            zid = z.get('id')
            zname = (z.get('name') or '').strip() or ('第%s话' % (len(parts) + 1))
            if zid is not None:
                parts.append('%s$%s' % (zname, zid))
        play_url = '#'.join(parts)
        tags = self._parse_marks(marks)
        tag_str = ''
        for t in tags:
            tag_str += self._cr(t, t) + ' '
        content = tag_str.strip()
        if miaoshu:
            content = (content + '\n' + miaoshu) if content else miaoshu
        vod = {
            'vod_id': vod_id,
            'vod_name': title,
            'vod_pic': self._img_proxy(cover) if cover else '',
            'type_name': '色图' if pic else '漫画',
            'vod_actor': '',
            'vod_director': '',
            'vod_content': content,
            'vod_play_from': '色图' if pic else '漫画',
            'vod_play_url': play_url,
        }
        return {'list': [vod]}

    def _book_detail(self, info, vod_id):
        bid = info.get('id', '')
        data = self._api_get('book/data/%s' % bid) or {}
        book = data.get('book') or {}
        zhangjie = data.get('zhangjie') or []
        title = book.get('title') or info.get('t', '')
        cover = book.get('imgurl') or info.get('p', '')
        marks = book.get('marks') or ''
        miaoshu = book.get('miaoshu') or ''
        parts = []
        for z in zhangjie or []:
            zid = z.get('id')
            zname = (z.get('name') or '').strip() or ('第%s章' % (len(parts) + 1))
            if zid is not None:
                parts.append('%s$%s' % (zname, zid))
        play_url = '#'.join(parts)
        tags = self._parse_marks(marks)
        tag_str = ''
        for t in tags:
            tag_str += self._cr(t, t) + ' '
        content = tag_str.strip()
        if miaoshu:
            content = (content + '\n' + miaoshu) if content else miaoshu
        vod = {
            'vod_id': vod_id,
            'vod_name': title,
            'vod_pic': self._img_proxy(cover) if cover else '',
            'type_name': '小说',
            'vod_actor': '',
            'vod_director': '',
            'vod_content': content,
            'vod_play_from': '小说',
            'vod_play_url': play_url,
        }
        return {'list': [vod]}

    # ================= searchContent =================
    def searchContent(self, key, quick, pg="1"):
        result = {'list': [], 'page': int(pg or 1)}
        try:
            result['list'] = self._search_videos(key, pg)
        except Exception:
            pass
        return result

    # ================= playerContent =================
    def _play_headers(self):
        h = dict(self.headers)
        if self.h5_base:
            h['Referer'] = self.h5_base
        if self.h5_host:
            h['Origin'] = self.h5_host
        return h

    def _get_book_text(self, txturl):
        if not txturl:
            return ''
        try:
            r = requests.get(txturl, headers=self.headers, proxies=self.proxy, timeout=20, verify=False)
            raw = r.content
            clean = raw.decode('utf-8', 'ignore').strip()
            if re.match(r'^[A-Za-z0-9+/=]+$', clean) and len(clean) > 20:
                txt = base64.b64decode(clean).decode('utf-8', 'ignore')
                return urllib.parse.unquote(txt)
            if AES:
                key = b'525202f9149e061d'
                cipher = AES.new(key, AES.MODE_ECB)
                pt = cipher.decrypt(raw)
                pad = pt[-1]
                if 1 <= pad <= 16:
                    pt = pt[:-pad]
                return pt.decode('utf-8', 'ignore')
            return ''
        except Exception:
            return ''

    def playerContent(self, flag, id, vipFlags):
        if flag in ('漫画', '色图'):
            data = self._api_get('manhua/data/zj/%s' % id) or {}
            imgurl = (data.get('imgurl') or '') if isinstance(data, dict) else ''
            pics = [self._img_proxy(u) for u in imgurl.split(',') if u.strip()]
            if not pics:
                return {'parse': 0, 'url': '', 'header': ''}
            proto = 'manga://' if flag == '漫画' else 'pics://'
            return {'parse': 0, 'playUrl': '', 'url': proto + '&&'.join(pics), 'header': ''}
        if flag == '小说':
            data = self._api_get('book/data/zj/%s' % id) or {}
            name = (data.get('name') or '') if isinstance(data, dict) else ''
            txturl = (data.get('txturl') or '') if isinstance(data, dict) else ''
            content = self._get_book_text(txturl)
            if not content:
                return {'parse': 0, 'url': '', 'header': ''}
            return {'parse': 0, 'playUrl': '', 'url': 'novel://' + json.dumps({'title': name, 'content': content}, ensure_ascii=False), 'header': ''}
        if '.m3u8' in id or '.mp4' in id:
            return {'parse': 0, 'url': self.plp + id, 'header': self._play_headers()}
        return {'parse': 1, 'url': id, 'header': self._play_headers()}

    # ================= localProxy =================
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
