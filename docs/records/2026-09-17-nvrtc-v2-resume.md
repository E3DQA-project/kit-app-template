# 中斷後續作：NVRTC v2 整合

日期：2026-09-17。此紀錄描述準備狀態，live run 另有獨立時間檔案。

## 狀態核對

中斷前僅完成 v2 interposer 與 public API 整合測試，已編出 shared library。
未完成 MOS 啟動器、private CPEx 實際攔截確認與 GUI 冷暖實驗；未提交。
因此先前「離線原型通過、MOS 尚未整合」的狀態描述正確。

## 本次補齊

- test_integration.py 增加真實 LD_PRELOAD 模式，從程序全域符號取得 API。
- 使用原始 libnrend 11.8 重跑，PASS：cold/warm identity、skipped compile、two programs、pointer lifetime、missing name、truncation、checksum、name-key isolation。
- run_experiment.py 限定同一場景，建立獨立 log、manifest、場景 SHA-256 scope 與 docs/records 記錄。
- README 明列 private CPEx 的輸入完整性限制。三個額外參數照原值轉交，但 key 尚未完整描述所有 private inputs；仍是單場景實驗原型。

## 實驗順序與判讀

先 seed 正常編譯，確認 private=1、stored names=5，並由使用者確認畫面可操作。
關閉 app 後檢查 artifact，再開始同場景 replay。暖執行須有 cache hit 與五個 name_hit、沒有原始長 compile，且畫面仍可操作，才算此情境成功。

場景指紋在 app 啟動前計算，會預熱檔案快取；兩次 run 都使用相同程序，不能拿這組數字聲稱冷磁碟讀取改善。
沒有將版本升級、小型測試或 RENDER_STABLE 當作 MOS 真正加速的證據。
