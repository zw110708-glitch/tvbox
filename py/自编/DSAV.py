# -*- coding: utf-8 -*-
# by @嗷呜
import time
import uuid
from base64 import b64decode, b64encode
import json
import sys
from urllib.parse import urlparse, urlunparse
from Crypto.Cipher import AES
from Crypto.Hash import MD5
from Crypto.Util.Padding import unpad, pad

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def init(self, extend=""):
        # 不使用 requests proxies；统一改为“URL 前缀代理”方式
        # extend 里包含 debug 时，打印关键入参便于排错
        self._debug = isinstance(extend, str) and ('debug' in extend.lower())

    def getName(self):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    host = "https://api.230110.xyz"

    phost = "https://cdn.230110.xyz"

    # URL 前缀代理（整体不可分割）
    proxy_prefix = "http://127.0.0.1:10079/p/0/127.0.0.1:10172/"

    def px(self, url: str) -> str:
        """给外部 URL 增加代理前缀；避免重复前缀。"""
        if not url:
            return url
        if url.startswith(self.proxy_prefix):
            return url
        return f"{self.proxy_prefix}{url}"

    headers = {
        'origin': host,
        'referer': f'{host}/',
        'user-agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.8 Mobile/15E148 Safari/604.1',
    }

    def homeContent(self, filter):
        data = '9XSPkyFMrOOG34JSg//ZosMof45cyBo9hwZMZ5rvI6Yz/ZZlXWIf8/644OzwW+FNIOdJ61R/Lxjy1tqN+ZzokxtiVzb8LjYAkh6GFudwAUXFt9yS1ZjAxC3tDKrQsJQLk3nym0s00DBBzLBntRBDFz7nbba+OOBuQOZpL3CESGL42l4opdoViQLhO/dIizY1kIOk2NxxpDC9Z751gPl1ctHWuLWhuLG/QWgNWi/iHScjKrMHJKcC9GQHst/4Q3dgZ03eQIIVB6jvoV1XXoBCz6fjM/jM3BXpzSttT4Stglwy93gWuNWuZiKypHK2Q0lO10oM0ceRW2a0fPGId+rNYMRO3cR/C0ZueD4cmTAVOuxVr9ZZSP8/nhD0bHyAPONXtchIDJb0O/kdFHk2KTJfQ5q4fHOyzezczc4iQDV/R0S8cGZKM14MF+wytA/iljfj43H0UYqq5pM+MCUGRTdYEtuxCp0+A+DiOhNZwY/Km/TgBoGZQWGbpljJ2LAVnWhxX+ickLH7zuR/FeIwP/R8zOuR+8C8UlT9eHTqtvfNzaGdFxt316atHy8TNjRO7J5a177mqsHs3ziG0toDDzLDCbhRUjFgVA3ktahhXiWaaCo/ZGSJAA8TDO5DYqnJ0JDaX0ILPj8QB5zxrHYmRE8PboIr3RBAjz1sREbaHfjrUjoh29ePhlolLV00EvgoxP5knaqt5Ws/sq5IG57qKCAPgqXzblPLHToJGBtukKhLp8jbGJrkb6PVn4/jysks0NGE'
        return {'class': self.aes(data, False)}

    def homeVideoContent(self):
        pass

    def categoryContent(self, tid, pg, filter, extend):
        data = {"q": "", "filter": [f"type_id = {tid}"], "offset": (int(pg) - 1) * 24, "limit": 24,
                "sort": ["video_time:desc"], "lang": "zh-cn", "route": "/videos/search"}
        result = {}
        if 'skey_' in tid:
            return self.searchContent(tid.split('_')[-1], True, pg)
        result['list'] = self.getl(self.getdata(data))
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def detailContent(self, ids):
        # 不同壳/框架这里可能传 list，也可能直接传字符串
        if isinstance(ids, (list, tuple)):
            vid = str(ids[0]) if ids else ''
        else:
            vid = str(ids) if ids is not None else ''
        vid = vid.strip()
        if not vid:
            return {'list': []}

        if getattr(self, '_debug', False):
            try:
                print(f"[18] detailContent ids={vid[:80]}")
            except Exception:
                pass

        # v3 核心修复：不再依赖 video_id filter 查详情（服务端已返回空）
        # 改为：列表页将必要字段编码进 vod_id，详情页直接解码。
        res = None
        try:
            # 兼容 urlsafe base64
            raw = vid.replace('-', '+').replace('_', '/')
            pad_len = (-len(raw)) % 4
            if pad_len:
                raw += '=' * pad_len
            dec = self.d64(raw)
            obj = json.loads(dec)
            if isinstance(obj, dict) and obj.get('video_url'):
                res = obj
        except Exception:
            res = None

        # 兜底：老壳/老列表未编码时，继续尝试 API（可能未来修复服务端）
        if res is None:
            if vid.isdigit():
                fid = f"video_id = {vid}"
            else:
                fid = f"video_id = '{vid}'"
            data = {"limit": 1, "filter": [fid], "lang": "zh-cn", "route": "/videos/search"}
            data_list = self.getdata(data)
            if not data_list:
                return {'list': []}
            res = data_list[0]

        # 详情页必须返回基础字段，否则壳可能“进不了详情”
        img = res.get('video_cover')
        if img and 'http' in img:
            img = urlunparse(urlparse(self.phost)._replace(path=urlparse(img).path))

        vurl = res.get('video_url')
        purl = ''
        if vurl:
            # 强制走 cdn 域名
            purl = urlunparse(urlparse(self.phost)._replace(path=urlparse(vurl).path))

        vod = {
            'vod_id': res.get('video_id') or vid,
            'vod_name': res.get('video_title') or '',
            'vod_pic': img or '',
            'vod_remarks': res.get('video_duration') or '',
            'vod_play_from': 'dsysav',
            # play_url 格式：线路名：剧集名$播放地址（允许用时长做剧集名）
            'vod_play_url': f"{res.get('video_duration') or '播放'}${purl}" if purl else ''
        }

        if res.get('video_tag'):
            clist = []
            tags = res['video_tag'].split(',')
            for k in tags:
                clist.append('[a=cr:' + json.dumps({'id': f'skey_{k}', 'name': k}) + '/]' + k + '[/a]')
            vod['vod_content'] = ' '.join(clist)

        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        data = {"q": key, "filter": [], "offset": (int(pg) - 1) * 24, "limit": 24, "sort": ["video_time:desc"],
                "lang": "zh-cn", "route": "/videos/search"}
        return {'list': self.getl(self.getdata(data)), 'page': pg}

    def playerContent(self, flag, id, vipFlags):
        if id.endswith('.mpd'):
            id = f"{self.getProxyUrl()}&url={self.e64(id)}&type=mpd"
        return {'parse': 0, 'url': id, 'header': self.headers}

    def localProxy(self, param):
        if param.get('type') and param['type'] == 'mpd':
            url = self.d64(param.get('url'))
            ids = url.split('/')
            id = f"{ids[-3]}/{ids[-2]}/"
            xpu = f"{self.getProxyUrl()}&path=".replace('&', '&amp;')
            data = self.fetch(self.px(url), headers=self.headers).text
            data = data.replace('initialization="', f'initialization="{xpu}{id}').replace('media="', f'media="{xpu}{id}')
            # MPD 建议返回 dash+xml，且保持文本编码
            return [200, 'application/dash+xml; charset=utf-8', data]
        else:
            # 生成带签名的真实分片地址
            # expire 需要动态生成，否则过期会导致 410/无法播放
            expire = int(time.time()) + 86400  # 24 小时有效
            hsign = self.md5(f"AjPuom638LmWfWyeM5YueKuJ9PuWLdRn/mpd/{param.get('path')}{expire}")
            bytes_data = bytes.fromhex(hsign)
            sign = b64encode(bytes_data).decode('utf-8').replace('=', '').replace('+', '-').replace('/', '_')
            real_url = f"{self.phost}/mpd/{param.get('path')}?sign={sign}&expire={expire}"

            # 关键修复：不要 302 重定向给播放器（部分 DASH 播放器/环境不会跟随分片重定向）
            # 直接由代理拉取并回传分片内容
            r = self.fetch(self.px(real_url), headers=self.headers)
            ctype = None
            try:
                ctype = r.headers.get('Content-Type')
            except Exception:
                pass
            if not ctype:
                # 兜底 MIME
                p = (param.get('path') or '').lower()
                if p.endswith('.mpd'):
                    ctype = 'application/dash+xml'
                elif p.endswith('.m4s') or p.endswith('.mp4'):
                    ctype = 'video/mp4'
                else:
                    ctype = 'application/octet-stream'
            return [200, ctype, getattr(r, 'content', r)]

    def liveContent(self, url):
        pass

    def aes(self, text, operation=True):
        key = b'OPQT123412FRANME'
        iv = b'MRDCQP12QPM13412'
        cipher = AES.new(key, AES.MODE_CBC, iv)
        if operation:
            ct_bytes = cipher.encrypt(pad(json.dumps(text).encode("utf-8"), AES.block_size))
            ct = b64encode(ct_bytes).decode("utf-8")
            return ct
        else:
            pt = unpad(cipher.decrypt(b64decode(text)), AES.block_size)
            return json.loads(pt.decode("utf-8"))

    def e64(self, text):
        try:
            text_bytes = text.encode('utf-8')
            encoded_bytes = b64encode(text_bytes)
            return encoded_bytes.decode('utf-8')
        except Exception as e:
            print(f"Base64编码错误: {str(e)}")
            return ""

    def d64(self, encoded_text):
        try:
            encoded_bytes = encoded_text.encode('utf-8')
            decoded_bytes = b64decode(encoded_bytes)
            return decoded_bytes.decode('utf-8')
        except Exception as e:
            print(f"Base64解码错误: {str(e)}")
            return ""

    def md5(self, text):
        h = MD5.new()
        h.update(text.encode('utf-8'))
        return h.hexdigest()

    def getl(self, data):
        videos = []
        for i in data:
            img = i.get('video_cover')
            if img and 'http' in img:
                img = urlunparse(urlparse(self.phost)._replace(path=urlparse(img).path))

            # v3：把详情页所需字段塞进 vod_id（base64+urlsafe），避免再调详情接口
            pack = {
                'video_id': i.get('video_id'),
                'video_title': i.get('video_title'),
                'video_cover': img,
                'video_duration': i.get('video_duration'),
                'video_tag': i.get('video_tag'),
                'video_url': i.get('video_url'),
            }
            vid = self.e64(json.dumps(pack, ensure_ascii=False))
            # urlsafe（避免壳对 + / = 处理不一致）
            vid = vid.replace('=', '').replace('+', '-').replace('/', '_')

            videos.append({
                'vod_id': vid,
                'vod_name': i.get('video_title'),
                'vod_pic': img,
                'vod_remarks': i.get('video_duration'),
                'style': {"type": "rect", "ratio": 1.33}
            })
        return videos

    def getdata(self, data):
        uid = str(uuid.uuid4())
        t = int(time.time())
        payload = {
            'sign': self.md5(f"{self.e64(json.dumps(data))}{uid}{t}AjPuom638LmWfWyeM5YueKuJ9PuWLdRn"),
            'nonce': uid,
            'timestamp': t,
            'data': self.aes(data),
        }

        url = f"{self.host}/v1"

        # 优先直连；直连失败再尝试走 URL 前缀代理（某些环境必须走代理）
        resp = None
        last_err = None
        for u in (url, self.px(url)):
            try:
                resp = self.post(u, json=payload, headers=self.headers)
                break
            except Exception as e:
                last_err = e
                resp = None

        if resp is None:
            raise Exception(f"请求 API 失败: {last_err}")

        j = resp.json()
        if not isinstance(j, dict) or 'data' not in j:
            # 直接把服务端返回抛出来，方便定位
            raise Exception(f"API 返回异常: {j}")

        try:
            res = self.aes(j['data'], False)
        except Exception as e:
            raise Exception(f"API data 解密失败: {e}，原始返回: {j}")

        return res
