// 由 gen-zh-tw.py 自 zh-CN 產生；手動修正請寫進腳本的 OVERRIDES，不要直接改本檔。
export const auth = {
  title: { setup: '設定訪問密碼', login: '登入' },
  setupHint: '首次使用，請設定訪問密碼以保護您的資料',
  fields: {
    username: '使用者名稱',
    usernamePlaceholder: '請輸入使用者名稱',
    password: '密碼',
    passwordSetup: '設定密碼',
    passwordPlaceholder: '請輸入密碼',
    passwordSetupPlaceholder: '至少 6 位',
    confirmPassword: '確認密碼',
    confirmPasswordPlaceholder: '再次輸入密碼',
  },
  actions: {
    login: '登入',
    setup: '設定密碼並進入',
    showPassword: '顯示密碼',
    hidePassword: '隱藏密碼',
  },
  messages: {
    passwordMismatch: '兩次密碼不一致',
    passwordTooShort: '密碼長度至少 6 位',
    setupSuccess: '密碼設定成功',
    loginSuccess: '登入成功',
    operationFailed: '操作失敗',
  },
} as const
