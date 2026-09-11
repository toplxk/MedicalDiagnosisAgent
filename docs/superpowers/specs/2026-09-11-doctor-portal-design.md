# 医生门户（Doctor Portal）设计文档

- 日期：2026-09-11
- 状态：已批准（设计评审通过，进入实现）
- 相关：智能医疗诊断多Agent交互系统（MedicalDiagnosisAgent）

## 1. 背景与目标

现状：

- 患者侧已有三栏工作台（`frontend/` 原生三文件）与 CLI；
- 认证体系已具备（`services/auth.py`，角色 patient/doctor/admin，演示账号 `doctor/123456`、`admin/admin123`）；
- 叫号后端能力已存在（`tools/queue_tool.py: call_next`，按科室队列）；
- 排班目前是**随机生成**的假数据（`appointment_tool._ensure_schedule` 首次查询时随机造）；
- 诊断结果**完全不落库**（`collected_info` 仅存内存，会话结束即失）。

目标：为医生/管理员提供后台门户，包含——值班/排班录入、叫号、今日预约患者列表、排队看板、诊断/病历记录、就诊统计，以及超管（admin）的**权限配置**（管理每个账号所分配的系统功能）。

术语约定：患者端是「取号」（take_number），医生端才是「叫号」（call_next）。

## 2. 总体架构（方案 A：同项目新增医生门户）

```
MedicalDiagnosisAgent/
├── web/                          # 新增：Vben Admin v5 前端工程（Vue3+TS，pnpm+Vite）
│   ├── src/views/doctor/         #   叫号台 / 今日预约 / 排班管理 / 诊断记录 / 统计
│   ├── src/views/board/          #   候诊大屏（全屏路由，无布局壳）
│   └── ...                       #   登录对接、role 权限、Vite 代理
├── frontend/                     # 不动：患者工作台（原生三文件，/ 路由）
├── api/
│   ├── server.py                 # include 新增 router；/api/chat 增加可选 Authorization
│   └── doctor_routes.py          # 新增：医生端 + 管理员端接口（APIRouter）
├── tools/
│   ├── doctor_tool.py            # 新增：排班录入/今日预约/统计/医生账号管理
│   └── diagnosis_tool.py         # 新增：诊断落库与查询
├── main.py                       # 诊断回合结束后 hook 落库
└── db/schema.py                  # 表结构变更（见 §3）
```

- 同一个 FastAPI 服务（:8000）承载患者端与医生端；数据库/认证/队列逻辑零重复。
- 开发联调：Vben dev server（5173）Vite proxy 将 `/api` 转发到 8000。
- 生产：`pnpm build` 产出 dist 由 FastAPI 挂载，仍为单端口部署。

## 3. 数据模型变更（5 处）

**1. `doctors` 表新增 `user_id INT NULL UNIQUE` 列**（登录账号 ↔ 医生实体关联）。

种子数据为每位医生生成账号：拼音用户名（如 `zhangjianguo`）、密码 `123456`、role=`doctor`。管理员可在后台新建医生+账号、禁用账号。

**2. 排班改为真实录入。**

`doctor_schedules` 表结构不变（doctor_id、schedule_date、period 上/下午、available_slots 已够用）。

- 移除 `appointment_tool._ensure_schedule()` 的随机生成逻辑；
- `seed_if_empty` 时为未来 7 天预生成一次演示排班（此后可真实修改）；
- 医生只能录入自己的排班；admin 可代录/修正所有人。`slots=0` 表示停诊（删除该时段）。

**3. 新增 `diagnosis_records` 表**（诊断结果持久化）：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INT AUTO_INCREMENT PK | 主键 |
| session_id | VARCHAR(64) | 会话 ID |
| user_id | INT NULL | 患者账号 |
| patient_name | VARCHAR(50) | 患者称呼 |
| department_id | INT NULL | 科室（可空） |
| doctor_id | INT NULL | 接诊医生（可空） |
| chief_complaint | VARCHAR(200) | 主诉 |
| collected_info | JSON | 采集的病史信息 |
| conclusion | TEXT | 诊断结论 |
| created_at | TIMESTAMP | 创建时间 |

**4. 统计不建新表**：基于 `appointments` / `queue_tickets` / `diagnosis_records` 现表聚合。

**5. 新增 `user_permissions` 表**（账号级功能授权，配合代码内功能注册表 `services/permissions.py`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| user_id | INT | 账号，联合主键 |
| feature_key | VARCHAR(40) | 功能键，联合主键 |
| granted | TINYINT | 1=授权，默认 1 |

- 功能注册表（医生门户 5 项）：`call_queue` 叫号台、`view_appointments` 今日预约、`manage_schedules` 排班管理、`view_records` 诊断记录、`view_stats` 就诊统计；
- 授权语义：admin 角色天然拥有全部权限（不受此表约束）；doctor 账号有记录即授权、无记录即禁止；
- 种子数据：每位医生的账号默认授予全部 5 项（演示开箱即用，admin 可回收）；admin 新建医生账号时同样默认全授；
- 患者（patient）账号的工作台功能不做逐项管控（范围外，见 §8）。

## 4. 后端 API

代码组织：新增 `api/doctor_routes.py`（APIRouter），`tools/doctor_tool.py`、`tools/diagnosis_tool.py`；server.py 仅 include router。

### 医生端（require_doctor：doctor 角色且关联 doctors 行）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/doctor/me` | 当前医生信息（姓名/科室/职称） |
| GET | `/api/doctor/schedules?start=&end=` | 查看自己排班（默认未来 7 天） |
| PUT | `/api/doctor/schedules` | 批量录入/修改 `[{date, period, available_slots}]`；slots=0 删除时段 |
| GET | `/api/doctor/appointments/today` | 今日预约本人的患者列表（可传 date） |
| GET | `/api/doctor/queue` | 本科室排队看板（复用 query_queue：当前号/等待人数/等待列表） |
| POST | `/api/doctor/call-next` | 叫号（复用 call_next，校验医生身份+科室匹配；原患者端接口不动） |
| GET | `/api/doctor/records` | 本科室患者诊断记录（可按患者筛选） |
| GET | `/api/doctor/stats` | 本人/本科室预约数、叫号数、诊断数及按日趋势 |

### 管理员端（require_admin）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/admin/doctors` | 医生列表 / 新建医生+账号 |
| PUT | `/api/admin/doctors/{id}` | 修改信息、启用/禁用账号 |
| PUT | `/api/admin/schedules` | 代录/修正任意医生排班（body 带 doctor_id） |
| GET | `/api/admin/permissions/users` | 账号列表（含 role 与已授功能） |
| GET | `/api/admin/permissions/features` | 功能注册表（功能键/名称） |
| PUT | `/api/admin/permissions/users/{id}` | 全量设置某账号的功能授权 |
| GET | `/api/admin/stats` | 全院统计 |

### 权限依赖（FastAPI Depends）

- `require_user`：登录即可（token 有效）；
- `require_doctor`：doctor 角色且关联 doctors 行，返回 `{user, doctor}`；
- `require_admin`：admin 角色；
- `require_doctor_feature(key)`：`require_doctor` + 功能授权校验（admin 直接放行）；
- 未登录 401、角色不符 403、功能未授权 403。

## 5. 前端：Vben Admin v5 医生门户

- 技术栈：vue-vben-admin v5（Ant Design Vue 版官方模板，裁剪演示代码），pnpm + Vite，目录 `web/`。
- 布局：用 Vben 内置布局切换（侧边栏/顶栏/混合），默认侧边栏，医生可自行切换。
- 登录：对接现有 `/api/auth/login`（账号密码），token 存 Vben 认证状态，请求统一 `Authorization: Bearer`。
- 权限路由：登录返回 `role` 控制菜单——doctor 见 5 个功能页；admin 额外见「医生管理」「权限配置」「全院统计」。401 跳登录。
- 页面（6 个路由）：
  1. **叫号台**（首页）：大号「叫下一个」按钮 + 科室队列（当前号/等待列表），轮询刷新；
  2. **今日预约**：本人患者预约列表（时段/状态）；
  3. **排班管理**：录入自己排班（日期×上下午×号源数）；admin 视图可代录全院；
  4. **诊断记录**：本科室患者诊断历史 + 详情抽屉；
  5. **统计**：预约/叫号/诊断卡片 + 趋势图（doctor：本人/本科室；admin：全院）；
  6. **候诊大屏** `/board`：全屏大字号当前叫号 + 等待队列（投候诊区）。
- **菜单按功能授权过滤**：登录后拉取 `/api/doctor/me` 返回的已授功能，未授权项不显示菜单（路由同样拦截）。
- **管理员扩展页**：医生管理（新建/编辑/禁用医生及账号）、权限配置（账号列表 + 功能授权勾选保存）、全院统计。
- 患者工作台 `frontend/` 完全不受影响。

## 6. 权限 / 错误处理 / 测试

**权限**：医生数据隔离——只能看/改自己的排班、本人预约、本科室队列与诊断记录；admin 全域。账号级功能授权由 `user_permissions` 控制，后端每个医生接口挂 `require_doctor_feature`，前端菜单按已授功能过滤——双层校验。

**错误处理**：沿用 `ApiEnvelope`（success/message/data）；排班校验（日期格式、时段枚举、号源 0–50，DB 唯一键兜底）；叫号空队列友好提示（现有逻辑已有）；诊断落库失败仅记日志，不影响对话主流程。

**测试**：引入 pytest（项目现无真实测试），范围限新增后端代码——`doctor_tool`（排班 CRUD/权限边界）、`diagnosis_tool`（落库/查询）、API 层 TestClient 测 401/403 与关键接口。前端不引入单测，手动冒烟（登录→叫号→排班→看板）。

## 7. 关键 hook 点

1. **诊断落库**：`DiagnosisAgent._generate_diagnosis()` 在 `_reset_state()` 前把 `{conclusion, collected_info}` 暂存 `agent.last_diagnosis`；`main.py` 诊断回合结束后调用 `diagnosis_tool.save_record()` 并清除。患者身份来自 `/api/chat` 新增的可选 `Authorization` 头（模式同现有 create_appointment/take_number）。
2. **叫号**：`/api/doctor/call-next` 内部复用 `queue_tool.call_next(department)`，仅增加身份与科室校验。

## 8. 范围外（YAGNI）

- 候诊大屏语音播报、短信/微信真实网关（现有为演示实现）、前端单测、排班变更审计、多租户、医生转移队列、患者账号的工作台功能逐项管控（patient 角色不做功能授权）。
