# -*- coding: utf-8 -*-
# by @嗷呜
# py维码弹窗测试
import sys
import threading
sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    _zxing_loader = None

    def init(self, extend=""):
        from android.os import Handler, Looper
        self._handler = Handler(Looper.getMainLooper())
        zxing = 'https://cdn.waimaimingtang.com/file/images/bwc/20260807112952-15e99bb962.png'
        self._zxing_loader = self._loadZxing(zxing)
        self._toast = None

    def _loadZxing(self, url=""):
        from java.io import File
        from java.lang import Runtime
        from dalvik.system import DexClassLoader
        if Spider._zxing_loader is not None: return Spider._zxing_loader
        activity = self.getActivity()
        if not activity: return None
        pyaowu_dir = File(str(activity.getFilesDir()), "pyaowu")
        if not pyaowu_dir.exists(): pyaowu_dir.mkdirs()
        zxing_file = File(pyaowu_dir, "zxing.jar")
        zxing_path = str(zxing_file.getAbsolutePath())
        if not zxing_file.exists():
            if not url: return None
            resp = self.fetch(url)
            if resp.status_code == 200:
                with open(zxing_path, 'wb') as f:
                    f.write(resp.content)
            else:
                return None
        Runtime.getRuntime().exec("chmod 755 " + zxing_path)
        Spider._zxing_loader = DexClassLoader(zxing_path, None, None, activity.getClassLoader())
        return Spider._zxing_loader

    def _loadClass(self, className):
        return self._zxing_loader.loadClass(className) if self._zxing_loader else None

    def _createQrBitmap(self, content, size=240):
        from java.lang import Thread, String, Integer, Class as JClass
        from java import jclass, jarray, jint
        old = Thread.currentThread().getContextClassLoader()
        Thread.currentThread().setContextClassLoader(self._zxing_loader)
        try:
            MultiFormatWriter = jclass("com.google.zxing.MultiFormatWriter")
            BarcodeFormat = jclass("com.google.zxing.BarcodeFormat")
            EncodeHintType = jclass("com.google.zxing.EncodeHintType")
            HashMap = jclass("java.util.HashMap")
            Bitmap = jclass("android.graphics.Bitmap")

            hints = HashMap()
            hints.put(EncodeHintType.CHARACTER_SET, String("UTF-8"))
            hints.put(EncodeHintType.MARGIN, 1)

            INT = Integer.TYPE
            writer = MultiFormatWriter()
            QR_CODE = BarcodeFormat.QR_CODE
            encodeMethod = writer.getClass().getMethod(
                "encode",
                JClass.forName("java.lang.String"), QR_CODE.getClass(),
                INT, INT, JClass.forName("java.util.Map")
            )
            matrix = encodeMethod.invoke(writer, String(content), QR_CODE,
                                         jint(size), jint(size), hints)

            mc = matrix.getClass()
            def getFld(name):
                f = mc.getDeclaredField(name)
                f.setAccessible(True)
                return f
            width = getFld("width").getInt(matrix)
            height = getFld("height").getInt(matrix)
            rowSize = getFld("rowSize").getInt(matrix)
            bits = list(getFld("bits").get(matrix))  

            BLACK, WHITE = -16777216, -1
            pixels = [WHITE] * (width * height)
            for y in range(height):
                rowOff = y * rowSize
                pixOff = y * width
                for x in range(width):
                    if (bits[rowOff + (x >> 5)] >> (x & 31)) & 1:
                        pixels[pixOff + x] = BLACK

            bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
            bitmap.setPixels(jarray(jint)(pixels), 0, width, 0, 0, width, height)
            return bitmap
        except Exception as e:
            import traceback
            self.log("_createQrBitmap error: " + str(e))
            self.log(traceback.format_exc())
            return None
        finally:
            Thread.currentThread().setContextClassLoader(old)

    def show_qr_dialog(self, url, title):
        from java import jclass, dynamic_proxy
        self.show("正在生成二维码")
        def build():
            try:
                activity = self.getActivity()
                if not activity: return
                bitmap = self._createQrBitmap(url, 480)
                if not bitmap: return

                ImageView = jclass("android.widget.ImageView")
                TextView = jclass("android.widget.TextView")
                LinearLayout = jclass("android.widget.LinearLayout")
                FrameLayout = jclass("android.widget.FrameLayout")
                ViewGroup = jclass("android.view.ViewGroup")
                Gravity = jclass("android.view.Gravity")
                Color = jclass("android.graphics.Color")
                ColorDrawable = jclass("android.graphics.drawable.ColorDrawable")
                KeyEvent = jclass("android.view.KeyEvent")
                AlertDialog = jclass("android.app.AlertDialog")
                OnKeyListener = jclass("android.content.DialogInterface$OnKeyListener")

                density = activity.getResources().getDisplayMetrics().density
                def dp(v): return int(v * density + 0.5)
                size = dp(240)

                imageView = ImageView(activity)
                imageView.setScaleType(ImageView.ScaleType.CENTER_CROP)
                imageView.setImageBitmap(bitmap)

                qrFrame = FrameLayout(activity)
                qrParams = FrameLayout.LayoutParams(size, size)
                qrParams.gravity = Gravity.CENTER
                qrFrame.addView(imageView, qrParams)

                tipView = TextView(activity)
                tipView.setText(title)
                tipView.setTextSize(20)
                tipView.setTextColor(Color.WHITE)
                tipView.setGravity(Gravity.CENTER)
                tipParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                tipParams.topMargin = dp(16)

                container = LinearLayout(activity)
                container.setOrientation(LinearLayout.VERTICAL)
                container.setGravity(Gravity.CENTER)
                padding = dp(16)
                container.setPadding(padding, padding, padding, padding)
                container.addView(qrFrame)
                container.addView(tipView, tipParams)

                outer = self
                class KeyListener(dynamic_proxy(OnKeyListener)):
                    def __init__(self):
                        super().__init__()
                    def onKey(self, dialog, keyCode, event):
                        if keyCode == KeyEvent.KEYCODE_BACK and event.getAction() == KeyEvent.ACTION_UP:
                            dialog.dismiss()
                            outer.show("二维码已关闭")
                            return True
                        return False

                builder = AlertDialog.Builder(activity)
                builder.setView(container)
                builder.setCancelable(False)
                dialog = builder.create()
                dialog.setOnKeyListener(KeyListener())
                window = dialog.getWindow()
                if window is not None:
                    window.setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
                dialog.show()
                self._qr_dialog = dialog
            except Exception as e:
                self.log("show_qr_dialog error: " + str(e))
        self.run(build)

    def dismiss_qr_dialog(self):
        def task():
            try:
                if hasattr(self, '_qr_dialog') and self._qr_dialog is not None:
                    self._qr_dialog.dismiss()
                    self._qr_dialog = None
            except Exception as e:
                self.log("dismiss_qr_dialog error: " + str(e))
        self.run(task)


    def getActivity(self):
        from java.lang import Class
        activityThreadClass = Class.forName("android.app.ActivityThread")
        activityThread = activityThreadClass.getMethod("currentActivityThread", None).invoke(None, None)
        activitiesField = activityThreadClass.getDeclaredField("mActivities")
        activitiesField.setAccessible(True)
        activities = activitiesField.get(activityThread)
        if activities is not None:
            values = activities.values()
            try:
                records = values.toArray()
            except:
                records = values.getClass().getMethod("toArray").invoke(values)
            for activityRecord in records:
                try:
                    activityRecordClass = activityRecord.getClass()
                    pausedField = activityRecordClass.getDeclaredField("paused")
                    pausedField.setAccessible(True)
                    if not pausedField.getBoolean(activityRecord):
                        activityField = activityRecordClass.getDeclaredField("activity")
                        activityField.setAccessible(True)
                        return activityField.get(activityRecord)
                except:
                    continue
        return None

    def execute(self, func):
        threading.Thread(target=func).start()

    def run(self, func, delay=0):
        from java import dynamic_proxy
        from java.lang import Runnable
        import traceback
        def safe():
            try:
                func()
            except Exception as e:
                self.log("run error: " + str(e))
                self.log(traceback.format_exc())
        if not hasattr(self, '_r_class'):
            class R(dynamic_proxy(Runnable)):
                def __init__(self, fn):
                    super().__init__()
                    self.fn = fn
                def run(self):
                    self.fn()
            self._r_class = R
        if delay > 0:
            self._handler.postDelayed(self._r_class(safe), delay)
        else:
            self._handler.post(self._r_class(safe))

    def finishActivity(self):
        def task():
            try:
                activity = self.getActivity()
                if activity is not None: activity.finish()
            except Exception as e:
                self.log("finishActivity error: " + str(e))
        self.run(task)


    def show(self, text):
        def make():
            from android.widget import Toast
            if not text: return
            try:
                activity = self.getActivity()
                if not activity: return
                if self._toast is not None: self._toast.cancel()
                self._toast = Toast.makeText(activity, text, Toast.LENGTH_LONG)
                self._toast.show()
            except Exception as e:
                self.log("show error: " + str(e))
        self.run(make)

    def _createListener(self, callback=None):
        from java import dynamic_proxy, jclass
        OnClickListener = jclass("android.content.DialogInterface$OnClickListener")
        if not hasattr(self, '_listener_class'):
            class Listener(dynamic_proxy(OnClickListener)):
                def __init__(self, cb):
                    super().__init__()
                    self.cb = cb
                def onClick(self, dialog, which):
                    dialog.dismiss()
                    if self.cb: self.cb()
            self._listener_class = Listener
        return self._listener_class(callback)

    def show_dialog(self, title, message, positive, callback=None):
        from java import jclass
        def build():
            try:
                activity = self.getActivity()
                if not activity: return
                AlertDialog = jclass("android.app.AlertDialog")
                AlertDialog.Builder(activity) \
                    .setTitle(title) \
                    .setMessage(message) \
                    .setPositiveButton(positive, self._createListener(callback)) \
                    .show()
            except Exception as e:
                self.log("show_dialog error: " + str(e))
        self.run(build)


    def destroy(self):
        pass

    def homeContent(self, filter):
        cate = {"电影": "movie", "剧集": "tv", "综艺": "shows",
                "动画": "anime", "音乐": "music", "短片": "short", "其他": "other"}
        classes = [{'type_name': k, 'type_id': v} for k, v in cate.items()]
        return {'class': classes, 'filters': {}}

    def homeVideoContent(self):
        return {'list': [{
            'vod_id': '1', 'vod_name': '弹窗测试', 'vod_pic': '',
            'action': '弹窗测试', 'vod_remarks': '点击触发',
        }, {
            'vod_id': '2', 'vod_name': '二维码测试', 'vod_pic': '',
            'action': '二维码', 'vod_remarks': '点击扫码',
        }, {
            'vod_id': '3', 'vod_name': 'fish', 'vod_pic': '',
            'vod_remarks': '点击触发',
        }, {
            'vod_id': '4', 'vod_name': 'toast', 'vod_pic': '',
            'action': 'toast', 'vod_remarks': '点击触发',
        }]}

    def action(self, action):
        if action == "二维码":
            self.show_qr_dialog("http://xn--nsr30bl8nb2kyt7a8vs.top/", "嗷呜二维码生成示例")
        elif action == "toast":
            self.show("嗷呜Toast测试")
        else:
            self.show_dialog("提示", "嗷呜py弹窗测试", "确定", lambda: self.show("弹窗已关闭"))

    def categoryContent(self, tid, pg, filter, extend): pass
    def detailContent(self, ids):
        self.finishActivity()
        return {'list': []}
    def searchContent(self, key, quick, pg="1"): pass
    def playerContent(self, flag, id, vipFlags): pass


if __name__ == "__main__":
    sp = Spider()
    sp.init()
