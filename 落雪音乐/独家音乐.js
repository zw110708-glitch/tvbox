/**
 * @name 聚合音源
 * @description 五平台聚合破解音源(QQ/网易/酷我/酷狗/咪咕)，参数在线自更新
 * @version 2.0.0
 * @author 可可
 */

const { EVENT_NAMES, request, on, send } = globalThis.lx

/* ==================== 参数自更新（每次打开软件自动重新拉取） ==================== */

// 参数配置文件地址（凯速）。以后接口参数变了，只改这个 config.json，不用重导音源。
const CONFIG_URL = 'https://9685.kstore.space/%E8%90%BD%E9%9B%AA%E9%9F%B3%E4%B9%90/config.json'

// 内置兜底参数：config.json 拉取失败时用，保证音源仍可用（内容与 config.json 保持一致）
const DEFAULT_CONFIG = {
  version: '1.0.0',
  haitangResolveUrl: 'https://musicserver.haitangw.cc/v1/music/resolve-url',
  nianxinTx: 'https://mcp.nianxinxz.com/share/ceshi/tx.php',
  nianxinWy: 'https://mcp.nianxinxz.com/share/ceshi/wy.php',
  haitangKg: 'https://music.haitangw.cc/kgqq1/kg.php',
  haitangMg: 'https://musicapi.haitangw.net/music/mg.php',
  kuwoUrl: 'http://nmobi.kuwo.cn/mobi.s',
  kuwoSource: 'kwplayerhd_ar_4.3.0.8_tianbao_T1A_qirui.apk',
  levelMap: { '128k': 'standard', '320k': 'exhigh', 'flac': 'lossless', 'flac24bit': 'lossless' },
  kwBr: { '128k': '128kmp3', '320k': '320kmp3', 'flac': '2000kflac', 'flac24bit': '4000kflac' },
}

// 当前生效配置：先兜底，后台拉到新配置后覆盖（闭包变量，musicUrl 每次读取最新值）
let config = Object.assign({}, DEFAULT_CONFIG)

/* ==================== 基础工具 ==================== */

// HTTP 请求封装（request 回调签名：err, resp, body，三态兼容）
const httpRequest = (url, options = {}) => new Promise((resolve, reject) => {
  request(url, options, (err, resp, body) => {
    if (err) return reject(err)
    let data = body
    if (data === undefined || data === null) data = resp && resp.body
    resolve(data)
  })
})

// 解析 JSON（兼容字符串 / 对象）
const toJson = (data) => {
  if (data == null) return null
  if (typeof data === 'object') return data
  try { return JSON.parse(String(data)) } catch (e) { return null }
}

// 从响应中提取播放 URL
const extractUrl = (data) => {
  if (!data) return ''
  if (typeof data === 'string') {
    const s = data.trim()
    if (/^https?:\/\//.test(s)) return s.replace(/^http:/, 'https:')
    data = toJson(data)
  }
  if (!data || typeof data !== 'object') return ''
  let u = data.url || (data.data && (typeof data.data === 'string' ? data.data : (data.data && data.data.url)))
  if (typeof u === 'string') {
    u = u.trim().replace(/\\u0026/gi, '&').replace(/^http:/, 'https:')
    if (/^https?:\/\//.test(u)) return u
  }
  return ''
}

/* ==================== 音质降级（高 -> 低依次尝试） ==================== */

const QA_ORDER = ['flac24bit', 'flac', '320k', '128k']
const qualityFallback = (quality) => {
  const idx = QA_ORDER.indexOf(quality)
  if (idx < 0) return [quality, '128k']
  return QA_ORDER.slice(idx)
}

/* ==================== 各平台音源（参数走 config，逻辑固定） ==================== */

// 海棠 resolve-url（解析型，返回真实 CDN 直链）；source: tx / wy / kg / kw / mg
const haitangResolve = (source, rid, quality) => {
  const level = config.levelMap[quality] || 'standard'
  return httpRequest(config.haitangResolveUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0' },
    body: JSON.stringify({ source, rid: String(rid), level }),
    timeout: 10000,
  }).then((body) => extractUrl(toJson(body)))
}

// 酷狗：从 _types 里按音质取对应 hash（320k/flac 的 hash 与默认不同）
const getKgHash = (musicInfo, quality) => {
  const types = musicInfo && musicInfo._types
  if (types && Array.isArray(types)) {
    for (let i = 0; i < types.length; i++) {
      const t = types[i]
      if (t && t.type === quality && t.hash) return t.hash
    }
    if (types[0] && types[0].hash) return types[0].hash
  }
  return (musicInfo && (musicInfo.hash || musicInfo.songmid)) || ''
}

const apis = {}

// -------- QQ 音乐 (tx) --------
apis.tx = {
  musicUrl(musicInfo, quality) {
    const songmid = musicInfo.songmid || musicInfo.media_mid || musicInfo.strMediaMid || ''
    if (!songmid) return Promise.reject(new Error('缺少歌曲ID'))
    const qlist = qualityFallback(quality)
    const tryOne = (i) => {
      if (i >= qlist.length) {
        // 全部解析失败：念心 302 直链兜底（标准音质）
        return Promise.resolve(config.nianxinTx + '?id=' + encodeURIComponent(songmid) + '&level=standard&type=mp3')
      }
      const q = qlist[i]
      return haitangResolve('tx', songmid, q)
        .then((url) => url ? url : tryOne(i + 1))
        .catch(() => tryOne(i + 1))
    }
    return tryOne(0)
  },
}

// -------- 网易云 (wy) --------
apis.wy = {
  musicUrl(musicInfo, quality) {
    const id = musicInfo.songmid || musicInfo.neteaseId || musicInfo.id || ''
    if (!id) return Promise.reject(new Error('缺少歌曲ID'))
    const qlist = qualityFallback(quality)
    const tryOne = (i) => {
      if (i >= qlist.length) {
        return Promise.resolve(config.nianxinWy + '?id=' + encodeURIComponent(id) + '&level=standard&type=mp3')
      }
      const q = qlist[i]
      return haitangResolve('wy', id, q)
        .then((url) => url ? url : tryOne(i + 1))
        .catch(() => tryOne(i + 1))
    }
    return tryOne(0)
  },
}

// -------- 酷我 (kw) --------
apis.kw = {
  musicUrl(musicInfo, quality) {
    let rid = musicInfo.songmid || musicInfo.rid || musicInfo.hash || ''
    rid = String(rid).replace(/^MUSIC_/i, '').replace(/^kw_/i, '')
    if (!rid) return Promise.reject(new Error('缺少歌曲ID'))
    const qlist = qualityFallback(quality)
    const tryOne = (i) => {
      if (i >= qlist.length) return Promise.reject(new Error('酷我解析失败'))
      const q = qlist[i]
      const br = config.kwBr[q] || '128kmp3'
      const url = config.kuwoUrl + '?f=web&user=0&source=' + encodeURIComponent(config.kuwoSource) + '&type=convert_url_with_sign&rid=' + encodeURIComponent(rid) + '&br=' + br
      return httpRequest(url, {
        headers: { 'User-Agent': 'Mozilla/5.0 (Linux; Android) AppleWebKit/537.36', 'Accept': 'application/json' },
        timeout: 10000,
      }).then((body) => {
        const j = toJson(body)
        if (j && j.code === 200) {
          const u = extractUrl(j)
          if (u) return u
        }
        return tryOne(i + 1)
      }).catch(() => tryOne(i + 1))
    }
    return tryOne(0)
  },
}

// -------- 酷狗 (kg) --------
apis.kg = {
  musicUrl(musicInfo, quality) {
    const hash = getKgHash(musicInfo, quality)
    if (!hash) return Promise.reject(new Error('缺少歌曲hash'))
    const qlist = qualityFallback(quality)
    const tryOne = (i) => {
      if (i >= qlist.length) {
        // 海棠 kg.php 302 直链兜底
        return Promise.resolve(config.haitangKg + '?type=mp3&id=' + encodeURIComponent(hash) + '&level=' + (config.levelMap[quality] || 'standard'))
      }
      const q = qlist[i]
      return haitangResolve('kg', hash, q)
        .then((url) => url ? url : tryOne(i + 1))
        .catch(() => tryOne(i + 1))
    }
    return tryOne(0)
  },
}

// -------- 咪咕 (mg) --------
apis.mg = {
  musicUrl(musicInfo, quality) {
    const sid = musicInfo.songmid || musicInfo.miguSongId || musicInfo.songId || musicInfo.resourceId || musicInfo.copyrightId || ''
    if (!sid) return Promise.reject(new Error('缺少歌曲ID'))
    const qlist = qualityFallback(quality)
    const tryOne = (i) => {
      if (i >= qlist.length) {
        // 海棠 mg.php 兜底
        return httpRequest(config.haitangMg + '?id=' + encodeURIComponent(sid) + '&type=json', { timeout: 10000 })
          .then((body) => {
            const u = extractUrl(toJson(body))
            if (u) return u
            return Promise.reject(new Error('咪咕解析失败'))
          })
      }
      const q = qlist[i]
      return haitangResolve('mg', sid, q)
        .then((url) => url ? url : tryOne(i + 1))
        .catch(() => tryOne(i + 1))
    }
    return tryOne(0)
  },
}

/* ==================== 注册请求事件 ==================== */

on(EVENT_NAMES.request, ({ source, action, info }) => {
  switch (action) {
    case 'musicUrl':
      if (apis[source]) return apis[source].musicUrl(info.musicInfo, info.type)
      return Promise.reject(new Error('不支持的源: ' + source))
  }
  return Promise.reject(new Error('不支持的 action: ' + action))
})

/* ==================== 初始化：立即就绪，后台拉新配置 ==================== */

// 立即发 inited，音源立即可用（不等待网络，避免打开软件卡顿）
send(EVENT_NAMES.inited, {
  sources: {
    tx: { name: 'QQ音乐', type: 'music', actions: ['musicUrl'], qualitys: ['128k', '320k', 'flac'] },
    wy: { name: '网易云', type: 'music', actions: ['musicUrl'], qualitys: ['128k', '320k', 'flac'] },
    kw: { name: '酷我音乐', type: 'music', actions: ['musicUrl'], qualitys: ['128k', '320k', 'flac'] },
    kg: { name: '酷狗音乐', type: 'music', actions: ['musicUrl'], qualitys: ['128k', '320k', 'flac'] },
    mg: { name: '咪咕音乐', type: 'music', actions: ['musicUrl'], qualitys: ['128k', '320k', 'flac'] },
  },
})

// 后台拉取最新参数，拉到后覆盖 config（下次搜歌即用新参数）
httpRequest(CONFIG_URL, { method: 'get', timeout: 8000 })
  .then((body) => {
    const cfg = toJson(body)
    if (cfg && typeof cfg === 'object') {
      config = Object.assign({}, DEFAULT_CONFIG, cfg)
    }
  })
  .catch(() => {
    // 拉取失败：继续用兜底 config，不报错，保证音源可用
  })
