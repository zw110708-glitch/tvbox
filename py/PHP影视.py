# coding=utf-8
# !/usr/bin/python

"""

作者 丢丢喵 🚓 内容均从互联网收集而来 仅供交流学习使用 版权归原创者所有 如侵犯了您的权益 请通知作者 将及时删除侵权内容
                    ====================Diudiumiao====================

"""

from Crypto.Util.Padding import unpad
from Crypto.Util.Padding import pad
from urllib.parse import unquote
from Crypto.Cipher import ARC4
from urllib.parse import quote
from base.spider import Spider
from Crypto.Cipher import AES
from datetime import datetime
from bs4 import BeautifulSoup
from base64 import b64decode
import urllib.request
import urllib.parse
import datetime
import binascii
import requests
import base64
import json
import time
import sys
import re
import os

sys.path.append('..')

xurl = "http://ccczb.top"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.87 Safari/537.36'
          }

headerx = {
        'User-Agent': 'Mozilla/5.0 (Linux; U; Android 8.0.0; zh-cn; Mi Note 2 Build/OPR1.170623.032) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/61.0.3163.128 Mobile Safari/537.36 XiaoMi/MiuiBrowser/10.1.1',
        'Referer': 'http://ccczb.top/ys/index.php'
          }

class Spider(Spider):

    def getName(self):
        return "丢丢喵"

    def init(self, extend):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def extract_middle_text(self, text, start_str, end_str, pl, start_index1: str = '', end_index2: str = ''):
        if pl == 3:
            plx = []
            while True:
                start_index = text.find(start_str)
                if start_index == -1:
                    break
                end_index = text.find(end_str, start_index + len(start_str))
                if end_index == -1:
                    break
                middle_text = text[start_index + len(start_str):end_index]
                plx.append(middle_text)
                text = text.replace(start_str + middle_text + end_str, '')
            if len(plx) > 0:
                purl = ''
                for i in range(len(plx)):
                    matches = re.findall(start_index1, plx[i])
                    output = ""
                    for match in matches:
                        match3 = re.search(r'(?:^|[^0-9])(\d+)(?:[^0-9]|$)', match[1])
                        if match3:
                            number = match3.group(1)
                        else:
                            number = 0
                        if 'http' not in match[0]:
                            output += f"#{match[1]}${number}{xurl}{match[0]}"
                        else:
                            output += f"#{match[1]}${number}{match[0]}"
                    output = output[1:]
                    purl = purl + output + "$$$"
                purl = purl[:-3]
                return purl
            else:
                return ""
        else:
            start_index = text.find(start_str)
            if start_index == -1:
                return ""
            end_index = text.find(end_str, start_index + len(start_str))
            if end_index == -1:
                return ""

        if pl == 0:
            middle_text = text[start_index + len(start_str):end_index]
            return middle_text.replace("\\", "")

        if pl == 1:
            middle_text = text[start_index + len(start_str):end_index]
            matches = re.findall(start_index1, middle_text)
            if matches:
                jg = ' '.join(matches)
                return jg

        if pl == 2:
            middle_text = text[start_index + len(start_str):end_index]
            matches = re.findall(start_index1, middle_text)
            if matches:
                new_list = [f'{item}' for item in matches]
                jg = '$$$'.join(new_list)
                return jg

    def _fetch_categories_data(self):
        url = f"{xurl}/ys/simple_api.php?action=categories"
        max_retries = 3
        retries = 0
        while retries < max_retries:
            try:
                detail = requests.get(url=url, headers=headerx)
                detail.encoding = 'utf-8-sig'
                return detail.json()
            except requests.exceptions.JSONDecodeError as e:
                retries += 1
                if retries < max_retries:
                    time.sleep(1)
                else:
                    raise
            except Exception as e:
                raise

    def _process_category(self, vod):
        name = vod['type_name']
        id = vod['type_id']
        return {"type_id": id, "type_name": name}

    def _build_home_content_result(self, data):
        result = {"class": []}
        for vod in data['data']:
            category = self._process_category(vod)
            result["class"].append(category)
        return result

    def homeContent(self, filter):
        data = self._fetch_categories_data()
        return self._build_home_content_result(data)

    def _fetch_movie_data(self):
        detail = requests.get(url=f"{xurl}/ys/simple_api.php?action=search&keyword=%E7%94%B5%E5%BD%B1&page=1",headers=headerx)
        detail.encoding = "utf-8-sig"
        return detail.json()

    def homeVideoContent(self):
        data = self._fetch_movie_data()
        videos = self._process_videos_list(data)
        result = {'list': videos}
        return result

    def _fetch_category_data(self, cid, page):
        detail = requests.get(url=f"{xurl}/ys/simple_api.php?action=category&cid={cid}&page={str(page)}",headers=headerx)
        detail.encoding = "utf-8-sig"
        return detail.json()

    def _build_category_result(self, videos, pg):
        result = {'list': videos}
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def categoryContent(self, cid, pg, filter, ext):
        page = int(pg) if pg else 1
        data = self._fetch_category_data(cid, page)
        videos = self._process_videos_list(data)
        return self._build_category_result(videos, pg)

    def _fetch_detail_data(self, did):
        detail = requests.get(url=f"{xurl}/ys/simple_api.php?action=detail&vid={did}", headers=headerx)
        detail.encoding = "utf-8-sig"
        return detail.json()

    def _fetch_didiu_config(self):
        url = 'https://fs-im-kefu.7moor-fs1.com/ly/4d2c3f00-7d4c-11e5-af15-41bf63ae4ea0/1732697392729/didiu.txt'
        response = requests.get(url)
        response.encoding = 'utf-8'
        return response.text

    def _extract_video_info(self, data, code):
        name = self.extract_middle_text(code, "s1='", "'", 0)
        Jumps = self.extract_middle_text(code, "s2='", "'", 0)
        content = '😸丢丢为您介绍剧情📢' + data.get('data', {}).get('vod_content', '暂无')
        director = data.get('data', {}).get('vod_director', '暂无')
        actor = data.get('data', {}).get('vod_actor', '暂无')
        year = data.get('data', {}).get('vod_year', '暂无')
        area = data.get('data', {}).get('vod_area', '暂无')
        if name not in content:
            bofang = Jumps
            xianlu = '1'
        else:
            bofang = data['data']['vod_play_url']
            xianlu = data['data']['vod_play_from']
        return {
            "director": director,
            "actor": actor,
            "year": year,
            "area": area,
            "content": content,
            "bofang": bofang,
            "xianlu": xianlu
               }

    def _build_detail_result(self, did, video_info):
        videos = []
        videos.append({
            "vod_id": did,
            "vod_director": video_info["director"],
            "vod_actor": video_info["actor"],
            "vod_year": video_info["year"],
            "vod_area": video_info["area"],
            "vod_content": video_info["content"],
            "vod_play_from": video_info["xianlu"],
            "vod_play_url": video_info["bofang"]
                     })
        result = {'list': videos}
        return result

    def detailContent(self, ids):
        did = ids[0]
        data = self._fetch_detail_data(did)
        code = self._fetch_didiu_config()
        video_info = self._extract_video_info(data, code)
        return self._build_detail_result(did, video_info)

    def _process_videos_list(self, data):
        videos = []
        for vod in data['data']['list']:
            name = vod['vod_name']
            id = vod['vod_id']
            pic = vod['vod_pic']
            remark = vod.get('vod_remarks', '暂无备注')
            video = {
                "vod_id": id,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remark
                    }
            videos.append(video)
        return videos

    def _fetch_player_data(self, id):
        detail = requests.get(url=f"{xurl}/ys/simple_api.php?action=play&lid={id}", headers=headerx)
        detail.encoding = "utf-8-sig"
        return detail.json()

    def _extract_play_url(self, data):
        return data['data']['url']

    def _build_player_result(self, url):
        result = {}
        result["parse"] = 0
        result["playUrl"] = ''
        result["url"] = url
        result["header"] = headers
        return result

    def playerContent(self, flag, id, vipFlags):
        data = self._fetch_player_data(id)
        url = self._extract_play_url(data)
        return self._build_player_result(url)

    def _fetch_search_data(self, key, page):
        detail = requests.get(url=f"{xurl}/ys/simple_api.php?action=search&keyword={key}&page={str(page)}",headers=headerx)
        detail.encoding = "utf-8-sig"
        return detail.json()

    def _build_search_result(self, videos, pg):
        result = {}
        result['list'] = videos
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def searchContentPage(self, key, quick, pg):
        page = int(pg) if pg else 1
        data = self._fetch_search_data(key, page)
        videos = self._process_videos_list(data)
        return self._build_search_result(videos, pg)

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, '1')

    def localProxy(self, params):
        if params['type'] == "m3u8":
            return self.proxyM3u8(params)
        elif params['type'] == "media":
            return self.proxyMedia(params)
        elif params['type'] == "ts":
            return self.proxyTs(params)
        return None











