# -*- coding: utf-8 -*-
"""
==================================================
@Spider Name : 玩物社区 (WanWuu)
@Author      : 飞鱼
@Description : 玩物社区 wanwuu.com 多内容源
              - 视频 / AI / 成人 / 社区帖子 / 小说 / 视频合集 / 热门标签
              - 播放走 /videos/detail_play 接口（packed JS 解码）
              - 小说按默影视 novel:// 协议返回
              - 详情页补全可点击作者(演员)标签、可点击简介标签、简介/视频介绍
==================================================
"""
import json
import re
import time
import requests
from urllib.parse import quote, quote_plus, unquote, urljoin
from bs4 import BeautifulSoup
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):

    # 预设备用域名池（被墙，靠域名池 + 发布页动态更新）
    DOMAINS = [
        "https://tju.bnmdquasi.cc",
        "https://xmu.ezgdtehh.com",
        "https://xmu.gpcqqmsof.cc",
        "https://thu.bnmdquasi.cc",
        "https://thu.gpcqqmsof.cc",
        "https://jlu.ezgdtehh.com",
        "https://hit.bnmdquasi.cc",
        "https://zju.gpcqqmsof.cc",
        "https://sysu.bnmdquasi.cc",
        "https://wanwuu.com",
    ]

    # 地址发布页
    PUBLISH_PAGES = [
        "https://wanwuu.pages.dev/",
        "https://wanwuu.github.io/",
    ]

    def getName(self):
        return "玩物社区 (作者: 飞鱼)"

    # ============================================================
    # 初始化
    # ============================================================
    def init(self, extend=""):
        config = {}
        site_url = ""
        if isinstance(extend, str) and extend:
            if extend.startswith("http"):
                site_url = extend.rstrip("/")
            else:
                try:
                    config = json.loads(extend)
                except Exception:
                    config = {}
        elif isinstance(extend, dict):
            config = extend

        self.site_url = (config.get("site", "") or site_url).rstrip("/") if (config.get("site") or site_url) else ""

        # ---- 代理三行（由 extend 传，没传就直连）----
        self.plp = config.get("plp", "")
        self.proxy = config.get("proxy", {})

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        # 未指定域名才探测（惰性：init 失败不固化，业务方法里重试）
        if not self.site_url:
            self._gethost()

    # ============================================================
    # 域名探测（惰性，被墙站点代理起来后可刷新恢复）
    # ============================================================
    def _gethost(self):
        if not self.site_url:
            self.site_url = self._get_working_domain()
            if self.site_url:
                self.headers["Referer"] = self.site_url + "/"
        return self.site_url

    def _get_working_domain(self):
        for domain in self.DOMAINS:
            url = domain.rstrip("/")
            if self._test_connectivity(url):
                return url

        for domain in self._fetch_domains_from_publish_pages():
            if domain not in self.DOMAINS:
                self.DOMAINS.append(domain)
            url = domain.rstrip("/")
            if self._test_connectivity(url):
                return url

        return self.DOMAINS[0]

    def _test_connectivity(self, domain):
        try:
            r = self._get(domain + "/videos/new/", timeout=6)
            return bool(r) and r.status_code == 200 and len(r.content) > 500
        except Exception:
            return False

    def _fetch_domains_from_publish_pages(self):
        extracted = []
        for pub_url in self.PUBLISH_PAGES:
            try:
                r = self._get(pub_url, timeout=8)
                if not r:
                    continue
                html = self._text(r)
                if not html:
                    continue

                js_match = re.search(r'src=["\']?(publish\.js[^"\'\s>]*)"\']?', html)
                if js_match:
                    js_url = urljoin(pub_url, js_match.group(1))
                    jr = self._get(js_url, timeout=8)
                    if jr:
                        html += "\n" + self._text(jr)

                for d in re.findall(r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html):
                    d = d.rstrip("/")
                    if ("github.io" not in d and "pages.dev" not in d and d not in extracted):
                        extracted.append(d)
            except Exception:
                continue
        return extracted

    # ============================================================
    # 内部请求（一律走 self.proxy）
    # ============================================================
    def _get(self, url, headers=None, timeout=15):
        h = dict(self.headers)
        if headers:
            h.update(headers)
        return requests.get(url, headers=h, proxies=self.proxy, timeout=timeout, verify=False)

    def _text(self, r):
        try:
            ctype = (r.headers or {}).get("Content-Type", "")
            m = re.search(r'charset\s*=\s*([\w\-]+)', ctype, re.I)
            if m:
                return r.content.decode(m.group(1), errors="ignore")
        except Exception:
            pass
        for enc in ("utf-8", "gb18030"):
            try:
                return r.content.decode(enc)
            except Exception:
                pass
        return r.content.decode("utf-8", "ignore")

    def _fetch_html_safe(self, path_or_url):
        """抓 HTML；失败则换域名重试一次"""
        if not path_or_url.startswith("http"):
            if not path_or_url.startswith("/"):
                path_or_url = "/" + path_or_url
            url = self.site_url + path_or_url
        else:
            url = path_or_url

        html = self._fetch_html(url)
        if html:
            return html

        # 域名失效，切换
        self.site_url = self._get_working_domain()
        self.headers["Referer"] = self.site_url + "/"
        if not path_or_url.startswith("http"):
            url = self.site_url + path_or_url
        return self._fetch_html(url)

    def _fetch_html(self, url):
        try:
            r = self._get(url, timeout=10)
            if not r:
                return ""
            return self._text(r)
        except Exception:
            return ""

    # ============================================================
    # packed JS 解码（Dean Edwards Packer，base36 覆盖关键字段即可）
    # ============================================================
    def _packer_token(self, c, base):
        """对应 Dean Edwards Packer 的 e(c) 函数，支持 base36/62"""
        head = "" if c < base else self._packer_token(c // base, base)
        rem = c % base
        if rem > 35:
            return head + chr(rem + 29)
        return head + "0123456789abcdefghijklmnopqrstuvwxyz"[rem]

    def _unescape_js_string(self, s):
        result = []
        i = 0
        while i < len(s):
            if s[i] == "\\" and i + 1 < len(s):
                nxt = s[i + 1]
                if nxt == "n":
                    result.append("\n")
                elif nxt == "r":
                    result.append("\r")
                elif nxt == "t":
                    result.append("\t")
                elif nxt == "\\":
                    result.append("\\")
                elif nxt == '"':
                    result.append('"')
                elif nxt == "'":
                    result.append("'")
                elif nxt == "/":
                    result.append("/")
                elif nxt == "b":
                    result.append("\b")
                elif nxt == "f":
                    result.append("\f")
                elif nxt == "x" and i + 3 < len(s):
                    try:
                        result.append(chr(int(s[i + 2:i + 4], 16)))
                        i += 2
                    except Exception:
                        result.append(s[i:i + 2])
                elif nxt == "u" and i + 5 < len(s):
                    try:
                        result.append(chr(int(s[i + 2:i + 6], 16)))
                        i += 4
                    except Exception:
                        result.append(s[i:i + 2])
                else:
                    result.append(nxt)
                i += 2
            else:
                result.append(s[i])
                i += 1
        return "".join(result)

    def _decode_packed_js(self, js):
        if not js:
            return None

        words = None
        for pat in (r"'([^']{20,})'\.split\('\|'\)", r'"([^"]{20,})"\.split\("\|"\)'):
            m = re.search(pat, js)
            if m:
                words = m.group(1).split("|")
                if len(words) >= 5:
                    break
        if not words:
            return None

        tm = re.search(r"\}\('(.*?)',(\d+),(\d+),", js, re.S) or re.search(r'\}\("(.*?)",(\d+),(\d+),', js, re.S)
        if not tm:
            return None

        template = self._unescape_js_string(tm.group(1))
        # detail_play 返回的 packed JS 是两层转义，反转义后再清理残留
        template = template.replace("\\\\", "\\").replace('\\"', '"').replace("\\'", "'")
        base = int(tm.group(2))
        for c in range(len(words) - 1, -1, -1):
            if words[c]:
                token = self._packer_token(c, base)
                template = re.sub(r"\b" + re.escape(token) + r"\b", words[c], template)
        return template

    # ============================================================
    # 播放地址解析（/videos/detail_play 新接口）
    # ============================================================
    def _extract_play_params(self, html):
        """从详情页 packed JS 提取 detail_play 所需参数"""
        if not html:
            return None
        for script in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S):
            if "split(" not in script:
                continue
            decoded = self._decode_packed_js(script)
            if not decoded or "detail_play" not in decoded:
                continue
            m_id = re.search(r'detail_play\?id=(\d+)', decoded)
            m_u = re.search(r'encodeURIComponent\("([^"]+)"\)', decoded)
            if not m_id or not m_u:
                continue
            m_img = re.search(r'[?&]img=([^&"]+)', decoded)
            m_ads = re.search(r'[?&]ads=([^&"]+)', decoded)
            return {
                "id": m_id.group(1),
                "u": m_u.group(1),
                "img": m_img.group(1) if m_img else "",
                "ads": m_ads.group(1) if m_ads else "",
            }
        return None

    def _fetch_play_url(self, html, page_url=""):
        """请求 detail_play 接口，解码返回真实 m3u8"""
        params = self._extract_play_params(html)
        if not params:
            return ""

        t = str(int(time.time() / 1800))
        api = "%s/videos/detail_play?id=%s&img=%s&ads=%s&u=%s&t=%s" % (
            self.site_url,
            params["id"],
            params["img"],
            params["ads"],
            quote(params["u"], safe=""),
            t,
        )
        ref = page_url if page_url.startswith("http") else self.site_url + page_url
        try:
            r = self._get(api, headers={"Referer": ref}, timeout=10)
            body = self._text(r) if r else ""
            if not body:
                return ""
            decoded = self._decode_packed_js(body)
            search = decoded or body
            m = re.search(r'data-url="([^"]+)"', search)
            if m:
                return m.group(1).replace("&amp;", "&")
        except Exception:
            pass
        return ""

    # ============================================================
    # 首页
    # ============================================================
    def homeContent(self, filter):
        result = {}
        classes = [
            {"type_id": "discover_all", "type_name": "发现"},
            {"type_id": "videos_zhibo", "type_name": "视频"},
            {"type_id": "ai_all", "type_name": "AI短剧"},
            {"type_id": "porn_all", "type_name": "成人视频"},
            {"type_id": "posts_all", "type_name": "玩物社区"},
            {"type_id": "novels_new", "type_name": "SM小说", "type": "list", "ratio": 1.1},
            {"type_id": "moviesets", "type_name": "视频合集"},
            {"type_id": "hot", "type_name": "热门标签", "type": "list", "ratio": 1.1},
        ]
        filters = {
            "discover_all": [
                {
                    "key": "cate", "name": "筛选",
                    "value": [
                        {"n": "正在播放", "v": "/videos/watchings/"},
                        {"n": "当前最热", "v": "/videos/popular/"},
                        {"n": "最近更新", "v": "/videos/new/"},
                        {"n": "本月最热", "v": "/videos/mon/"},
                        {"n": "10分钟以上", "v": "/videos/10min/"},
                        {"n": "20分钟以上", "v": "/videos/20min/"},
                        {"n": "本月收藏", "v": "/videos/collect/"},
                        {"n": "高清", "v": "/videos/hd/"},
                        {"n": "每月最热", "v": "/videos/every/"},
                        {"n": "本月讨论", "v": "/videos/current/"},
                        {"n": "收藏最多", "v": "/videos/most/"},
                    ],
                }
            ],
            "videos_zhibo": [
                {
                    "key": "cate", "name": "分类",
                    "value": [
                        {"n": "全部视频", "v": "/videos/new/"},
                        {"n": "直播回放", "v": "/videos/zhibo-huifang/"},
                        {"n": "国产sm", "v": "/videos/guochan-sm/"},
                        {"n": "日韩sm", "v": "/videos/rihan-sm/"},
                        {"n": "欧美sm", "v": "/videos/oumei-sm/"},
                        {"n": "动漫sm", "v": "/videos/dongman-sm/"},
                        {"n": "调教av", "v": "/videos/tiaojiao-av/"},
                    ],
                }
            ],
            "ai_all": [
                {
                    "key": "cate", "name": "分类",
                    "value": [
                        {"n": "全部", "v": "/ai/all/"},
                        {"n": "AI成人短剧", "v": "/ai/ai-duanju/"},
                        {"n": "AI漫剧", "v": "/ai/ai-manju/"},
                        {"n": "AI换脸", "v": "/ai/ai-huanlian/"},
                        {"n": "AI美女", "v": "/ai/ai-meinv/"},
                    ],
                }
            ],
            "porn_all": [
                {
                    "key": "cate", "name": "分类",
                    "value": [
                        {"n": "全部", "v": "/porn/all/"},
                        {"n": "日韩AV", "v": "/porn/rihan-av/"},
                        {"n": "欧美无码", "v": "/porn/oumei-wuma/"},
                        {"n": "国产探花", "v": "/porn/guochan-tanhua/"},
                        {"n": "黑人专区", "v": "/porn/heiren-zhuanqu/"},
                        {"n": "绿帽淫妻", "v": "/porn/lvmao-yinqi/"},
                        {"n": "黑料吃瓜", "v": "/porn/chigua-baoliao/"},
                    ],
                }
            ],
            "posts_all": [
                {
                    "key": "cate", "name": "分类",
                    "value": [
                        {"n": "全部", "v": "/posts/all/"},
                        {"n": "玩物畅聊", "v": "/posts/wanwu-changliao/"},
                        {"n": "恋足原创", "v": "/posts/lianzu-yuanchuang/"},
                        {"n": "抖M天堂", "v": "/posts/doum-tiantang/"},
                        {"n": "女王天地", "v": "/posts/nvwang-tiandi/"},
                    ],
                }
            ],
            "novels_new": [
                {
                    "key": "cate", "name": "排序",
                    "value": [
                        {"n": "最新", "v": "/novels/new/"},
                        {"n": "精华", "v": "/novels/popular/"},
                        {"n": "热门", "v": "/novels/hot/"},
                    ],
                }
            ],
            "moviesets": [
                {
                    "key": "cate", "name": "分类",
                    "value": [
                        {"n": "热度优先", "v": "/moviesets/"},
                        {"n": "AI成人短剧", "v": "/moviesets/?cate=ai-duanju"},
                        {"n": "热门合集", "v": "/moviesets/?cate=rmfl"},
                        {"n": "女王合集", "v": "/moviesets/?cate=nwhj"},
                    ],
                }
            ],
            "hot": [
                {
                    "key": "cate", "name": "排序",
                    "value": [
                        {"n": "默认", "v": "/hot/"},
                        {"n": "本周", "v": "/hot/week/"},
                        {"n": "本月", "v": "/hot/month/"},
                        {"n": "近3月", "v": "/hot/90d/"},
                    ],
                }
            ],
        }
        result["class"] = classes
        result["filters"] = filters
        result["list"] = self.homeVideoContent().get("list", [])
        return result

    def homeVideoContent(self):
        html = self._fetch_html_safe("/videos/popular/")
        return {"list": self._parse_video_list(html)}

    # ============================================================
    # 分类列表
    # ============================================================
    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        page = int(pg) if pg else 1

        path_map = {
            "discover_all": "/videos/watchings/",
            "videos_zhibo": "/videos/new/",
            "ai_all": "/ai/all/",
            "porn_all": "/porn/all/",
            "posts_all": "/posts/all/",
            "novels_new": "/novels/new/",
            "moviesets": "/moviesets/",
            "hot": "/hot/",
        }

        target = str(tid)
        if extend and isinstance(extend, dict) and extend.get("cate"):
            # 仅当 tid 是大类 type_id（裸名，不含 /）时才用筛选 cate 覆盖；
            # folder 点击时 tid 是 URL 路径（如 /moviesets/baiwa/），不能被 cate 覆盖
            if not target.startswith("/") and not target.startswith("http"):
                target = extend["cate"]
        elif target in path_map:
            target = path_map[target]

        # 拼 URL（moviesets 子分类带 ?cate=，分页格式为 /page/N/?cate=xx）
        if target.startswith("http"):
            base, query = (target.split("?", 1) + [""])[:2]
            if page > 1:
                path = "%s/page/%d/%s" % (base.rstrip("/"), page, ("?" + query if query else ""))
            else:
                path = target
            clean_path = base
        else:
            if not target.startswith("/"):
                target = "/" + target
            base, query = (target.split("?", 1) + [""])[:2]
            clean_path = base.rstrip("/")
            if page > 1:
                path = "%s/page/%d/%s" % (clean_path, page, ("?" + query if query else ""))
            else:
                path = target

        html = self._fetch_html_safe(path)

        # 路由到对应解析
        if str(tid) == "hot" or "/hot" in clean_path:
            items = self._parse_hot_tags(html)
        elif str(tid) == "moviesets" and not re.search(r"/moviesets/[^/]+/?$", clean_path):
            items = self._parse_movieset_list(html)
        elif re.search(r"/moviesets/[^/]+/?$", clean_path):
            items = self._parse_movieset_detail_videos(html)
        elif "/novels/" in clean_path:
            items = self._parse_novel_list(html)
        elif "/posts/" in clean_path:
            items = self._parse_post_list(html)
        else:
            items = self._parse_video_list(html)

        result["page"] = page
        result["pagecount"] = page + 1 if len(items) > 0 else page
        result["limit"] = len(items)
        result["total"] = 999
        result["list"] = items
        return result

    # ============================================================
    # 详情页
    # ============================================================
    def detailContent(self, array):
        if not array:
            return {"list": []}
        vod_id = array[0]
        html = self._fetch_html_safe(vod_id)
        if not html:
            return {"list": []}

        soup = BeautifulSoup(html, "html.parser")

        # ---------- 小说 / 社区帖子详情（图文，novel:// 规则） ----------
        if "/novels/" in vod_id or "/posts/" in vod_id:
            return {"list": [self._parse_article_detail(vod_id, soup)]}

        # ---------- 视频详情 ----------
        title_el = soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else "未知标题"

        raw_pic = self._extract_pic_from_soup(soup)
        pic = self._format_pic_url(raw_pic)

        # 可点击作者（演员）标签
        vod_actor = ""
        author_el = soup.select_one('a[href*="/publicvideo/"]')
        if author_el:
            author_name = author_el.get_text(strip=True)
            author_href = author_el.get("href", "")
            if author_name and author_href:
                vod_actor = self._cr(author_href, author_name)

        # 简介可点击标签：只取简介区 ul.mt-3.flex.flex-wrap 容器内的标签（避免抓到推荐区/底部重复标签）
        tag_items = []
        seen_tags = set()
        tag_ul = soup.select_one('ul.mt-3.flex.flex-wrap')
        if tag_ul:
            for t in tag_ul.select('a[href*="/videos/search/"]'):
                name = t.get_text(strip=True)
                href = t.get("href", "")
                if name and href and name not in seen_tags:
                    seen_tags.add(name)
                    tag_items.append(self._cr(href, name))
        tag_text = " ".join(tag_items)

        # 简介 / 视频介绍
        intro = ""
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            intro = og_desc["content"].strip()

        # 时长（ISO8601 转中文）
        duration = self._extract_duration(html)

        # 播放地址（detail_play 链路）
        play_url = self._fetch_play_url(html, page_url=vod_id)

        # 标签放前面、视频介绍放后面
        content_parts = []
        if tag_text:
            content_parts.append(tag_text)
        if intro:
            content_parts.append(intro)
        vod_content = "\n".join(content_parts)

        # 副标题：只放时长（作者已入 vod_actor，标签/简介已入 vod_content，铁律要求 remarks 尽量空）
        vod_remarks = duration if duration else ""

        vod = {
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_actor": vod_actor,
            "vod_content": vod_content,
            "vod_remarks": vod_remarks,
            "vod_play_from": "玩物社区",
            "vod_play_url": "播放$" + (play_url if play_url else vod_id),
        }
        return {"list": [vod]}

    def _parse_article_detail(self, vod_id, soup):
        """小说 / 帖子详情：标题 + 作者 + 日期 + 正文，供 novel:// 播放"""
        is_novel = "/novels/" in vod_id
        title_el = soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else "未知标题"

        raw_pic = self._extract_pic_from_soup(soup)
        pic = self._format_pic_url(raw_pic)

        # 作者 / 日期（小说 .dx-text 里 #author / #time 图标后；帖子用 og 发布时间）
        author = ""
        date_text = ""
        meta = soup.select_one(".dx-text")
        if meta:
            for div in meta.find_all("div"):
                txt = div.get_text(strip=True)
                if not txt:
                    continue
                if div.find("use", href=re.compile("author")):
                    author = txt
                elif div.find("use", href=re.compile("time")):
                    date_text = txt

        # 帖子/兜底：og 发布时间
        if not date_text:
            og_time = soup.find("meta", property="article:published_time")
            if og_time and og_time.get("content"):
                date_text = og_time["content"].strip()[:10]

        # 清理纯分隔符垃圾值
        if author in ("•", "·", "-", "|", "/", "—"):
            author = ""
        if date_text in ("•", "·", "-", "|", "/", "—"):
            date_text = ""

        # 正文（markdown-body 的段落）
        article = soup.select_one("article.markdown-body") or soup.select_one("article")
        paragraphs = []
        if article:
            paragraphs = [p.get_text(strip=True) for p in article.find_all("p") if p.get_text(strip=True)]
        content = "\n\n".join(paragraphs) if paragraphs else (article.get_text("\n", strip=True) if article else "")

        remarks = "小说" if is_novel else "帖子"
        if author:
            remarks = "作者:" + author
        if date_text:
            remarks += " · " + date_text

        vod = {
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_actor": author,
            "vod_content": content[:500],
            "vod_remarks": remarks,
            "vod_play_from": "小说" if is_novel else "帖子",
            "vod_play_url": "全文$" + vod_id,
        }
        return vod

    def _extract_duration(self, html):
        m = re.search(r'"duration"\s*:\s*"PT(\d+)H(\d+)M(\d+)S"', html)
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if h > 0:
                return "%d:%02d:%02d" % (h, mi, s)
            return "%d:%02d" % (mi, s)
        return ""

    # ============================================================
    # 搜索
    # ============================================================
    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        clean_key = quote(key)
        if page > 1:
            path = "/videos/search/%s/page/%d/" % (clean_key, page)
        else:
            path = "/videos/search/%s/" % clean_key
        html = self._fetch_html_safe(path)
        return {"list": self._parse_video_list(html)}

    # ============================================================
    # 播放
    # ============================================================
    def playerContent(self, flag, id, vipFlags):
        play_headers = {
            "User-Agent": self.headers["User-Agent"],
            "Referer": self.site_url + "/",
        }

        # 小说 / 帖子：novel:// 协议（默影视阅读器）
        if "/novels/" in id or "/posts/" in id:
            html = self._fetch_html_safe(id)
            if html:
                soup = BeautifulSoup(html, "html.parser")
                title_el = soup.select_one("h1")
                title = title_el.get_text(strip=True) if title_el else "小说"
                article = soup.select_one("article.markdown-body") or soup.select_one("article")
                paragraphs = []
                if article:
                    paragraphs = [p.get_text(strip=True) for p in article.find_all("p") if p.get_text(strip=True)]
                content = "\n\n".join(paragraphs)
                if not content and article:
                    content = article.get_text("\n", strip=True)
                if content:
                    return {
                        "parse": 0,
                        "playUrl": "",
                        "url": "novel://" + json.dumps({"title": title, "content": content}, ensure_ascii=False),
                        "header": "",
                    }

        # 直链 m3u8/mp4
        if id.endswith(".m3u8") or id.endswith(".mp4") or ".m3u8?" in id or ".mp4?" in id:
            return {"parse": 0, "url": self.plp + id, "header": play_headers}

        # 详情页 URL → 重新解析播放地址
        if "/videos/" in id or "/ai/" in id or "/porn/" in id or "/posts/" in id:
            html = self._fetch_html_safe(id)
            if html:
                real_url = self._fetch_play_url(html, page_url=id)
                if real_url:
                    return {"parse": 0, "url": self.plp + real_url, "header": play_headers}

        return {"parse": 1, "url": id, "header": play_headers}

    # ============================================================
    # 列表解析
    # ============================================================
    def _parse_video_list(self, html):
        videos = []
        if not html:
            return videos
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("li.group")
        if not items:
            items = soup.select("li, div.video-item")
        seen = set()

        for item in items:
            a_tag = item.find("a", href=re.compile(r"^/videos/.*vd-"))
            if not a_tag:
                continue
            vod_id = self._clean_vod_id(a_tag.get("href", ""))
            if not vod_id or vod_id in seen or "/search/" in vod_id:
                continue

            img_tag = item.find("img")
            vod_name = ""
            if img_tag and img_tag.get("alt"):
                vod_name = img_tag.get("alt").strip()
            if not vod_name:
                title_el = item.select_one("a.line-clamp-2, a.line-clamp-1, .line-clamp-2, .line-clamp-1, h2, h3, .title")
                vod_name = title_el.get_text(strip=True) if title_el else ""

            raw_pic = self._extract_pic_from_node(item)
            vod_pic = self._format_pic_url(raw_pic)

            vod_remarks = self._extract_video_remarks(item)

            if vod_id and vod_name:
                seen.add(vod_id)
                videos.append({
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                    "vod_pic": vod_pic,
                    "vod_remarks": vod_remarks,
                })
        return videos

    def _parse_novel_list(self, html):
        novels = []
        if not html:
            return novels
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("article, li, div.card, div.novel-item")
        seen = set()
        exclude = ("/novels", "/novels/new", "/novels/popular", "/novels/hot")

        for item in items:
            a_tag = item.find("a", href=re.compile(r"^/novels/"))
            if not a_tag:
                continue
            vod_id = self._clean_vod_id(a_tag.get("href", ""))
            if not vod_id or vod_id in seen or vod_id.rstrip("/") in exclude or "/cate/" in vod_id:
                continue

            vod_name = a_tag.get("title") or ""
            if not vod_name:
                title_el = item.select_one("h2.dx-title, h2, h3, .title")
                vod_name = title_el.get_text(strip=True) if title_el else ""

            raw_pic = self._extract_pic_from_node(item)
            vod_pic = self._format_pic_url(raw_pic)

            if vod_id and vod_name:
                seen.add(vod_id)
                novels.append({
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                    "vod_pic": vod_pic,
                    "vod_remarks": "小说",
                })
        return novels

    def _parse_post_list(self, html):
        posts = []
        if not html:
            return posts
        soup = BeautifulSoup(html, "html.parser")
        # 帖子详情链接包裹在 article 外层：<li><a href="/posts/xxx/"><article class="post-item">...
        items = soup.select('a[href^="/posts/"]')
        seen = set()
        excluded = {
            "/posts", "/posts/all", "/posts/all/",
            "/posts/wanwu-changliao", "/posts/wanwu-changliao/",
            "/posts/lianzu-yuanchuang", "/posts/lianzu-yuanchuang/",
            "/posts/doum-tiantang", "/posts/doum-tiantang/",
            "/posts/nvwang-tiandi", "/posts/nvwang-tiandi/",
        }

        for a_tag in items:
            href = a_tag.get("href", "").strip()
            clean_href = href.rstrip("/")
            if clean_href in excluded:
                continue

            vod_id = self._clean_vod_id(href)
            if not vod_id or vod_id in seen:
                continue

            title_el = a_tag.select_one(".post-item-title, h2, h3, .title")
            vod_name = title_el.get_text(strip=True) if title_el else ""
            if not vod_name or len(vod_name) < 2:
                continue

            poster = a_tag.select_one(".post-item-poster, [data-src]")
            raw_pic = poster.get("data-src") if poster else ""
            vod_pic = self._format_pic_url(raw_pic)

            desc_el = a_tag.select_one(".post-item-desc")
            vod_remarks = desc_el.get_text(" ", strip=True) if desc_el else "社区帖子"

            seen.add(vod_id)
            posts.append({
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_remarks": vod_remarks,
            })
        return posts

    def _parse_movieset_list(self, html):
        sets = []
        if not html:
            return sets
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("ul.fc-albums-grid > li, li, div.album-item")
        seen = set()

        for item in items:
            a_tag = item.find("a", href=re.compile(r"^/moviesets/"))
            if not a_tag:
                continue
            vod_id = self._clean_vod_id(a_tag.get("href", ""))
            if not vod_id or vod_id in seen or vod_id.rstrip("/") == "/moviesets":
                continue

            img_tag = item.find("img")
            vod_name = ""
            if img_tag and img_tag.get("alt"):
                vod_name = img_tag.get("alt").strip()
            if not vod_name:
                p_title = item.select_one("p.line-clamp-2, .title, h3, h2")
                vod_name = p_title.get_text(strip=True) if p_title else ""

            raw_pic = self._extract_pic_from_node(item)
            vod_pic = self._format_pic_url(raw_pic)

            count_tag = item.select_one("span.rounded-full, .badge, .count")
            vod_remarks = count_tag.get_text(strip=True) if count_tag else "合集"

            if vod_id and vod_name:
                seen.add(vod_id)
                sets.append({
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                    "vod_pic": vod_pic,
                    "vod_remarks": vod_remarks,
                    "vod_tag": "folder",
                })
        return sets

    def _parse_movieset_detail_videos(self, html):
        videos = []
        if not html:
            return videos
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("li.group, li, div.video-item")
        seen = set()

        for item in items:
            a_tag = item.find("a", href=re.compile(r"^/videos/.*vd-"))
            if not a_tag:
                continue
            # 专辑页视频卡片是裸 <li>，会混入搜索历史等无封面项，用 img 过滤
            if not item.find("img"):
                continue
            vod_id = self._clean_vod_id(a_tag.get("href", ""))
            if not vod_id or vod_id in seen:
                continue

            img_tag = item.find("img")
            vod_name = ""
            if img_tag and img_tag.get("alt"):
                vod_name = img_tag.get("alt").strip()
            if not vod_name:
                title_el = item.select_one(".line-clamp-2, .line-clamp-1, h2, h3, .title")
                vod_name = title_el.get_text(strip=True) if title_el else ""

            raw_pic = self._extract_pic_from_node(item)
            vod_pic = self._format_pic_url(raw_pic)
            vod_remarks = self._extract_video_remarks(item)

            if vod_id and vod_name:
                seen.add(vod_id)
                videos.append({
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                    "vod_pic": vod_pic,
                    "vod_remarks": vod_remarks,
                })
        return videos

    def _parse_hot_tags(self, html):
        tags = []
        if not html:
            return tags
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select('a[href*="/search/"], a[href*="/tags/"], .tag-list a, .tag-cloud a')
        seen = set()

        for item in items:
            href = item.get("href", "").strip()
            vod_id = self._clean_vod_id(href)
            if not vod_id or vod_id in seen:
                continue
            tag_name = item.get_text(strip=True)
            if not tag_name or len(tag_name) < 2:
                continue
            vod_name = tag_name.lstrip("#").strip()
            if not vod_name:
                continue

            seen.add(vod_id)
            tags.append({
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": "",
                "vod_remarks": "热门标签",
                "vod_tag": "folder",
            })
        return tags

    def _extract_video_remarks(self, item):
        """时长作为主要副标题，角标/分类紧随其后"""
        time_text = ""
        badge_tags = []

        duration_el = item.select_one('div[class*="bottom-0"] div, .duration, .time, .opacity-50')
        if duration_el:
            time_text = duration_el.get_text(strip=True)

        if not time_text or not re.search(r"\d+:\d+", time_text):
            m = re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", item.get_text())
            if m:
                time_text = m.group(0)

        badge_el = item.select_one('div[class*="top-0"], div[class*="absolute"][class*="left-0"], .badge, .label')
        if badge_el:
            text = badge_el.get_text(strip=True)
            if text and len(text) <= 8 and text != time_text:
                badge_tags.append(text)

        sub_a_tags = item.select(".dx-subtitle a, div[class*='subtitle'] a, a[href*='/search/']")
        for a in sub_a_tags:
            t = a.get_text(strip=True)
            if t and t != time_text and t not in badge_tags:
                badge_tags.append(t)
            if len(badge_tags) >= 2:
                break

        result_parts = []
        if time_text:
            result_parts.append(time_text)
        result_parts.extend(badge_tags)

        if result_parts:
            return " | ".join(result_parts)
        return "HD"

    # ============================================================
    # 工具：可点击标签 / vod_id / 图片
    # ============================================================
    def _cr(self, href, name):
        return '[a=cr:%s/]%s[/a]' % (json.dumps({"id": href, "name": name}, ensure_ascii=False), name)

    def _clean_vod_id(self, href):
        if not href:
            return ""
        href = href.strip()
        for d in self.DOMAINS:
            if href.startswith(d):
                href = href[len(d):]
                break
        return href

    def _extract_pic_from_node(self, node):
        data_node = node.select_one("[data-src], [data-original]")
        if data_node:
            val = data_node.get("data-src") or data_node.get("data-original")
            if val and "loading" not in val:
                return val.strip()

        img_tag = node.find("img")
        if img_tag:
            for attr in ("data-src", "data-original", "data-lazy-src", "src"):
                val = img_tag.get(attr, "").strip()
                if val and "poster_loading" not in val and "loading.svg" not in val:
                    return val

        bg_node = node.select_one('[style*="background-image"]')
        if bg_node:
            m = re.search(r'url\(["\']?([^"\']+)["\']?\)', bg_node.get("style", ""))
            if m:
                return m.group(1).strip()
        return ""

    def _extract_pic_from_soup(self, soup):
        poster_el = soup.select_one(".post-item-poster, [data-src]")
        if poster_el:
            val = poster_el.get("data-src") or poster_el.get("src") or ""
            if val and "poster_loading" not in val:
                return val
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            return og_image["content"]
        return ""

    def _format_pic_url(self, raw_pic_url):
        if not raw_pic_url:
            return ""
        raw_pic_url = raw_pic_url.strip()
        if raw_pic_url.startswith("//"):
            raw_pic_url = "https:" + raw_pic_url
        elif raw_pic_url.startswith("/"):
            raw_pic_url = self.site_url + raw_pic_url

        proxy_base = self.getProxyUrl()
        if proxy_base:
            return proxy_base + "&action=pic&url=" + quote_plus(raw_pic_url)
        return raw_pic_url + "@Referer=" + self.site_url + "/"

    # ============================================================
    # 图片本地代理（解密 / 防盗链）
    # ============================================================
    def localProxy(self, param):
        raw_url = param.get("url") or param.get("pic") or ""
        if not raw_url:
            return [404, "text/plain", b"Missing URL Parameter"]

        url = unquote(raw_url)
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = self.site_url + url

        img_headers = {
            "User-Agent": self.headers["User-Agent"],
            "Referer": self.site_url + "/",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        }
        try:
            r = self._get(url, headers=img_headers, timeout=15)
            content = r.content if r else b""
            if not content or len(content) < 100:
                return [404, "text/plain", b"Image too small or blocked"]

            if self._is_valid_image_header(content):
                return [200, self._detect_image_type(content), content]

            decrypted = self._try_aes_decrypt(content)
            if decrypted and self._is_valid_image_header(decrypted):
                return [200, self._detect_image_type(decrypted), decrypted]

            fixed = self._try_fix_image(content)
            if fixed and self._is_valid_image_header(fixed):
                return [200, self._detect_image_type(fixed), fixed]

            return [200, "application/octet-stream", content]
        except Exception:
            return [500, "text/plain", b"Proxy Error"]

    def _detect_image_type(self, data):
        if not data or len(data) < 12:
            return "application/octet-stream"
        if data[:4] == b"\x89PNG":
            return "image/png"
        if data[:2] == b"\xff\xd8":
            return "image/jpeg"
        if data[:4] == b"RIFF" and len(data) > 12 and data[8:12] == b"WEBP":
            return "image/webp"
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if data[:2] == b"BM":
            return "image/bmp"
        return "application/octet-stream"

    def _is_valid_image_header(self, data):
        return self._detect_image_type(data) != "application/octet-stream"

    def _try_fix_image(self, data):
        if not data or len(data) < 100:
            return None
        for skip in (2, 4, 8, 16, 32, 64, 128, 256, 512, 1024):
            if len(data) > skip + 4:
                sub = data[skip:skip + 4]
                if sub in (b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"\x89PNG", b"RIFF"):
                    return data[skip:]
        inverted = bytes([b ^ 0xFF for b in data])
        if self._is_valid_image_header(inverted):
            return inverted
        return None

    def _try_aes_decrypt(self, data):
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import unpad
        except ImportError:
            return None
        if not data or len(data) < 32:
            return None

        candidates = [
            (b"f5d965df75336270", b"97b60394abc2fbe1"),
            (b"75336270f5d965df", b"abc2fbe197b60394"),
            (b"f5d965df75336270", b"f5d965df75336270"),
            (b"f5d965df75336270", None),
        ]

        rem = len(data) % 16
        data_to_try = [data]
        if rem != 0:
            data_to_try.append(data[:-rem])

        for chunk in data_to_try:
            for key, iv in candidates:
                try:
                    if iv:
                        cipher = AES.new(key, AES.MODE_CBC, iv=iv)
                    else:
                        cipher = AES.new(key, AES.MODE_ECB)
                    decrypted = cipher.decrypt(chunk)
                    try:
                        unpadded = unpad(decrypted, AES.block_size)
                        if self._is_valid_image_header(unpadded):
                            return unpadded
                    except Exception:
                        pass
                    if self._is_valid_image_header(decrypted):
                        return decrypted
                except Exception:
                    continue
        return None
