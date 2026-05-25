# 每日热点内容生成器

每天 8:03 AM 自动搜集**抖音 / YouTube / TikTok** 热点，AI 生成不露脸短视频选题，推送飞书。

## 部署步骤

### 1. 上传到 GitHub

```bash
# 初始化仓库
git init
git add .
git commit -m "初始化"

# 创建 GitHub 仓库（在网页上创建）后：
git remote add origin https://github.com/你的用户名/auto-content-bot.git
git branch -M main
git push -u origin main
```

### 2. 配置 Secrets

在 GitHub 仓库页面 → **Settings → Secrets and variables → Actions**，添加：

| Secret | 值 |
|--------|-----|
| `AI_API_KEY` | 你的 API Key |
| `FEISHU_WEBHOOK` | `https://open.feishu.cn/open-apis/bot/v2/hook/905d944d-de89-4611-8cc6-bbd8206ba0fd` |

### 3. 启用 Actions

推送后，GitHub Actions 会自动启用。每天 8:03 AM (北京时间) 自动运行。

也可以手动触发：Actions → Daily Content Generation → Run workflow

## 本地测试

```bash
pip install -r requirements.txt
AI_API_KEY=sk-xxx FEISHU_WEBHOOK=https://... python src/main.py
```
