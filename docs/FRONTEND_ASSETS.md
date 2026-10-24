# 本地图表资源

看板与舆情页面使用本地资源，避免运行时依赖外部 CDN。

- `app/static/dist/echarts/echarts.min.js`：项目原有 ECharts 文件。
- `app/static/dist/echarts-gl/echarts-gl.min.js`：项目原有 ECharts GL 文件。
- `app/static/dist/echarts/echarts-wordcloud.min.js`：echarts-wordcloud 2.1.0，来源 https://cdn.jsdelivr.net/npm/echarts-wordcloud@2.1.0/dist/echarts-wordcloud.min.js ，保留文件内原始许可声明。
- `app/static/images/earth-map.jpg`：Apache ECharts 官方示例地球贴图，来源 https://raw.githubusercontent.com/apache/echarts-website/asf-site/examples/data-gl/asset/earth.jpg 。

地图使用上述等距圆柱投影贴图，平面热点按经纬度转换定位；立体视图不可用时自动切换平面视图。
