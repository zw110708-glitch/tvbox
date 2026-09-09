# coding=utf-8
# !/usr/bin/python

"""

作者 丢丢喵推荐 🚓 内容均从互联网收集而来 仅供交流学习使用 版权归原创者所有 如侵犯了您的权益 请通知作者 将及时删除侵权内容
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

xurl = "https://free-api.bighotwind.cc"

xurl1 = "https://speed.hiknz.com"

headerx = {
    "Authorization": "c979589a-e542-4f75-aaba-28a6a0558c41",
    "User-Agent": "Mozilla/5.0 (Linux; Android 12; 22041211A Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Safari/537.36",
    "UUID": "707c81939662391f",
    "Host": "free-api.bighotwind.cc",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip, deflate"
          }

headers = {
    'User-Agent': 'Linux; Android 12; Pixel 3 XL) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.101 Mobile Safari/537.36'
          }

class Spider(Spider):
    global xurl
    global xurl1
    global headerx
    global headers

    def getName(self):
        return "首页"

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

    def homeContent(self, filter):
        result = {"class": []}

        url = f'{xurl}/papaya/papaya-api/theater/tags'
        detail = requests.get(url=url, headers=headerx)
        detail.encoding = "utf-8"
        data = detail.json()

        for vod in data['data']:

            name = vod['text_val']

            id = vod['id']

            result["class"].append({"type_id": id, "type_name":"" + name})

        return result

    def homeVideoContent(self):
        pass

    def categoryContent(self, cid, pg, filter, ext):
        result = {}
        videos = []

        if pg:
            page = int(pg)
        else:
            page = 1

        url = f'{xurl}/papaya/papaya-api/videos/page?type=5&tagId={cid}&pageNum={str(page)}&pageSize=12'
        detail = requests.get(url=url, headers=headerx)
        detail.encoding = "utf-8"
        data = detail.json()

        for vod in data['list']:

            name = vod['title']

            itemId = vod['itemId']

            videoCode = vod['videoCode']

            content = vod.get('content')
            if not content:
                content = '未知'

            id = str(itemId) + "@" + str(videoCode) + "@" + content

            imageKey = vod['imageKey']

            imageName = vod['imageName']

            pic = f"{xurl1}/papaya/papaya-file/files/download/{imageKey}/{imageName}"

            remark = vod['tags']

            video = {
                "vod_id": id,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": '' + remark
                   }
            videos.append(video)

        result = {'list': videos}
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def detailContent(self, ids):
        did = ids[0]
        result = {}
        videos = []
        xianlu = ''
        bofang = ''

        fenge = did.split("@")

        url = f'{xurl}/papaya/papaya-api/videos/info?videoCode={fenge[1]}&itemId={fenge[0]}'
        detail = requests.get(url=url, headers=headerx)
        detail.encoding = "utf-8"
        data = detail.json()

        url = 'https://m.baidu.com/'
        response = requests.get(url)
        response.encoding = 'utf-8'
        code = response.text
        name = self.extract_middle_text(code, "s1='", "'", 0)
        Jumps = self.extract_middle_text(code, "s2='", "'", 0)

        content = '' + fenge[2]

        if name not in content:
            bofang = Jumps
            xianlu = '1'
        else:
            data = data['data']['episodesList']

            for vod in data:

                fileKey = vod['resolutionList'][0]['fileKey']

                fileName = vod['resolutionList'][0]['fileName']

                id = f'{xurl1}/papaya/papaya-file/files/download/{fileKey}/{fileName}'

                name = vod['episodes']

                bofang = bofang + str(name) + '$' + str(id) + '#'

            bofang = bofang[:-1]

            xianlu = '专线'

        videos.append({
            "vod_id": did,
            "vod_content": content,
            "vod_play_from": xianlu,
            "vod_play_url": bofang
                     })

        result['list'] = videos
        return result

    def playerContent(self, flag, id, vipFlags):

        result = {}
        result["parse"] = 0
        result["playUrl"] = ''
        result["url"] = id
        result["header"] = headers
        return result

    def searchContentPage(self, key, quick, pg):
        result = {}
        videos = []

        if pg:
            page = int(pg)
        else:
            page = 1

        url = f'{xurl}/papaya/papaya-api/videos/page?type=5&search={key}&pageNum={str(page)}&pageSize=12'
        detail = requests.get(url=url, headers=headerx)
        detail.encoding = "utf-8"
        data = detail.json()

        for vod in data['list']:

            name = vod['title']

            itemId = vod['itemId']

            videoCode = vod['videoCode']

            content = vod.get('content')
            if not content:
                content = '未知'

            id = str(itemId) + "@" + str(videoCode) + "@" + content

            imageKey = vod['imageKey']

            imageName = vod['imageName']

            pic = f"{xurl1}/papaya/papaya-file/files/download/{imageKey}/{imageName}"

            remark = vod['tags']

            video = {
                "vod_id": id,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": '' + remark
                    }
            videos.append(video)

        result['list'] = videos
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

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








