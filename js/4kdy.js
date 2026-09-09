var rule = {
    title: '快盘[搜]',
    host: 'https://www.4kdy.vip',
    url: '/4K-list/fyclass-fypage.html',
    searchUrl: '/4K-search/**----------fypage---.html',
    searchable: 2,
    quickSearch: 0,
    headers: {
        'User-Agent': 'PC_UA',
    },
    timeout: 5000,
    class_name: '电影&电视剧&动漫',
    class_url: '1&2&3',
    play_parse: true,
    //推送阿里播放  支持影视壳
    lazy: $js.toString(() => {
        let url = input.startsWith('push://') ? input : 'push://' + input;
        input = {parse: 0, url: url};
    }),
    一级: '.myui-vodlist li;a&&title;a&&data-original;.pic-tag-top&&Text;a&&href',
    二级: {
        "title": ".myui-vodlist__thumb&&title",
        "img": "img&&data-original",
        "desc": ";;;;",
        "content": ".sketch&&p",
        "tabs": "js:TABS=['4kdy']",
        "lists": ".myui-down__list li",
        "list_text": "a:eq(0)&&Text",
        "list_url": "a:eq(0)&&href",
    },
    搜索: '.myui-vodlist__media li;a&&title;a&&data-original;.pic-tag-top&&Text;a&&href',
}