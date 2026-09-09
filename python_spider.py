"""TV / Chaquopy Python 爬蟲範例。

將本檔放到配置伺服器的 vod/ 目錄，sites 加入：
{
  "key": "PythonDemo", "name": "Python 功能範例", "type": 3,
  "api": "./vod/python_spider.py", "lang": "zh-TW",
  "searchable": 1, "quickSearch": 1, "changeable": 0,
  "ext": {
    "web_url": "https://example.org/", "cookie_name": "",
    "media_url": "", "media_headers": {}
  }
}

填入自己的登入入口與 Cookie 名稱可測試登入；填入 HLS 網址可測試播放。
三張影片卡片共用 media_url。每頁 2 筆，第三個互動功能在第 2 頁。
"""
import json
from urllib.parse import urlsplit

from base.spider import Spider as BaseSpider


PAGE_SIZE = 2
VIDEOS = (
    ("demo1", "影片範例一", "動畫"),
    ("demo2", "影片範例二", "戲劇"),
    ("demo3", "影片範例三", "動畫"),
)


class Spider(BaseSpider):
    def init(self, extend=""):
        # TV 把 Site.ext 物件轉成 JSON 字串後傳入。
        self.options = json.loads(extend) if extend else {}
        self.web_url = self.options.get("web_url", "https://example.org/")
        if urlsplit(self.web_url).scheme != "https" or not urlsplit(self.web_url).netloc:
            raise ValueError("web_url 必須是完整 HTTPS 網址")
        self.cookie_name = self.options.get("cookie_name", "")

    def getName(self):
        return "Python 功能範例"

    def homeContent(self, filter):
        result = {"class": [
            {"type_id": "tools", "type_name": "互動功能"},
            {"type_id": "videos", "type_name": "影片範例"},
            {"type_id": "collections", "type_name": "資料夾"},
        ]}
        if filter:
            result["filters"] = {"videos": [{
                "key": "genre", "name": "類型", "value": [
                    {"n": "全部", "v": ""}, {"n": "動畫", "v": "動畫"},
                    {"n": "戲劇", "v": "戲劇"}],
            }]}
        return result

    def homeVideoContent(self):
        return {"list": self._videos()[:PAGE_SIZE]}

    @staticmethod
    def _page(items, pg):
        page = max(1, int(pg))
        return {"list": items[(page - 1) * PAGE_SIZE:page * PAGE_SIZE],
                "page": page, "pagecount": (len(items) + PAGE_SIZE - 1) // PAGE_SIZE,
                "limit": PAGE_SIZE, "total": len(items)}

    @staticmethod
    def _videos():
        return [{"vod_id": ident, "vod_name": name, "vod_remarks": genre,
                 "style": {"type": "rect", "ratio": 0.75}}
                for ident, name, genre in VIDEOS]

    def categoryContent(self, tid, pg, filter, extend):
        if tid == "tools":
            items = [{"vod_id": "action/" + action, "vod_name": name,
                      "vod_remarks": remark, "action": action, "style": {"type": "list"}}
                     for action, name, remark in (
                         ("toast", "顯示訊息", "action 回傳 msg，由 App 顯示提示"),
                         ("web", "開啟網頁", "使用 App 內建 WebView"),
                         ("cookie", "檢查登入 Cookie", "只顯示是否存在，不顯示 Cookie 內容"))]
        elif tid == "collections":
            items = [{"vod_id": "folder/featured", "vod_name": "精選資料夾",
                      "vod_remarks": "點擊後繼續呼叫 categoryContent",
                      "vod_tag": "folder", "style": {"type": "list"}}]
        elif tid in ("videos", "folder/featured"):
            items = self._videos()
            genre = (extend or {}).get("genre", "")
            if genre:
                items = [item for item in items if item["vod_remarks"] == genre]
        else:
            items = []
        return self._page(items, pg)

    def action(self, action):
        # 不要 json.dumps：Python 橋接層負責序列化回傳的 dict。
        if action == "toast":
            return {"msg": "這是 Python action 的訊息提示"}
        if action == "web":
            self._open_web()
            return {"msg": "已開啟網頁"}
        if action == "cookie":
            if not self.cookie_name:
                return {"msg": "請先在 ext 設定 cookie_name"}
            cookies = self._cookies()
            for item in cookies.split(";"):
                name, separator, value = item.strip().partition("=")
                if separator and name == self.cookie_name and value:
                    return {"msg": "登入 Cookie 已存在；是否有效仍須向官方 API 確認"}
            return {"msg": "尚未取得指定的登入 Cookie"}
        return {"msg": "不支援此操作"}

    def _open_web(self):
        # 延後 import，只有在 Android 執行此動作時才需要 Java 類別。
        from android.content import Intent
        from com.chaquo.python import Python
        context = Python.getPlatform().getApplication()
        intent = Intent()
        intent.setClassName(context, "com.fongmi.android.tv.ui.activity.WebActivity")
        intent.putExtra("url", self.web_url)
        if self.cookie_name:
            # 返回起始 HTTPS origin，且此 Cookie 變為非空的新值時才自動關閉。
            # Cookie 沒變或登入只寫入 localStorage 時，可手動返回 App。
            intent.putExtra("loginCookie", self.cookie_name)
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)

    def _cookies(self):
        # requests 不會自動共用 WebView Cookie，需自行從 CookieManager 讀取。
        from android.webkit import CookieManager
        return str(CookieManager.getInstance().getCookie(self.web_url) or "")

    def searchContent(self, key, quick, pg="1"):
        # SiteApi 已依 Site.lang 做繁簡轉換，爬蟲只負責搜尋。
        query = key.strip().casefold()
        items = [item for item in self._videos() if query in item["vod_name"].casefold()] if query else []
        return self._page(items, pg)

    def detailContent(self, ids):
        item = next((item for item in self._videos() if item["vod_id"] == ids[0]), None)
        if item is None:
            # 明確 msg 與拋出例外不同；目前 App 對空詳情 + msg 會提示並離開詳情。
            return {"list": [], "msg": "找不到此範例影片"}
        item.update({"vod_content": "請在 ext.media_url 填入可播放的 HLS 網址。",
                     "vod_play_from": "範例播放線",
                     "vod_play_url": "示範集數$" + item["vod_id"]})
        return {"list": [item]}

    def playerContent(self, flag, id, vipFlags):
        if id not in {item[0] for item in VIDEOS}:
            return {"parse": 0, "msg": "無效的範例影片 ID"}
        url = self.options.get("media_url", "")
        if not url:
            return {"parse": 0, "msg": "請先設定 ext.media_url 再測試播放"}
        return {"parse": 0, "jx": 0, "url": url,
                "header": self.options.get("media_headers", {}),
                "format": "application/x-mpegURL"}

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return urlsplit(url).path.lower().endswith(".m3u8")
