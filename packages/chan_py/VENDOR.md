# chan.py vendor

- 來源：Vespa314/chan.py
- commit：`429d6ed`
- 授權：MIT（見 `LICENSE`）
- 取用目錄：`Bi`、`BuySellPoint`、`Combiner`、`Common`、`KLine`、`Math`、`Seg`、`ZS`，以及根目錄的 `Chan.py`、`ChanConfig.py`、`__init__.py`、`LICENSE`。

## 修改清單

- `Chan.py`：移除頂層 `DataAPI.CommonStockAPI` 匯入，並移除其僅用於型別註記的型別名稱。這讓精簡 vendor 在沒有 `DataAPI` 目錄時仍能匯入；實際資料由 `trigger_load` 注入，不會使用該 API。
- `BuySellPoint/BS_Point.py`：內嵌原 `ChanModel.Features.CFeatures` 的小型等價容器，避免核心买卖点模块依赖被排除的 `ChanModel` 目录。

## 未來更新

1. 在上游 checkout 目標 commit。
2. 只同步上述核心目錄與檔案，不帶 `DataAPI`、`Plot`、`Debug`、`Script`、`App`、`ChanModel`、`Image` 及文件範例。
3. 檢查核心模組的排除目錄匯入；若必要，做同樣範圍的最小修補並更新本檔。
4. 執行 `tests/test_chan_analysis.py` 與完整驗收命令。
