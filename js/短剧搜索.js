var rule = {
    类型: '短剧搜索',
    title: '短剧搜索',
    host: 'https://ss.apps.dj',
    url: '/search.php?name=fyclass&page=fypage',
    searchUrl: '/search.php?name=**&page=fypage',
    searchable: 1,
    quickSearch: 1,
    timeout: 5000,
    headers: {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 13; M2102J2SC Build/TKQ1.221114.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/142.0.7444.32 Mobile Safari/537.36'
    },
    class_name: '新剧&系统&重生&下乡&年代&古代&穿越&战神&开局&逆袭&女帝&神医&总裁&萌宝&都市',
    class_url: '新剧&系统&重生&下乡&年代&古代&穿越&战神&开局&逆袭&女帝&神医&总裁&萌宝&都市',
    play_parse: true,
    lazy: $js.toString(() => {
        let html = request(input);
        let json = JSON.parse(html);
        input = {
            url: json.data.url,
            parse: 0
        };
    }),
    double: true,
    一级: $js.toString(() => {
        let d = [];
        let html = request(input);
        let list = pdfa(html, 'div.book-card');
        list.forEach(it => {
            let title = pdfh(it, 'h3.book-title&&Text');
            let img = pdfh(it, 'img.book-cover&&src').replace('\\', '').replace('amp;', '');
            let bookUrl = pdfh(it, 'a&&href');
            let bookId = bookUrl.match(/book_id=(\d+)/)[1];
            let id = 'https://api.xingzhige.com/API/playlet/?book_id=' + bookId;
            d.push({
                url: id,
                title: title,
                img: img
            });
        });
        setResult(d);
    }),
    二级: $js.toString(() => {
        let json = JSON.parse(request(input));
        let detail = json.data.detail;
        let list = json.data.video_list;

        let vod = {
            vod_name: detail.title,
            vod_pic: detail.cover,
            vod_remarks: detail.record_number,
            type_name: detail.category_schema,
            vod_content: detail.desc,
            vod_play_from: '短剧搜索',
            vod_play_url: list.map(v => `${v.title}$https://api.cenguigui.cn/api/duanju/api.php?video_id=${v.video_id}`).join('#')
        };
        VOD = vod;
    }),
    搜索: $js.toString(() => {
        let d = [];
        let html = request(input);
        let list = pdfa(html, 'div.book-card');
        list.forEach(it => {
            let title = pdfh(it, 'h3.book-title&&Text');
            let img = pdfh(it, 'img.book-cover&&src').replace('\\', '').replace('amp;', '');
            let bookUrl = pdfh(it, 'a&&href');
            let bookId = bookUrl.match(/book_id=(\d+)/)[1];
            let id = 'https://api.xingzhige.com/API/playlet/?book_id=' + bookId;
            d.push({
                url: id,
                title: title,
                img: img
            });
        });
        setResult(d);
    }),
};