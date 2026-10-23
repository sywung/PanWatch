// 由 gen-zh-tw.py 自 zh-CN 產生；手動修正請寫進腳本的 OVERRIDES，不要直接改本檔。
export const bizUi = {
  markets: { TW: '台股', TWF: '期貨', CN: 'A股', HK: '港股', US: '美股' },
  logsLogger: '日誌源', amountWithCurrency: '加倉金額（{{currency}}）', approximatelyWithCurrency: '約 {{currency}} {{amount}}',
  dispersion: {
    title: '台股集保股權分散表',
    description: '集保戶股權分級與每週變化',
    loading: '正在載入集保資料…',
    failed: '集保資料載入失敗',
    retry: '重試',
    empty: '尚無集保資料',
    summary: '集保股權摘要',
    dataDate: '資料日期',
    holders: '總人數',
    weeklyChange: '週增減',
    holderUnit: '人',
    thousandLot: '千張以上大戶',
    bigHolders: '400 張以上大戶',
    percentagePointUnit: 'pp',
    retail: '散戶',
    mid: '中實戶',
    big: '大戶',
    levelsTitle: '集保分級',
    levelColumn: '持股級距',
    holdersColumn: '人數',
    sharesColumn: '股數',
    pctColumn: '占比',
    historyTitle: '每週趨勢',
    thousandTrend: '千張以上大戶 (%)',
    holdersTrend: '總人數',
    trendAccumulating: '趨勢從 {{date}} 起每週累積，目前只有 {{count}} 週',
    chartUnavailable: '圖表庫尚未載入',
    level1: '1–999 股',
    level2: '1–5 張',
    level3: '5–10 張',
    level4: '10–15 張',
    level5: '15–20 張',
    level6: '20–30 張',
    level7: '30–40 張',
    level8: '40–50 張',
    level9: '50–100 張',
    level10: '100–200 張',
    level11: '200–400 張',
    level12: '400–600 張',
    level13: '600–800 張',
    level14: '800–1,000 張',
    level15: '1,000 張以上',
    level16: '差異數調整',
    level17: '合計',
  },
  klineModal: { title: 'K線：{{symbol}}', fallbackTitle: 'K線', description: '日K/周K/月K切換，含MA/成交量/MACD。', noStock: '未選擇股票', attribution: '圖表：TradingView Lightweight Charts™' },
  interactiveKline: { loadFailed: '載入K線失敗', title: 'K線圖', ma: 'MA', ma60: '季線 MA60', ma120: '半年線 MA120', ma240: '年線 MA240', boll: 'BOLL', vwap: 'VWAP', macd: 'MACD', rsi: 'RSI', kd: 'KD', obv: 'OBV', dispersion: '千張大戶', dispersionTitle: '千張大戶持股 %', chan: '纏論', chanDisabled: '纏論僅適用於日線', drawings: { hline: '水平線', trend: '趨勢線', delete: '刪除', clearAll: '清除全部', confirmClear: '確定清除？', hlineHint: '點選圖表放置水平線', trendHint: '點選兩次畫出趨勢線（Esc 取消）' }, intervals: { day: '日K', week: '周K', month: '月K', fiveMinutes: '5分', fifteenMinutes: '15分', thirtyMinutes: '30分', sixtyMinutes: '60分' }, loadingEarlier: '載入更早資料…', refresh: '重新整理', libraryFailed: '圖表庫載入失敗（網路受限時可能發生）。可稍後重試或檢查網路/代理。', metrics: { latest: '最新價', change: '漲跌', amplitude: '振幅', range: '可見區間高低', averageVolume: '均量' }, hover: { open: '開盤價', close: '收盤價', high: '最高價', low: '最低價', ma5: 'MA5', ma10: 'MA10', ma20: 'MA20', ma60: 'MA60', ma120: 'MA120', ma240: 'MA240', bollUpper: 'BOLL上軌', bollMiddle: 'BOLL中軌', bollLower: 'BOLL下軌', vwap: 'VWAP', kd: 'KD K / D', obv: 'OBV', macd: 'MACD線', signal: '訊號線', rsi: 'RSI' }, momentum: '副圖指標（{{rsi}}）', momentumRsi: ' + RSI強弱線', help: 'MACD 用來看趨勢動能和拐點；RSI 用來看是否偏熱/偏弱（一般 70 以上偏熱，30 以下偏弱）。', tenThousand: '{{value}}萬' },
  chan: { labels: { buy: '買{{type}}', sell: '賣{{type}}' }, direction: { up: '向上', down: '向下' }, title: '纏論', day: '日線', thirtyMinutes: '30 分鐘', confirmed: '已確認', pending: '未確認', pivot: '中樞', position: { above: '中樞上方', inside: '中樞內', below: '中樞下方', none: '無中樞' }, latestPoints: '最近買賣點', nesting: '區間套', nestingBuy: '確認買進方向', nestingSell: '確認賣出方向', nestingPending: '未確認', lastPoint: '最後一筆：{{value}}', pivotRange: '中樞 {{zd}}–{{zg}} · {{position}}' },
  tour: {
  "title": "新手操作引導",
  "welcome": "跟著高亮提示完成一條連貫流程：新增自選、檢視行情、連線 AI 並生成第一份分析，然後按需設定提醒和通知。高亮區域可以直接點選，隨時可暫停。",
  "flow": "完整操作流程",
  "start": "開始操作引導",
  "progress": "第 {{current}} / {{total}} 步",
  "pause": "暫停引導",
  "back": "上一步",
  "next": "下一步",
  "skip": "跳過此步",
  "finish": "完成引導",
  "verified": "操作已完成，可以繼續",
  "actOnPage": "請點選高亮區域，在頁面上完成這一步。",
  "chooseExisting": "已有自選？選擇一隻繼續",
  "waiting": "正在尋找頁面上的操作入口…",
  "leftPage": "你已離開目前引導頁面。進度已儲存。",
  "return": "回到目前步驟",
  "openAnalysis": "開啟首次分析",
  "analysisNotReady": "請先檢視行情，並在設定中測試預設模型。",
  "doneTitle": "操作引導已完成",
  "doneDescription": "你可以繼續使用這些頁面，也可以從「開始使用」重新開啟引導。跳過的可選項隨時可以在設定中補充。",
  "doneAction": "開始使用",
  "steps": {
    "stock": {
      "title": "先新增一隻自選",
      "description": "點選高亮的「新增自選」，搜尋股票並確認新增。已有自選也可以直接選一隻。"
    },
    "stockForm": {
      "title": "搜尋並確認新增",
      "description": "輸入代碼或名稱，選擇搜尋結果，再點選「確認新增」。儲存後會進入行情步驟。"
    },
    "stockChoose": {
      "title": "選擇一隻現有自選",
      "description": "點選任意一張自選卡片或股票名稱，用它完成這次體驗。範例股票不會自動算作已選擇。"
    },
    "quote": {
      "title": "親手重新整理一次行情",
      "description": "點選高亮的重新整理按鈕，取得剛才所選股票的真實行情。成功後會高亮對應卡片。"
    },
    "quoteRead": {
      "title": "檢視這隻股票的行情",
      "description": "這裡顯示價格和漲跌幅，點選股票名稱還能開啟詳情。注意資料時間，休市期間可能顯示最近交易日行情。點選下一步繼續。"
    },
    "ai": {
      "title": "連線並測試預設模型",
      "description": "在這裡新增 AI 服務商和模型，設定一個預設模型，再點選它旁邊的測試按鈕。已有預設模型可直接測試。"
    },
    "providerForm": {
      "title": "填寫服務商連線資訊",
      "description": "填寫名稱、介面地址和 API Key 後儲存。接著為這個服務商新增模型。"
    },
    "modelForm": {
      "title": "新增一個可用模型",
      "description": "選擇服務商並填寫模型標識後儲存，也可以從發現結果新增。返回列表，將模型設為預設並測試。"
    },
    "analysis": {
      "title": "開啟首次分析",
      "description": "點選這個入口，在彈窗裡確認生成。分析使用剛才驗證的預設模型，不會自動啟動。"
    },
    "analysisForm": {
      "title": "生成並等待結果",
      "description": "點選「生成首次分析」。這次會實際呼叫模型併產生用量，你也可以關閉彈窗，稍後回來檢視。"
    },
    "analysisRead": {
      "title": "閱讀第一份分析",
      "description": "結果儲存在這裡，附有模型和生成時間。閱讀後點選下一步，去試試價格提醒。"
    },
    "alert": {
      "title": "設定一個價格提醒",
      "description": "點選「新建提醒」，為剛才的股票填寫觸發條件。這個步驟可選，也可以跳過。"
    },
    "alertForm": {
      "title": "填寫並儲存提醒規則",
      "description": "確認標的，填寫規則名稱、價格條件和通知管道，然後儲存。規則會實際生效，按你設定的條件監控。"
    },
    "notify": {
      "title": "測試通知管道",
      "description": "在這裡新增並啟用通知管道，再點選紙飛機測試按鈕。這會傳送一條真實測試訊息；暫時不需要可以跳過。"
    },
    "channelForm": {
      "title": "設定通知管道",
      "description": "選擇管道型別並填寫接收端資訊，儲存後啟用，再點選列表中的紙飛機按鈕測試。"
    }
  }
},
  guideCenter: {
  "title": "引導中心",
  "description": "從第一次使用到進階探索，所有操作引導都在這裡。每條路線獨立儲存進度，完成後也可以再次體驗。",
  "mainTitle": "主流程：從自選到第一份 AI 分析",
  "mainBadge": "首次自動進入 · 必做步驟不可跳過",
  "mainDescription": "新增自選 → 檢視行情 → 連線 AI → 生成分析。價格提醒和通知接在後面，可按需完成；整個流程可以暫停，稍後繼續。",
  "moreTitle": "繼續探索",
  "moreDescription": "進入真實頁面跟著高亮提示操作。探索路線的進度表示已閱讀提示；實際設定和執行仍由你在頁面上確認。",
  "replay": "再次體驗",
  "inProgress": "進行中",
  "notStarted": "未開始",
  "trackProgress": "已瞭解 {{done}} / {{total}} 步",
  "explore": "開始探索",
  "understood": "我已瞭解，繼續",
  "finishTrack": "完成並返回中心",
  "closeDialog": "在這裡完成操作，或關閉彈窗後繼續引導。",
  "explorationHint": "可以先嚐試高亮控制元件，再確認已瞭解這一步。",
  "tracks": {
    "opportunities": {
      "title": "發現與評估機會",
      "description": "學會篩選候選、閱讀訊號依據，並在驗證中心回看建議結果。",
      "steps": {
        "filters": {
          "title": "篩選你關心的機會",
          "description": "點選市場、來源、策略或風險篩選，再點選應用。沒有候選時可放寬條件；候選由分析任務產生，不會因為進入引導而生成。"
        },
        "signals": {
          "title": "閱讀訊號，再決定是否關注",
          "description": "有候選時點選卡片檢視股票詳情，先看資料時間、依據、入場區間和失效條件，再主動新增自選。空列表表示目前沒有匹配訊號，可以繼續瞭解驗證中心。"
        },
        "evaluation": {
          "title": "回看建議的後續表現",
          "description": "使用這裡的篩選檢視歷史建議及後續表現，點選有記錄的行檢視依據。沒有已執行的分析時這裡會為空；完成主流程後可回來繼續檢視。"
        }
      }
    },
    "paper": {
      "title": "體驗模擬盤",
      "description": "認識模擬資金、市場分配、執行開關與持倉記錄，按自己的選擇啟動。",
      "steps": {
        "capital": {
          "title": "先檢視模擬資金配置",
          "description": "點選資金配置，檢視總資金和 A 股、港股、美股分配比例。修改後需要主動儲存；這是模擬帳戶，獨立於實際持倉。"
        },
        "controls": {
          "title": "瞭解模擬盤的執行開關",
          "description": "這個開關控制模擬盤是否自動處理訊號。確認資金配置後再決定是否啟動；上方掃描按鈕會處理目前訊號，可能產生模擬交易。引導不會替你開啟或掃描。"
        },
        "positions": {
          "title": "檢視持倉與交易記錄",
          "description": "這裡展示模擬持倉、盈虧和可賣數量。有成交後可從上方檢視已結束的交易。A 股遵守 T+1；沒有訊號或交易時列表為空，可以稍後回來。"
        }
      }
    },
    "assistant": {
      "title": "使用研究助手",
      "description": "從自己的問題開始，瞭解工具許可權和後台任務，保留自己的執行選擇。",
      "steps": {
        "composer": {
          "title": "提出一個具體問題",
          "description": "在輸入框寫下標的、時間範圍和你關心的問題，也可以選取股票。點擊傳送才會實際呼叫模型；暫時沒有模型時，先完成主流程中的 AI 連線。"
        },
        "context": {
          "title": "檢視助手的工具許可權",
          "description": "點選這個按鈕檢視可用工具及許可權。涉及寫入或其他需要確認的操作，助手會先請求審批；請閱讀操作內容再決定是否允許。"
        },
        "activity": {
          "title": "找到會話與進行中的任務",
          "description": "這裡可以返回會話列表、新建研究或檢視目前上下文。傳送問題後，任務進度和待審批操作會出現在會話中；離開頁面後仍可以回來繼續檢視。"
        }
      }
    },
    "automation": {
      "title": "設定日常分析任務",
      "description": "認識執行時間、繫結標的與歷史記錄，再按需啟用定時分析。",
      "steps": {
        "schedule": {
          "title": "檢視實際執行時間",
          "description": "點選執行週期，檢視時區和接下來執行時間，再按需要修改並儲存。定時任務只有啟用後才會執行，會使用所選模型額度。"
        },
        "binding": {
          "title": "選擇任務關注的標的",
          "description": "點選繫結標的，再點選股票名稱切換繫結狀態，修改會立即儲存。首次分析不會替你繫結或開啟定時任務。"
        },
        "history": {
          "title": "核對任務歷史與結果",
          "description": "在這裡按任務型別或標的篩選執行記錄，點選記錄檢視結果、模型和時間。尚未執行時列表為空；失敗記錄可用於檢查模型與資料設定。"
        }
      }
    },
    "datasources": {
      "title": "檢查行情與研究資料來源",
      "description": "認識資料分類、優先順序和連線測試，處理缺失資料時有地方可查。",
      "steps": {
        "catalog": {
          "title": "按資料類別查詢來源",
          "description": "點選分類標題展開或收起。行情、K 線、新聞和基本面有各自的資料來源；優先順序較高的來源會優先嚐試，失敗後可能使用其他來源。"
        },
        "config": {
          "title": "檢視來源設定",
          "description": "展開分類後點擊設定，檢視優先順序、測試標的和必要的連線參數。需要金鑰的來源由你填寫並儲存；無需金鑰的內建來源也可以直接測試。"
        },
        "test": {
          "title": "測試連線並閱讀結果",
          "description": "點選播放按鈕測試已啟用的來源，檢視資料時間、返回數量和缺失明細。測試成功表示這次請求可用，其他市場或標的仍可能缺失；關閉結果彈窗後繼續。"
        }
      }
    }
  }
},
  gettingStarted: {
  title: '開始使用', description: '從一個關注的標的開始，親手完成第一次行情檢視和分析。進度會自動儲存。',
  bannerTitle: '讓盯盤俠開始為你工作', bannerDescription: '跟著高亮提示，在真實頁面上完成第一次操作。',
  continue: '繼續設定', start: '開始設定', later: '稍後處理', resume: '恢復引導', review: '檢視開始指南',
  progress: '已完成 {{done}} / {{total}} 個必要步驟', loading: '正在讀取設定進度…', retry: '重試',
  completed: '已完成', pending: '待完成', skipped: '稍後處理', optional: '可選', required: '必要',
  quotesGoal: '先看行情', quotesGoalDesc: '無需 AI 服務，先關注標的、檢視價格。',
  aiGoal: '啟用 AI 分析', aiGoalDesc: '在行情基礎上連線模型，生成第一份分析。',
  next: '下一步', backHome: '返回首頁', doneTitle: '你已完成所選目標', doneDescription: '現在可以日常檢視行情或分析。價格提醒和通知可以隨時繼續設定。',
  chooseStock: '選擇關注的標的', existingStocks: '從自選列表選擇', stockPlaceholder: '請選擇一個標的',
  sampleHint: '首次啟動的範例標的也可以選用；選擇表示你確認關注它，無需錄入持倉。',
  search: '搜尋並新增標的', searchPlaceholder: '輸入名稱或代碼', market: '市場', markets: { CN: 'A 股', HK: '港股', US: '美股' },
  searching: '搜尋中…', noResults: '沒有找到匹配標的，可在持倉頁手動新增。', manageStocks: '管理或手動新增自選',
  addStock: '新增並選擇', currentStock: '目前標的：{{name}}（{{symbol}}）', selectFirst: '先選擇一個關注的標的，再繼續此步驟。',
  fetchQuote: '檢視行情', refreshQuote: '重新整理行情', quoteHint: '休市時會展示最近一次報價。行情時間和本次取得時間可能不同。',
  source: '資料來源：{{value}}', sourceTime: '行情時間：{{value}}', observedAt: '取得時間：{{value}}', unknown: '來源未提供',
  dataSources: '檢查資料來源', configureAi: '設定 AI 服務', aiHint: '新增服務商和模型，設為預設並測試。儲存設定不等於連線成功。測試會呼叫一次所選模型。',
  model: '預設模型', modelPlaceholder: '請選擇一個模型', testModel: '測試預設模型', modelVerified: '目前預設模型已測試通過',
  configureChanged: '修改服務地址、金鑰或模型後，需要重新測試。', runAnalysis: '生成首次分析', rerunAnalysis: '重新生成分析',
  analysisHint: '使用預設模型進行一次簡短分析，可能產生服務商費用。結果包含觀察、依據、關注點和資料限制。',
  analysisScope: '首次分析不會開啟定時任務、傳送外部通知或產生模擬盤交易。',
  analysisRunning: '正在取得資料並生成分析，你可以離開頁面；回來後會恢復進度。',
  analysisFailed: '本次分析未完成，可以修正設定後重試。', analysisModel: '分析模型：{{value}}', analysisTime: '生成於：{{value}}',
  readAnalysis: '怎樣閱讀這份分析', readAnalysisHint: '先看結論對應的資料依據，再看資料時間和限制。缺少資料的判斷需要繼續核實。',
  advanced: '進一步使用', advancedHint: '盤前 / 盤中 / 收盤 Agent 用於日常監控；TradingAgents 深度分析會進行多輪研究，耗時和費用更高，可按需手動啟動。', agents: '瞭解分析任務',
  createAlert: '建立價格提醒', alertTitle: '設定第一個價格提醒', alertHint: '設定你關心的條件，命中後會記錄在應用內通知中心。外部推播需選擇通知管道。',
  manageAlerts: '管理提醒', alertSaved: '所選標的已有啟用中的提醒',
  configureNotify: '設定通知管道', notifyHint: '通知是可選的。新增管道後，主動傳送測試訊息；傳送成功才算通過。',
  channel: '通知管道', channelPlaceholder: '請選擇啟用的管道', testChannel: '傳送測試通知', notifyVerified: '已有啟用的管道傳送測試成功',
  deliveryHint: '測試成功表示傳送端接受了訊息，請在接收端確認收到。正式提醒仍需在規則中選擇該管道。',
  skippedHint: '這一步已留待稍後，可以隨時繼續。', doNow: '現在設定',
  steps: {
    stock: { title: '關注一個標的', description: '選擇已有自選，或新增你關注的標的。' },
    quote: { title: '看到第一條行情', description: '確認價格、來源和資料時間。' },
    ai: { title: '連線並測試 AI', description: '選擇預設模型，確認它能正常響應。' },
    analysis: { title: '完成首次分析', description: '生成並閱讀一份簡短的分析。' },
    alert: { title: '設定價格提醒', description: '讓重要價格條件出現在通知中心。' },
    notify: { title: '接收外部通知', description: '接入你常用的管道並主動測試。' },
  },
  errors: { load: '無法讀取設定進度，請重試。', action: '操作未完成，請重試。',
    interrupted: '服務重啟中斷了分析，進度已保留，請重新生成。', empty: '模型返回了空結果，請重試或更換模型。' },
},
  addPosition: { title: '加倉測算', emptySuffix: '（目前空倉 · 建倉測算）', collapse: '收起 ▾', expand: '展開 ▸', byShares: '按股數', byAmount: '按金額', shares: '加倉股數', amount: '加倉金額(元)', price: '加倉價', sharesExample: '如 200', amountExample: '如 10000', estimatedShares: '≈ {{shares}} 股{{lots}}', estimatedLots: '（≈{{lots}} 手）', afterCost: '加倉後成本', initialCost: '建倉成本', dilution: '攤薄', total: '合計股數 / 投入', lotWarning: '提示：A股通常 100 股/手，建議取整到 100 的倍數', inputHint: '填寫加倉股數/金額與價格後自動計算', targetCost: '反推：目標成本', targetHint: '按加倉價反推所需股數', required: '需加 {{shares}} 股{{lots}}', approximately: '約 {{amount}} 元', targetInvalid: '需滿足 加倉價 < 目標 < 現成本 才能降到該成本', evaluating: 'AI 評估中…', evaluate: '讓 AI 評估適不適合加倉', aiResult: 'AI 結論 · 僅供參考', invalidInput: '請先填寫有效的加倉股數/金額與價格', evalFailed: 'AI 評估失敗', verdicts: { suitable: '適合', cautious: '謹慎', unsuitable: '不適合', unknown: '未知' } },
  onboarding: { welcome: '歡迎使用盯盤俠', ready: '你的自選股已就緒，可以開始使用了', samples: '我們已為你添加了 5 只熱門股票作為範例，你可以立即檢視即時行情', liveTitle: '即時行情監控', liveDesc: '跟蹤自選股價格變動，快速發現異動', aiTitle: 'AI 智慧分析', aiDesc: '盤後日報、異動建議、技術分析', notifyTitle: '智慧通知推播', notifyDesc: 'Telegram、企業微信等多管道推播', start: '開始使用', skip: '跳過引導', configureAi: '設定 AI 分析', configureAiDesc: '連線 AI 服務後，可獲得智慧分析功能', aiItems: { report: '盤後日報自動分析', suggestion: '異動 AI 建議', chart: '技術圖表分析' }, aiProviders: '支援 OpenAI、智譜、DeepSeek 等服務商', later: '稍後再說', configure: '前往設定', configureNotify: '設定通知管道', configureNotifyDesc: '設定後可收到即時推播通知', notifyItems: { intraday: '盤中異動提醒', report: 'AI 分析報告推播', stop: '止盈止損預警' }, notifyProviders: '支援 Telegram、企業微信等管道', complete: '設定完成', completeDesc: '你可以隨時在「設定」頁面修改設定', dashboard: '進入 Dashboard', portfolio: '管理自選股' },
  logs: { title: '日誌', autoRefresh: '自動重新整理', refresh: '重新整理', clear: '清空', clearConfirm: '確定清空所有日誌？', search: '搜尋日誌內容 / trace_id / logger...', all: '全部', domains: { business: '業務優先', all: '全部', infra: '基礎設施' }, flows: { all: '全部鏈路', premarket: '盤前分析', daily: '收盤復盤', intraday: '盤中監測', deep: '深度分析' }, records: '{{count}} 條記錄', loggerFilter: 'Logger過濾', loggerHint: '預設鏈路會自動包含 `src.agents.base` 決策日誌', filters: '過濾器：{{summary}}', clearFilters: '清空過濾', empty: '暫無日誌', emptyHint: '後台執行後日誌會自動出現在這裡', columns: { time: '時間', level: '級別', flow: '鏈路', message: '訊息' }, loaded: '已載入 {{loaded}} / {{total}}', loading: '載入中...', loadMore: '載入更多', noMore: '沒有更多了', summary: { keyword: '關鍵詞：{{value}}', level: '級別：{{value}}', time: '時間：{{value}}h', domain: '範圍：{{value}}', flow: '鏈路：{{value}}', loggers: '自選 Logger：{{count}}', none: '目前無額外過濾' } },
  suggestionBadge: { blocked: '執行受限', technicalPending: '暫無資料', review: '待複核', source: '來源：', unknown: '未知', expired: '（已過期）', detailTitle: '點選檢視建議詳情', technicalTitle: '點選檢視技術面詳情', technical: '技術指標', technicalShort: '指標', watch: '觀望', signal: '訊號', reason: '理由', aiResponse: 'AI 響應', promptContext: 'Prompt 上下文', expand: '（點選展開）', klineAsOf: 'K線截止 {{value}}', calculated: '計算 {{value}}', agents: { intraday_monitor: '盤中監測', daily_report: '盤後日報', premarket_outlook: '盤前分析', technical_fallback: '技術指標' } },
  deepAnalysis: { title: '🧠 深度分析 · {{name}} ({{symbol}})', description: 'TradingAgents 多 Agent 決策框架 · 僅供學習研究參考，不構成投資建議', stages: { data_collection: '資料準備', market_analyst: '技術分析師', social_analyst: '情緒分析師', news_analyst: '新聞分析師', fundamentals_analyst: '基本面分析師', bull_bear_debate: '看多看空辯論', research_manager: '研究主管', trader: '交易員決策', risk_judge: '風控判定', final_decision: 'PM 整合' }, errors: { resultMissing: '結果尚未寫入，請稍後到「AI 歷史」檢視', analysisFailed: '分析失敗', triggerFailed: '觸發失敗' }, triggered: '已觸發', failedTitle: '分析失敗', close: '關閉', retry: '重試', idle: { upcoming: '即將分析：{{symbol}}', framework: '呼叫 4 類分析師（技術 / 情緒 / 新聞 / 基本面）+ 看多看空辯論 + 風控 + PM 整合', duration: '⏱ 預計耗時：3-8 分鐘', async: 'ℹ️ 非同步執行，可關閉彈窗，完成時透過通知管道推播', cancel: '取消', start: '開始分析' }, running: { title: '分析進行中...', elapsed: '已用 {{time}}', currentAgent: '目前 Agent：', currentOperation: '目前操作：', dataTool: '資料工具 ', preparing: '準備中...', background: '後台執行（完成時推播通知）' }, data: { title: '資料準備明細', sources: { quote: '行情', klines: 'K 線', capital_flow: '資金流', events: '事件', news: '新聞', financial: '財報', technical: '技術指標' }, statuses: { pending: '等待', running: '請求中', done: '完成', error: '失敗降級' } }, toolkit: { title: '資料注入診斷', subtitle: '（PanWatch 資料 → TradingAgents 工具）', passthrough: '透傳', fallback: '兜底', error: '錯誤', legendHit: '用 PanWatch 資料', legendMiss: '命中但 PanWatch 未實現', legendPassthrough: '非 A 股直接走上游 vendor', legendFallback: 'A 股但 cache 為空，走了上游', empty: '⚠️ 還沒有任何工具呼叫記錄（可能 TradingAgents 還在準備階段）。', chars: ' · {{count}} 字元', truncated: '...（共 {{total}} 字元，僅展示前 {{shown}}）' }, usage: { total: 'Token 合計 {{value}}', input: '輸入 {{value}}', output: '輸出 {{value}}', unavailable: 'Token 用量未記錄', partial: '部分用量（{{recorded}} / {{total}} 次呼叫已記錄）' }, done: { analysisDate: '報告日期：{{value}}', generatedAt: '生成時間：{{value}}', dateUnavailable: '未記錄', fallbackAction: '持有', fallbackAgent: 'TradingAgents 深度', cached: 'ℹ️ 快取報告：展示此前生成的結果，本次檢視未呼叫模型', rerun: '忽略快取重新分析', confidence: '置信度 {{value}} / 10', details: '檢視詳細頁', cost: '成本：${{value}}', disclaimer: '本分析由 AI 多 Agent 框架生成，僅供學習研究參考，不構成任何投資建議。投資有風險，決策需自主判斷。' } },
  stockPriceAlert: {
    conditions: { price: '價格', change_pct: '漲跌幅%', turnover: '成交額', volume: '成交量', volume_ratio: '量比' },
    messages: { loadFailed: '載入提醒失敗', stockNotFound: '無法定位股票', createFailed: '無法建立提醒', saved: '提醒已儲存', saveFailed: '儲存失敗', toggleFailed: '切換失敗', deleted: '已刪除', deleteFailed: '刪除失敗', deleteConfirm: '確認刪除規則「{{name}}」？' },
    alert: '提醒', priceAlert: '價格提醒', title: '{{name}} 提醒', summary: '{{market}} · 啟用 {{enabled}} / 共 {{total}}', create: '新建提醒', loading: '載入中...', empty: '該股票暫無提醒規則', enabled: '啟用', paused: '暫停', disable: '停用', enable: '啟用', or: ' 或 ', and: ' 且 ', between: '介於', editTitle: '編輯提醒規則', createTitle: '新建提醒規則', formDescription: '支援價格、漲跌幅、成交額、量比條件，支援 AND / OR 組合', saveRule: '儲存規則', defaultName: '{{name}} 價格提醒', fallbackName: '{{name}} 提醒',
  },
  kline: {
    title: 'K線 / 技術指標', period: '週期：{{value}}', dataAsOf: '資料截至：{{value}}', calculatedAt: '計算時間：{{value}}', loading: '載入中...', empty: '暫無資料', held: '已持倉', notHeld: '未持倉', score: '評分 {{value}}', disclaimer: '僅基於技術指標規則生成，非投資建議', hoverHint: '提示：懸停指標標籤可檢視詳細說明', current: '目前：{{value}}',
    statuses: { bullish: '多頭排列', bearish: '空頭排列', mixed: '均線交織', goldenCross: '金叉', deathCross: '死叉', overbought: '超買', oversold: '超賣', strong: '偏強', weak: '偏弱', volumeUp: '放量', volumeDown: '縮量', upperBreak: '突破上軌', lowerBreak: '跌破下軌', normalVolatility: '正常波動', bollSqueeze: '波幅收斂', bollExpansion: '波動擴大', positive: '為正', negative: '為負', neutral: '接近0' },
    actions: { buy: '買入', add: '加倉', sell: '賣出', reduce: '減倉', avoid: '迴避', hold: '持有', watch: '觀望', alert: '提醒' },
    neutralSignal: '技術面中性',
    items: { trendBull: '均線多頭排列，趨勢偏強', trendBear: '均線空頭排列，趨勢偏弱', trendMixed: '均線交織，趨勢不明', macdGolden: 'MACD 金叉，短線動能偏強', macdDeath: 'MACD 死叉，短線動能轉弱', macdHist: 'MACD 柱體{{status}}', macdPositive: 'MACD 柱體為正（動能偏多）', macdNegative: 'MACD 柱體為負（動能偏空）', rsiOversold: 'RSI 超賣，可能存在反彈', rsiStrong: 'RSI 偏強，買盤佔優', rsiOverbought: 'RSI 超買，注意回撥風險', rsiWeak: 'RSI 偏弱，短線承壓', rsiNeutral: 'RSI 中性', kdjGolden: 'KDJ 金叉，短線轉強', kdjDeath: 'KDJ 死叉，短線轉弱', bollUpper: '突破布林上軌，趨勢強勢', bollLower: '跌破布林下軌，走勢偏弱', volumeUp: '放量配合，資金參與度提升', volumeDown: '縮量，動能不足', nearSupport: '價格接近支撐位，止跌反彈機率提升', nearResistance: '價格接近壓力位，上行空間受限' },
    tags: { bullish: '多頭', bearish: '空頭', macdGolden: 'MACD 金叉', macdDeath: 'MACD 死叉', rsiOversold: 'RSI 超賣', rsiStrong: 'RSI 偏強', rsiOverbought: 'RSI 超買', rsiWeak: 'RSI 偏弱', kdjGolden: 'KDJ 金叉', kdjDeath: 'KDJ 死叉', bollUpper: '突破上軌', bollLower: '跌破下軌', volumeUp: '放量', volumeDown: '縮量', nearSupport: '靠近支撐', nearResistance: '靠近壓力' },
    indicators: {
      trend: { title: '趨勢（均線排列）', description: '趨勢標籤來自 MA5 / MA10 / MA20 的相對位置。多頭排列偏強，空頭排列偏弱，均線交織更依賴成交量和關鍵價位。' },
      macd: { title: 'MACD（趨勢 / 動能）', description: 'DIF 上穿 DEA 為金叉，下穿為死叉；柱體正負反映目前多空動能。需結合趨勢和量價確認。' },
      rsi: { title: 'RSI（相對強弱）', description: 'RSI6 衡量近 6 個交易日的相對強弱。70 以上偏強，80 以上超買；30 以下偏弱，20 以下超賣。' },
      kdj: { title: 'KDJ（轉折 / 超買超賣）', description: 'J 值更敏感，金叉 / 死叉用於觀察短期轉折，但震盪中容易失真，需結合趨勢與量價。' },
      volume: { title: '量能（成交量配合）', description: '放量常用於確認突破或反彈的有效性；縮量上衝 / 下跌需警惕動能不足。' },
      boll: { title: '布林帶（波動 / 偏離）', description: '突破上軌或跌破下軌常見於趨勢階段或極端波動，應結合量能與回踩 / 站穩確認。' },
      pattern: { title: 'K線形態（區域性結構）', description: '單根形態的提示意義有限，更需結合所處趨勢、支撐壓力位與量能。' },
      support: { title: '支撐位（關鍵支撐區）', label: '支撐 {{value}}', description: '接近支撐時更容易止跌反彈；放量跌破後支撐可能轉為壓力。它更偏向一個區域，而非精確點位。' },
      resistance: { title: '壓力位（關鍵壓力區）', label: '壓力 {{value}}', description: '越接近壓力位，上行難度越大；放量突破並站穩後，原壓力位可能轉為支撐。' },
    },
    metrics: { fiveDay: '5日 {{value}}%', twentyDay: '20日 {{value}}%', amplitude: '振幅 {{value}}%' },
    rules: { title: '建議 / 評分規則說明', expand: '（點選展開）', recommendation: '建議規則（按是否持倉）', unheld: '未持倉：score ≥ 3 → 買入；score ≤ -2 → 迴避；其他 → 觀望', held: '已持倉：score ≥ 3 → 加倉；score ≥ 1 → 持有；score ≤ -3 → 賣出；score ≤ -1 → 減倉；其他 → 觀望', scoring: '評分規則（各項累加，0 為中性）', trend: '趨勢（均線）：多頭排列 +2；空頭排列 -2', macd: 'MACD：金叉 +2；死叉 -2；柱體為正 +1；柱體為負 -1', rsi: 'RSI：超賣 +1；偏強 +1；超買 -1；偏弱 -1', kdj: 'KDJ：金叉 +1；死叉 -1', boll: '布林：突破上軌 +1；跌破下軌 -1', volume: '量能：放量 +1；縮量 -1', levels: '支撐 / 壓力：收盤價 ≤ 支撐×1.02 → +1；收盤價 ≥ 壓力×0.98 → -1' },
    askAI: '問 AI 分析這些指標',
  },
  stockInsight: {
    description: '概覽、K線、AI建議、新聞、歷史分析都在同一彈窗檢視',
    markets: { TW: '台股', TWF: '期貨', CN: 'A股', HK: '港股', US: '美股' },
    actions: { generating: '生成中', image: '圖片', share: '分享', copy: '複製', processing: '處理中...', held: '持倉中', unfollow: '取消關注', follow: '快速關注', setting: '設定中...', setAlert: '一鍵設提醒', askAI: '問 AI', refresh: '重新整理', holdingCannotUnfollow: '持倉中的股票無法取消關注', more: '更多', openDetails: '開啟詳情頁 ↗' },
    tabs: { overview: '概覽', suggestions: '建議 ({{count}})', reports: '報告 ({{count}})', deep: '深度', deepCount: '深度 (1)', kline: 'K線', announcements: '公告 ({{count}})', news: '新聞 ({{count}})' },
    autoRefresh: '自動重新整理', seconds: '{{count}}秒',
    metrics: { open: '今開', high: '最高', low: '最低', volume: '成交量', turnover: '成交額', amplitude: '振幅', turnoverRate: '換手率', pe: '市盈率', marketCap: '總市值' },
    futures: { title: '期貨資訊', contractMonth: '合約月份', contractMonthValue: '{{month}} 月合約 {{contract}}', settlementDate: '結算日', daysRemaining: '剩餘 {{days}} 天', spot: '現貨', basis: '價差', spotDaySessionClose: '現貨為日盤收盤' },
    holding: { title: '持倉資訊', quantity: '持倉數量', cost: '持倉成本(單價)', marketValue: '持倉市值', pnl: '總盈虧', empty: '未在持倉中' },
    miniKline: { title: '迷你K線', noSummary: '暫無K線摘要', empty: '暫無迷你K線', open: '點選進入互動式K線' },
    cards: { aiSuggestions: 'AI建議', updating: '更新中...', core: '核心判斷', noDescription: '暫無說明', action: '動作：', rationale: '依據：', noRationale: '暫無補充依據', source: '來源：', recentSuggestions: '近期補充建議', generatingSuggestion: '正在自動生成 AI 建議...', generatingSuggestionWait: '正在自動生成 AI 建議（通常 5-15 秒）...', noSuggestion: '暫無 AI 建議', news: '新聞', noNews: '暫無相關新聞', aiReports: 'AI報告', noReport: '暫無報告', reportSummary: '報告摘要', noReportContent: '暫無報告內容' },
    reports: { premarket: '盤前', afterMarket: '盤後', premarketAgent: '盤前分析', afterMarketAgent: '盤後日報', context: '檢視分析上下文', promptStats: 'Prompt統計', newsDetails: '新聞注入明細', contextSnapshot: '上下文快照', promptOriginal: 'Prompt原文' },
    suggestions: { showExpired: '顯示過期建議', includeExpired: '包含過期', activeOnly: '僅有效', technicalFallback: '目前顯示技術指標基礎建議', empty: '暫無建議' },
    ranges: { hours6: '近6小時', hours12: '近12小時', hours24: '近24小時', hours48: '近48小時', hours72: '近72小時', days7: '近7天', days14: '近14天', days30: '近30天', days90: '近90天', days180: '近180天' },
    announcementsEmpty: '暫無公告',
    messages: { loadFailed: '載入失敗', canvasUnavailable: '無法建立畫布', imageSaved: '分享圖片已生成並下載', imageFailed: '圖片生成失敗，請稍後重試', copied: '洞察內容已複製', copyFailed: '複製失敗，請優先使用「圖片」分享', shareCopied: '目前環境不支援系統分享，已自動複製內容', shareFailed: '分享失敗，已自動複製內容', shareAndCopyFailed: '分享與複製均失敗，請使用「圖片」分享', alertSet: '已設定提醒，AI 分析已提交', alertFailed: '設定提醒失敗', holdingCannotUnfollow: '該股票存在持倉，請先刪除持倉後再取消關注', unfollowed: '已取消關注', followed: '已新增關注', operationFailed: '操作失敗', autoSuggestionFailed: '自動 AI 建議觸發失敗，可點選「一鍵設提醒」重試' },
    share: { title: 'PanWatch 洞察', time: '時間', currentPrice: '現價', suggestion: '建議', signal: '訊號', reason: '理由', risk: '風險', technical: '技術', levels: '關鍵位', source: '來源', trigger: '觸發', invalidation: '失效', support: '支撐', resistance: '壓力', disclaimer: '僅供參考，不構成投資建議' },
    technical: { neutral: '技術面中性', fallbackReason: '基於K線技術指標自動生成的基礎建議', indicators: '技術指標建議', score: '評分 {{value}}', marketRisk: '市場波動風險', none: '暫無技術指標' },
    deep: { loading: '正在載入深度分析報告...', empty: '暫無深度分析報告', emptyHint: '可在持倉 / 自選頁點選 🧠 深度分析按鈕觸發', title: 'TradingAgents 深度', confidence: '置信度 {{value}} / 10', cost: '成本：${{value}}', analysts: '4 位分析師報告', truncated: '... （已截斷）', debate: '看多看空辯論', judge: '研究主管裁決：', disclaimer: '本分析由 AI 多 Agent 框架生成，僅供學習研究參考，不構成任何投資建議。', stages: { market: '技術分析師', social: '情緒分析師', news: '新聞分析師', fundamentals: '基本面分析師' }, historyLoading: '歷史對比載入中...', historyTitle: '歷史決策 vs 實際漲跌', historyHint: '僅基於滿 20 個交易日的決策統計', hitRate: '總命中率', buy: '買入 / 加倉 ({{count}})', sell: '賣出 / 減倉 ({{count}})', avg20d: '平均 20 日收益', columns: { date: '日期', decision: '決策', price: '分析價', day1: '1日', day5: '5日', day20: '20日', hit: '命中' } },
  },
} as const
