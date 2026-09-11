  # WebRTC 串流連線檢查與開通 Todo List

  目標：讓已授權使用者能從瀏覽器連線至 140.113.214.34 上的 Omniverse Kit 串流服務。

  所需連接埠：

  - TCP 49100：WebRTC 訊號協商
  - UDP 47998：WebRTC 影像與互動資料

  ## 1. 先確認主機防火牆規則

  在 140.113.214.34 上以管理員權限執行：

  sudo ufw status numbered
  sudo nft list ruleset

  檢查是否已有規則允許或拒絕：

  - TCP 49100
  - UDP 47998

  同時確認 UFW 預設策略：

  sudo ufw status verbose

  預期看到入站預設為 deny／reject 是正常的；只需為指定來源新增例外規則。

  ## 2. 確認上游網路是否也有封鎖

  請查詢實驗室交換器、防火牆或學校邊界 ACL，確認目的位址 140.113.214.34 是否僅允許 TCP 22，或有其他入站封鎖規則。

  需要確認的流量：

  來源：校園 VPN 網段或指定使用者公網 IP
  目的：140.113.214.34
  協定／目的連接埠：TCP 49100、UDP 47998
  方向：入站

  若主機 UFW 已允許、但外部仍連不上，即代表阻擋在主機以外的網路設備。

  ## 3. 決定可連線的使用者範圍

  優先順序：

  1. 校園 VPN 網段，例如 <VPN_CIDR>
  2. 指定使用者的公網 IP，例如 <USER_PUBLIC_IP>/32
  3. 不要對 0.0.0.0/0 全網開放

  請提供實際要允許的 VPN CIDR 或使用者 IP 清單。

  ## 4. 在主機 UFW 新增最小權限規則

  以下以 VPN 網段 <VPN_CIDR> 為例；請替換成真實值：

  sudo ufw allow from <VPN_CIDR> to any port 49100 proto tcp comment 'Omniverse WebRTC signaling'
  sudo ufw allow from <VPN_CIDR> to any port 47998 proto udp comment 'Omniverse WebRTC media'
  sudo ufw status numbered

  若只允許單一使用者：

  sudo ufw allow from <USER_PUBLIC_IP> to any port 49100 proto tcp comment 'Omniverse WebRTC signaling'
  sudo ufw allow from <USER_PUBLIC_IP> to any port 47998 proto udp comment 'Omniverse WebRTC media'

  不需要修改 SSH 的既有規則，也不需要開放 HTTP、HTTPS、健康檢查或其他管理連接埠。

  ## 5. 在上游防火牆加入相同的精準規則

  若實驗室或校級防火牆有入站 ACL，新增：

  ALLOW <VPN_CIDR 或 allowlist IPs>
    → 140.113.214.34 TCP/49100

  ALLOW <VPN_CIDR 或 allowlist IPs>
    → 140.113.214.34 UDP/47998

  啟用狀態式回程流量即可；不應另外對外開放寬廣的 ephemeral-port 範圍。

  請在測試期間啟用這兩個目的連接埠的 deny log。

  ## *以下由我執行

  ## 6. 啟動 Kit 串流測試 

  由應用程式管理者在主機上啟動 MOS 測試：

  cd /mnt/gen5_SSD/pierce/kit-app-template

  ./repo.sh launch nycu.mos_app.kit -- --no-window \
    --enable omni.kit.livestream.app \
    --/exts/omni.kit.livestream.app/primaryStream/streamType=webrtc \
    --/exts/omni.kit.livestream.app/primaryStream/publicIp=140.113.214.34 \
    --/exts/omni.kit.livestream.app/primaryStream/signalPort=49100 \
    --/exts/omni.kit.livestream.app/primaryStream/streamPort=47998

  確認服務已啟動：

  ss -lntup | rg '49100|47998'

  預期日誌包含：

  Started primary stream server on signal port 49100 and stream port 47998

  ## 7. 由 VPN／allowlist 外部用戶端驗證

  使用者從核准網路開啟瀏覽器串流客戶端，並在 Chrome 開啟：

  chrome://webrtc-internals

  驗收條件：

  - TCP 49100 可連線。
  - WebRTC ICE candidate pair 狀態出現 succeeded。
  - 可看到畫面、可操作滑鼠與鍵盤。
  - 防火牆 deny log 沒有阻擋 UDP 47998。

  若 UI 出現但黑畫面，優先檢查：

  使用者端是否允許 outbound UDP → 140.113.214.34:47998

  ## 8. 測試後收尾

  若測試失敗，保留防火牆日誌供分析，但不要擴大開放範圍。

  若測試成功：

  - 保持來源限制為 VPN 或 allowlist。
  - 為瀏覽器前端與訊號通道規劃 TLS。
  - 在對外正式使用前加入登入／工作階段授權。
  - 為 nycu.e3dqa_scene_viewer 額外關閉不適合遠端使用者操作的編輯、檔案與開發功能。