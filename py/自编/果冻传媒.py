# -*- coding: utf-8 -*-
import json
import re
import base64
import hashlib
import time
import requests
import sys
sys.path.append('..')
from base.spider import Spider
from urllib.parse import quote, unquote
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

TIMEOUT = 10

# API 加密配置
OAUTH_ID = '3fb8fcf855e55f6818a4e9c7a4161817'
BUNDLE_ID = 'com.pwa.gdcm'
VERSION = '3.9.0'
AES_KEY = b'2acf7e91e9864673'
AES_IV = b'1c29882d3ddfcfd6'
SIGN_SALT = '5589d41f92a597d016b037ac37db243d'

# 图片加密配置
IMG_KEY = b'f5d965df75336270'
IMG_IV = b'97b60394abc2fbe1'

API_BASE = 'https://api3.gdapi1.com/api.php/api/mv/'
PROXY_TYPE = 'gdcm_img'


class Spider(Spider):
    host = 'https://gdcm.com'
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    # ==================== 初始化 ====================
    def init(self, extend=''):
        if extend:
            try:
                ext = json.loads(extend) if isinstance(extend, str) else extend
                self.proxies = ext.get('proxies', {})
            except Exception:
                self.proxies = {}
        else:
            self.proxies = {}

    def getName(self):
        return "果冻传媒"

    def isVideoFormat(self, url):
        return url and ('.mp4' in url or '.m3u8' in url or '.ts' in url)

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def liveContent(self, url):
        pass

    def action(self, action):
        pass

    # ==================== AES 加解密 ====================
    def _aes_encrypt(self, plaintext):
        cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
        encrypted = cipher.encrypt(pad(plaintext.encode('utf-8'), AES.block_size))
        return base64.b64encode(encrypted).decode('utf-8')

    def _aes_decrypt(self, ciphertext):
        cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
        decrypted = unpad(cipher.decrypt(base64.b64decode(ciphertext)), AES.block_size)
        return decrypted.decode('utf-8')

    def _generate_sign(self, data, timestamp):
        raw = f"client=pwa&data={data}&timestamp={timestamp}{SIGN_SALT}"
        sha = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        return hashlib.md5(sha.encode('utf-8')).hexdigest()

    # ==================== API 请求 ====================
    def _api_request(self, endpoint, params=None):
        if params is None:
            params = {}
        ts = int(time.time())
        data = {
            'oauth_id': OAUTH_ID,
            'bundleId': BUNDLE_ID,
            'version': VERSION,
            'oauth_type': 'web',
            'language': 'zh',
            'via': 'pwa',
            'token': '',
        }
        data.update(params)
        data_str = json.dumps(data, ensure_ascii=False)
        encrypted_data = self._aes_encrypt(data_str)
        sign = self._generate_sign(encrypted_data, ts)

        post_data = {
            'client': 'pwa',
            'timestamp': str(ts),
            'data': encrypted_data,
            'sign': sign,
        }
        try:
            r = requests.post(API_BASE + endpoint, data=post_data,
                              headers=self.headers, timeout=TIMEOUT, verify=False,
                              proxies=self.proxies)
            resp = r.json()
            if 'data' in resp:
                decrypted = self._aes_decrypt(resp['data'])
                return json.loads(decrypted)
        except Exception:
            pass
        return None

    # ==================== 图片处理 ====================
    def get_proxy_image_url(self, img_url):
        if not img_url:
            return ''
        base_proxy = self.getProxyUrl()
        if not base_proxy:
            base_proxy = 'http://127.0.0.1:9978/proxy?do=py'
        return base_proxy + '&type=' + PROXY_TYPE + '&url=' + quote(img_url, safe='')

    def _fmt_duration(self, seconds):
        try:
            s = int(seconds or 0)
        except (TypeError, ValueError):
            return ''
        if s <= 0:
            return ''
        m, s = divmod(s, 60)
        return f"{m}:{s:02d}"

    # ==================== 视频列表解析（公共方法） ====================
    def _parse_vod_list(self, items):
        vod_list = []
        for item in items:
            if not item.get('tag_list'):
                continue
            pic_url = item.get('cover_horizontal', '')
            vod_list.append({
                'vod_id': item['id'],
                'vod_name': item.get('title', ''),
                'vod_pic': self.get_proxy_image_url(pic_url) if pic_url else '',
                'vod_remarks': self._fmt_duration(item.get('duration', 0)),
            })
        return vod_list

    # ==================== 标签格式化（可点击） ====================
    def _format_tags(self, raw_tags):
        """将标签列表格式化为 OK影视 可点击的 [a=cr:...] 格式"""
        tag_parts = []
        for t in raw_tags:
            tag_name = ''
            if isinstance(t, dict):
                tag_name = t.get('name', '')
            elif isinstance(t, str):
                tag_name = t
            else:
                tag_name = str(t)
            tag_name = tag_name.strip()
            if tag_name:
                cr = json.dumps({"id": "tag_" + tag_name, "name": tag_name}, ensure_ascii=False)
                tag_parts.append(f'[a=cr:{cr}/]{tag_name}[/a]')
        return ' '.join(tag_parts)

    # ==================== 首页 ====================
    def homeContent(self, filter):
        main_categories = [
            {'type_id': '1', 'type_name': '推荐'},
            {'type_id': '236', 'type_name': '禁忌乱伦'},
            {'type_id': '2', 'type_name': '华语AV'},
            {'type_id': '264', 'type_name': '偷拍摄狼'},
            {'type_id': '3', 'type_name': '国产专区'},
            {'type_id': '4', 'type_name': '日韩欧美'},
            {'type_id': '5', 'type_name': '动漫之家'},
        ]

        filters = {
            '1': [{'key': 'sub', 'name': '子分类', 'value': [
                {'n': '全部', 'v': '1'},
                {'n': '黑料吃瓜', 'v': '65'},
                {'n': 'JK萝莉', 'v': '215'},
                {'n': '偷拍攝像', 'v': '264'},
                {'n': '会所按摩', 'v': '153'},
                {'n': '探花外围', 'v': '43'},
                {'n': '白虎美穴', 'v': '231'},
                {'n': '知名网黄', 'v': '152'},
                {'n': '肥臀巨乳', 'v': '227'},
                {'n': '媚黑母狗', 'v': '230'},
                {'n': 'FC2无码', 'v': '115'},
                {'n': '肉欲调教', 'v': '61'},
                {'n': '野外激情', 'v': '234'},
                {'n': '人妖伪娘', 'v': '229'},
                {'n': 'AI换脸', 'v': '233'},
                {'n': '浪淫孕妇', 'v': '266'},
                {'n': '中东美女', 'v': '258'},
            ]}],
            '236': [{'key': 'sub', 'name': '子分类', 'value': [
                {'n': '全部', 'v': '236'},
                {'n': '母子', 'v': '237'},
                {'n': '父女', 'v': '238'},
                {'n': '兄妹', 'v': '239'},
                {'n': '姐弟', 'v': '240'},
                {'n': '岳母', 'v': '241'},
                {'n': '儿媳', 'v': '242'},
                {'n': '舅侄', 'v': '243'},
                {'n': '叔嫂', 'v': '245'},
                {'n': '妹婿', 'v': '246'},
                {'n': '学生老师', 'v': '247'},
                {'n': '小姨子', 'v': '248'},
                {'n': '近亲乱伦', 'v': '249'},
            ]}],
            '2': [{'key': 'sub', 'name': '子分类', 'value': [
                {'n': '全部', 'v': '2'},
                {'n': '果冻传媒', 'v': '35'},
                {'n': '91制片厂', 'v': '34'},
                {'n': '麻豆传媒', 'v': '33'},
                {'n': '精东影业', 'v': '36'},
                {'n': '天美传媒', 'v': '37'},
                {'n': '蜜桃传媒', 'v': '38'},
                {'n': '星空无限', 'v': '91'},
                {'n': '爱豆传媒', 'v': '94'},
                {'n': '皇家华人', 'v': '39'},
                {'n': 'JVID', 'v': '90'},
                {'n': '51吃瓜', 'v': '267'},
                {'n': '其它传媒', 'v': '40'},
            ]}],
            '264': [{'key': 'sub', 'name': '子分类', 'value': [
                {'n': '全部', 'v': '264'},
                {'n': '金先生', 'v': '263'},
                {'n': '李宗瑞', 'v': '262'},
                {'n': '酒店偷拍', 'v': '254'},
                {'n': '家庭摄像', 'v': '179'},
                {'n': '街头抄底', 'v': '261'},
                {'n': '足浴偷拍', 'v': '260'},
                {'n': '窥探澡堂', 'v': '253'},
                {'n': '跟拍如厕', 'v': '177'},
            ]}],
            '3': [{'key': 'sub', 'name': '子分类', 'value': [
                {'n': '全部', 'v': '3'},
                {'n': '单男绿帽', 'v': '217'},
                {'n': '原创自拍', 'v': '44'},
                {'n': '自慰足交', 'v': '214'},
                {'n': '熟女少妇', 'v': '184'},
                {'n': '中出内射', 'v': '199'},
                {'n': '多人群交', 'v': '198'},
                {'n': '黑丝制服', 'v': '259'},
                {'n': '国产微剧', 'v': '205'},
                {'n': '甜美主播', 'v': '68'},
                {'n': '勾引出轨', 'v': '62'},
                {'n': 'KTV蕉谈', 'v': '250'},
                {'n': '美女空姐', 'v': '251'},
                {'n': '极品反差', 'v': '252'},
                {'n': 'Cosplay', 'v': '255'},
                {'n': '伦理换妻', 'v': '256'},
                {'n': '成人综艺', 'v': '213'},
            ]}],
            '4': [{'key': 'sub', 'name': '子分类', 'value': [
                {'n': '全部', 'v': '4'},
                {'n': '无码流出', 'v': '46'},
                {'n': '中文字幕', 'v': '114'},
                {'n': '欧美最新', 'v': '97'},
                {'n': '变态家族', 'v': '265'},
                {'n': '不伦换妻', 'v': '119'},
                {'n': '强奸轮奸', 'v': '122'},
                {'n': '无套中出', 'v': '124'},
                {'n': '黑丝制服', 'v': '120'},
                {'n': '巨根黑人', 'v': '100'},
                {'n': '西洋华裔', 'v': '104'},
                {'n': '素人自拍', 'v': '118'},
                {'n': '韩国性事', 'v': '203'},
            ]}],
            '5': [{'key': 'sub', 'name': '子分类', 'value': [
                {'n': '全部', 'v': '5'},
                {'n': 'H动漫', 'v': '49'},
                {'n': '原神IP', 'v': '196'},
                {'n': '3D动画', 'v': '51'},
                {'n': '剧场番剧', 'v': '50'},
                {'n': '角色扮演', 'v': '52'},
                {'n': '轮奸淫乱', 'v': '129'},
                {'n': '妖兽鬼畜', 'v': '155'},
                {'n': '家族不伦', 'v': '154'},
            ]}],
        }

        # 获取首页推荐视频
        result = self._api_request('list_construct', {
            'page': '1',
            'id': '1',
            'limit': '12',
            'sort': 'new',
        })
        items = (result or {}).get('data', {}).get('list', [])
        vod_list = self._parse_vod_list(items)

        return {
            'class': main_categories,
            'filters': filters,
            'list': vod_list,
        }

    def homeVideoContent(self):
        pass

    # ==================== 分类列表 ====================
    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid)
        pg = int(pg)

        # 处理标签点击：tag_开头的 tid 走标签过滤
        if tid.startswith('tag_'):
            tag_name = tid[4:]  # 去掉 "tag_" 前缀
            result = self._api_request('list_construct', {
                'page': str(pg),
                'id': '1',
                'limit': '15',
                'sort': 'new',
                'tag': tag_name,
            })
            items = (result or {}).get('data', {}).get('list', [])
            vod_list = self._parse_vod_list(items)
            return {
                'list': vod_list,
                'page': pg,
                'pagecount': 99,
                'limit': len(vod_list),
                'total': len(vod_list) * 99,
            }

        # 处理搜索点击：search_开头的 tid 走搜索
        if tid.startswith('search_'):
            keyword = tid[7:]
            result = self._api_request('search', {
                'word': keyword,
                'type': '1',
                'page': str(pg),
                'limit': '15',
            })
            items = (result or {}).get('data', [])
            if isinstance(items, dict):
                items = items.get('list', [])
            vod_list = self._parse_vod_list(items)
            return {
                'list': vod_list,
                'page': pg,
                'pagecount': 99,
                'limit': len(vod_list),
                'total': len(vod_list) * 99,
            }

        # 常规分类列表
        actual_id = tid
        if extend:
            try:
                if isinstance(extend, str):
                    ext_data = json.loads(base64.b64decode(extend).decode('utf-8'))
                elif isinstance(extend, dict):
                    ext_data = extend
                else:
                    ext_data = {}
                if ext_data.get('sub'):
                    actual_id = ext_data['sub']
            except Exception:
                pass

        result = self._api_request('list_construct', {
            'page': str(pg),
            'id': actual_id,
            'limit': '15',
            'sort': 'new',
        })

        items = (result or {}).get('data', {}).get('list', [])
        vod_list = self._parse_vod_list(items)

        return {
            'list': vod_list,
            'page': pg,
            'pagecount': 99,
            'limit': len(vod_list),
            'total': len(vod_list) * 99,
        }

    # ==================== 详情 ====================
    def detailContent(self, ids):
        did = ids[0] if isinstance(ids, list) else ids
        result = self._api_request('getDetail', {'id': str(did)})
        if not result:
            return {'list': []}

        detail = result.get('data', {}).get('detail', {})
        if not detail:
            return {'list': []}

        pic = self.get_proxy_image_url(detail.get('cover_horizontal', ''))

        # 标签格式化为可点击
        raw_tags = detail.get('tag_list', [])
        tags_text = self._format_tags(raw_tags)

        # 分类名称
        construct_id = detail.get('construct_id', '')
        category_name = detail.get('video_type_name', '')

        vod_id = detail.get('id', did)
        duration_str = self._fmt_duration(detail.get('duration', 0))
        return {'list': [{
            'vod_id': vod_id,
            'vod_name': detail.get('title', ''),
            'vod_pic': pic,
            'vod_actor': tags_text,
            'vod_director': detail.get('publisher', ''),
            'vod_content': detail.get('description', ''),
            'vod_year': detail.get('release_at', '')[:4] if detail.get('release_at') else '',
            'vod_area': '',
            'vod_remarks': '时长: ' + duration_str if duration_str else '',
            'vod_play_from': '果冻传媒',
            'vod_play_url': '播放$' + str(vod_id),
            'type': 'video',
        }]}

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg="1"):
        result = self._api_request('search', {
            'word': key,
            'type': '1',
            'page': str(pg),
            'limit': '15',
        })
        if not result:
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 0, 'total': 0}

        items = result.get('data', [])
        if isinstance(items, dict):
            items = items.get('list', [])
        vod_list = self._parse_vod_list(items)

        return {
            'list': vod_list,
            'page': pg,
            'pagecount': 99,
            'limit': len(vod_list),
            'total': len(vod_list) * 99,
        }

    # ==================== 播放解析 ====================
    def playerContent(self, flag, id, vipFlags):
        vid = id.split('$')[-1]
        result = self._api_request('getDetail', {'id': vid})
        if not result:
            return {'parse': 0, 'url': '', 'jx': 0}

        play_url = result.get('data', {}).get('detail', {}).get('preview_url', '')
        if not play_url:
            return {'parse': 0, 'url': '', 'jx': 0}

        # 直接使用 API 返回的 preview_url，不做域名替换
        return {
            'parse': 0,
            'url': play_url,
            'jx': 0,
            'header': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            },
        }

    # ==================== 图片代理（AES 解密图片） ====================
    def localProxy(self, param):
        try:
            if param.get('type') != PROXY_TYPE:
                return [404, 'text/plain', 'not found']

            img_url = param.get('url', '')
            if not img_url:
                return [400, 'text/plain', 'missing url']

            img_url = unquote(img_url)

            r = requests.get(img_url, headers={
                'User-Agent': 'Mozilla/5.0',
            }, timeout=TIMEOUT, verify=False, proxies=self.proxies)
            if r.status_code != 200:
                return [404, 'text/plain', 'image not found']

            encrypted_data = r.content
            try:
                cipher = AES.new(IMG_KEY, AES.MODE_CBC, IMG_IV)
                decrypted = unpad(cipher.decrypt(encrypted_data), AES.block_size)
            except Exception:
                return [500, 'text/plain', 'decrypt error']

            if decrypted[:2] == b'\xff\xd8':
                return [200, 'image/jpeg', decrypted, {'Content-Length': str(len(decrypted))}]
            elif decrypted[:4] == b'\x89PNG':
                return [200, 'image/png', decrypted, {'Content-Length': str(len(decrypted))}]
            elif decrypted[:4] == b'RIFF' and decrypted[8:12] == b'WEBP':
                return [200, 'image/webp', decrypted, {'Content-Length': str(len(decrypted))}]
            else:
                return [200, 'image/jpeg', decrypted, {'Content-Length': str(len(decrypted))}]
        except Exception:
            return [500, 'text/plain', 'proxy error']
