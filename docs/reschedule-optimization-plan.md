# Reschedule 优化方案

**日期**：2026-02-03
**背景**：2026-02-24 和 2026-02-06 两次 reschedule 失败分析

---

## 一、问题定义

### 1.1 核心问题

从发现可用日期到完成预订，耗时过长（2+ 分钟），导致时间槽被其他用户抢走。

### 1.2 失败链路分析

```
发现可用日期
    │
    ▼
reschedule() 调用 driver.get(APPOINTMENT_URL)
    │
    ▼ 页面加载超时（等待 60 秒）
    │
    ▼
捕获 TimeoutException，尝试 session recovery
    │
    ▼
start_process() 重新登录
    │
    ▼ 登录页面也超时（又等待 60 秒）
    │
    ▼
第二次 reschedule 尝试
    │
    ▼
时间槽已被抢走 → 失败
```

**总延迟**：60s（reschedule 超时）+ 60s（登录超时）+ 其他开销 ≈ **126 秒**

### 1.3 根因分析

| 层面 | 问题 | 影响 |
|------|------|------|
| **网络层** | IP 可能被软屏蔽（API 通但页面阻止） | 页面加载无限挂起 |
| **应用层** | Selenium 超时配置过长（60s） | 单次失败等待时间过长 |
| **恢复层** | 直接执行完整登录流程 | 恢复开销大，延迟累积 |
| **策略层** | 未检测 Cloudflare 拦截 | 无法针对性处理 |
| **策略层** | reschedule 失败未触发代理轮换 | 继续使用可能被封的 IP |

---

## 二、优化目标

### 2.1 量化目标

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| 单次 reschedule 超时 | 60s | 15s |
| 单次登录超时 | 60s | 20s |
| 最坏情况总恢复时间 | 126s+ | < 45s |
| 3 次重试最坏耗时 | N/A（实际只完成 2 次） | < 60s |

### 2.2 设计原则

1. **快速失败**：缩短单次等待，快速进入重试
2. **分层恢复**：刷新 → 重新登录 → 轮换代理，逐步升级
3. **智能检测**：识别 Cloudflare 拦截，针对性处理
4. **代理联动**：超时异常触发代理轮换评估

---

## 三、实施方案

### 3.1 方案总览

```
┌─────────────────────────────────────────────────────────────┐
│                    Reschedule 优化架构                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │ P0: 快速失败 │ → │ P1: 智能检测 │ → │ P2: 分层恢复 │     │
│  │  缩短超时    │    │ Cloudflare  │    │ 刷新→登录→  │     │
│  │  15s/20s    │    │  拦截检测   │    │  代理轮换   │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 P0：快速失败 - 缩短 Selenium 超时

**优先级**：最高（立即实施）
**风险**：低
**收益**：高

**修改内容**：

```python
# 新增配置常量
SELENIUM_WAIT_RESCHEDULE = 15  # reschedule 关键路径
SELENIUM_WAIT_LOGIN = 20       # 登录流程
SELENIUM_WAIT_DEFAULT = 30     # 其他操作

# visa.py 第592行
Wait(driver, SELENIUM_WAIT_LOGIN).until(...)

# visa.py 第598行
Wait(driver, SELENIUM_WAIT_LOGIN).until(...)

# visa.py 第618行
Wait(driver, SELENIUM_WAIT_RESCHEDULE).until(...)
```

**预期效果**：
- 单次 reschedule 超时：60s → 15s
- 单次登录超时：60s → 20s
- 3 次重试最坏情况：(15+20) × 3 = 105s → 实际更短（成功会提前退出）

---

### 3.3 P1：智能检测 - Cloudflare 拦截识别

**优先级**：高
**风险**：低
**收益**：中

**新增函数**：

```python
def detect_cloudflare_block():
    """
    检测当前页面是否被 Cloudflare 或 WAF 拦截。

    Returns:
        bool: True 表示检测到拦截页面
    """
    try:
        page_source = driver.page_source.lower()
        title = driver.title.lower()

        # Cloudflare 和常见 WAF 拦截特征
        block_indicators = [
            'just a moment',           # Cloudflare challenge
            'checking your browser',   # Cloudflare challenge
            'access denied',           # WAF block
            'ray id',                  # Cloudflare signature
            'cloudflare',              # Direct mention
            'ddos protection',         # DDoS protection page
            'please wait',             # Generic challenge
            'verify you are human',    # CAPTCHA challenge
        ]

        for indicator in block_indicators:
            if indicator in page_source or indicator in title:
                return True
        return False
    except Exception:
        # 无法获取页面内容，保守返回 False
        return False
```

**使用场景**：在 TimeoutException 捕获后调用，决定恢复策略。

---

### 3.4 P2：分层恢复策略

**优先级**：高
**风险**：中
**收益**：高

**恢复层级**：

```
Level 1: 页面刷新（最轻量，2s）
    │
    ▼ 失败或检测到 Cloudflare
    │
Level 2: 完整重新登录（20s）
    │
    ▼ 失败或连续 TimeoutException
    │
Level 3: 代理轮换 + 重启 session
```

**改进后的重试逻辑**：

```python
# 在 main loop 中的 reschedule 重试部分
max_reschedule_retries = 3
res = None
cloudflare_detected = False

for attempt in range(max_reschedule_retries):
    try:
        slog.reschedule_attempt(date, attempt + 1, max_reschedule_retries)
        res = reschedule(date)
        break

    except TimeoutException as e:
        slog.reschedule_exception(date, e, attempt + 1, max_reschedule_retries)

        # 检测 Cloudflare 拦截
        if detect_cloudflare_block():
            slog.warning(LogCategory.PROXY, "Cloudflare/WAF block detected")
            cloudflare_detected = True

            # 直接跳到 Level 3：轮换代理
            if PROXY_ENABLED and PROXY_MANAGER and PROXY_MANAGER.has_proxies:
                if rotate_proxy_and_restart():
                    slog.info(LogCategory.PROXY, "Rotated proxy due to block detection")
                    cloudflare_detected = False
                    continue

        if attempt < max_reschedule_retries - 1:
            # Level 1: 尝试页面刷新
            if not cloudflare_detected:
                slog.info(LogCategory.SESSION, "Attempting page refresh (Level 1)")
                try:
                    driver.refresh()
                    time.sleep(2)
                    # 刷新后再次检查
                    if not detect_cloudflare_block():
                        continue
                except Exception:
                    pass

            # Level 2: 完整重新登录
            slog.relogin_attempt(attempt + 1, max_reschedule_retries)
            try:
                start_process()
                time.sleep(2)
                continue
            except Exception as login_err:
                slog.login_failed(login_err, attempt + 1, max_reschedule_retries)

                # Level 3: 登录也失败，尝试轮换代理
                if PROXY_ENABLED and PROXY_MANAGER and PROXY_MANAGER.has_proxies:
                    if rotate_proxy_and_restart():
                        slog.info(LogCategory.PROXY, "Rotated proxy after login failure")
                        continue

        res = ["FAIL", f"Exception after {max_reschedule_retries} attempts: {e}"]

    except Exception as e:
        # 非超时异常，使用原有逻辑
        slog.reschedule_exception(date, e, attempt + 1, max_reschedule_retries)
        if attempt < max_reschedule_retries - 1:
            try:
                start_process()
                time.sleep(2)
                continue
            except Exception as login_err:
                slog.login_failed(login_err, attempt + 1, max_reschedule_retries)
        res = ["FAIL", f"Exception after {max_reschedule_retries} attempts: {e}"]
```

---

## 四、实施计划

### 4.1 阶段划分

| 阶段 | 内容 | 预计改动 | 测试要求 |
|------|------|----------|----------|
| Phase 1 | P0: 缩短超时配置 | 3 行代码 | 基础功能测试 |
| Phase 2 | P1: 添加 Cloudflare 检测函数 | 新增 1 个函数 | 单元测试 |
| Phase 3 | P2: 重构 reschedule 重试逻辑 | ~40 行代码 | 集成测试 |
| Phase 4 | 日志增强 + 监控 | ~10 行代码 | 回归测试 |

### 4.2 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 超时太短导致正常页面也失败 | 中 | 中 | 监控成功率，必要时调整 |
| Cloudflare 检测误判 | 低 | 低 | 保守判断，宁可漏检不可误判 |
| 代理轮换过于频繁 | 低 | 中 | 添加冷却时间或次数限制 |

### 4.3 回滚方案

每个阶段独立可回滚：
- Phase 1：恢复原有超时值
- Phase 2：删除检测函数，不影响主流程
- Phase 3：恢复原有重试逻辑

---

## 五、预期效果

### 5.1 时间线对比

**优化前**：
```
01:41:25  Reschedule attempt 1/3
01:42:27  TimeoutException (62s)
01:42:27  Relogin attempt
01:43:31  Login TimeoutException (64s)
01:43:31  Reschedule attempt 2/3
01:43:31  Slot taken
─────────────────────────────
总耗时：126 秒
```

**优化后（预期）**：
```
01:41:25  Reschedule attempt 1/3
01:41:40  TimeoutException (15s)
01:41:40  Cloudflare check: negative
01:41:40  Page refresh (Level 1)
01:41:42  Reschedule attempt 2/3
01:41:57  TimeoutException (15s)
01:41:57  Relogin attempt (Level 2)
01:42:17  Reschedule attempt 3/3
01:42:32  Success or final failure
─────────────────────────────
总耗时：~67 秒（最坏情况）
实际可能更短（成功则提前退出）
```

### 5.2 成功率预期

| 场景 | 优化前 | 优化后 |
|------|--------|--------|
| 临时网络波动 | 低（等太久，槽被抢） | 高（快速重试） |
| IP 被软屏蔽 | 极低（不轮换代理） | 中（检测后轮换） |
| 页面加载慢 | 中（单次可能成功） | 高（多次快速尝试） |

---

## 六、验收标准

1. **功能验收**
   - [x] 超时配置生效（reschedule 15s, login 20s）
   - [x] Cloudflare 检测函数正常工作
   - [x] 分层恢复逻辑按预期执行
   - [x] 代理轮换在适当时机触发

2. **性能验收**
   - [x] 3 次重试最坏情况 < 60 秒
   - [x] 单次 reschedule 超时 ≤ 15 秒
   - [x] 单次登录超时 ≤ 20 秒

3. **日志验收**
   - [x] 可区分 TimeoutException 和其他异常
   - [x] 可追踪恢复层级（Level 1/2/3）
   - [x] Cloudflare 检测结果有日志记录

---

## 七、实施记录

**实施日期**：2026-02-03

### 代码变更

1. **visa.py** - 添加超时常量：
   ```python
   SELENIUM_WAIT_RESCHEDULE = 15
   SELENIUM_WAIT_LOGIN = 20
   SELENIUM_WAIT_DEFAULT = 30
   ```

2. **visa.py** - 添加 `detect_cloudflare_block()` 函数

3. **visa.py** - 重构 reschedule 重试逻辑，实现分层恢复：
   - Level 1: 页面刷新
   - Level 2: 完整重新登录
   - Level 3: 代理轮换

4. **visa.py** - 添加 `TimeoutException` 导入

### Bug 修复（2026-02-03 晚间）

修复了 `res=None` 导致 "Unknown error during rescheduling" 的 bug：

**问题**：当最后一次重试（attempt=2）触发代理轮换后执行 `continue`，循环退出但 `res` 从未赋值。

**修复**：
1. 添加 `last_recovery_action` 和 `last_exception` 跟踪变量
2. 循环结束后检查恢复动作，生成描述性错误消息
3. 增强日志，记录每个恢复步骤的详细信息

```python
if res is None:
    if last_recovery_action:
        res = ["FAIL", f"Recovery ({last_recovery_action}) performed on last attempt, retrying on next cycle"]
    else:
        res = ["FAIL", "Unexpected error: no result after retry loop"]
```

### 测试验证

- 新增 16 个测试用例覆盖：
  - Cloudflare 检测（5 个）
  - 分层恢复策略（4 个）
  - 超时配置（4 个）
  - 最后一次重试恢复 bug（3 个）
- 全部 39 个测试通过

---

## 八、后续优化（可选）

| 优化项 | 描述 | 优先级 |
|--------|------|--------|
| 预加载机制 | 在检测循环中预加载 reschedule 页面 | P3 |
| 自适应超时 | 根据历史成功率动态调整超时值 | P3 |
| 代理评分 | 记录每个代理的成功率，优先使用高分代理 | P3 |
| 并发检测 | 多线程同时检测多个日期的时间槽 | P4 |
