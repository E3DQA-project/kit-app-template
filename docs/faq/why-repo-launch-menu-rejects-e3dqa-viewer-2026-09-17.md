# 為什麼 `repo.sh launch` 選單拒絕 E3DQA Viewer？

## 問題

執行沒有指定 app 的 `./repo.sh launch` 時，出現
`Redefinition of an existing table`，並指向
`nycu.e3dqa_scene_viewer.kit`。

## 答案

這不等於 E3DQA Scene Viewer 已經不能使用。這次失敗的是 local launch
選單在列出所有 app 時，以嚴格 TOML reader 解析每一個 `.kit` 檔。
E3DQA Viewer 的設定中有兩個 `[settings.app.exts]` 區段；Kit 的設定載入
流程可以合併這類設定，但這個嚴格 TOML reader 會先拒絕它。

因此目前仍可直接指定要開的 app：

```bash
./repo.sh launch nycu.e3dqa_scene_viewer.kit
```

MOS 則使用：

```bash
./repo.sh launch nycu.mos_app.kit
```

## 後續修正方向

修正 launch 選單，使它列出 `.kit` 檔名時不必嚴格解析所有 legacy app 的
TOML。這樣能恢復無參數選單，同時不必修改 E3DQA Viewer 的既有設定。
