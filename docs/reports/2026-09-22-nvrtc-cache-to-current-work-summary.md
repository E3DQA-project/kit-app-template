# MOS：從 NVRTC cache 到目前工作的總結

_更新日期：2026-09-22。範圍：`cleanup` branch 上，從找出約 19 秒 NVRTC 編譯延遲、實作預設 cache，到目前 Matrix-3D 相機／鏡像資料診斷的工作。_

## 一句話結論

MOS 的「第一次看到場景很慢」並不只有一個來源。已經**實際排除**的一個固定大成本，是 Kit 內嵌 NVRTC 在 RTX 5090 上的約 **18.952 秒 PTX 編譯**；同一份 scene list 第二次啟動可由本機 SSD cache 重用，該步驟降為約 **333 ms**。但另一組較早期的量測也顯示，Kit RTX 仍可能在 `USD_ASSETS_LOADED` 前出現約 20 秒的內部 graphics synchronization wait；這不是 NVRTC cache 已經證明能完全消除的成本。

目前 MOS 的相機初始位置與 WASD 操作已修正；另有四個 Matrix-3D 樣本仍被觀察到場景本身左右鏡像。後者是資料座標／重建管線問題，不能誤當成 MOS 相機問題，也尚未對 NuRec 幾何做任何破壞性修改。

## 1. 為什麼會做 NVRTC cache

在長時間場景轉換的調查中，使用者可見的等待常約 20–30 秒。較完整的一次 lifecycle run 顯示：

| 里程碑 | 自 `BEGIN` 起 | 意義 |
| --- | ---: | --- |
| `STAGE_OPENED` | 129 ms | USDZ 已成為 Kit 的 active stage。 |
| `RENDER_STABLE` | 7.726 s | 畫面擷取連續穩定；它不保證畫面不是黑的，也不代表互動完成。 |
| `USD_ASSETS_LOADED` | 27.336 s | Kit 宣告 late asset/streaming completion。 |
| `VIEWER_STAGE_LOADED` | 27.353 s | viewer completion gate 釋放。 |
| 首次刻意輸入 | 27.829 s | MOS 收到 `W`。 |

後續針對 renderer library 的實驗發現：Kit embedded NVRTC 對目前 scene-list scope 編譯 PTX 時，單次真實編譯需要約 19 秒。這個時間與使用者看到的大缺口高度一致，因此先實作一個保守、可關閉的重用機制。它快取的是 NVRTC 產生的 PTX 及 Kit 所需的 lowered names；不是把 USDZ、材質、貼圖或 NuRec 場景檔複製到記憶體。

## 2. 實作了什麼

### 預設啟用、但仍可繞過的 cache 路徑

正常啟動：

```bash
./repo.sh launch nycu.mos_app.kit
```

現在會由 repository 的 MOS launch routing 自動套上 NVRTC interposer。它：

1. 以 `LD_PRELOAD` 載入 repo 編譯的 interposer，而非修改 Kit 安裝內容。
2. 以 renderer library digest、NVRTC program identity 與目前 `mos_scenes.json` 的 scope 建立 cache key。
3. 將 PTX artifact 與同一組 lowered names 放在使用者可存取的本機 SSD 專用目錄：`/mnt/gen5_SSD/pierce/mos-nvrtc-cache-v2/`。
4. `auto` 模式先嘗試安全 replay；沒有 artifact、key 不相符或 artifact 無效時，回到原本 NVRTC 編譯並儲存新結果。
5. 保留 `--no-nvrtc-cache`，可啟動未包裝的 MOS 作為回歸／比較基線。

實作主要位於：

- `tools/mos_nvrtc_cache_v2/interposer.cpp`：攔截 NVRTC、儲存與回傳 PTX/name 結果。
- `tools/mos_nvrtc_cache_v2/default_launch.py`：設定預設 `auto` 環境與 cache root。
- `tools/repoman/mos_launch.py`、`tools/repoman/launch.py`：只把 `nycu.mos_app.kit` 導向此 wrapper；其他 app 不共用這條快取路徑。
- `tools/mos_nvrtc_cache_v2/test_integration.py`、`test_default_launch.py`：檢查真實 embedded NVRTC 的 seed/replay/fallback 與 launcher 環境。

此設計的邊界很重要：它沒有替不同 scene 猜測可否共用結果。能命中的是**相同、相容 scope**的已編譯結果；換 scene list、renderer library 或 program identity 時，會重新編譯一次並建立另一個 artifact。這比錯誤 replay 造成黑畫面或 renderer 不穩定安全。

## 3. 已完成的 NVRTC 驗證

| 實驗 | 啟動方式 | 關鍵觀察 | 結果 |
| --- | --- | --- | --- |
| cold run（2026-09-17） | 正常 MOS launch、cache 預設 `auto` | `compile_begin` 後 `compile result=0 ms=18952`；產生 6,577,549-byte artifact | 第一次真的編譯並存檔。使用者確認場景可見、相機可移動。 |
| warm run（2026-09-17） | 相同 scene list、同一正常 launch | `tracked → hit` 約 333 ms、五個 `name_hit`、沒有 `compile_begin` / `stored` | 成功重用先前 PTX，移除了此段重複的 18.952 秒編譯。 |
| safety / fallback tests | 無 GUI 的真實 embedded NVRTC 子程序 | seed、auto hit、replay 與損壞 artifact fallback | cache 失效時會回到正常 compile，而非假裝成功。 |

五個 warm-hit restored lowered names 為：`preProcessParticles`、`projectOnTiles`、`expandTileProjections`、`render`、`prepareScene`。

## 4. cache 解決了什麼；沒有解決什麼

### 已解決／可重用的部分

- 對同一相容 scene-list scope，避免重複的 embedded-NVRTC PTX 編譯。
- 讓一般 `./repo.sh launch nycu.mos_app.kit` 不必再手動 opt-in。
- cache 放在本機 SSD 而非 NAS，也不改寫 Kit 安裝目錄或原始 dataset。

### 不應過度宣稱的部分

- cache hit **不等於**每個從未載入的場景都必須再花 19 秒；NVRTC program 的 key 是 renderer/program/scope 層級，不是「每一個 USDZ 各自一份」。因此同一次 scope 裡第一個觸發者完成編譯後，後面未單獨看過的 scenes 也可能很快。
- cache 不是完整 scene cache；它不保證 USD asset resolving、texture/material streaming、GPU residency、swapchain present 或 viewer gate 都變快。
- 曾出現的黑畫面／hang 不能單靠 cache log 判為成功；GUI 必須確認可見且可操作。

## 5. 與 NVRTC 並行存在的 20 秒 renderer 問題

在另一組較早且較完整的 instrumented run，延遲被定位到 `RENDER_STABLE → USD_ASSETS_LOADED` 約 **19.610 秒**（`USD_ASSETS_LOADING → USD_ASSETS_LOADED` 約 **20.249 秒**）。這兩個區間與前面的 lifecycle 有重疊，不能相加成 40 秒。

已收集的負面／定位證據：

- `BEGIN → STAGE_OPENED` 只有 129 ms：頂層 USDZ open 與 MOS Python setup 不是主因。
- 對等 NAS 與 SSD 的中位數約 20.681 s 與 20.944 s：不是單純 SSD/NAS 頻寬瓶頸。
- MDL/material activity spans 只有約數毫秒，未解釋 20 秒。
- Vulkan、CUDA trace 未看到持續 20 秒的普通 kernel 或 memcpy。
- 同段期間 GPU 使用率平均 5%、最高 19%，VRAM 約 4.45–5.56 GB / 32 GB：不是一般 GPU 滿載或顯存不足。
- CPU trace 看到約 20.7 秒巢狀於 `RtxHydraEngine::endFrame` 的 `CommandList::waitForLastSubmission`。

因此目前最精確的說法是：Kit RTX graphicsmux 的 submission/completion path 正在等待某個前一份 submission/fence/resource 完成；現有 trace 尚未揭露「究竟哪個 resource 或 driver operation」。這是高優先級線索，但不等於已證明 Blackwell driver bug，也不等於 Python 加平行載入就能修好。

先前還做過兩個有用但不充分的設定調整：

- 關閉多 GPU 模式後，對照 interval 約從 20.852 s 到 19.591 s（約 6% 改善），應保留 single-GPU，但不是根治。
- Kit 110.2 與 asynchronous shader-finalization 排除了 cold-start 的 `Waiting for RtPso async group async compilation` 卡住，使 prompt 約 3 秒可用；它與場景晚期 20 秒 wait 是分開的問題。

## 6. cache 後的相機與資料品質工作

在使用 cache 後實際巡覽 Matrix-3D scenes 時，發現兩種不同問題，已刻意分開處理。

### 6.1 相機 pose reflection：已在 MOS app 修復

部分相鄰 `geom_optim/output/cameras.json` 的 3×3 rotation determinant 是 `-1`。真正的 rotation 應為 `+1`；這種 reflected pose 會造成初始視角翻到背面、roll 不對或左右操作反向。

`6246582 fix: repair reflected Matrix-3D camera poses` 新增純 Python helper，僅在 determinant 約為 `-1` 時翻轉 camera-local X basis，並記錄 `CAMERA_HANDEDNESS_REPAIRED`。proper pose（約 `+1`）不變；其他異常 determinant 只記錄、不猜修法。GUI 已確認初始視角與 camera navigation 正常。

這個修正位於 MOS consumer boundary，不改 NAS dataset、USDZ、PLY 或 upstream `cameras.json`；所以未來上游修好後可安全移除。

### 6.2 幾何左右鏡像：仍是未解資料問題

使用者確認下列樣本在相機修復後仍是整個場景左右鏡像：`0030`、`0088`、`0106`、`0114`。`0014` 也有 determinant `-1`，但場景幾何正常；`0037`、`0100` 則為 `+1` 且正常。

所以：**camera determinant 可以分類 camera pose defect，不能分類 geometry mirror。** 已檢查的 USDZ 外層 `default.usda` / `gauss.usda` 均有同樣的 Z-up、identity transform 與 NuRec layout，沒有可直接修掉的外層 `scale(-1,1,1)`。PLY-to-USDZ converter 也直接取 PLY `x/y/z`，未對特定 index 啟用座標轉換。

最合理的剩餘範圍是 Matrix-3D/Pano-GS 上游的 PLY 與 camera coordinate relationship，或更早的 reconstruction convention；尚未證實 PLY 幾何本身在哪一步被鏡像。下一個能縮小範圍的證據是：以 `condition/cameras.npz` frame 0 render 原始 PLY，和保留的 `condition/firstframe_rgb.png` 對照，至少比較正常 `0014` 與鏡像 `0030`。

對 NR 3D scene QA 而言，左右鏡像未必破壞同一方法內、同一方向 variants 的相對品質排序，但會成為跨方法比較的混雜因子（觀察者可能評的是語意方向，而非重建品質）。在確認／canonicalize 前，這四個樣本應標為 orientation-unresolved，避免與正常方向的方法直接混合比較。

## 7. 現在可採取的下一步

1. **確認 cache 的實際 coverage。** 對每個預計的 scene-list scope 做一次正常 cold launch，保留 `MOS_V2` log；第二次相同 scope 應為 hit。不要把「後續 scene 很快」誤解成每個場景各自被預編譯。
2. **保留 GUI regression。** 每次 cache 相關改動都要跑：cold、warm hit、`--no-nvrtc-cache`；確認 viewport 有內容且可移動，而非只看 terminal。
3. **若 20 秒仍存在，追 graphics backend 邊界。** 用最小單 scene、盡量低干擾的 Nsight Graphics / driver timeline，將 `waitForLastSubmission` 對應到 fence、queue submission、resource residency 或 pipeline event；暫時不要優先投入 Python async loading。
4. **做 PLY/frame-image 對照。** 它將回答鏡像是在原始 reconstruction 前、訓練 PLY/camera pairing，還是 consumer export 後才出現。
5. **QA protocol 加 orientation 欄位。** 在做跨 generation/reconstruction method 的主觀比較前，先做小型 blinded normal/mirrored pilot，或將所有候選 scene canonicalize 到同一座標慣例。

## 8. 相關證據與原始記錄

- `docs/records/2026-09-17-default-nvrtc-cache-cold-run.md`
- `docs/records/2026-09-17-default-nvrtc-cache-warm-run.md`
- `docs/records/2026-08-20-mos-scene-loading-consolidated.md`
- `docs/wiki/mos-scene-loading-current-knowledge.md`
- `docs/faq/mos-scene-loading.md`
- `docs/debug/camera-geometry-mirroring-followup-2026-09-22.md`
- `docs/faq/why-camera-handing-is-repaired-in-mos-app-2026-09-22.md`
- `docs/faq/does-left-right-mirroring-matter-for-nr-3d-scene-qa-2026-09-22.md`

## 9. 狀態標記

| 項目 | 狀態 |
| --- | --- |
| NVRTC cache 預設整合、測試、cold/warm GUI 驗證 | 已完成並已推送 |
| NVRTC compiled PTX 的相同 scope 重用 | 已實測成功 |
| 所有場景／所有 scope 都一勞永逸不再編譯 | 不宣稱；取決於 cache key 與 renderer program identity |
| 約 20 秒 `waitForLastSubmission` 的具體 fence/resource owner | 未找到 |
| MOS camera reflected-pose 修正 | 已完成並已推送 |
| 四個 NuRec scene 的左右鏡像根因／修正 | 未完成；尚未改動幾何資料 |
