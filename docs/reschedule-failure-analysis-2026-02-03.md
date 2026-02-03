# Reschedule 失败分析报告

**日期**：2026-02-03
**分析对象**：2026-02-24 和 2026-02-06 两次 reschedule 失败事件

---

## 一、失败事件概述

| 目标日期 | 发现时间 | 失败确认时间 | 总耗时 | 最终状态 |
|----------|----------|--------------|--------|----------|
| 2026-02-24 | 01:41:24 | 01:43:31 | 2分7秒 | Slot taken |
| 2026-02-06 | 02:15:22 | 02:17:43 | 2分21秒 | Slot taken |

两次失败模式完全相同：发现可用日期后，在尝试预订过程中遭遇 Selenium 超时，最终时间槽被其他用户抢走。

---

## 二、详细时间线分析

### 2.1 第一次失败：2026-02-24

```
01:41:24  [BOOKING] Found 34 available dates, earliest: 2026-02-24
01:41:24  [BOOKING] Starting reschedule for 2026-02-24
01:41:25  [SYSTEM]  Telegram sent: Rescheduling Started
01:41:25  [BOOKING] Reschedule attempt 1/3
          │
          ▼ 等待 Selenium 操作... (62 秒)
          │
01:42:27  [SELENIUM] Reschedule exception: TimeoutException
01:42:27  [SESSION]  Attempting session recovery (relogin)
          │
          ▼ 等待登录页面加载... (64 秒)
          │
01:43:31  [SESSION]  Login failed: TimeoutException
01:43:31  [BOOKING] Reschedule attempt 2/3
01:43:31  [BOOKING] No time slots for 2026-02-24 - slot may have been taken
01:43:31  [BOOKING] Slot taken before booking: 2026-02-24
```

### 2.2 第二次失败：2026-02-06

```
02:15:22  [BOOKING] Found 34 available dates, earliest: 2026-02-06
02:15:22  [BOOKING] Starting reschedule for 2026-02-06
02:15:22  [SYSTEM]  Telegram sent: Rescheduling Started
02:15:22  [BOOKING] Reschedule attempt 1/3
          │
          ▼ 等待 Selenium 操作... (77 秒)
          │
02:16:39  [SELENIUM] Reschedule exception: TimeoutException
02:16:39  [SESSION]  Attempting session recovery (relogin)
          │
          ▼ 等待登录页面加载... (63 秒)
          │
02:17:42  [SESSION]  Login failed: TimeoutException
02:17:42  [BOOKING] Reschedule attempt 2/3
02:17:42  [BOOKING] No time slots for 2026-02-06 - slot may have been taken
02:17:43  [BOOKING] Slot taken before booking: 2026-02-06
```

---

## 三、根因分析（多角度）

### 3.1 直接原因：Selenium TimeoutException

两次失败的直接表现都是 `reschedule()` 函数内部的 Selenium 操作超时：

```python
# visa.py:618
Wait(driver, 60).until(EC.presence_of_element_located((By.NAME, "authenticity_token")))
```

### 3.2 角度一：网络层 - IP 软屏蔽（Soft Ban）假设

**核心观点**：脚本能通过后台 JS API (`get_dates`) 检测到空位，但在尝试通过浏览器加载预约页面 (`driver.get(APPOINTMENT_URL)`) 时，页面无法在 60 秒内完成加载。

**证据支持**：
- API 检测（XHR 请求）成功返回可用日期
- 浏览器页面导航（完整 HTML 渲染）超时
- 登录页面同样无法加载

**可能的技术原因**：
1. **Cloudflare/WAF 软屏蔽**：目标网站可能对高频访问的 IP 进行限流
   - API 接口（XHR）较轻量，可能基于缓存或绕过部分检测
   - 完整浏览器页面导航触发更严格的检测（加载 CSS/JS/Fonts），被阻止或无限挂起

2. **代理出口 IP 质量问题**：
   - 使用的旋转代理 (`brd.superproxy.io`) 出口 IP 可能已被标记
   - IP 跳变可能导致 Session 在页面跳转间隙失效

**检测与恢复层的差异**：

| 操作 | 实现方式 | 触发检测 | 被拦截风险 |
|------|----------|----------|------------|
| `get_dates` | `driver.execute_script()` + XHR | 轻量 | 低 |
| `reschedule` | `driver.get()` 全页面导航 | 完整渲染 | 高 |
| `start_process` | `driver.get()` 全页面导航 | 完整渲染 | 高 |

### 3.3 角度二：应用层 - 超时配置过长

**核心观点**：即使页面最终会加载成功（只是慢），60 秒的超时配置也过于宽松。

**当前配置**：
```python
Wait(driver, 60)  # 所有 Selenium 等待统一使用 60 秒
```

**问题分析**：
- 单次 reschedule 超时需等待完整 60 秒
- 登录恢复同样需要 60 秒
- 累计延迟轻易超过 2 分钟

**与 ec16da9 改进的关系**：
- ec16da9 将"重试循环间等待"从 60 秒降到 2 秒 ✅
- 但未修改"Selenium 操作本身"的超时配置 ❌

```
预期（ec16da9 设计）：异常 → 2s → 重试（总计 ~7 秒）
实际（超时场景）：异常(等60s) → 登录(等60s) → 重试（总计 ~126 秒）
```

### 3.4 角度三：恢复策略过重

**当前恢复流程**：
```
Reschedule TimeoutException
    │
    ▼
直接调用 start_process() 完整重新登录
    │
    ▼
登录也 TimeoutException
    │
    ▼
进入下一次 reschedule 重试
```

**问题**：
1. 没有先尝试轻量级恢复（如页面刷新）
2. 没有检测是否是 Cloudflare 拦截
3. reschedule 失败时没有触发代理轮换

### 3.5 角度四：竞争条件（Race Condition）

无论根因是网络层还是应用层，最终结果相同：
- 从发现可用日期到第二次尝试获取时间槽，总延迟达到 **2+ 分钟**
- 热门签证预约系统中，这足够让其他用户抢走时间槽

---

## 四、ec16da9 改进评估

### 4.1 改进内容

commit `ec16da9` 实现了 reschedule 快速重试机制：

| 改进项 | 改进前 | 改进后 |
|--------|--------|--------|
| 重试次数 | 1 次 | 3 次 |
| 重试间隔 | 60 秒（通用网络错误处理） | 2 秒 |
| Session 恢复 | 无 | 立即重新登录 |
| Telegram 超时 | 无 | 5 秒超时保护 |

### 4.2 改进的局限性

| 问题 | 是否解决 | 说明 |
|------|----------|------|
| 重试循环间等待 60 秒 | ✅ 已解决 | 改为 2 秒 |
| `reschedule()` Selenium 超时 60 秒 | ❌ 未解决 | 超时配置未修改 |
| `start_process()` 登录超时 60 秒 | ❌ 未解决 | 超时配置未修改 |
| 超时场景的特殊处理 | ❌ 未实现 | 未区分超时与其他异常 |
| Cloudflare 拦截检测 | ❌ 未实现 | 无法识别 IP 被封场景 |
| reschedule 失败触发代理轮换 | ❌ 未实现 | 继续使用可能被封的 IP |
| 轻量级恢复（先刷新） | ❌ 未实现 | 直接执行完整登录 |

**核心评价**：ec16da9 的设计思路正确，但只解决了"重试循环层面"的问题，未触及更底层的超时配置和恢复策略。

---

## 五、综合结论

### 5.1 两种分析视角的关系

| 视角 | 关注点 | 改进方向 |
|------|--------|----------|
| 网络层（软屏蔽假设） | **为什么**会超时 | 改善代理质量、检测拦截、轮换 IP |
| 应用层（超时配置） | 超时后**如何响应** | 缩短超时、分层恢复、快速重试 |

**两种视角不冲突，可能同时成立**：
1. IP 被软屏蔽导致页面加载极慢或完全不加载 ← 网络层问题
2. 超时后恢复流程耗时过长 ← 应用层问题

### 5.2 本次失败的完整因果链

```
代理 IP 可能被 Cloudflare 软屏蔽
         │
         ▼
浏览器页面导航被阻止/极慢（API 仍可用）
         │
         ▼
reschedule() 中的 Wait(driver, 60) 超时
         │
         ▼
触发 session recovery → start_process()
         │
         ▼
登录页面同样被阻止 → 又等待 60 秒超时
         │
         ▼
未检测 Cloudflare、未轮换代理、未尝试刷新
         │
         ▼
第二次 reschedule 尝试（此时已过 2+ 分钟）
         │
         ▼
时间槽已被其他用户抢走 → 失败
```

### 5.3 关键教训

1. **时间敏感操作需要激进的超时策略**：预约系统竞争以秒计，60 秒超时过于宽松
2. **快速失败优于长时间等待**：宁可多重试几次，也不要在单次尝试上浪费时间
3. **异常处理需要分层**：不同类型的异常应有不同的恢复策略
4. **需要识别 IP 被封场景**：检测 Cloudflare 拦截页面，针对性处理
5. **API 成功 ≠ 页面可访问**：XHR 请求和浏览器导航可能被区别对待
6. **日志系统证明了价值**：结构化日志使本次分析成为可能

---

## 六、改进方向

详细方案见 [reschedule-optimization-plan.md](reschedule-optimization-plan.md)

### 6.1 必要改进（P0-P1）

| 优先级 | 改进项 | 目标 |
|--------|--------|------|
| P0 | 缩短 Selenium 超时 | reschedule 15s, login 20s |
| P1 | 添加 Cloudflare 检测 | 识别 "Just a moment" 等拦截页面 |
| P1 | 分层恢复策略 | 刷新 → 登录 → 代理轮换 |
| P1 | reschedule 失败触发代理评估 | 检测到拦截时轮换代理 |

### 6.2 可选改进（P2-P3）

| 优先级 | 改进项 | 说明 |
|--------|--------|------|
| P2 | 更换静态住宅代理 | 减少 IP 被封风险 |
| P3 | 预加载 reschedule 页面 | 减少关键路径延迟 |
| P3 | 代理评分机制 | 优先使用高成功率代理 |

---

## 七、附录：日志证据

### 7.1 JSON 日志关键记录（2026-02-24）

```json
{"timestamp": "2026-02-03T01:41:24.899358", "level": "INFO", "category": "BOOKING", "message": "Found 34 available dates, earliest: 2026-02-24"}
{"timestamp": "2026-02-03T01:41:25.431048", "level": "INFO", "category": "BOOKING", "message": "Reschedule attempt for 2026-02-24", "attempt": 1, "max_attempts": 3}
{"timestamp": "2026-02-03T01:42:27.003601", "level": "ERROR", "category": "SELENIUM", "message": "Reschedule exception for 2026-02-24", "error_type": "TimeoutException"}
{"timestamp": "2026-02-03T01:43:31.256912", "level": "ERROR", "category": "SESSION", "message": "Login failed", "error_type": "TimeoutException"}
{"timestamp": "2026-02-03T01:43:31.925856", "level": "WARNING", "category": "BOOKING", "message": "Slot taken before booking: 2026-02-24"}
```

### 7.2 Error 日志关键记录

```
2026-02-03 01:42:27 [ERROR] [SELENIUM] [reschedule] [1/3] Reschedule exception for 2026-02-24 (type: TimeoutException)
2026-02-03 01:43:31 [ERROR] [SESSION] [login] [1/3] Login failed (type: TimeoutException)
2026-02-03 02:16:39 [ERROR] [SELENIUM] [reschedule] [1/3] Reschedule exception for 2026-02-06 (type: TimeoutException)
2026-02-03 02:17:42 [ERROR] [SESSION] [login] [1/3] Login failed (type: TimeoutException)
```
