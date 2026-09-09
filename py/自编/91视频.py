import json,re,sys
import requests
from bs4 import BeautifulSoup as BS
sys.path.append('..')
from base.spider import Spider as BaseSpider

class Spider(BaseSpider):
    def init(self,extend=""):
        try:
            cfg=json.loads(extend) if extend else {}
        except Exception:
            cfg={}
        self.proxies=cfg.get('proxies',{          "http": "http://127.0.0.1:10172",

          "https": "http://127.0.0.1:10172"})
        self.host='https://91spz.com'
        self.ua='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        self.base_headers={'User-Agent':self.ua,'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8','Accept-Language':'zh-CN,zh;q=0.9','Connection':'keep-alive','Upgrade-Insecure-Requests':'1'}
        self.headers={**self.base_headers,'Origin':self.host,'Referer':self.host+'/'}

    def getName(self):
        return '麻豆传媒适配-极简'

    def _req(self,url,ref=None):
        h={**self.base_headers,'Origin':self.host,'Referer':ref or self.host+'/'}
        r=requests.get(url,headers=h,proxies=self.proxies,timeout=20)
        try:
            r.encoding=r.apparent_encoding or r.encoding
        except Exception:
            pass
        return r

    def _s(self,html):
        return BS(html or '','lxml')

    def _u(self,u):
        if not u:return ''
        if u.startswith('http'):return u
        return self.host+u if u.startswith('/') else self.host+'/'+u

    def _img(self,u):
        u=self._u((u or '').strip('"\' '))
        if not u:return ''
        if re.search(r'\.(jpg|jpeg|png|webp|gif)(\?.*)?$',u,re.I) or 'imgwebsa.shzvsh.cn' in u:
            return f"{self.getProxyUrl()}&type=img&url={u}"
        return u

    def _list(self,soup):
        out=[]
        for li in soup.select('li.section-content__item'):
            a=li.select_one('a[href^="/archives/"]')
            if not a:continue
            if (a.get('data-type','0') or '0').strip()!='0':
                continue
            h3=li.select_one('h3.text-truncate')
            title=(h3.get_text(' ',strip=True) if h3 else '').strip()
            if not title:continue
            img=li.select_one('img')
            pic=self._img((img.get('data-src') or img.get('src') or '') if img else '')
            out.append({'vod_id':a.get('href'),'vod_name':title,'vod_pic':pic,'vod_remarks':'','style':{'type':'rect','ratio':1.33}})
        return out

    def _norm_topic(self,href,main_code):
        if not href:return ''
        href=href.strip()
        m=re.search(r'^/topic/(\d+)/(\d+)/(\d+)/?$',href)
        if m:
            return f"/topic/{m.group(1)}/{m.group(2)}/{m.group(3)}/"
        m=re.search(r'^/topic/0/(\d+)(?:/(\d+))?/?$',href)
        if m:
            return f"/topic/{main_code}/{m.group(1)}/1/"
        return href if href.endswith('/') else href+'/'

    def homeContent(self,filter):
        r=self._req(self.host+'/')
        if r.status_code!=200:return {'class':[],'filters':{},'list':[]}
        soup=self._s(r.text)
        main={'麻豆AV':'17521','传媒片商':'30521','国产视频':'30526','日本AV':'30522','欧美AV':'30524'}
        cls=[]
        seen=set()
        for h in soup.select('main.home-sections .section-header'):
            h2=h.select_one('h2')
            a=h.select_one('a[href^="/topic/"]')
            name=(h2.get_text(' ',strip=True) if h2 else '').strip()
            href=(a.get('href') if a else '').strip()
            if not name or not href:continue
            href=self._norm_topic(href,main['国产视频'])
            if (name,href) not in seen:
                seen.add((name,href))
                cls.append({'type_name':name,'type_id':href})
        for name,code in main.items():
            href=f"/topic/{code}/0/1/"
            if (name,href) not in seen:
                seen.add((name,href))
                cls.append({'type_name':name,'type_id':href})

        filters={}
        for item in soup.select('nav.pcNav .navItem'):
            btn=item.select_one('.navBtn')
            if not btn:continue
            t=btn.get_text(' ',strip=True)
            if t not in main:continue
            type_id=f"/topic/{main[t]}/0/1/"
            vals=[]
            for a in item.select('.dropdownBox a.dropdownItem[href^="/topic/"]'):
                n=(a.get_text(' ',strip=True) or '').strip()
                href=self._norm_topic(a.get('href',''),main[t])
                if n and href:
                    vals.append({'n':n,'v':href})
            if vals:
                filters[type_id]=[{'key':'type','name':'分类','value':vals}]

        return {'class':cls,'filters':filters,'list':self._list(soup)}

    def homeVideoContent(self):
        r=self._req(self.host+'/')
        return {'list':self._list(self._s(r.text))} if r.status_code==200 else {'list':[]}

    def categoryContent(self,tid,pg,filter,extend):
        pg=int(pg)
        if extend and 'type' in extend:
            tid=extend['type']
        path=tid if str(tid).startswith('/') else '/'+str(tid)
        if path.startswith('/tag/'):
            parts=path.strip('/').split('/')
            base=f"/tag/{parts[1]}/1/"
            first=self.host+base
            url=first if pg==1 else f"{first}{pg}/"
        else:
            base=(path if path.endswith('/') else path+'/')
            first=self.host+base
            url=first if pg==1 else f"{first}{pg}/"
        r=self._req(url,ref=first)
        if r.status_code!=200:
            return {'list':[],'page':pg,'pagecount':1,'limit':90,'total':0}
        soup=self._s(r.text)
        return {'list':self._list(soup),'page':pg,'pagecount':99999 if soup.find('link',rel='next') else pg,'limit':90,'total':999999}

    def searchContent(self,key,quick,pg='1'):
        from urllib.parse import quote
        pg=int(pg)
        kw=quote((key or '').strip())
        first=f"{self.host}/searchvideo/{kw}/"
        url=first if pg==1 else f"{first}{pg}/"
        r=self._req(url,ref=first)
        if r.status_code!=200:
            return {'list':[],'page':pg,'pagecount':1}
        soup=self._s(r.text)
        return {'list':self._list(soup),'page':pg,'pagecount':99999 if soup.find('link',rel='next') else pg}

    def detailContent(self,ids):
        vid=ids[0]
        url=vid if str(vid).startswith('http') else self.host+vid
        r=self._req(url)
        if r.status_code!=200:
            return {'list':[{'vod_play_from':'麻豆传媒','vod_play_url':'获取失败'}]}
        soup=self._s(r.text)
        s='\n'.join((x.get_text() or '') for x in soup.find_all('script'))
        m=re.search(r'const\s+path\s*=\s*"([^"]+)"\s*;',s)
        if not m:
            return {'list':[{'vod_play_from':'麻豆传媒','vod_play_url':f"未找到视频源${url}"}]}
        path=m.group(1).replace('\\/','/').replace('\\u0026','&').replace('\u0026','&').replace('\u0026','&')
        play=f"{self.host}/h5/m3u8/{path}" if not path.startswith('http') else path
        h1=soup.find('h1')
        title=(h1.get_text(' ',strip=True) if h1 else (soup.title.get_text(' ',strip=True) if soup.title else '在线播放')).split('｜')[0].strip()

        actors=[]
        for a in soup.select('a.related-gls__item[href^="/actressinfo/"]'):
            h5=a.select_one('h5')
            name=(h5.contents[0].strip() if h5 and h5.contents else '').strip()
            p=a.select_one('p')
            ps=(p.get_text(' ',strip=True) if p else '').strip()
            href=(a.get('href') or '').strip()
            if name and href:
                show=f"{name} {ps}".strip() if ps else name
                actors.append(f"[a=cr:{json.dumps({'id':href,'name':name},ensure_ascii=False)}/]{show}[/a]")
        vod_actor=' '.join(actors)

        tags=[]
        for a in soup.select('span.tags a[href^="/tag/"]'):
            name=(a.get_text(' ',strip=True) or '').strip()
            href=(a.get('href') or '').strip()
            if name and href:
                tags.append(f"[a=cr:{json.dumps({'id':href,'name':name},ensure_ascii=False)}/]{name}[/a]")

        desc=''
        p=soup.select_one('p.vd-infos__desc')
        if p:
            desc=p.get_text(' ',strip=True).strip()

        vod_content=('标签：'+' '.join(tags) if tags else '')
        if desc:
            vod_content=(vod_content+'\n' if vod_content else '')+desc
        if not vod_content:
            vod_content=title

        vod_year=''
        for p in soup.find_all('p'):
            t=p.get_text(' ',strip=True)
            m=re.search(r'发行日期：\s*([0-9]{4}/[0-9]{1,2}/[0-9]{1,2})',t)
            if m:
                vod_year=m.group(1)
                break

        return {'list':[{'vod_play_from':'麻豆传媒','vod_play_url':f"{title}${play}",'vod_content':vod_content,'vod_actor':vod_actor,'vod_year':vod_year}]}

    def playerContent(self,flag,id,vipFlags):
        return {'parse':0,'url': 'http://127.0.0.1:10079/p/0/127.0.0.1:10172/' + self._u(id),'header':self.headers}

    def aesimg(self,data:bytes)->bytes:
        k=b'2019ysapp7527'
        b=bytearray(data)
        for i in range(min(100,len(b))):
            b[i]^=k[i%len(k)]
        return bytes(b)

    def localProxy(self,param):
        if param.get('type')!='img' or not param.get('url'):
            return [404,'text/plain',b'']
        r=requests.get(param['url'],headers={**self.base_headers,'Origin':self.host,'Referer':self.host+'/'},proxies=self.proxies,timeout=20)
        c=self.aesimg(r.content)
        ct='image/jpeg'
        if c.startswith(b'\x89PNG'):ct='image/png'
        elif c.startswith(b'GIF8'):ct='image/gif'
        elif c.startswith(b'RIFF') and b'WEBP' in c[8:16]:ct='image/webp'
        return [200,ct,c]
