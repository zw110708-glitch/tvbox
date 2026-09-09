# -*- coding: utf-8 -*-
# 18.py —— 基于 R星.apk 静态提取的域名/API 重构的 OK影视 数据源插件
#
# 数据来源：R星.apk（Flutter AOT，libapp.so 字符串池静态提取）
#  - API 基地址：https://r9nhyvkt.vip/front/
#  - 域名/IP 池：qmybjw23.com / t5xn2yqd.com / dacmeyhw.com / dabxr6sg.com /
#                wth22546.com / 8sd579dt.com / 15.165.223.248 / 52.68.119.87 /
#                3.38.102.153 / 154.211.32.1:9527
#  - 字段名（驼峰）：videoUrl / streamUrl(s) / mediaCoverImg / videoCoverImg /
#                   videoDescription / videoDuration / commentCount / totalPage /
#                   currPageNum / pageNo / pageSize / searchKeyword / searchType /
#                   categoryId / secondCategoryId / mediaId / videoId ...
#
# 重要说明（推断部分，运行时可能需微调）：
#  1. 请求方式按 GET + query 实现（列表/搜索接口通常幂等 GET；若后端要求
#     POST+JSON，把 _api() 里的 requests.get 换成 requests.post(json=params) 即可）。
#  2. 响应 JSON 顶层结构做了多形态容错（code/data/list/records/rows/content 等）。
#  3. 标题/封面/播放地址字段做了多候选匹配（因 AOT 字符串池无法 100% 锁定唯一字段名）。
#  4. R星 含 RSA 公钥（assets/rsa_key/rsa_public_key.pem），登录/敏感接口可能加密；
#     本插件只访问匿名可用的列表/搜索/播放接口，不做登录。

import json
import re
import sys
from urllib.parse import urljoin

import requests

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    # ---- R星 域名池（主 + 备用） ----
    # 主 API 基地址
    PRIMARY_BASE = "https://r9nhyvkt.vip/front/"
    # 备用域名（与 libapp.so 中硬编码的域名池一致）
    FALLBACK_HOSTS = [
        "qmybjw23.com",
        "t5xn2yqd.com",
        "dacmeyhw.com",
        "dabxr6sg.com",
        "wth22546.com",
        "8sd579dt.com",
    ]
    UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

    # ---- 响应 JSON 字段多候选（AOT 字符串无法唯一锁定，故做容错） ----
    TITLE_KEYS = ["videoName", "mediaName", "title", "name", "videoTitle", "mediaTitle", "contentTitle"]
    COVER_KEYS = ["mediaCoverImg", "videoCoverImg", "coverImg", "cover", "imageUrl", "imgUrl", "picUrl", "coverUrl", "articleCoverImg"]
    URL_KEYS = ["videoUrl", "streamUrl", "definitionURL", "previewVideoUrl", "videoPreviewUrl", "previewUrl", "downloadUrl", "url"]
    ID_KEYS = ["videoId", "mediaId", "id"]
    DUR_KEYS = ["videoDuration", "duration", "timeLen"]
    DESC_KEYS = ["videoDescription", "contentText", "description", "remark"]

    # ---- API 路径 ----
    API_CATEGORY_LIST = "media/category/listAllCategory"        # 全部分类
    API_CATEGORY_BY_PARENT = "media/category/listAllByParentId" # 按父分类
    API_MEDIA_BY_CATEGORY = "media/listAllBySecondCategoryIdNew"# 按二级分类列出
    API_MEDIA_RANDOM = "media/listShortVideoRandom"             # 随机短视频
    API_MEDIA_SEARCH = "media/listMediaBySearchType"            # 搜索

    def getName(self):
        return "R星"

    def manualVideoCheck(self):
        return False

    def init(self, extend=""):
        try:
            cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
        except Exception:
            cfg = {}
        self.proxies = cfg.get("proxies") or {}
        # 用户可在配置里覆盖 host/base
        override = (cfg.get('host') or cfg.get('base') or '').strip().rstrip('/')
        if override:
            self._bases = [override if override.endswith('/') else override + '/']
        else:
            self._bases = [self.PRIMARY_BASE] + [("https://%s/front/" % h) for h in self.FALLBACK_HOSTS]
        self._base_idx = 0
        self.host = self._bases[0].rstrip('/')
        self.headers = {
            "User-Agent": self.UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": self.host,
            "Referer": self.host + "/",
        }
        self.s = requests.Session()

    # ---- 基础设施 ----
    def isVideoFormat(self, url):
        u = (url or '').lower()
        return ('.m3u8' in u) or ('.mp4' in u)

    def _base(self):
        return self._bases[self._base_idx % len(self._bases)]

    def _rotate_base(self):
        self._base_idx = (self._base_idx + 1) % len(self._bases)
        self.host = self._base().rstrip('/')
        self.headers['Origin'] = self.host
        self.headers['Referer'] = self.host + '/'
        return self._base()

    def _url(self, path):
        path = (path or '').lstrip('/')
        if path.startswith('http'):
            return path
        return self._base() + path

    def _abs(self, u):
        u = (u or '').strip()
        if not u:
            return ''
        if u.startswith('http'):
            return u
        # 相对路径：优先拼当前 base，若字段本身是绝对路径则用主域名
        if u.startswith('/'):
            return urljoin(self.host + '/', u)
        return urljoin(self._base(), u)

    def _get(self, url, params=None, timeout=10):
        try:
            r = self.s.get(url, params=params, headers=self.headers, proxies=self.proxies, timeout=timeout)
        except Exception:
            return None
        return r

    # 统一 JSON API 请求（带域名轮换与重试）
    def _api(self, path, params=None, timeout=10, tries=None):
        if tries is None:
            tries = len(self._bases)
        params = params or {}
        for i in range(tries):
            url = self._url(path)
            r = self._get(url, params=params, timeout=timeout)
            if r is not None and r.status_code == 200:
                try:
                    return r.json()
                except Exception:
                    # 非 JSON 返回，尝试文本兜底
                    return r.text
            # 失败则轮换到下一个域名
            self._rotate_base()
        return None

    # ---- 从任意 JSON 结构里稳健地提取 list ----
    def _extract_list(self, obj):
        if obj is None:
            return []
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            # 1) 常见 {code, data:{list|records|rows|content}} / {code, data:[...]}
            for k in ('data', 'result', 'results'):
                v = obj.get(k)
                if isinstance(v, list):
                    return v
                if isinstance(v, dict):
                    for lk in ('list', 'records', 'rows', 'content', 'items', 'data'):
                        if isinstance(v.get(lk), list):
                            return v[lk]
                    # data 本身是个字典对象（单条）
                    return [v]
            # 2) 顶层直接带 list 字段
            for lk in ('list', 'records', 'rows', 'content', 'items'):
                if isinstance(obj.get(lk), list):
                    return obj[lk]
            # 3) 顶层就是单条对象
            return [obj]
        return []

    def _first(self, item, keys):
        for k in keys:
            v = item.get(k)
            if v not in (None, '', [], {}):
                return v
        return None

    def _as_str(self, v):
        if v is None:
            return ''
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return str(v)

    # 从单个 item 解析出播放地址（支持 streamUrls 数组 / definitionURL 字典）
    def _play_urls(self, item):
        urls = []
        for k in self.URL_KEYS:
            v = item.get(k)
            if not v:
                continue
            if isinstance(v, list):
                for u in v:
                    if isinstance(u, str) and u.startswith('http'):
                        urls.append(u)
                    elif isinstance(u, dict):
                        uu = self._first(u, self.URL_KEYS)
                        if uu and str(uu).startswith('http'):
                            urls.append(str(uu))
            elif isinstance(v, dict):
                # definitionURL 可能是 {清晰度: url}
                for uu in v.values():
                    if isinstance(uu, str) and uu.startswith('http'):
                        urls.append(uu)
            elif isinstance(v, str) and v.startswith('http'):
                urls.append(v)
        # 去重保序
        seen, out = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    # ---- 列表项 -> OK影视 数据模型 ----
    def _to_vod(self, item):
        title = self._as_str(self._first(item, self.TITLE_KEYS) or '')
        cover = self._abs(self._as_str(self._first(item, self.COVER_KEYS) or ''))
        play_urls = self._play_urls(item)
        play = play_urls[0] if play_urls else ''
        dur = self._as_str(self._first(item, self.DUR_KEYS) or '')
        desc = self._as_str(self._first(item, self.DESC_KEYS) or '')
        vid = self._as_str(self._first(item, self.ID_KEYS) or play or cover)

        # 列表阶段就把播放地址编码进 vod_id，detail 阶段直接解码，避免依赖
        # 一个未被静态确认的“详情接口”。
        meta = json.dumps({'title': title, 'cover': cover, 'urls': play_urls}, ensure_ascii=False)
        vod_id = "[rx:%s]%s" % (meta, vid)

        vod = {
            'vod_id': vod_id,
            'vod_name': title or '未知',
            'vod_pic': cover,
            'vod_remarks': dur or desc or '',
            'vod_content': desc or '',
        }
        if play_urls:
            vod['vod_play_from'] = '播放'
            vod['vod_play_url'] = '正片$' + play_urls[0]
        return vod

    # ---- OK影视 标准接口 ----
    def homeContent(self, filter):
        classes = []
        # 尝试动态拉分类
        data = self._api(self.API_CATEGORY_LIST)
        for it in self._extract_list(data):
            cid = self._first(it, ['categoryId', 'secondCategoryId', 'id', 'typeId', 'tagId'])
            cname = self._first(it, ['categoryName', 'thirdCategoryName', 'tagName', 'name', 'title'])
            if cid is not None and cname:
                classes.append({'type_name': self._as_str(cname), 'type_id': self._as_str(cid)})
        # 分类拉取失败时的硬编码兜底
        if not classes:
            classes = [
                {'type_name': '随机推荐', 'type_id': 'random'},
                {'type_name': '全部分类', 'type_id': ''},
            ]

        videos = []
        for it in self._extract_list(self._api(self.API_MEDIA_RANDOM)):
            vod = self._to_vod(it)
            if vod['vod_pic'] or vod['vod_play_url']:
                videos.append(vod)
        return {'class': classes, 'filters': {}, 'list': videos}

    def homeVideoContent(self):
        return {'list': (self.homeContent(None) or {}).get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if pg else 1
        tid = str(tid or '')
        params = {'pageNo': pg, 'pageSize': 20}
        if tid and tid != 'random':
            # 优先按二级分类 ID；也兼容 categoryId/secondCategoryId 两类字段
            params['secondCategoryId'] = tid
            path = self.API_MEDIA_BY_CATEGORY
        else:
            path = self.API_MEDIA_RANDOM

        data = self._api(path, params=params)
        items = self._extract_list(data)
        videos = []
        for it in items:
            vod = self._to_vod(it)
            if vod['vod_pic'] or vod['vod_play_url']:
                videos.append(vod)

        # 分页信息
        total_page = 9999
        if isinstance(data, dict):
            tp = data.get('totalPage') or data.get('total_page') or data.get('total')
            if tp is not None:
                try:
                    total_page = int(tp)
                except Exception:
                    total_page = 9999
        return {'list': videos, 'page': pg, 'pagecount': total_page, 'limit': 20, 'total': len(videos)}

    def searchContent(self, key, quick, pg='1'):
        pg = int(pg) if pg else 1
        data = self._api(self.API_MEDIA_SEARCH, params={'searchKeyword': str(key), 'pageNo': pg, 'pageSize': 20})
        videos = []
        for it in self._extract_list(data):
            vod = self._to_vod(it)
            if vod['vod_pic'] or vod['vod_play_url']:
                videos.append(vod)
        return {'list': videos, 'page': pg, 'pagecount': 9999}

    def detailContent(self, ids):
        vid = ids[0] if ids else ''
        # 直接 URL（m3u8/mp4）
        if str(vid).startswith('http') and self.isVideoFormat(vid):
            return {'list': [{'vod_id': vid, 'vod_name': vid, 'vod_play_from': '播放', 'vod_play_url': '正片$' + vid}]}
        # 从列表阶段编码的元数据里解码
        m = re.match(r'^\[rx:(.*?)\](.*)$', str(vid))
        if m:
            try:
                meta = json.loads(m.group(1))
            except Exception:
                meta = {}
            title = meta.get('title') or m.group(2) or '视频'
            cover = meta.get('cover') or ''
            urls = meta.get('urls') or []
            play = urls[0] if urls else ''
            return {'list': [{
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': cover,
                'vod_play_from': '播放',
                'vod_play_url': ('正片$' + play) if play else '获取失败',
            }]}
        return {'list': [{'vod_id': vid, 'vod_name': '视频', 'vod_play_from': '播放', 'vod_play_url': '获取失败'}]}

    def playerContent(self, flag, id, vipFlags):
        if isinstance(id, str) and id.startswith('http') and ('.m3u8' in id or '.mp4' in id):
            h = dict(self.headers or {})
            h['Origin'] = self.host
            h['Referer'] = self.host + '/'
            return {'parse': 0, 'url': id, 'header': h}
        return {'parse': 1, 'url': id, 'header': self.headers}
