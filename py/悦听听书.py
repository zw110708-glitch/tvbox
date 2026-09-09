# coding=utf-8
# !/usr/bin/python

"""

作者 丢丢喵 内容均从互联网收集而来 仅供交流学习使用 严禁用于商业用途 请于24小时内删除
         ====================Diudiumiao====================

"""

from concurrent.futures import ThreadPoolExecutor, as_completed
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

xurl = "http://www.yuetingba.cn"

headerx = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.87 Safari/537.36'
          }

class Spider(Spider):

    def getName(self):
        return "丢丢喵"

    def init(self, extend):
        pass

    def homeVideoContent(self):
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
        doc = self.get_document()
        soups = doc.find_all('ul', class_="nav navbar-nav")
        all_classes = self.parse_classes(soups)
        recommended_item, filtered_classes = self.process_classes(all_classes)
        self.assemble_result(result, recommended_item, filtered_classes)
        return result

    def is_skipped_name(self, name):
        return name in ["首页", "打赏"]

    def process_classes(self, all_classes):
        recommended_item = None
        filtered_classes = []
        for item in all_classes:
            if item["type_name"] == "推荐":
                recommended_item = item
            else:
                filtered_classes.append(item)
        return recommended_item, filtered_classes

    def assemble_result(self, result, recommended_item, filtered_classes):
        if recommended_item:
            result["class"].append(recommended_item)
        result["class"].extend(filtered_classes)

    def categoryContent(self, cid, pg, filter, ext):
        page = self.get_page_number(pg)
        url = self.build_category_url(cid, page)
        doc = self.fetch_category_document(url)
        soups = doc.find_all('div', class_="col-md-9")
        videos = self.extract_videos(soups)
        return self.build_category_result(videos, pg)

    def extract_videos(self, soups):
        videos = []
        for soup in soups:
            for vod in soup.find_all('div', class_="section-box-list-item"):
                videos.append(self.parse_video_data(vod))
        return videos

    def parse_video_data(self, vod):
        name = vod.find('img')['alt']
        ids = vod.find('div', class_="box-list-item-img")
        id = ids.find('a')['href']
        pic = vod.find('img')['src']
        if 'http' not in pic:
            pic = xurl + pic
        return {"vod_id": id,"vod_name": name,"vod_pic": pic}

    def build_category_result(self, videos, pg):
        result = {'list': videos}
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def _get_full_url(self, did):
        if 'http' not in did:
            return f"{xurl}{did}"
        return did

    def _parse_pagination_tasks(self, doc):
        tasks = []
        page_index = 0
        soupss = doc.find_all('ul', class_="nav nav-tabs")
        for item in soupss:
            vodss = item.find_all('a')
            for vo in vodss:
                tasks.append((page_index, vo['href']))
                page_index += 1
        return tasks

    def _extract_episodes_from_soup(self, page_doc, did):
        page_episodes = []
        p_soups = page_doc.find_all('div', class_="ting-list-content row")
        for p_soup in p_soups:
            vods = p_soup.find_all('div', class_="col-md-3")
            for sou in vods:
                try:
                    ids_div = sou.find('div', class_="ting-list-content-item")
                    if not ids_div:
                        continue
                    vid = ids_div['id'].replace('item_', '')
                    names_tag = sou.find('a', {'style': 'overflow: hidden;'})
                    name = names_tag.text.strip()
                    page_episodes.append(f"{name}${vid}@{did}")
                except Exception:
                    continue
        return page_episodes

    def _process_page_task(self, index, href, did):
        try:
            page_url = f"{xurl}{href}"
            resp = requests.get(url=page_url, headers=headerx, timeout=10)
            resp.encoding = "utf-8"
            page_doc = BeautifulSoup(resp.text, "lxml")
            episodes = self._extract_episodes_from_soup(page_doc, did)
            return index, episodes
        except Exception:
            return index, []

    def build_key_str(self, str1, str2):
        key_str = ""
        for i in range(20):
            char_code = ord(str1[i]) + int(str2[i])
            key_str += chr(char_code)
        for i in range(20, len(str1)):
            char_code = ord(str1[i]) + int(str2[i - 20])
            key_str += chr(char_code)
        return key_str

    def build_iv_str(self, str1, str2):
        iv_str = ""
        for i in range(20, 4, -1):
            char_code = ord(str1[i]) + int(str2[i - 1])
            iv_str += chr(char_code)
        return iv_str

    def get_document(self):
        detail = requests.get(url=xurl, headers=headerx)
        detail.encoding = "utf-8"
        return BeautifulSoup(detail.text, "lxml")

    def parse_classes(self, soups):
        all_classes = []
        for soup in soups:
            for vod in soup.find_all('a'):
                name = vod.text.strip()
                if self.is_skipped_name(name):
                    continue
                all_classes.append({"type_id": vod['href'], "type_name": name})
        return all_classes

    def detailContent(self, ids):
        did = ids[0]
        did = self._get_full_url(did)
        try:
            detail = requests.get(url=did, headers=headerx)
            detail.encoding = "utf-8"
            doc = BeautifulSoup(detail.text, "lxml")
            tasks = self._parse_pagination_tasks(doc)
        except Exception:
            return {'list': []}
        final_results = [None] * len(tasks)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(self._process_page_task, t[0], t[1], did) for t in tasks]
            for future in as_completed(futures):
                idx, episodes = future.result()
                final_results[idx] = episodes
        flat_episodes = []
        for page_data in final_results:
            if page_data:
                flat_episodes.extend(page_data)
        bofang = "#".join(flat_episodes)
        return {'list': [{"vod_id": did,"vod_play_from": "悦听专线","vod_play_url": bofang}]}

    def get_page_number(self, pg):
        return int(pg) if pg else 1

    def build_category_url(self, cid, page):
        fenge = cid.split("/")
        return f'{xurl}/{fenge[1]}/{fenge[2]}/{str(page)}'

    def fetch_category_document(self, url):
        detail = requests.get(url=url, headers=headerx)
        detail.encoding = "utf-8"
        return BeautifulSoup(detail.text, "lxml")

    def decrypt_assl(self, encrypted_text):
        key = self.decode_key()
        iv = self.decode_iv()
        ciphertext = self.prepare_ciphertext(encrypted_text)
        decrypted_bytes = self.aes_decrypt(ciphertext, key, iv)
        result_str = decrypted_bytes.decode('utf-8')
        return json.loads(result_str)

    def decode_key(self):
        key_b64 = "le95G3hnFDJsBE+1/v9eYw=="
        return base64.b64decode(key_b64)

    def extract_search_videos(self, soups):
        videos = []
        for soup in soups:
            for vod in soup.find_all('div', class_="section-box-list-item"):
                videos.append(self.parse_search_video(vod))
        return videos

    def parse_search_video(self, vod):
        name = vod.find('img')['alt']
        ids = vod.find('div', class_="box-list-item-img")
        id = ids.find('a')['href']
        pic = vod.find('img')['src']
        if 'http' not in pic:
            pic = xurl + pic
        return {"vod_id": id,"vod_name": name,"vod_pic": pic}

    def aes_decrypt(self, ciphertext, key, iv):
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ciphertext), AES.block_size)

    def find_audio_server(self, server_list, full_book_id):
        short_id = self.extract_short_id(full_book_id)
        matched_server = self.find_matched_server(server_list, short_id)
        if matched_server:
            return self.build_server_url(matched_server)
        return self.get_best_fallback_server(server_list)

    def extract_short_id(self, full_book_id):
        return full_book_id.split('-')[-1] if '-' in full_book_id else full_book_id

    def find_matched_server(self, server_list, short_id):
        for server in server_list:
            supported_ids_str = server.get('BookIds')
            if supported_ids_str:
                supported_ids = supported_ids_str.split(',')
                if short_id in supported_ids:
                    return server
        return None

    def build_server_url(self, server):
        host = server.get('Value')
        port = server.get('Port')
        scheme = server.get('Scheme', 'http')
        return f"{scheme}://{host}:{port}"

    def get_best_fallback_server(self, server_list):
        sorted_servers = self.sort_servers_by_ratio(server_list)
        if sorted_servers:
            return self.build_server_url(sorted_servers[0])
        return None

    def decrypt_efi(self, efi_data, ting_id, creation_time):
        clean_id = self.clean_ting_id(ting_id)
        clean_time = self.clean_creation_time(creation_time)
        gen_key_str, gen_iv_str = self._generate_key_iv(clean_id, clean_time)
        key = gen_key_str.encode('latin-1')
        iv = gen_iv_str.encode('latin-1')
        ciphertext = base64.b64decode(efi_data)
        decrypted_bytes = self.aes_decrypt(ciphertext, key, iv)
        return decrypted_bytes.decode('utf-8')

    def clean_ting_id(self, ting_id):
        return ting_id.replace("-", "")

    def clean_creation_time(self, creation_time):
        clean_time = creation_time.replace("-", "").replace(":", "").replace("T", "").replace(".", "").replace(" ", "")
        return clean_time.ljust(20, '0')

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

    def aes_decrypt(self, ciphertext, key, iv):
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ciphertext), AES.block_size)

    def playerContent(self, flag, id, vipFlags):
        fenge = id.split("@")
        res = self.fetch_detail_page(fenge[1])
        my_book_id = self.extract_middle_text(res, "bookId = '", "'", 0)
        encrypted_assl_text = self.extract_middle_text(res, "assl = '", "'", 0)
        server_data_list = self.decrypt_assl(encrypted_assl_text)
        target_url = self.find_audio_server(server_data_list, my_book_id)
        data = self.fetch_api_data(fenge[0])
        path = self.decrypt_efi(data['efi'], data['id'], data['creationTime'])
        urlsss = f"{target_url}{path}"
        return self.build_player_result(urlsss)

    def fetch_detail_page(self, url):
        detail = requests.get(url=url, headers=headerx)
        detail.encoding = "utf-8"
        return detail.text

    def decode_iv(self):
        iv_b64 = "IvswQFEUdKYf+d1wKpYLTg=="
        return base64.b64decode(iv_b64)

    def prepare_ciphertext(self, encrypted_text):
        clean_text = encrypted_text.strip().replace('\n', '')
        return base64.b64decode(clean_text)

    def fetch_api_data(self, episode_id):
        url = f"{xurl}/api/app/docs-listen/{episode_id}/ting-with-efi"
        detail = requests.get(url=url, headers=headerx)
        detail.encoding = "utf-8"
        return detail.json()

    def build_player_result(self, urlsss):
        result = {}
        result["parse"] = 0
        result["playUrl"] = ''
        result["url"] = urlsss
        result["header"] = headerx
        return result

    def searchContentPage(self, key, quick, pg):
        url = self.build_search_url(key)
        doc = self.fetch_search_document(url)
        soups = doc.find_all('div', class_="col-md-12")
        videos = self.extract_search_videos(soups)
        return self.build_search_result(videos, pg)

    def build_search_url(self, key):
        return f'{xurl}/Search?type=1&name={key}'

    def sort_servers_by_ratio(self, server_list):
        return sorted(
            server_list,
            key=lambda x: int(x.get('Ratio') or -1),
            reverse=True)

    def _generate_key_iv(self, str1, str2):
        key_str = self.build_key_str(str1, str2)
        iv_str = self.build_iv_str(str1, str2)
        return key_str, iv_str

    def fetch_search_document(self, url):
        detail = requests.get(url=url, headers=headerx)
        detail.encoding = "utf-8"
        return BeautifulSoup(detail.text, "lxml")

    def build_search_result(self, videos, pg):
        result = {'list': videos}
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result



