# -*- coding: utf-8 -*-
"""
绿帽社 —— OK影视 spider（由海阔视界规则 v17 逆向而来，作者 KFC）

核心机制（全部逆向完成）：
1. 签名 authSign(path) = "{ts}-{rand}-0-{sha256(path-ts-rand-0-privateKey)}"
   所有接口/图片都要带 ?auth_key_sigh=<签名>
2. 列表 /oss/pages/tag/{tagId}/{page}.json  → {file_time, json_data(AES加密)}
3. 详情 /oss/pages/detail/{id}.json         → 明文播放地址 + json_data(AES加密元数据)
4. 加密 AES-256-CBC，key=aesKey(32字节)，iv=aesKey[:16]，解密后取最后一个 }/] 前内容
5. 图片 img(path)：后缀 .webp/.jpg... 换成 .w.js + 签名；.w.js 内容实际是 WebP 二进制
6. 播放：video_api + mainVideoUrl(m3u8)，可直连
7. 付费墙：priceType=0/coinNum=null/isVip=null/isBuy=null → 全免，无会员/金币/vip
8. 原规则无搜索(search_url 空)、无排序
"""
import json, re, base64, time, hashlib, random
import requests
from urllib.parse import quote
from base.spider import Spider

try:
    from Crypto.Cipher import AES
    HAS_CRYPTO = True
except Exception:
    HAS_CRYPTO = False


class Spider(Spider):
    def init(self, extend="{}"):
        try:
            config = json.loads(extend) if isinstance(extend, str) else extend
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}

        # ---- 域名（extend 可覆盖）----
        self.host = config.get('site', 'https://jsonbfq24.rkxte.com')            # JSON API
        self.video_api = config.get('video_api', 'https://videos20.redhatxiao.com')  # 视频 CDN
        self.img_api = config.get('img_api', 'https://mstaticiu21.rkxte.com')   # 图片 CDN（vdfm 已 403 失效）
        self.aes_key = config.get('aes_key', 'zH3JDuCRXVGa3na7xbOqpx1bw6DAkbTP')
        self.private_key = config.get('private_key', '3q6yv6Ra1aex8i56HRO2IwCCTPg2Y1Bk')

        # ---- 代理三行（照抄，由 extend 传，没传就直连）----
        self.plp = config.get('plp', '')       # 播放器/封面/播放地址 URL 前缀
        self.proxy = config.get('proxy', {})   # 内部请求代理

        self.ua = 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
        self.headers = {
            'User-Agent': self.ua,
            'Accept': 'application/json,*/*',
            'Referer': 'https://07548876.214573.cc/',
            'Origin': 'https://07548876.214573.cc',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }

        # ---- 分类（channelsData 展平，type_id = 子分类 tagId）----
        # 频道结构：推荐 / 日本AV / 国产传媒 / 环球精选 / 动漫世界 / 网黄博主
        self._classes = [
            {'type_id': '2725', 'type_name': '推荐'},
            {'type_id': '95', 'type_name': '中文字幕'},
            {'type_id': '3719', 'type_name': '无码破解'},
            {'type_id': '23', 'type_name': '91茄子'},
            {'type_id': '24', 'type_name': 'SA国际传媒'},
            {'type_id': '25', 'type_name': '爱豆传媒'},
            {'type_id': '26', 'type_name': '皇家华人'},
            {'type_id': '27', 'type_name': '扣扣传媒'},
            {'type_id': '29', 'type_name': '七度空间'},
            {'type_id': '31', 'type_name': '性视界传媒'},
            {'type_id': '54', 'type_name': '大象传媒'},
            {'type_id': '60', 'type_name': '萝莉社'},
            {'type_id': '61', 'type_name': '色情解说'},
            {'type_id': '62', 'type_name': '麻豆传媒'},
            {'type_id': '63', 'type_name': '起点传媒'},
            {'type_id': '64', 'type_name': '糖心VLOG'},
            {'type_id': '70', 'type_name': '原创微剧'},
            {'type_id': '72', 'type_name': 'ED Mosaic'},
            {'type_id': '73', 'type_name': '小哥哥艾理'},
            {'type_id': '74', 'type_name': '天美传媒'},
            {'type_id': '75', 'type_name': '兔子先生'},
            {'type_id': '76', 'type_name': '星空无限'},
            {'type_id': '77', 'type_name': '杏吧传媒'},
            {'type_id': '3062', 'type_name': '性爱采访'},
            {'type_id': '3099', 'type_name': '蜜桃传媒'},
            {'type_id': '3133', 'type_name': '91果冻'},
            {'type_id': '3688', 'type_name': '香蕉传媒'},
            {'type_id': '3691', 'type_name': '精东影业'},
            {'type_id': '3699', 'type_name': '放克传媒'},
            {'type_id': '3835', 'type_name': '乌鸦传媒'},
            {'type_id': '3836', 'type_name': '乐播传媒'},
            {'type_id': '3837', 'type_name': 'SWAG'},
            {'type_id': '3848', 'type_name': '天使映画'},
            {'type_id': '928', 'type_name': 'P站'},
            {'type_id': '930', 'type_name': '欧美区'},
            {'type_id': '19', 'type_name': '欧美激情'},
            {'type_id': '3253', 'type_name': 'bang bros'},
            {'type_id': '3735', 'type_name': '欧美大屁股'},
            {'type_id': '146', 'type_name': '里番'},
            {'type_id': '149', 'type_name': '3D同人'},
            {'type_id': '163', 'type_name': '推特'},
            {'type_id': '929', 'type_name': '亚洲区'},
        ]

    def getName(self):
        return '绿帽社'

    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(m3u8|mp4|ts)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ==================== 核心工具 ====================

    def _sha256(self, s):
        return hashlib.sha256(s.encode('utf-8')).hexdigest()

    # 签名：ts-rand-uid-sha256(path-ts-rand-uid-privateKey)
    def _auth_sign(self, path):
        ts = str(int(time.time()))
        rand = ''.join(random.choice('0123456789abcdef') for _ in range(32))
        uid = '0'
        sig = self._sha256(path + '-' + ts + '-' + rand + '-' + uid + '-' + self.private_key)
        return '%s-%s-%s-%s' % (ts, rand, uid, sig)

    # AES-256-CBC 解密（NoPadding，手动取最后一个 }/] 前内容）
    def _dec(self, data):
        if not HAS_CRYPTO or not data:
            return None
        try:
            ct = base64.b64decode(data)
            c = AES.new(self.aes_key.encode('utf-8'), AES.MODE_CBC, self.aes_key[:16].encode('utf-8'))
            pt = c.decrypt(ct)
            end = max(pt.rfind(b'}'), pt.rfind(b']'))
            if end >= 0:
                pt = pt[:end + 1]
            return json.loads(pt.decode('utf-8', 'ignore'))
        except Exception:
            return None

    # 请求 JSON 接口（带签名，自动解密）
    def _get_json(self, path, timeout=15):
        url = self.host + path + '?auth_key_sigh=' + self._auth_sign(path)
        try:
            r = requests.get(url, headers=self.headers, proxies=self.proxy, timeout=timeout, verify=False)
            if r.status_code != 200:
                return None
            j = r.json()
        except Exception:
            return None
        if isinstance(j, dict) and j.get('json_data'):
            d = self._dec(j['json_data'])
            if d is not None:
                return d
        return j

    # 图片：后缀换 .w.js + 签名（内容实为 WebP）
    def _pic(self, u):
        if not u:
            return ''
        if u.startswith('http'):
            return u
        p = re.sub(r'\.(webp|jpg|jpeg|png|bmp|gif)(\?.*)?$', '.w.js', u, flags=re.I)
        if not re.search(r'\.(w\.js|js)$', p, re.I):
            p = p + '.w.js'
        return self.img_api + p + '?auth_key_sigh=' + self._auth_sign(p)

    # 播放：拼 video_api 绝对地址
    def _play(self, u):
        if not u:
            return ''
        if u.startswith('http'):
            return u
        if not u.startswith('/'):
            u = '/' + u
        return self.video_api + u

    # 可点击标签（跳转分类）
    def _cr(self, href, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({'id': str(href), 'name': name}, ensure_ascii=False), name)

    # ==================== 页面 ====================

    def homeContent(self, filter):
        result = {'class': self._classes, 'list': []}
        try:
            data = self._get_json('/oss/pages/tag/2725/0.json')
            if data:
                result['list'] = self._build_list(data)
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'page': int(pg or 1), 'pagecount': 9999, 'limit': 90, 'total': 999999}
        try:
            page = int(pg or 1)
            data = self._get_json('/oss/pages/tag/%s/%d.json' % (tid, page - 1))
            if data:
                result['list'] = self._build_list(data)
        except Exception:
            pass
        return result

    def _build_list(self, data):
        videos = []
        if not isinstance(data, list):
            return videos
        seen = []
        for it in data:
            if not isinstance(it, dict):
                continue
            vid = it.get('id')
            if not vid or vid in seen:
                continue
            seen.append(vid)
            dur = it.get('duration') or ''
            view = it.get('view') or 0
            videos.append({
                'vod_id': str(vid),
                'vod_name': it.get('title') or '',
                'vod_pic': self.plp + self._pic(it.get('mainImgUrl')),
                'vod_remarks': ('%s  %s人看' % (dur, view)) if dur else '',
            })
        return videos

    def detailContent(self, ids):
        result = {'list': []}
        if not ids:
            return result
        try:
            vid = str(ids[0]).strip()
            path = '/oss/pages/detail/%s.json' % vid
            url = self.host + path + '?auth_key_sigh=' + self._auth_sign(path)
            r = requests.get(url, headers=self.headers, proxies=self.proxy, timeout=15, verify=False)
            if r.status_code != 200:
                return result
            d = r.json()
            meta = self._dec(d.get('json_data', '')) or {}

            title = meta.get('title') or ''
            intro = (meta.get('intro') or '').strip()
            category = (meta.get('category') or {}).get('name') or ''
            author = meta.get('createUserName') or ''
            tags = [t.get('name') for t in (meta.get('tags') or []) if isinstance(t, dict) and t.get('name')]
            tag_ids = [t.get('id') for t in (meta.get('tags') or []) if isinstance(t, dict) and t.get('name')]
            chapters = meta.get('videoChapterList') or []

            # 播放地址（多清晰度：主列表 m3u8 已是多码率 master，另给 1200kb/700kb）
            main = d.get('mainVideoUrl') or meta.get('videoUrl') or ''
            q2 = d.get('quality2') or ''
            q1 = d.get('quality1') or ''
            quals = []
            if main:
                quals.append(('原画', self._play(main)))
            if q2:
                quals.append(('高清', self._play(q2)))
            if q1:
                quals.append(('标清', self._play(q1)))

            # 可点击标签
            crs = []
            for i, nm in enumerate(tags):
                tid = tag_ids[i] if i < len(tag_ids) else ''
                crs.append(self._cr(tid, nm))
            tags_line = ' '.join(crs) if crs else ''

            # 简介：优先 intro，空则用分类/作者/章节补
            lines = []
            if intro:
                lines.append(intro)
            if category:
                lines.append('分类：' + category)
            if author:
                lines.append('作者：' + author)
            if chapters:
                lines.append('章节：' + '、'.join([c.get('title') or '' for c in chapters if c.get('title')]))

            vod = {
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': self.plp + self._pic(meta.get('mainImgUrl') or ''),
                'type_name': category,
                'vod_actor': tags_line,
                'vod_content': '\n'.join(lines),
            }
            if quals:
                vod['vod_play_from'] = '$$$'.join([q[0] for q in quals])
                vod['vod_play_url'] = '$$$'.join([q[1] for q in quals])

            result['list'] = [vod]
        except Exception:
            pass
        return result

    # 原规则无搜索（search_url 空，search 接口需鉴权）
    def searchContent(self, key, quick, pg="1"):
        return {'list': [], 'page': int(pg or 1)}

    def playerContent(self, flag, id, vipFlags):
        if id and ('.m3u8' in id or '.mp4' in id):
            return {'parse': 0, 'url': self.plp + id, 'header': self.headers}
        return {'parse': 1, 'url': id, 'header': self.headers}

    def localProxy(self, param):
        return [404, 'text/plain', b'']
