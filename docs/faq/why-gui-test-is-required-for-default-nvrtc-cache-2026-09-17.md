# 為什麼自動測試後仍需要 GUI 測試？

需要。embedded-NVRTC 自動測試只驗證 interposer 在小型真實 NVRTC program 上能在 `auto` 模式命中、回傳 PTX／lowered names，並在快取損壞時改走正常編譯。它不會啟動 Kit、開啟 USDZ、建立 CUDA module 或顯示 viewport。

預設 cache 的 GUI 驗證要等正常 `./repo.sh launch nycu.mos_app.kit` 路由完成後進行。必做三次：第一次 default launch 建立 artifact；第二次相同 scene-list default launch 必須有 `hit`、五個 `name_hit`、沒有原始 NVRTC compile，且使用者確認畫面可見與相機可移動；第三次加 `--no-nvrtc-cache`，確認可回到無 preload 的原始行為。

因此目前的自動測試是必要的底層安全網，不是 GUI 功能完成宣告。每次 GUI run 要在使用者正常關閉 app 後寫入 `docs/records/`。
