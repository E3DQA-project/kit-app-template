# 修復 app 選單會影響 MOS NVRTC cache 嗎？

不會。兩者位於 local launch tool 的不同步驟：

1. **選單修復**只影響未指定 app 時，`./repo.sh launch` 如何列出 `.kit`
   檔案。
2. **MOS cache**只在已選定 `nycu.mos_app.kit` 後，包裝它的實際啟動命令，
   設定 preload shim 與 `/mnt/gen5_SSD/pierce/mos-nvrtc-cache-v2/`。

修復選單時不會修改 `tools/mos_nvrtc_cache_v2/`、cache artifact、scene list，
或指定 MOS app 的 cache routing。回歸測試會另外確認指定 MOS app 仍走 cache
wrapper。
