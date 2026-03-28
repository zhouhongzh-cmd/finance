# 多电脑同步手册

> 适用仓库：`git@github.com:zhouhongzh-cmd/finance.git`
> 当前主项目目录：`arbitrage_monitor/`

---

## 1. 目标

这份手册用于在多台电脑之间同步当前代码，并降低以下问题：

- 改动互相覆盖
- 推送失败
- 分支混乱
- SSH 连不上 GitHub
- 不同电脑提交身份不一致

推荐原则：

- 每台电脑各自配置一把 SSH key
- 所有电脑使用同一个 Git 身份
- 所有电脑都从同一个远程仓库 clone
- 默认先 `pull` 再开始改
- 功能开发优先使用独立分支
- 监控频率、阈值和时间窗口默认保存在仓库内的共享配置文件里

---

## 2. 仓库信息

- GitHub 仓库：`git@github.com:zhouhongzh-cmd/finance.git`
- 默认分支：`main`
- 当前作者身份：
  - `user.name = hikiwa`
  - `user.email = zhouhong.zh@gmail.com`

---

## 3. 新电脑首次配置

### 3.1 配 Git 身份

```bash
git config --global user.name "hikiwa"
git config --global user.email "zhouhong.zh@gmail.com"
```

验证：

```bash
git config --global --get user.name
git config --global --get user.email
```

### 3.2 生成 SSH key

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -C "zhouhong.zh@gmail.com"
```

如果系统问保存路径，直接回车使用默认值即可。

### 3.3 查看公钥

```bash
cat ~/.ssh/id_ed25519.pub
```

复制输出内容，添加到 GitHub：

- 打开：[https://github.com/settings/keys](https://github.com/settings/keys)
- 选择 `New SSH key`
- 粘贴公钥

### 3.4 测试 GitHub SSH

```bash
ssh -T git@github.com
```

正常结果类似：

```text
Hi zhouhongzh-cmd! You've successfully authenticated, but GitHub does not provide shell access.
```

### 3.5 clone 仓库

```bash
git clone git@github.com:zhouhongzh-cmd/finance.git
cd finance
```

---

## 4. 每天开始工作前

进入仓库后先同步主分支：

```bash
git switch main
git pull
```

如果你只是想看看远程最新状态，也可以用：

```bash
git fetch
git status
```

---

## 5. 推荐开发流程

### 5.1 新功能或新修改

先从最新 `main` 开新分支：

```bash
git switch main
git pull
git switch -c codex/你的分支名
```

示例：

```bash
git switch -c codex/metals-dashboard-tweak
```

### 5.2 提交改动

```bash
git add .
git commit -m "feat: 说明你的改动"
```

### 5.3 第一次推送该分支

```bash
git push -u origin codex/你的分支名
```

以后同一分支继续推送只需要：

```bash
git push
```

---

## 6. 想在另一台电脑继续同一个分支

先拉最新远程分支：

```bash
git fetch
git switch codex/你的分支名
git pull
```

如果本地还没有这个分支：

```bash
git fetch
git switch --track origin/codex/你的分支名
```

---

## 7. 改完后合并回 main

如果你在本机上完成开发并想合回主分支：

```bash
git switch main
git pull
git merge codex/你的分支名
git push
```

如果以后你更习惯在 GitHub 网页上合并，也可以直接推分支后走 Pull Request。

---

## 8. 如果两台电脑都改了同一块代码

先在当前电脑执行：

```bash
git fetch
git pull --rebase
```

如果出现冲突：

1. 打开冲突文件
2. 手动保留正确内容
3. 解决后执行：

```bash
git add 冲突文件
git rebase --continue
```

如果不想继续这次 rebase：

```bash
git rebase --abort
```

---

## 9. 常用检查命令

查看当前状态：

```bash
git status
```

查看当前分支：

```bash
git branch --show-current
```

查看远程：

```bash
git remote -v
```

查看最近提交：

```bash
git log --oneline -5
```

---

## 10. 当前仓库的使用建议

当前 `finance` 仓库已经收口为源码主仓，建议：

- 把主要开发都放在 `arbitrage_monitor/`
- 不要把数据库、归档压缩包、临时工具一起纳入 Git
- 不要依赖网盘来解决代码同步，统一以 GitHub 为准
- 运行参数优先看 `config/runtime_settings.json`
- 金属阈值优先看 `config/metals_thresholds.json`
- `.env` 只建议放通知地址、Cookie 这类本机私密项

同步原则：

- 代码同步看 GitHub
- 数据文件单独处理
- 每台电脑独立 SSH key
- 每次工作前先 `git pull`

---

## 11. 快速版操作清单

新电脑：

```bash
git config --global user.name "hikiwa"
git config --global user.email "zhouhong.zh@gmail.com"
ssh-keygen -t ed25519 -C "zhouhong.zh@gmail.com"
cat ~/.ssh/id_ed25519.pub
ssh -T git@github.com
git clone git@github.com:zhouhongzh-cmd/finance.git
```

日常开始工作：

```bash
cd finance
git switch main
git pull
git switch -c codex/你的分支名
```

提交并推送：

```bash
git add .
git commit -m "feat: 说明"
git push -u origin codex/你的分支名
```

继续已有分支：

```bash
git fetch
git switch codex/你的分支名
git pull
```

---

## 12. 新机器最短安装清单

如果你打算直接在本机跑，不走 Docker：

```bash
cd /Users/hikiwa/Library/CloudStorage/OneDrive-个人/coding/finance/arbitrage_monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

然后补这两类配置：

- `.env` 里填写本机私密项：`FEISHU_WEBHOOK_URL`、`WECOM_WEBHOOK_URL`、`JSL_COOKIE`、`XUEQIU_COOKIE`
- `config/runtime_settings.json` 和 `config/metals_thresholds.json` 会在 `git pull` 后自动同步

如果你走 Docker：

```bash
cd /Users/hikiwa/Library/CloudStorage/OneDrive-个人/coding/finance/arbitrage_monitor
cp .env.example .env
docker compose up -d --build
```

Docker 版本不需要手工安装 Python 依赖，镜像会按 `requirements.txt` 自动装好。
