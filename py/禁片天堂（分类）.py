# -*- coding: utf-8 -*-
import re
import sys
import json
import html
from urllib.parse import quote

import requests
from lxml import etree

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    """
    禁片天堂适配（参考 M麻豆.py 逻辑）
    - 首页主分类：最新发行、热门影片主题（含二级）、私藏连播（含二级）、热门女优（含二级）、发行商（含二级，可从导航进入）
    - 列表页：统一卡片解析，支持 oneVideo/card/article 等结构；点击型“folder”入口：热门主题(tag_list)、私藏连播(video_list_info)、女优(actor?id=)、发行商(tag_list?fid=)
    - 详情页：补充可点击标签（标签、女优、厂商、导演），番号、观看数、发行日期；播放地址解析（<source src> 或 m3u8）
    - 返回结构保持影视APP兼容；可点击标签格式：[a=cr:{"id":"/path","name":"名称"}/]名称[/a]
    """

    def getName(self):
        return "禁片天堂适配-增强版"

    def init(self, extend):
        try:
            ext = json.loads(extend)
        except Exception:
            ext = {}
        if not isinstance(ext, dict):
            ext = {}
        self.proxy = ext.get('proxy', {})
        self.plp = ext.get('plp', '')
        self.host = 'https://jptt.tv'
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Referer": self.host + "/",
            "Origin": self.host,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }

    def fetch(self, url):
        return requests.get(url, headers=self.headers, proxies=self.proxy, timeout=15)

    def _clean(self, s):
        return re.sub(r"\s+", " ", html.unescape((s or '').strip()))

    def _abs(self, url):
        if not url:
            return ''
        if url.startswith('http'):
            return url
        if url.startswith('/'):
            return self.host + url
        return self.host + '/' + url

    def _clickable(self, name, href):
        name = self._clean(name)
        href = (href or '').strip()
        if not name or not href:
            return ''
        target = json.dumps({"id": href, "name": name}, ensure_ascii=False)
        return f"[a=cr:{target}/]{name}[/a]"

    def homeContent(self, filter):
        classes = [
            {"type_name": "最新发行", "type_id": "/list?sort=2"},
            {"type_name": "热门影片主题", "type_id": "/tag?idx=1&sort=2"},
            {"type_name": "私藏连播", "type_id": "/video_list?idx=1"},
            {"type_name": "热门女优", "type_id": "/actor_list"}
        ]
        filters = {
            "/list?sort=2": [{"key": "order", "name": "排序", "value": [
                {"n": "最新发行", "v": "2"}, {"n": "今日热门", "v": "3"}, {"n": "本周热门", "v": "4"}, {"n": "本月热门", "v": "5"}
            ]}],
            "/tag?idx=1&sort=2": [{"key": "order", "name": "排序", "value": [
                {"n": "热门搜寻", "v": "2"}, {"n": "最多影片", "v": "3"}
            ]}],
            "/video_list?idx=1": [{"key": "order", "name": "排序", "value": [
                {"n": "最新发行", "v": "2"}
            ]}],
            "/actor_list": []
        }
        return {"class": classes, "filters": filters, "list": []}

    def homeVideoContent(self):
        return {"list": []}

    def _parse_cards(self, root):
        from urllib.parse import urlparse
        videos = []
        seen = set()
        for node in root.xpath('//div[contains(@class,"oneVideo")] | //article | //li[contains(@class, "section-content__item")]'):
            try:
                # 标题优先顺序：h3 → a@title/a文本 → img@alt
                name = ''
                name_elements = node.xpath('.//h3/text()')
                if name_elements:
                    name = self._clean(name_elements[0])
                if not name:
                    a_title = node.xpath('.//a/@title')
                    if a_title:
                        name = self._clean(a_title[0])
                if not name:
                    a_text = node.xpath('.//a/text()')
                    if a_text:
                        name = self._clean(''.join([t for t in a_text if self._clean(t)]))
                if not name:
                    alt = node.xpath('.//img/@alt')
                    if alt:
                        name = self._clean(alt[0])
                # 图片（支持懒加载）
                img = ''
                for attr in ['data-src', 'data-original', 'src']:
                    img_elements = node.xpath(f'.//img/@{attr}')
                    if img_elements:
                        img = self._abs(img_elements[0])
                        break
                # 备注（时长/日期/观看/多少部）
                desc = ''
                # 影片卡片的总时长（保持不变）
                dur = node.xpath('.//p[contains(@class,"p_duration")]/text()')
                if dur:
                    desc = self._clean(dur[0])
                else:
                    # 多少部：私藏连播一级卡片（vdo_lst_mask）
                    mask_texts = node.xpath('.//div[contains(@class,"vdo_lst_mask")]//text() | .//div[contains(@class,"vdo_lst_mask")]//br/preceding-sibling::text()')
                    if mask_texts:
                        raw = self._clean(' '.join([t for t in mask_texts if t and t.strip()]))
                        mcnt = re.search(r'(\d+)\s*部', raw)
                        if mcnt:
                            desc = f"{mcnt.group(1)}部"
                # 若仍为空，保留原有观看/日期兜底
                if not desc:
                    eye = node.xpath('.//i[contains(@class,"fa-eye")]/following-sibling::span/text()')
                    date = node.xpath('.//time/text()')
                    d_eye = self._clean(eye[0]) if eye else ''
                    d_date = self._clean(date[0]) if date else ''
                    if d_eye:
                        desc += f"👁 {d_eye} "
                    if d_date:
                        desc += f"📅 {d_date}"
                    desc = desc.strip()
                # 若为热门影片主题一级卡片（type-item），按需求用“多少部”替换人气：尝试从覆盖层或标签中抽取“X部”，取不到则不显示人气
                if not dur and node.xpath('ancestor-or-self::div[contains(@class,"type-item")]'):
                    # 热门主题页通常只有“人氣”，此处不再显示人气；保持为空或后续兜底
                    # 可扩展：若未来能获取该主题总片数则填充
                    pass
                # 对“无码”影片增加标记（仅视频卡片，保持总时长不变）
                unc_in_node = node.xpath('.//a[contains(text(),"無碼") or contains(text(),"無修正")] | .//*[contains(text(),"無碼") or contains(text(),"無修正")]')
                if dur and unc_in_node:
                    desc = (desc + ' ' + '无码').strip()
                # 链接：优先 oneVideo-top 的 data-href → 其次 a[href]
                link = ''
                data_href = node.xpath('.//div[contains(@class,"oneVideo-top")]/@data-href')
                if data_href:
                    link = data_href[0]
                else:
                    link_elements = node.xpath('.//div[contains(@class,"oneVideo-top")]//a/@href | .//a/@href')
                    if link_elements:
                        link = link_elements[0]
                # 必要字段
                if not (name and img and link):
                    continue
                # 规范化链接用于去重（仅用路径和查询中 list/kw/fid/tid 等关键参数，忽略协议与域名）
                norm = link
                try:
                    if link.startswith('http'):
                        p = urlparse(link)
                        norm = p.path
                        if p.query:
                            norm_q = []
                            for kv in p.query.split('&'):
                                if kv.startswith('list=') or kv.startswith('kw=') or kv.startswith('fid=') or kv.startswith('tid='):
                                    norm_q.append(kv)
                            if norm_q:
                                norm += '?' + '&'.join(sorted(norm_q))
                except Exception:
                    pass
                if norm in seen:
                    continue
                seen.add(norm)
                # folder 判断：二级入口（主题/连播/女优/发行商）
                is_folder = (
                    str(link).startswith('/video_list_info') or
                    str(link).startswith('/tag_list') or
                    str(link).startswith('/actor?id=') or
                    str(link).startswith('/tags/')
                )
                videos.append({
                    "vod_name": name,
                    "vod_pic": f'{self.plp}{img}',
                    "vod_remarks": desc,
                    "vod_id": link,
                    "vod_tag": ("folder" if is_folder else "")
                })
            except Exception:
                continue
        return videos

    def _sort_by_date(self, items):
        def parse_date(s):
            if not s:
                return ''
            m = re.search(r'(\d{4}-\d{2}-\d{2})', s)
            return m.group(1) if m else ''
        try:
            return sorted(items, key=lambda x: parse_date(x.get('vod_remarks','')), reverse=True)
        except Exception:
            return items

    # ------------------ 分类页 ------------------
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except Exception:
            pg = 1

        url = ''
        if tid.startswith('/list'):
            if pg == 1:
                url = f"{self.host}/list"
            else:
                # 最新/热门页翻页规则使用 idx=pg，默认 sort=2（热门搜寻）
                url = f"{self.host}/list?idx={pg}&sort=2"
        elif tid.startswith('/tag_list?tid='):
            m = re.search(r'tag_list\?tid=(\d+)', tid)
            t = m.group(1) if m else ''
            url = f"{self.host}/tag_list?tid={t}&idx={pg}"
        elif tid.startswith('/tag?'):
            # 一级热门主题页（作为folder入口）——仅匹配 /tag?，避免误伤 /tag_list
            sort = '2'
            if extend and isinstance(extend, dict):
                sort = extend.get('order', sort) or sort
            idx = str(pg)
            url = f"{self.host}/tag?idx={idx}&sort={sort}"
        elif tid.startswith('/video_list_info'):
            url = f"{self.host}{tid}"
        elif tid.startswith('/video_list'):
            m = re.search(r'idx=(\d+)', tid)
            idx = m.group(1) if m else str(pg)
            if str(idx) == '1' or pg == 1:
                url = f"{self.host}/video_list"
            else:
                url = f"{self.host}/video_list?idx={idx}"
        elif tid.startswith('/actor_list'):
            url = f"{self.host}/actor_list" + (f"?idx={pg}" if pg > 1 else '')
        elif tid.startswith('/actor?id='):
            url = f"{self.host}{tid}" + (f"&idx={pg}" if pg > 1 else '')
        elif tid.startswith('/tag_list?fid='):
            # 厂商（导演）二级列表：第一页不带 idx，第二页起 &idx={pg}
            m = re.search(r'tag_list\?fid=(\d+)', tid)
            fid = m.group(1) if m else ''
            url = f"{self.host}/tag_list?fid={fid}" if pg == 1 else f"{self.host}/tag_list?fid={fid}&idx={pg}"
        else:
            url = self._abs(tid)
            if pg > 1:
                sep = '&' if '?' in url else '?'
                url = f"{url}{sep}page={pg}"

        try:
            rsp = self.fetch(url)
            if rsp.status_code != 200:
                return {"list": [], "page": pg, "pagecount": 0, "limit": 0, "total": 0}
            root = etree.HTML(rsp.text)
            vodList = []

            if '/list' in url:
                vodList = self._parse_cards(root)
            elif '/tag?idx=' in url:
                # 主题一级 → folder 到具体 tag_list?tid=
                for a in root.xpath('//div[contains(@class,"type-item")]//a[@href]'):
                    href = a.get('href')
                    title_nodes = a.xpath('.//h5/text()') or a.xpath('.//h4/text()')
                    title = self._clean(''.join(title_nodes))
                    img = ''
                    for attr in ['data-src', 'data-original', 'src']:
                        nodes = a.xpath(f'.//img/@{attr}')
                        if nodes:
                            img = self._abs(nodes[0])
                            break
                    if href and title:
                        vodList.append({
                            "vod_id": href,
                            "vod_name": title,
                            "vod_pic": f'{self.plp}{img}',
                            "vod_remarks": self._clean(''.join(a.xpath('.//p/text()'))),
                            "vod_tag": "folder"
                        })
            elif '/actor_list' in url:
                # 仅抓取主体内容区域的女優卡片，排除导航/页眉/页脚中的固定下拉条目
                for a in root.xpath('//a[starts-with(@href, "/actor?id=")][not(ancestor::*[contains(@class,"nav-dropdown") or contains(@class,"nav-top") or contains(@class,"navbar") or contains(@class,"footer")])]'):
                    href = a.get('href')
                    name = self._clean(''.join(a.xpath('.//text()')))
                    img = ''
                    for attr in ['data-src', 'data-original', 'src']:
                        nodes = a.xpath(f'.//img/@{attr}')
                        if nodes:
                            img = self._abs(nodes[0])
                            break
                    if href and name:
                        vodList.append({
                            "vod_id": href,
                            "vod_name": name,
                            "vod_pic": f'{self.plp}{img}',
                            "vod_remarks": "",
                            "vod_tag": "folder"
                        })
            elif '/actor?id=' in url:
                # 热门女优的二级视频列表：按最新发行排序
                vodList = self._sort_by_date(self._parse_cards(root))
            elif '/tag_list?tid=' in url:
                # 热门影片主题的二级视频列表：按最新发行排序
                vodList = self._sort_by_date(self._parse_cards(root))
            elif tid.startswith('factory_click_'):
                # 通过可点击导演（厂商）进入的二级列表（稳定处理）
                base = tid.replace('factory_click_', '')  # e.g. /tag_list?fid=1199
                m = re.search(r'tag_list\?fid=(\d+)', base)
                fid = m.group(1) if m else ''
                # 页码规则一致：第一页不带 idx，第二页开始带 &idx={pg}
                url = f"{self.host}/tag_list?fid={fid}" if pg == 1 else f"{self.host}/tag_list?fid={fid}&idx={pg}"
                rsp = self.fetch(url)
                if rsp.status_code != 200:
                    return {"list": [], "page": pg, "pagecount": 0, "limit": 0, "total": 0}
                root = etree.HTML(rsp.text)
                vodList = self._sort_by_date(self._parse_cards(root))
                return {"list": vodList, "page": pg, "pagecount": 9999, "limit": 90, "total": 999999}
            elif '/video_list_info' in url:
                for item in root.xpath('//div[contains(@class,"div_v_list_item")]'):
                    href_nodes = item.xpath('.//*[@data-href]/@data-href')
                    href = href_nodes[0] if href_nodes else ''
                    title_nodes = item.xpath('.//h3[contains(@class,"h3_item_title")]/text()')
                    title = self._clean(''.join(title_nodes))
                    img = ''
                    for attr in ['data-src', 'data-original', 'src']:
                        nodes = item.xpath(f'.//img/@{attr}')
                        if nodes:
                            img = self._abs(nodes[0])
                            break
                    remarks = ''
                    eye_nodes = item.xpath('.//i[contains(@class,"fa-eye")]/following-sibling::span/text()')
                    date_nodes = item.xpath('.//time/text()')
                    if eye_nodes:
                        remarks = f"👁 {self._clean(eye_nodes[0])}"
                    if date_nodes:
                        d = self._clean(date_nodes[0])
                        remarks = (remarks + (" " if remarks else "") + f"📅 {d}").strip()
                    if href and title:
                        vodList.append({
                            "vod_id": href,
                            "vod_name": title,
                            "vod_pic": f'{self.plp}{img}',
                            "vod_remarks": remarks
                        })
                # 二级视频列表统一按“最新发行”（日期）降序
                vodList = self._sort_by_date(vodList)
            elif '/factory' in url:
                # 厂商一览表删除：不支持该一级分类
                vodList = []
            elif '/tag_list?fid=' in url:
                # 发行商二级：视频列表 → 按日期降序
                vodList = self._sort_by_date(self._parse_cards(root))
            else:
                # 其它情况保持原顺序（一级列表）
                vodList = self._parse_cards(root)

            return {"list": vodList, "page": pg, "pagecount": 9999, "limit": 90, "total": 999999}
        except Exception:
            return {"list": [], "page": pg, "pagecount": 0, "limit": 0, "total": 0}

    # ------------------ 详情与播放 ------------------
    def extractVideoUrl(self, html_text):
        try:
            # <source data-src= 或 src=（data-src 优先）
            m = re.search(r'<source[^>]+?(?:data-src|src)="([^"]+)"', html_text)
            if not m:
                # JS 变量 videoSourceUrl（含转义 \/）
                m = re.search(r'videoSourceUrl\s*=\s*"([^"]+)"', html_text)
            if m:
                u = m.group(1).strip().replace('\\/', '/')
            else:
                # 兜底：任意 //cdn.../index.m3u8 或 https://...m3u8
                m2 = re.search(r"(?:https?:)?//[^\"'\s\\]+?\.m3u8[^\"'\s\\]*", html_text)
                u = m2.group(0).strip() if m2 else ''
            if u and u.startswith('//'):
                u = 'https:' + u
            return u
        except Exception:
            pass
        return ''

    def detailContent(self, array):
        try:
            tid = array[0]
            url = tid if tid.startswith('http') else f"{self.host}{tid}"
            rsp = self.fetch(url)
            if rsp.status_code != 200:
                return {"list": []}
            root = etree.HTML(rsp.text)

            # 标题
            title_nodes = root.xpath('//h1[@class="h1_title"]/text()')
            title = self._clean(title_nodes[0]) if title_nodes else ''
            if not title:
                tnodes = root.xpath('//title/text()')
                if tnodes:
                    title = self._clean(tnodes[0].split('｜')[0])
                if not title:
                    alt_nodes = root.xpath('//img/@alt')
                    if alt_nodes:
                        title = self._clean(alt_nodes[0])

            # 封面
            pic_nodes = root.xpath('//video/@poster')
            pic = self._abs(pic_nodes[0]) if pic_nodes else ''

            # 简介（原文）：标签在前，影视介绍在后，确保总是能取到简介
            desc_nodes = root.xpath('//div[contains(@class,"info_original")]//p/text() | //div[contains(@class,"entry-content")]//p/text()')
            desc = self._clean(''.join(desc_nodes)) if desc_nodes else ''
            if not desc:
                # 元标签兜底
                meta_desc = root.xpath('//meta[@property="og:description"]/@content | //meta[@name="description"]/@content | //meta[@itemprop="description"]/@content')
                if meta_desc:
                    desc = self._clean(meta_desc[0])
            if not desc:
                # 再兜底页面正文
                body_desc_nodes = root.xpath('//div[contains(@class,"post-content")]//p/text() | //article//p/text()')
                if body_desc_nodes:
                    desc = self._clean(''.join(body_desc_nodes))
            if not desc:
                desc = title

            # 标签（可点击）——兼容 hohoj 的 span.ctg a，并补充 info-list 中的「標籤」
            tags = []
            # 常见标签容器
            for a in root.xpath('//div[contains(@class,"tagBox")]//a[@href] | //div[contains(@class,"keywords")]//a[@href] | //span[contains(@class,"ctg")]//a[@href]'):
                tag_name = self._clean(''.join(a.xpath('.//text()')))
                href = a.get('href') or ''
                if tag_name and href:
                    tags.append(self._clickable(tag_name, href))
            # 播放详情2的真实标签位置：info-list → li「標籤」
            for a in root.xpath('//div[contains(@class,"info-list")]//li[contains(.,"標籤")]//a[@href]'):
                tag_name = self._clean(''.join(a.xpath('.//text()')))
                href = a.get('href') or ''
                if tag_name and href:
                    tags.append(self._clickable(tag_name, href))
            tag_text = ' '.join(tags)
            # 若仍为空，兜底：meta keywords（分词，仅当存在明显以逗号分隔的标签）
            if not tag_text:
                meta_kw = root.xpath('//meta[@name="keywords"]/@content')
                if meta_kw:
                    parts = [self._clean(p) for p in (meta_kw[0] or '').split(',')]
                    for p in parts:
                        # 仅当站内存在对应标签链接时才生成可点击（避免假标签）
                        a = root.xpath(f'//a[normalize-space(text())="{p}"]/@href')
                        if a:
                            tags.append(self._clickable(p, a[0]))
                    tag_text = ' '.join(tags)

            # 女优（可点击）——严格限制至详情的 info-list「女優」条目，且仅 /actor?id=，并排除导航/页眉/页脚
            actors = []
            for a in root.xpath('//div[contains(@class,"info-list")]//li[contains(.,"女優")]//a[starts-with(@href, "/actor?id=")][not(ancestor::*[contains(@class,"nav-dropdown") or contains(@class,"nav-top") or contains(@class,"navbar") or contains(@class,"footer")])]'):
                name = self._clean(''.join(a.xpath('.//text()')))
                href = a.get('href') or ''
                if name and href:
                    actors.append(self._clickable(name, href))
            # 去重演员条目（避免重复），按完整标签去重，避免空格拆分导致后续演员显示代码片段
            if actors:
                seen = set()
                uniq = []
                for t in actors:
                    if t and t not in seen:
                        uniq.append(t)
                        seen.add(t)
                vod_actor = ' '.join(uniq)
            else:
                vod_actor = ''

            # 厂商（发行商，可点击）——与演员平行，参考 javxx 的“制作商|系列”解析
            factories = []
            # A. info-list 中的「廠商/發行商/制作商/系列」条目（精准）
            for a in root.xpath('//div[contains(@class,"info-list")]//li[(contains(.,"廠商") or contains(.,"發行商") or contains(.,"制作商") or contains(.,"系列"))]//a[starts-with(@href, "/tag_list?fid=")]'):
                name = self._clean(''.join(a.xpath('.//text()')))
                href = a.get('href') or ''
                if name and href and (name not in ["更多發行商","發行商一覽"]):
                    factories.append(self._clickable(name, href))
            # B. 其它容器类似 javxx：根据 label 文本定位「制作商|系列|發行商|廠商」，取其后续 a
            for label in root.xpath('//div[contains(@class,"meta")]//label[contains(text(),"制作商") or contains(text(),"系列") or contains(text(),"發行商") or contains(text(),"廠商")]'):
                a_nodes = label.xpath('./following-sibling::a')
                for a in a_nodes:
                    name = self._clean(''.join(a.xpath('.//text()')))
                    href = a.get('href') or ''
                    if name and href and href.startswith('/tag_list?fid='):
                        factories.append(self._clickable(name, href))
            # C. 排除导航/页眉/页脚的固定入口
            factories = [t for t in factories if ('更多發行商' not in t and '發行商一覽' not in t)]
            # 去重厂商条目（按完整可点击标签去重，逻辑与演员一致），并串联为单行显示
            if factories:
                seen_f = set()
                uniq_f = []
                for t in factories:
                    if t and t not in seen_f:
                        uniq_f.append(t)
                        seen_f.add(t)
                vod_pub = ' '.join(uniq_f)
            else:
                vod_pub = ''

            # 导演即厂商（可点击）——以 info-list 的「廠商」唯一结构为准（精准稳定）
            directors = []
            for a in root.xpath('//div[contains(@class,"info-list")]//li[contains(@class,"my-2") and contains(.,"廠商")]//a[starts-with(@href, "/tag_list?fid=")]'):
                name = self._clean(''.join(a.xpath('.//text()')))
                href = a.get('href') or ''
                if name and href:
                    # 统一为 jptt.tv 相对路径：/tag_list?fid={fid}
                    mfid = re.search(r'tag_list\?fid=(\d+)', href)
                    rel_id = f"/tag_list?fid={mfid.group(1)}" if mfid else (href if href.startswith('/tag_list?fid=') else '/tag_list?fid=')
                    target = json.dumps({"id": rel_id, "name": name}, ensure_ascii=False)
                    directors.append(f"[a=cr:{target}/]{name}[/a]")
            # 去重并串联
            if directors:
                seen_d = set()
                uniq_d = []
                for t in directors:
                    if t and t not in seen_d:
                        uniq_d.append(t)
                        seen_d.add(t)
                vod_director = ' '.join(uniq_d)
            else:
                vod_director = ''
            # 不再强制映射厂商到 vod_pub，避免重复与地址偏移；保留独立 vod_pub 字段

            # 番号（从标题或图片 alt 中尝试）
            code = ''
            mcode = re.search(r'([A-Za-z]{2,}[ -]?\d{3,})', title or '')
            if not mcode:
                alt_nodes = root.xpath('//img/@alt')
                alt_text = self._clean(alt_nodes[0]) if alt_nodes else ''
                mcode = re.search(r'([A-Za-z]{2,}[ -]?\d{3,})', alt_text)
            if mcode:
                code = mcode.group(1)

            # 观看数与发行日期
            views = ''
            vnodes = root.xpath('//span[contains(@class,"eye")]/text()')
            if vnodes:
                views = self._clean(vnodes[0])
            release_date = ''
            dnodes = root.xpath('//time/text()')
            if dnodes:
                release_date = self._clean(dnodes[0])

            # 提取“多少部”计数（若存在）
            count_text = ''
            cnt_nodes = root.xpath('//div[contains(@class,"vdo_lst_mask")]//text() | //div[contains(@class,"vdo_lst_mask")]//br/preceding-sibling::text()')
            if cnt_nodes:
                raw = self._clean(' '.join([t for t in cnt_nodes if t and t.strip()]))
                mcnt = re.search(r'(\d+)\s*部', raw)
                if mcnt:
                    count_text = f"{mcnt.group(1)}部"
            if not count_text:
                info_cnt = root.xpath('//div[contains(@class,"info-list")]//li//text()')
                raw2 = self._clean(' '.join(info_cnt)) if info_cnt else ''
                mcnt2 = re.search(r'(\d+)\s*部', raw2)
                if mcnt2:
                    count_text = f"{mcnt2.group(1)}部"

            # 是否「無碼/無修正」→ 在副标题特别显示
            is_uncensored = bool(root.xpath('//div[contains(@class,"info-list")]//li[contains(. ,"標籤")]//a[contains(text(),"無碼") or contains(text(),"無修正")]'))

            play_url = self.extractVideoUrl(rsp.text)

            # 详情简介内容：保留“简介的标签”并补充厂商可点击标签（与演员分列显示的逻辑一致）
            content_parts = []
            # 简介的标签只展示“標籤”与主题标签，不插入片商（避免在标签与简介中间出现片商入口文本）
            if tag_text:
                content_parts.append(tag_text)
            if desc:
                content_parts.append(desc)
            # 注意：部分影视APP对换行后的文本可能只渲染第一行，这里改为空格拼接，确保“标签 + 简介”一起显示
            vod_content_final = (' '.join([p for p in content_parts if p]).strip()) or (title or '')

            # 兼容影视APP：很多 APP 只渲染“演员/导演”两行，为保证“厂商”并行显示，
            # 我们将厂商（vod_pub）并入导演行（vod_director）一并展示，同时保留独立的 vod_pub 字段
            display_director = vod_director
            vod = {
                "vod_id": tid,
                "vod_name": title or '未知标题',
                "vod_pic": f'{self.plp}{pic}',
                "vod_content": vod_content_final,
                "vod_play_from": "注意身体",
                "vod_play_url": f"多看少打卡${play_url}",
                "vod_remarks": code,
                "vod_actor": vod_actor,
                "vod_director": display_director,
                "vod_pub": vod_pub,
                "vod_year": release_date,
            }
            # 副标题：优先显示“多少部”，其次显示“无码”标记，再次显示浏览数
            remarks_parts = []
            if count_text:
                remarks_parts.append(count_text)
            if is_uncensored:
                remarks_parts.append('无码')
            if views:
                remarks_parts.append(f"👁 {views}")
            if remarks_parts:
                vod["vod_remarks"] = (vod["vod_remarks"] + (" " if vod["vod_remarks"] else "") + ' '.join(remarks_parts)).strip()

            return {"list": [vod]}
        except Exception:
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        try:
            kw = quote(self._clean(key))
            page = int(pg)
            url = f"{self.host}/search?kw={kw}" if page == 1 else f"{self.host}/search?kw={kw}&page={page}"
            rsp = self.fetch(url)
            if rsp.status_code != 200:
                return {"list": []}
            root = etree.HTML(rsp.text)
            return {"list": self._parse_cards(root)}
        except Exception:
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        result = {}
        if flag == "注意身体":
            try:
                if id.startswith('http') and '.m3u8' in id:
                    result["parse"] = 0
                    result["playUrl"] = ''
                    result["url"] = f'{self.plp}{id}'
                else:
                    url = id if id.startswith('http') else f"{self.host}{id}"
                    rsp = self.fetch(url)
                    play_url = self.extractVideoUrl(rsp.text)
                    result["parse"] = 0
                    result["playUrl"] = ''
                    result["url"] = self.plp + play_url
            except Exception:
                result["parse"] = 0
                result["playUrl"] = ''
                result["url"] = ''
        result["header"] = self.headers
        return result

    def isVideoFormat(self, url):
        return any(ext in (url or '') for ext in ['.m3u8', '.mp4'])

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None
