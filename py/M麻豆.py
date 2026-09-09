import json
import re
import sys
import html
from urllib.parse import urlparse

import requests
from pyquery import PyQuery as pq
sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def init(self, extend=""):
        try:
            self.proxies = json.loads(extend)
        except:
            self.proxies = {}
        self.proxy_prefix = 'http://127.0.0.1:10079/p/0/127.0.0.1:10172/'
        self.use_proxy_prefix = bool(self.proxies.get('use_prefix')) if isinstance(self.proxies, dict) else False
        self.base_headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
        }
        self.host = self.get_working_host()
        self.headers = dict(self.base_headers)
        self.headers.update({'Origin': self.host, 'Referer': f"{self.host}/"})
        # 广告域名与关键词
        self.ad_domains = ['pq8dm9','ppq6wb','channelCode','fvb3c7tv','55234795.com','sv333','laosiji']
        self.ad_words = ['同城约炮','迷情春药','广告','推广']
        print(f"使用站点: {self.host}")

    def getName(self):
        return "麻豆传媒适配-修复v11"

    def isVideoFormat(self, url):
        return any(ext in (url or '') for ext in ['.m3u8', '.mp4', '.ts'])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def get_working_host(self):
        dynamic_urls = [
            'https://madou.com'
        ]
        for url in dynamic_urls:
            try:
                response = requests.get(url, headers=self.base_headers, proxies=self.proxies, timeout=10)
                if response.status_code == 200:
                    return url
            except Exception:
                continue
        return dynamic_urls[0]

    def _req(self, url, referer=None):
        h = dict(self.base_headers)
        h.update({'Origin': self.host, 'Referer': referer or url})
        resp = requests.get(url, headers=h, proxies=self.proxies, timeout=15)
        # 使用服务器自动侦测的编码，避免强制 UTF-8 造成标题乱码
        try:
            resp.encoding = resp.apparent_encoding or resp.encoding
        except:
            pass
        return resp

    # —— 文本与片名处理 ——
    def _clean_text(self, s: str) -> str:
        s = html.unescape(s or '')
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _strip_trailing_id(self, s: str) -> str:
        m = re.match(r"^(.*?)-(\d+)$", s)
        if m:
            return m.group(1).strip()
        return s

    def _is_bad_title(self, s: str) -> bool:
        if not s:
            return True
        if ' ' in s:
            return True
        han = len(re.findall(r"[\u4e00-\u9fff]", s))
        if han < 2:
            return True
        return False

    def _maybe_fix_mojibake(self, s: str) -> str:
        try:
            if not s:
                return s
            # 中文字符统计
            han = len(re.findall(r"[\u4e00-\u9fff]", s))
            # 典型 mojibake 特征字符统计
            moj = len(re.findall(r"[éèåæçâêîôûÃ¼Ã©Ã¯Ã±é°»è±]", s))
            # 触发条件：中文很少且疑似字符较多
            if han < 2 and moj >= 2:
                fixed = ''
                try:
                    fixed = s.encode('latin1', 'ignore').decode('utf-8', 'ignore')
                except:
                    fixed = ''
                if fixed:
                    # 纠正后若中文显著增加，则采用纠正值
                    han2 = len(re.findall(r"[\u4e00-\u9fff]", fixed))
                    if han2 > han:
                        return fixed
            return s
        except:
            return s

    def _title_candidates(self, k, a):
        cand = []
        for sel in ['h2', '.entry-title', '.post-title', 'h3.text-truncate', 'h5.gl-text']:
            t = self._clean_text(k(sel).text() or '')
            if t:
                cand.append(self._strip_trailing_id(t))
        if a is not None:
            # aria-label最稳定
            aria = self._clean_text(a.attr('aria-label') or '')
            if aria:
                cand.append(self._strip_trailing_id(aria))
            t = self._clean_text(a.text() or '')
            if t:
                cand.append(self._strip_trailing_id(t))
            for attr in ['title','data-title']:
                t2 = self._clean_text(a.attr(attr) or '')
                if t2:
                    cand.append(self._strip_trailing_id(t2))
        # img alt 兜底
        img = None
        if k('div.item-cover img, .gl-cover img, .tag-cover img').length:
            img = k('div.item-cover img, .gl-cover img, .tag-cover img').eq(0)
        elif k('img').length:
            img = k('img').eq(0)
        if img is not None:
            alt = self._clean_text(img.attr('alt') or '')
            if alt:
                cand.append(self._strip_trailing_id(alt))
        # 区块文本兜底
        itxt = self._clean_text(k('div.item-texts, .gl-infos, .tag-infos').text() or '')
        if itxt:
            cand.append(self._strip_trailing_id(itxt))
        # 去重
        uniq, seen = [], set()
        for s in cand:
            if s and s not in seen:
                uniq.append(s)
                seen.add(s)
        return uniq

    # —— 标题原样获取（不做任何加工） ——
    def _get_title_unified(self, k):
        a = k('a[href^="/archives/"]').eq(0)
        if not a or not a.attr('href'):
            a = k('a').eq(0)
        # 优先 h3.text-truncate（页面可见片名）
        v = k('div.item-texts h3.text-truncate').eq(0).text() or k('h3.text-truncate').eq(0).text()
        if v:
            return v
        # 其次 a.text()
        if a is not None:
            v = a.text()
            if v:
                return v
        # 再次 img[alt]
        v = k('img').attr('alt')
        if v:
            return v
        # 最后 .entry-title/.post-title/h2
        v = k('.entry-title').text() or k('.post-title').text() or k('h2').text()
        if v:
            return v
        return ''

    # —— 首页 / 导航 ——
    def homeContent(self, filter):
        try:
            # 主分类映射（用于将 /topic/0/{id}/ 规范化为 /topic/{code}/{id}/1/）
            main_map = {
                '麻豆AV': '17521',
                '传媒片商': '30521',
                '国产视频': '30526',
                '日本AV': '30522',
                '欧美AV': '30524'
            }

            def norm_topic(href: str, main_code: str) -> str:
                if not href:
                    return ''
                p = href.strip('/').split('/')
                # 支持两种写法：/topic/0/13678/ 与 /topic/17521/13678/1/
                if len(p) >= 4 and p[0] == 'topic' and p[1].isdigit() and p[2].isdigit():
                    # 已是规范：/topic/{code}/{id}/{order}/ → 仅保证以 / 结尾
                    return f"/topic/{p[1]}/{p[2]}/{p[3].strip('/')}/"
                if len(p) >= 3 and p[0] == 'topic' and p[1] == '0' and p[2].isdigit():
                    return f"/topic/{main_code}/{p[2]}/1/"
                # 兜底：保持原值
                return href if href.endswith('/') else href + '/'

            # 解析导航，构建主分类 + 子分类过滤器
            resp = self._req(self.host)
            if resp.status_code != 200:
                return {'class': [], 'filters': {}, 'list': []}
            doc = self.getpq(resp.text)

            classes = []
            filters = {}

            seen_classes = set()
            for nav in doc('nav.pcNav .navItem').items():
                name = self._clean_text(nav('.navBtn').eq(0).text() or '')
                if not name:
                    continue
                if name not in main_map and name not in ['女优列表', '全部标签']:
                    # 只保留指定的五个主类，另外两个特殊入口在后面补充
                    continue
                # 规范化主类ID
                if name in main_map:
                    type_id = f"/topic/{main_map[name]}/0/1/"
                elif name == '女优列表':
                    type_id = '/actresslist/1/'
                else:
                    type_id = '/tag/all/0/'

                key = f"{name}|{type_id}"
                if key in seen_classes:
                    continue
                seen_classes.add(key)
                classes.append({'type_name': name, 'type_id': type_id})

                # 构造子类过滤器（女优、全部标签没有子类）
                if name in main_map:
                    type_filter = {
                        'key': 'type',
                        'name': '类型',
                        'value': []
                    }
                    # “所有”入口
                    type_filter['value'].append({'n': '所有', 'v': f"/topic/{main_map[name]}/0/1/"})
                    # 导航下拉中的子类
                    for a in nav('.dropdownBox a.dropdownItem').items():
                        tname = self._clean_text(a.text() or '')
                        href = a.attr('href') or ''
                        norm = norm_topic(href, main_map[name])
                        if tname and norm:
                            type_filter['value'].append({'n': tname, 'v': norm})
                    # 排序过滤器（参考模板）
                    order_filter = {
                        'key': 'order',
                        'name': '排序',
                        'value': [
                            {'n': '发行日期', 'v': '1'},
                            {'n': '最新更新', 'v': '2'},
                            {'n': '今日浏览', 'v': '3'},
                            {'n': '本周浏览', 'v': '4'},
                            {'n': '本月浏览', 'v': '5'},
                            {'n': '最新发布', 'v': '6'},
                            {'n': '总浏览数', 'v': '7'},
                        ]
                    }
                    filters[type_id] = [order_filter, type_filter]

            # 额外补充两个父分类（无子类）：女优列表、全部标签
            if not any(c['type_name'] == '女优列表' for c in classes):
                classes.append({'type_name': '女优列表', 'type_id': '/actresslist/1/'})
            if not any(c['type_name'] == '全部标签' for c in classes):
                classes.append({'type_name': '全部标签', 'type_id': '/tag/all/0/'})

            # 首页列表（用于展示）
            videos = self.getlist(doc('li.section-content__item, #index article, article'))
            return {'class': classes, 'filters': filters, 'list': videos}
        except Exception:
            return {'class': [], 'filters': {}, 'list': []}

    def homeVideoContent(self):
        try:
            data = self.getpq(self._req(self.host).text)
            return {'list': self.getlist(data('li.section-content__item, #index article, article'))}
        except Exception:
            return {'list': []}

    # —— 搜索（视频） ——
    def searchContent(self, key, quick, pg="1"):
        try:
            from urllib.parse import quote
            kw = quote(key.strip())
            real_pg = int(pg)
            # 新规则：第一页 /searchvideo/{kw}/，第二页 /searchvideo/{kw}/2/，第三页 /searchvideo/{kw}/3/ ...
            url = f"{self.host}/searchvideo/{kw}/" if real_pg == 1 else f"{self.host}/searchvideo/{kw}/{real_pg}/"
            first = f"{self.host}/searchvideo/{kw}/"
            resp = self._req(url, referer=first)
            if resp.status_code != 200:
                # 兜底：不带末尾斜杠
                alt = (f"{self.host}/searchvideo/{kw}/{real_pg}" if real_pg != 1 else first.rstrip('/'))
                resp = self._req(alt, referer=first)
            if resp.status_code != 200:
                return {'list': [], 'page': int(pg), 'pagecount': 1}
            data = self.getpq(resp.text)
            # 解析结果列表（与分类页一致的卡片结构）
            videos = self.getlist(data('ul.section-content li.section-content__item, li.section-content__item'))
            # 仅视频：getlist内部已限制 /archives/ 与过滤广告
            # 根据HTML中的 <link rel="next" href="..."> 判断是否有下一页
            has_next = bool(data('link[rel="next"]').attr('href'))
            pagecount = 99999 if has_next else int(pg)
            return {'list': videos, 'page': int(pg), 'pagecount': pagecount}
        except Exception:
            return {'list': [], 'page': int(pg), 'pagecount': 1}

    # —— 分类页构造 ——
    def _build_category_url(self, base_path, pg):
        if base_path.startswith('/actresslist/'):
            base = '/actresslist/1'
            return f"{self.host}{base}/" if pg == 1 else f"{self.host}{base}/{pg}"
        if base_path.startswith('/tag/all'):
            base = '/tag/all'
            return f"{self.host}{base}/" if pg == 1 else f"{self.host}{base}/{pg}"
        if base_path.startswith('/home'):
            return f"{self.host}/home" if pg == 1 else f"{self.host}/home/{pg}"
        if base_path.startswith('/category/'):
            cat_base = base_path.rstrip('/')
            primary = f"{self.host}{cat_base}/" if pg == 1 else f"{self.host}{cat_base}/{pg}"
            backup = f"{self.host}{cat_base}/0/{pg}/" if pg > 1 else primary
            return primary, backup
        if base_path.startswith('/topic/'):
            topic_base = base_path.rstrip('/')
            primary = f"{self.host}{topic_base}/" if pg == 1 else f"{self.host}{topic_base}/0/{pg}/"
            backup = f"{self.host}{topic_base}/{pg}/" if pg > 1 else primary
            return primary, backup
        base_url = f"{self.host}{base_path}".rstrip('/')
        return (f"{base_url}/" if pg == 1 else f"{base_url}/{pg}/"), None

    def categoryContent(self, tid, pg, filter, extend):
        try:
            # 点击型入口：标签/女优（保留原逻辑）
            if isinstance(tid, str) and tid.startswith('tag_click_'):
                tag_url = tid.replace('tag_click_', '')  # e.g. /tag/34091
                # 页码模式：第一页 /tag/{id}/1/；第二页 /tag/{id}/1/2/；第三页 /tag/{id}/1/3/
                first = f"{self.host}{tag_url}/1/"
                url = first if int(pg) == 1 else f"{self.host}{tag_url}/1/{int(pg)}/"
                resp = self._req(url, referer=first)
                if resp.status_code == 200:
                    data = self.getpq(resp.text)
                    videos = self.getlist(data('ul.section-content li.section-content__item, li.section-content__item, article'))
                    has_next = bool(data('link[rel="next"]').attr('href'))
                    pagecount = (int(pg) + 1) if has_next else int(pg)
                    return {'list': videos, 'page': int(pg), 'pagecount': pagecount, 'limit': 90, 'total': 999999}
                return {'list': [], 'page': int(pg), 'pagecount': 1, 'limit': 90, 'total': 0}

            if isinstance(tid, str) and tid.startswith('actress_click_'):
                actress_url = tid.replace('actress_click_', '')
                url = f"{self.host}{actress_url}" if str(pg) == '1' else (f"{self.host}{actress_url}&page={pg}" if '?' in actress_url else f"{self.host}{actress_url}?page={pg}")
                resp = self._req(url, referer=f"{self.host}{actress_url}")
                if resp.status_code == 200:
                    data = self.getpq(resp.text)
                    videos = self.getlist(data('ul.section-content li.section-content__item, li.section-content__item, article'))
                    has_next = bool(data('link[rel="next"]').attr('href'))
                    pagecount = (int(pg) + 1) if has_next else int(pg)
                    return {'list': videos, 'page': int(pg), 'pagecount': pagecount, 'limit': 90, 'total': 999999}
                return {'list': [], 'page': int(pg), 'pagecount': 1, 'limit': 90, 'total': 0}

            # 支持 extend：{'type': '/topic/17521/13678/1/', 'order': '3'}
            base_path = tid if tid.startswith('/') else f'/{tid}'
            chosen = ''
            order = ''
            if extend and isinstance(extend, dict):
                chosen = extend.get('type', '') or ''
                order = extend.get('order', '') or ''
            # 女优/全部标签入口按原实现
            if base_path.startswith('/actresslist/'):
                return self._get_actress_folders(pg)
            if base_path.startswith('/tag/all'):
                return self._get_tag_folders(pg)

            # 优先以 extend['type'] 为准（来自过滤器选择的子类）
            use_type = chosen or base_path
            p = use_type.strip('/').split('/')
            url = ''
            refer = ''
            if len(p) >= 4 and p[0] == 'topic':
                # /topic/{code}/{id}/{order}/ → 规范拼接分页
                cur_order = order if order else p[3]
                refer = f"{self.host}/topic/{p[1]}/{p[2]}/{cur_order}/"
                url = refer if str(pg) == '1' else f"{refer}{int(pg)}/"
            else:
                # 其他：回退到既有构造器
                built = self._build_category_url(use_type if use_type.startswith('/') else f'/{use_type}', int(pg))
                primary, backup = (built if isinstance(built, tuple) else (built, None))
                refer = primary if int(pg) == 1 else (self._build_category_url(use_type if use_type.startswith('/') else f'/{use_type}', 1)[0] if isinstance(self._build_category_url(use_type if use_type.startswith('/') else f'/{use_type}', 1), tuple) else self._build_category_url(use_type if use_type.startswith('/') else f'/{use_type}', 1))
                url = primary

            resp = self._req(url, referer=refer)
            if resp.status_code != 200 and 'built' in locals() and backup:
                resp = self._req(backup, referer=refer)
            if resp.status_code != 200:
                return {'list': [], 'page': int(pg), 'pagecount': 9999, 'limit': 90, 'total': 0}
            data = self.getpq(resp.text)
            videos = self.getlist(data('li.section-content__item, #archive article, #index article, article'), use_type)
            return {'list': videos, 'page': int(pg), 'pagecount': 9999, 'limit': 90, 'total': 999999}
        except Exception:
            return {'list': [], 'page': int(pg), 'pagecount': 9999, 'limit': 90, 'total': 0}

    def _detect_page_count(self, html_text, current_page):
        try:
            next_pg = int(current_page) + 1
            return 99999 if f"page={next_pg}" in (html_text or '') else int(current_page)
        except:
            return 1

    # —— 一级：生成“folder”型 女优/标签 列表（保留图片） ——
    def _get_tag_folders(self, pg="1"):
        try:
            if int(pg) <= 1:
                url = f"{self.host}/tag/all/1/"
                refer = url
            else:
                url = f"{self.host}/tag/all/{int(pg)}/"
                refer = f"{self.host}/tag/all/{int(pg)-1}/"
            resp = self._req(url, referer=refer)
            if resp.status_code != 200:
                return {'list': [], 'page': int(pg), 'pagecount': int(pg), 'limit': 0, 'total': 0}
            data = self.getpq(resp.text)
            folders = []
            for li in data('ul.section-content.section-tags li.section-content__item.tag-cover').items():
                a = li('a').eq(0)
                href = (a.attr('href') or '').strip()
                name = self._clean_text(li('h2.tag-text').text() or a.text() or li('img').attr('alt') or '')
                vod_pic = ''
                img = li('img').eq(0)
                for attr in ['data-src', 'data-original', 'src']:
                    v = (img.attr(attr) or '').strip()
                    if v and not v.startswith('blob:'):
                        vod_pic = self._proc_url(v)
                        break
                if not href or not name:
                    continue
                base = href.strip('/').split('/')
                tag_base = f"/tag/{base[1]}" if (len(base) >= 2 and base[0] == 'tag') else href
                folders.append({
                    'vod_id': f'tag_click_{tag_base}',
                    'vod_name': name,
                    'vod_pic': vod_pic,
                    'vod_remarks': self._clean_text(li('p.tag-works').text() or '标签分类'),
                    'vod_tag': 'folder',
                    'style': {"type": "rect", "ratio": 1.33}
                })
            # 计算有限页：优先 link[rel=next]，否则解析所有指向 /tag/all/{num}/ 的链接取最大值
            has_next = bool(data('link[rel="next"]').attr('href'))
            if has_next:
                pagecount = int(pg) + 1
            else:
                # 收集所有 href 中的页码
                import re as _re
                max_pg = int(pg)
                for a in data('a').items():
                    href = (a.attr('href') or '').strip()
                    m = _re.search(r"/tag/all/(\d+)/?", href)
                    if m:
                        try:
                            num = int(m.group(1))
                            if num > max_pg:
                                max_pg = num
                        except:
                            pass
                pagecount = max_pg
            return {'list': folders, 'page': int(pg), 'pagecount': pagecount, 'limit': len(folders), 'total': len(folders)}
        except Exception:
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 0, 'total': 0}

    def _get_actress_folders(self, pg="1"):
        try:
            # 支持分页，非第1页不再提前返回
            if str(pg) != "1":
                url_try = f"{self.host}/actresslist/1/{pg}/".rstrip('/')
                resp = self._req(url_try, referer=f"{self.host}/actresslist/1/")
            else:
                url = f"{self.host}/actresslist/1/"
                resp = self._req(url, referer=f"{self.host}/actresslist/1/")
            if resp.status_code != 200:
                return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 0, 'total': 0}
            data = self.getpq(resp.text)
            folders = []
            for li in data('ul.section-content.section-models li.section-content__item.gl-cover').items():
                a = li('a').eq(0)
                href = (a.attr('href') or '').strip()
                name = self._clean_text(li('h5.gl-text').text() or a.text() or li('img').attr('alt') or '')
                vod_pic = ''
                img = li('img').eq(0)
                for attr in ['data-src', 'data-original', 'src']:
                    v = (img.attr(attr) or '').strip()
                    if v and not v.startswith('blob:'):
                        vod_pic = self._proc_url(v)
                        break
                if not href or not name:
                    continue
                base = href.strip('/').split('/')
                actress_base = f"/actressinfo/{base[1]}" if (len(base) >= 2 and base[0] == 'actressinfo') else href
                folders.append({
                    'vod_id': f'actress_click_{actress_base}',
                    'vod_name': name,
                    'vod_pic': vod_pic,
                    'vod_remarks': self._clean_text(li('p.gl-works').text() or '女优分类'),
                    'vod_tag': 'folder',
                    'style': {"type": "rect", "ratio": 1.33}
                })
            # 为兼容影视APP翻页，统一返回一个较大的 pagecount
            return {'list': folders, 'page': int(pg), 'pagecount': 9999, 'limit': len(folders), 'total': len(folders)}
        except Exception:
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 0, 'total': 0}

    # —— 列表解析（统一，去广告与片名修复） ——
    def _is_ad(self, k, a):
        try:
            dt = (a.attr('data-type') or '').strip()
        except:
            dt = (k.attr('data-type') or '').strip()
        href = (a.attr('href') or '') if a else ''
        dlink = (a.attr('data-link') or '') if a else ''
        # 明确广告过滤
        if dt and dt != '0':
            return True
        if href == '/archives/0/':
            return True
        if any(dom in (dlink or '') for dom in self.ad_domains):
            return True
        # 文案包含广告关键词
        text_all = self._clean_text((k.text() or '') + ' ' + (a.text() or ''))
        if any(w in text_all for w in self.ad_words):
            return True
        return False

    def getlist(self, data, tid=''):
        videos = []
        is_folder = '/mrdg' in (tid or '')
        for k in data.items():
            # 锁定主链接（优先 /archives/xx/）
            a = k('a[href^="/archives/"]').eq(0)
            if (not a) or (not a.attr('href')):
                a = k('a').eq(0)
            href = a.attr('href') if a else None
            if not href:
                continue
            # 二级入口允许 /actressinfo/ 与 /tag/；视频详情必须 /archives/
            if not (str(href).startswith('/archives/') or str(href).startswith('/actressinfo/') or str(href).startswith('/tag/')):
                continue
            # 去广告
            if self._is_ad(k, a):
                continue
            # 标题统一原样获取（不做任何加工）
            title = self._maybe_fix_mojibake(self._get_title_unified(k))
            if not title:
                continue
            # 图片
            vod_pic = ''
            img_el = None
            if k('div.item-cover img, .gl-cover img, .tag-cover img').length:
                img_el = k('div.item-cover img, .gl-cover img, .tag-cover img').eq(0)
            elif k('img').length:
                img_el = k('img').eq(0)
            if img_el is not None:
                for attr in ['data-src', 'data-original', 'src']:
                    v = (img_el.attr(attr) or '').strip()
                    if v and not v.startswith('blob:'):
                        vod_pic = self._proc_url(v)
                        break
            if not vod_pic:
                card_html = k.outer_html() if hasattr(k, 'outer_html') else str(k)
                vod_pic = self.getimg(k('script').text(), k, card_html) or ''
            videos.append({
                'vod_id': f"{href}{'@folder' if is_folder else ''}",
                'vod_name': title,
                'vod_pic': vod_pic,
                'vod_remarks': '',
                'vod_tag': 'folder' if is_folder else '',
                'style': {"type": "rect", "ratio": 1.33}
            })
        return videos

    # —— 详情 / 播放 ——
    def _decode_js_string(self, s: str) -> str:
        if not s:
            return s
        s = s.replace('\\/', '/').replace('\\u0026', '&').replace('\u0026', '&')
        return s

    def detailContent(self, ids):
        try:
            id0 = ids[0]
            url = id0 if str(id0).startswith('http') else f"{self.host}{id0}"
            resp = self._req(url, referer=self.host)
            data = self.getpq(resp.text)

            plist = []
            used = set()
            scripts_text = '\n'.join([(k.text() or '') for k in data('script').items()])
            m = re.search(r'const\s+path\s*=\s*"([^"]+)"\s*;', scripts_text)
            if m:
                raw_path = m.group(1)
                video_path = self._decode_js_string(raw_path)
                video_url = f"{self.host}/h5/m3u8/{video_path}" if not video_path.startswith('http') else video_path
                # 标题按参考写法：优先 h1，其次 <title>（去掉网站名分隔｜），最后 h2；原样返回
                title = data('h1').text()
                if not title:
                    title = data('title').text()
                    title = title.split('｜')[0].strip() if title else ''
                if not title:
                    title = data('h2').text()
                title = self._maybe_fix_mojibake(title)
                ep_name = title or '在线播放'
                plist.append(f"{ep_name}${video_url}")

            for c, k in enumerate(data('#dplayer').items(), start=len(plist)+1):
                try:
                    data_url = (k.attr('data-url') or '').strip()
                    if not data_url:
                        continue
                    video_url = data_url if data_url.startswith('http') else f"{self.host}/h5/m3u8/{data_url}"
                    parent = k.parents().eq(0)
                    ep_name = ''
                    for _ in range(4):
                        if not parent:
                            break
                        title = self._clean_text(parent.find('h1, h2, h3').eq(0).text() or '')
                        if title:
                            ep_name = title
                            break
                        parent = parent.parents().eq(0)
                    ep_name = self._maybe_fix_mojibake(ep_name)
                    base = ep_name if ep_name else f"在线播放{c}"
                    name = base
                    i = 2
                    while name in used:
                        name = f"{base} {i}"
                        i += 1
                    used.add(name)
                    plist.append(f"{name}${video_url}")
                except:
                    continue

            for c, k in enumerate(data('.dplayer').items(), start=len(plist)+1):
                try:
                    conf = k.attr('data-config')
                    if not conf:
                        continue
                    js = json.loads(conf)
                    video_url = (js.get('video', {}) or {}).get('url')
                    if not video_url:
                        continue
                    parent = k.parents().eq(0)
                    ep_name = ''
                    for _ in range(4):
                        if not parent:
                            break
                        title = self._clean_text(parent.find('h2, h3, h4').eq(0).text() or '')
                        if title:
                            ep_name = title
                            break
                        parent = parent.parents().eq(0)
                    ep_name = self._maybe_fix_mojibake(ep_name)
                    base = ep_name if ep_name else f"视频{c}"
                    name = base
                    i = 2
                    while name in used:
                        name = f"{base} {i}"
                        i += 1
                    used.add(name)
                    plist.append(f"{name}${video_url}")
                except:
                    continue

            if not plist:
                content_area = data('.post-content, article')
                for i, link in enumerate(content_area('a').items(), start=1):
                    lt = self._clean_text(link.text() or '')
                    href = link.attr('href')
                    if href and any(kw in lt for kw in ['点击观看','观看','播放','视频']):
                        ep = (lt.replace('点击观看：','').replace('点击观看','').strip()) or f"视频{i}"
                        if not str(href).startswith('http'):
                            href = f"{self.host}{href}" if str(href).startswith('/') else f"{self.host}/{href}"
                        plist.append(f"{ep}${href}")

            play_url = '#'.join(plist) if plist else f"未找到视频源${url}"

            # 简介：影片详情介绍 + 标签（过滤广告外链）
            try:
                # 影片详情介绍优先：og:description → 正文摘要
                desc = self._clean_text(data('meta[property="og:description"]').attr('content') or '')
                if not desc:
                    desc = self._clean_text(data('.post-content').text() or data('.entry-content').text() or '')
                # 标签
                tags = []
                for k in data('.tags a, .keywords a, .post-tags a, .tagBox a, .tagBox a.tagItem').items():
                    title = self._clean_text(k.text() or '')
                    href = k.attr('href') or ''
                    if not title or not href:
                        continue
                    if any(dom in href for dom in self.ad_domains):
                        continue
                    target = json.dumps({'id': href, 'name': title}, ensure_ascii=False)
                    tags.append(f"[a=cr:{target}/]{title}[/a]")
                # 标签统一放在前面，不与详情介绍混在一起：先标签后简介
                if tags:
                    vod_content = (' '.join(tags) + ('\n' if desc else '')) + desc
                else:
                    vod_content = desc
                vod_content = vod_content.strip()
                if not vod_content:
                    vod_content = self._clean_text(data('.post-title').text() or data('h1').text() or '') or '麻豆传媒'
            except Exception:
                vod_content = self._clean_text(data('.post-title').text() or data('h1').text() or '') or '麻豆传媒'

            # 详情补充：发行日期、番号、女优（可点击）
            release_date = self._clean_text(data('.text-social span').not_('.eye').eq(0).text() or data('time').text() or '')
            # 从标题或图片alt中尝试抽取番号样式（如 MSD-001、MDL-0011 等）
            source_title = self._clean_text(data('h1').text() or data('title').text() or '')
            mcode = re.search(r'([A-Za-z]{2,}[ -]?\d{3,})', source_title)
            if not mcode:
                alt_any = self._clean_text(data('img').attr('alt') or '')
                mcode = re.search(r'([A-Za-z]{2,}[ -]?\d{3,})', alt_any)
            code = mcode.group(1) if mcode else ''
            # 女优可点击：链接到 /actressinfo/
            actors = []
            for a in data('a[href^="/actressinfo/"]').items():
                name = self._clean_text(a.text() or a('h5.gl-text').text() or '')
                href = a.attr('href') or ''
                if name and href:
                    target = json.dumps({'id': href, 'name': name}, ensure_ascii=False)
                    actors.append(f"[a=cr:{target}/]{name}[/a]")
            vod_actor = ' '.join(actors)

            return {'list': [{'vod_play_from': '麻豆传媒', 'vod_play_url': play_url, 'vod_content': vod_content, 'vod_year': release_date, 'vod_actor': vod_actor, 'vod_remarks': code}]}
        except Exception:
            return {'list': [{'vod_play_from': '麻豆传媒', 'vod_play_url': '获取失败'}]}

    def playerContent(self, flag, id, vipFlags):
        parse = 0 if self.isVideoFormat(id) else 1
        full = id
        if not str(id).startswith('http'):
            full = f"{self.host}{id}" if str(id).startswith('/') else f"{self.host}/{id}"
        url = f"{self.proxy_prefix}{full}"
        return {'parse': parse, 'url': url, 'header': self.headers}

    # —— 图片与辅助 ——
    def getimg(self, text, elem=None, html_content=None):
        if m := re.search(r"loadBannerDirect\('([^']+)'", text or ''):
            return self._proc_url(m.group(1))
        def pick_img_from_elem(el):
            try:
                if hasattr(el, 'is_') and el.is_('img'):
                    for attr in ['data-src', 'data-original', 'src']:
                        v = (el.attr(attr) or '').strip()
                        if v and not v.startswith('blob:'):
                            return v
                for img in el('img').items():
                    for attr in ['data-src', 'data-original', 'src']:
                        v = (img.attr(attr) or '').strip()
                        if v and not v.startswith('blob:'):
                            return v
            except:
                pass
            return ''
        if elem is not None:
            picked = pick_img_from_elem(elem)
            if picked:
                return self._proc_url(picked)
        if html_content is None and elem is not None:
            html_content = elem.outer_html() if hasattr(elem, 'outer_html') else str(elem)
        if not html_content:
            return ''
        html_content = html_content.replace('\u0026quot;', '"').replace('\u0026apos;', "'").replace('\u0026amp;', '&')
        if 'data:image' in html_content:
            m = re.search(r'(data:image/[a-zA-Z0-9+/=;,]+)', html_content)
            if m:
                return self._proc_url(m.group(1))
        m = re.search(r'(https?://[^"\s)]+\.(?:jpg|png|jpeg|webp))', html_content, re.I)
        if m:
            return self._proc_url(m.group(1))
        if 'url(' in html_content:
            m = re.search(r'url\s*\(\s*[\'\"]?([^"\'\)]+)[\'\"]?\s*\)', html_content, re.I)
            if m:
                return self._proc_url(m.group(1))
        return ''

    def _proc_url(self, url):
        if not url:
            return ''
        url = url.strip('\'" ')
        if not url.startswith('http'):
            url = f"{self.host}{url}" if url.startswith('/') else f"{self.host}/{url}"
        if re.search(r"\.(?:jpg|jpeg|png|webp|gif)(?:\?.*)?$", url, re.I) or ('imgwebsa.shzvsh.cn' in url):
            return f"{self.getProxyUrl()}&type=img&url={url}"
        return f"{self.proxy_prefix}{url}"

    def getpq(self, data):
        try:
            return pq(data)
        except:
            return pq(data.encode('utf-8'))

    # 图片解密代理
    def aesimg(self, data: bytes) -> bytes:
        try:
            key = b'2019ysapp7527'
            arr = bytearray(data)
            n = 100 if len(arr) >= 100 else len(arr)
            klen = len(key)
            for i in range(n):
                arr[i] ^= key[i % klen]
            return bytes(arr)
        except:
            return data

    def localProxy(self, param):
        try:
            type_ = param.get('type')
            url = param.get('url')
            if type_ == 'img' and url:
                res = requests.get(url, headers=self.base_headers, proxies=self.proxies, timeout=10)
                content = self.aesimg(res.content)
                ctype = 'image/jpeg'
                if content.startswith(b'\x89PNG'):
                    ctype = 'image/png'
                elif content.startswith(b'GIF8'):
                    ctype = 'image/gif'
                elif content.startswith(b'RIFF') and b'WEBP' in content[8:16]:
                    ctype = 'image/webp'
                elif content.startswith(b'\xff\xd8'):
                    ctype = 'image/jpeg'
                return [200, ctype, content]
            return [404, 'text/plain', b'']
        except:
            return [404, 'text/plain', b'']