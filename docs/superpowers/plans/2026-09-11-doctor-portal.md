# 医生门户（Doctor Portal）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在同一 FastAPI 项目内新增医生门户（Vben Admin 前端 + 医生/管理员 API），实现排班录入、叫号、今日预约、排队看板、诊断记录、就诊统计与账号级权限配置。

**Architecture:** 后端沿用 MySQL + 现有 tools 层，新增 `services/permissions.py`（功能授权）、`tools/doctor_tool.py`、`tools/diagnosis_tool.py`、`api/deps.py`（权限依赖）、`api/doctor_routes.py`、`api/admin_routes.py`；`/api/chat` 挂可选 Authorization 并在诊断完成时落库。前端为 `web/` 目录下的 vue-vben-admin v5 工程（Ant Design Vue 版），开发 5173 代理到 8000，生产构建 dist 由 FastAPI 挂载 `/doctor`。

**Tech Stack:** Python 3.12 + FastAPI + pymysql + pytest；Vue 3 + TypeScript + Vite + vue-vben-admin v5 + Ant Design Vue 4；MySQL（本机）。

**约定：** 每个后端任务走 TDD（先写失败测试→实现→通过→提交）。测试库用 `meddesk_test`（conftest 设 `MYSQL_DATABASE` 环境变量，config.py 的 `os.getenv` 优先于 .env，因此安全隔离）。提交只 add 计划涉及的文件，绝不提交 `__pycache__`、用户未提交的无关改动。

---

## 文件结构总览

**新建：**
- `services/permissions.py` — 功能注册表 + 账号级授权读写
- `tools/diagnosis_tool.py` — 诊断记录落库/查询
- `tools/doctor_tool.py` — 排班录入/今日预约/排队列表/统计/医生账号管理
- `api/deps.py` — `current_user`/`require_user`/`require_doctor`/`require_admin`/`require_doctor_feature`
- `api/doctor_routes.py` — 医生端接口（APIRouter）
- `api/admin_routes.py` — 管理员端接口（APIRouter）
- `tests/conftest.py`、`tests/test_permissions.py`、`tests/test_doctor_tool.py`、`tests/test_diagnosis_tool.py`、`tests/test_api_doctor.py`
- `pytest.ini`
- `web/` — Vben Admin v5 前端工程（任务 9-12 详述）

**修改：**
- `db/schema.py` — DDL 增 `diagnosis_records`/`user_permissions`；ALTERS 增 `doctors.user_id`；种子：医生账号+授权+7 天演示排班；demo 账号去掉通用 `doctor`（改由每位医生真实账号登录）
- `tools/appointment_tool.py` — 移除随机排班生成
- `agents/diagnosis_agent.py` — `last_diagnosis` 暂存
- `main.py` — `process_message` 增 `user`/`session_id` 参数 + `_maybe_save_diagnosis`
- `api/schemas.py` — 新增请求模型
- `api/server.py` — 替换本地 auth 工具为 `api.deps`；chat 挂 Authorization；include 两个 router
- `requirements.txt` — 增 `pytest`、`httpx`
- `.gitignore` — 增 `web/node_modules`、`web/**/dist`
- `README.md` — 医生账号表与启动说明

---

### Task 1: 数据库 schema 变更（表/列/种子）

**Files:**
- Modify: `db/schema.py`
- Test: `tests/test_schema.py`（本任务直接建库验证，不写单测函数）

- [ ] **Step 1: 在 DDL 列表末尾（`sms_codes` 之后）加两张表**

在 `db/schema.py` 的 `DDL = [...]` 中、`sms_codes` 建表语句之后追加：

```python
    """
    CREATE TABLE IF NOT EXISTS diagnosis_records (
        id INT AUTO_INCREMENT PRIMARY KEY,
        session_id VARCHAR(64) NOT NULL,
        user_id INT NULL,
        patient_name VARCHAR(50) NOT NULL DEFAULT '匿名患者',
        department_id INT NULL,
        doctor_id INT NULL,
        chief_complaint VARCHAR(200) NOT NULL DEFAULT '',
        collected_info JSON NULL,
        conclusion TEXT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        KEY idx_dr_session (session_id),
        KEY idx_dr_department (department_id),
        KEY idx_dr_user (user_id),
        CONSTRAINT fk_dr_user FOREIGN KEY (user_id)
            REFERENCES users (id) ON DELETE SET NULL,
        CONSTRAINT fk_dr_department FOREIGN KEY (department_id)
            REFERENCES departments (id) ON DELETE SET NULL,
        CONSTRAINT fk_dr_doctor FOREIGN KEY (doctor_id)
            REFERENCES doctors (id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS user_permissions (
        user_id INT NOT NULL,
        feature_key VARCHAR(40) NOT NULL,
        granted TINYINT NOT NULL DEFAULT 1,
        PRIMARY KEY (user_id, feature_key),
        CONSTRAINT fk_up_user FOREIGN KEY (user_id)
            REFERENCES users (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
```

- [ ] **Step 2: ALTERS 增 `doctors.user_id`**

在 `ALTERS` 列表追加（注意 `_ensure_columns` 按 `(table, column, stmt)` 结构处理）：

```python
    (
        "doctors",
        "user_id",
        "ALTER TABLE doctors ADD COLUMN user_id INT NULL AFTER specialty, "
        "ADD UNIQUE KEY uq_doctors_user (user_id)",
    ),
```

- [ ] **Step 3: 医生拼音账号映射表**

在 `SEED_DEPARTMENTS` 定义之后新增：

```python
# 医生登录账号（拼音用户名，密码统一 123456）
SEED_DOCTOR_ACCOUNTS: dict[tuple[str, str], str] = {
    ("内科", "张建国"): "zhangjianguo",
    ("内科", "李明华"): "liminghua",
    ("内科", "王芳"): "wangfang",
    ("外科", "刘强"): "liuqiang",
    ("外科", "陈伟"): "chenwei",
    ("儿科", "赵敏"): "zhaomin",
    ("儿科", "孙丽"): "sunli",
    ("妇产科", "周洁"): "zhoujie",
    ("妇产科", "吴婷"): "wuting",
    ("眼科", "黄明"): "huangming",
    ("耳鼻喉科", "郑伟"): "zhengwei",
    ("皮肤科", "林小红"): "linxiaohong",
    ("中医科", "马永健"): "mayongjian",
    ("骨科", "杨志刚"): "yangzhigang",
    ("骨科", "陈伟"): "chenwei2",
    ("神经内科", "韩冰"): "hanbing",
    ("口腔科", "许洁"): "xujie",
    ("精神科", "何志强"): "hezhiqiang",
}
```

- [ ] **Step 4: seed_if_empty 中为医生建账号并授权**

把 `seed_if_empty` 中医生插入循环改为（原循环体基础上，在 `cur.execute(... INSERT INTO doctors ...)` 之后、`dept_id` 可用时追加账号逻辑）：

```python
                for dept_name, doctors in SEED_DEPARTMENTS.items():
                    cur.execute(
                        "INSERT INTO departments (name) VALUES (%s)",
                        (dept_name,),
                    )
                    dept_id = cur.lastrowid
                    for doc in doctors:
                        cur.execute(
                            """
                            INSERT INTO doctors (department_id, name, title, specialty)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (dept_id, doc["name"], doc["title"], doc["specialty"]),
                        )
                        doctor_id = cur.lastrowid
                        username = SEED_DOCTOR_ACCOUNTS.get((dept_name, doc["name"]))
                        if username:
                            cur.execute(
                                """
                                INSERT INTO users (username, password_hash, display_name, phone, role)
                                VALUES (%s, %s, %s, %s, 'doctor')
                                """,
                                (username, hash_password("123456"), doc["name"],
                                 f"139{doctor_id:08d}"),
                            )
                            uid = cur.lastrowid
                            cur.execute(
                                "UPDATE doctors SET user_id = %s WHERE id = %s",
                                (uid, doctor_id),
                            )
                            for key in ("call_queue", "view_appointments",
                                        "manage_schedules", "view_records", "view_stats"):
                                cur.execute(
                                    """
                                    INSERT INTO user_permissions (user_id, feature_key, granted)
                                    VALUES (%s, %s, 1)
                                    """,
                                    (uid, key),
                                )
```

注意：`seed_if_empty` 顶部已有 `from services.auth import hash_password`（在 `seed_demo_users` 内），把该 import 提到 `seed_if_empty` 内使用即可（函数内 import 即可，保持现状风格）。**不要**重复 import 顶层。

- [ ] **Step 5: seed_demo_users 去掉通用 doctor 演示账号**

把 `demo` 列表改为两项（已有库不受影响，仅影响全新库）：

```python
        demo = [
            ("admin", "admin123", "系统管理员", "admin", "13800000001"),
            ("zhangsan", "123456", "张三", "patient", "13800000002"),
        ]
```

- [ ] **Step 6: 新增 seed_demo_schedules 并在 seed_if_empty 中调用**

```python
def seed_demo_schedules(conn) -> None:
    """为未来 7 天预生成演示排班（每个医生每天上/下午，号源 10，幂等）。"""
    from datetime import date, timedelta

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM doctors")
        doctor_ids = [r["id"] for r in cur.fetchall()]
        for offset in range(7):
            day = (date.today() + timedelta(days=offset)).strftime("%Y-%m-%d")
            for doctor_id in doctor_ids:
                for period in ("上午", "下午"):
                    cur.execute(
                        """
                        INSERT IGNORE INTO doctor_schedules
                            (doctor_id, schedule_date, period, available_slots)
                        VALUES (%s, %s, %s, 10)
                        """,
                        (doctor_id, day, period),
                    )
```

在 `seed_if_empty` 的 `if cur.fetchone()["c"] > 0: pass else:` 分支末尾（`queue_states` 初始化循环之后、`conn.commit()` 之前）加：

```python
                seed_demo_schedules(conn)
```

- [ ] **Step 7: 验证（全新测试库）**

```bash
cd D:/Work/Projects/Python/MedicalDiagnosisAgent
MYSQL_DATABASE=meddesk_test .venv/Scripts/python.exe -c "
from db.schema import bootstrap
bootstrap()
from db.connection import get_connection
conn = get_connection()
with conn.cursor() as cur:
    cur.execute('SHOW TABLES'); print('tables:', [r['Tables_in_meddesk_test'] for r in cur.fetchall()])
    cur.execute(\"SELECT u.username, d.name FROM users u JOIN doctors d ON d.user_id=u.id LIMIT 3\")
    print('doctor accounts:', cur.fetchall())
    cur.execute('SELECT COUNT(*) AS c FROM user_permissions'); print('grants:', cur.fetchone()['c'])
    cur.execute('SELECT COUNT(*) AS c FROM doctor_schedules'); print('schedules:', cur.fetchone()['c'])
conn.close()
"
```

Expected: tables 含 `diagnosis_records`、`user_permissions`；doctor accounts 打印 3 行；grants=90（18 医生×5）；schedules=252（18×7×2）。

- [ ] **Step 8: 提交**

```bash
git add db/schema.py
git commit -m "feat(db): 诊断记录/账号功能授权表与医生账号种子"
```

---

### Task 2: services/permissions.py（功能注册表与授权）

**Files:**
- Create: `services/permissions.py`
- Create: `tests/conftest.py`
- Test: `tests/test_permissions.py`

- [ ] **Step 1: 写 conftest（测试库隔离 + 建表）**

`tests/conftest.py`：

```python
"""pytest 公共配置：隔离测试库并初始化 schema。"""
import os

# 必须在导入任何 db 模块之前设置（config.py 的 os.getenv 优先于 .env）
os.environ["MYSQL_DATABASE"] = "meddesk_test"

import pytest  # noqa: E402

from db.schema import bootstrap  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _setup_schema():
    bootstrap()
    yield
```

- [ ] **Step 2: 写失败测试**

`tests/test_permissions.py`：

```python
"""功能授权读写测试。"""
import pytest

from db.connection import get_connection
from services.permissions import (
    FEATURE_KEYS,
    feature_label,
    get_user_features,
    grant_features,
)


@pytest.fixture
def patient_id():
    """种子患者账号 zhangsan（无 doctor 档案，不受授权语义干扰）。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username = 'zhangsan'")
            row = cur.fetchone()
        assert row, "种子账号 zhangsan 不存在，先执行 db.schema.bootstrap"
        return row["id"]
    finally:
        conn.close()


def test_seeded_doctor_has_all_features():
    """每位种子医生默认拥有全部 5 项功能。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT u.id FROM users u JOIN doctors d ON d.user_id = u.id LIMIT 1"
            )
            row = cur.fetchone()
        assert row
        assert get_user_features(row["id"]) == FEATURE_KEYS
    finally:
        conn.close()


def test_grant_replaces_previous(patient_id):
    grant_features(patient_id, ["call_queue"])
    assert get_user_features(patient_id) == {"call_queue"}
    grant_features(patient_id, list(FEATURE_KEYS))
    assert get_user_features(patient_id) == FEATURE_KEYS


def test_grant_filters_unknown_keys(patient_id):
    grant_features(patient_id, ["call_queue", "not_a_feature"])
    assert get_user_features(patient_id) == {"call_queue"}


def test_feature_label_roundtrip():
    for key, label in [("call_queue", "叫号台"), ("view_stats", "就诊统计")]:
        assert feature_label(key) == label
    assert feature_label("nope") == "nope"
```

- [ ] **Step 3: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_permissions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.permissions'`

- [ ] **Step 4: 实现 services/permissions.py**

```python
"""系统功能注册表与账号级授权。"""

from __future__ import annotations

from db.connection import get_connection

# 医生门户功能（admin 可在「权限配置」中对账号逐项授权）
DOCTOR_FEATURES: list[tuple[str, str]] = [
    ("call_queue", "叫号台"),
    ("view_appointments", "今日预约"),
    ("manage_schedules", "排班管理"),
    ("view_records", "诊断记录"),
    ("view_stats", "就诊统计"),
]

FEATURE_KEYS: set[str] = {key for key, _ in DOCTOR_FEATURES}


def feature_label(key: str) -> str:
    """功能键 → 中文名（未知键原样返回）。"""
    for k, label in DOCTOR_FEATURES:
        if k == key:
            return label
    return key


def get_user_features(user_id: int) -> set[str]:
    """账号已授权的功能集合。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT feature_key FROM user_permissions "
                "WHERE user_id = %s AND granted = 1",
                (user_id,),
            )
            return {r["feature_key"] for r in cur.fetchall()}
    finally:
        conn.close()


def has_feature(user_id: int, feature_key: str) -> bool:
    return feature_key in get_user_features(user_id)


def grant_features(user_id: int, feature_keys: list[str]) -> dict:
    """全量设置账号功能授权（先删后插，非法键被过滤）。"""
    keys = [k for k in feature_keys if k in FEATURE_KEYS]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_permissions WHERE user_id = %s", (user_id,))
            for key in keys:
                cur.execute(
                    "INSERT INTO user_permissions (user_id, feature_key, granted) "
                    "VALUES (%s, %s, 1)",
                    (user_id, key),
                )
        conn.commit()
        return {"success": True, "granted": keys}
    finally:
        conn.close()
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_permissions.py -v`
Expected: 4 passed（若首次运行有 chromadb/langchain 依赖告警忽略，测试不触发 LLM）

- [ ] **Step 6: 提交**

```bash
git add services/permissions.py tests/conftest.py tests/test_permissions.py
git commit -m "feat(services): 功能注册表与账号级授权"
```

---

### Task 3: tools/diagnosis_tool.py（诊断落库/查询）

**Files:**
- Create: `tools/diagnosis_tool.py`
- Test: `tests/test_diagnosis_tool.py`

- [ ] **Step 1: 写失败测试**

`tests/test_diagnosis_tool.py`：

```python
"""诊断记录落库与查询测试。"""
import pytest

from db.connection import get_connection
from tools.diagnosis_tool import get_record, list_records, save_record


@pytest.fixture
def dept_id():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM departments WHERE name = '内科'")
            row = cur.fetchone()
        assert row, "种子科室不存在"
        return row["id"]
    finally:
        conn.close()


def test_save_and_get_record(dept_id):
    result = save_record(
        session_id="sess-001",
        user_id=None,
        patient_name="张三",
        collected_info={"main_symptom": "头痛", "duration": "三天"},
        conclusion="考虑紧张性头痛，建议休息并观察。",
        department_id=dept_id,
    )
    assert result["success"], result
    record_id = result["record_id"]
    got = get_record(record_id)
    assert got["success"]
    rec = got["record"]
    assert rec["patient_name"] == "张三"
    assert rec["chief_complaint"] == "头痛"
    assert rec["collected_info"]["duration"] == "三天"
    assert "紧张性头痛" in rec["conclusion"]


def test_list_records_by_department(dept_id):
    save_record(
        session_id="sess-002", user_id=None, patient_name="李四",
        collected_info={"main_symptom": "咳嗽"}, conclusion="考虑急性支气管炎。",
        department_id=dept_id,
    )
    result = list_records(department_id=dept_id)
    assert result["success"]
    patients = [r["patient_name"] for r in result["records"]]
    assert "李四" in patients


def test_get_missing_record():
    result = get_record(999999)
    assert result["success"] is False
    assert "未找到" in result["message"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_diagnosis_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.diagnosis_tool'`

- [ ] **Step 3: 实现 tools/diagnosis_tool.py**

```python
"""诊断记录持久化工具。"""

from __future__ import annotations

import json

from db.connection import get_connection
from db.schema import bootstrap

_bootstrapped = False


def _ensure_db() -> None:
    global _bootstrapped
    if not _bootstrapped:
        bootstrap()
        _bootstrapped = True


def save_record(
    session_id: str,
    user_id: int | None,
    patient_name: str,
    collected_info: dict,
    conclusion: str,
    department_id: int | None = None,
    doctor_id: int | None = None,
) -> dict:
    """保存一条诊断记录。失败不影响调用方（由调用方决定如何处理）。"""
    _ensure_db()
    chief = str(collected_info.get("main_symptom", "") or "")[:200]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO diagnosis_records
                    (session_id, user_id, patient_name, department_id, doctor_id,
                     chief_complaint, collected_info, conclusion)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    user_id,
                    patient_name or "匿名患者",
                    department_id,
                    doctor_id,
                    chief,
                    json.dumps(collected_info, ensure_ascii=False, default=str),
                    conclusion,
                ),
            )
            record_id = cur.lastrowid
        conn.commit()
        return {"success": True, "record_id": record_id}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"success": False, "message": f"保存诊断记录失败：{e}"}
    finally:
        conn.close()


def list_records(
    department_id: int | None = None,
    user_id: int | None = None,
    limit: int = 100,
) -> dict:
    """按科室/患者筛选诊断记录列表（倒序）。"""
    _ensure_db()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT r.id, r.session_id, r.patient_name, r.user_id,
                       d.name AS department, r.chief_complaint, r.conclusion,
                       r.created_at
                FROM diagnosis_records r
                LEFT JOIN departments d ON d.id = r.department_id
                WHERE 1=1
            """
            params: list = []
            if department_id is not None:
                sql += " AND r.department_id = %s"
                params.append(department_id)
            if user_id is not None:
                sql += " AND r.user_id = %s"
                params.append(user_id)
            sql += " ORDER BY r.id DESC LIMIT %s"
            params.append(limit)
            cur.execute(sql, params)
            rows = cur.fetchall()
        for row in rows:
            if hasattr(row.get("created_at"), "strftime"):
                row["created_at"] = row["created_at"].strftime("%Y-%m-%d %H:%M")
        return {"success": True, "records": rows}
    finally:
        conn.close()


def get_record(record_id: int) -> dict:
    """单条诊断记录详情（含采集信息）。"""
    _ensure_db()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.id, r.session_id, r.patient_name, r.user_id,
                       d.name AS department, r.chief_complaint, r.collected_info,
                       r.conclusion, r.created_at
                FROM diagnosis_records r
                LEFT JOIN departments d ON d.id = r.department_id
                WHERE r.id = %s
                """,
                (record_id,),
            )
            row = cur.fetchone()
        if not row:
            return {"success": False, "message": f"未找到诊断记录 {record_id}。"}
        if row.get("collected_info") and isinstance(row["collected_info"], str):
            try:
                row["collected_info"] = json.loads(row["collected_info"])
            except json.JSONDecodeError:
                pass
        if hasattr(row.get("created_at"), "strftime"):
            row["created_at"] = row["created_at"].strftime("%Y-%m-%d %H:%M")
        return {"success": True, "record": row}
    finally:
        conn.close()
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_diagnosis_tool.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add tools/diagnosis_tool.py tests/test_diagnosis_tool.py
git commit -m "feat(tools): 诊断记录落库与查询"
```

---

### Task 4: 排班真实化（appointment_tool 改造 + doctor_tool 排班接口）

**Files:**
- Modify: `tools/appointment_tool.py`
- Create: `tools/doctor_tool.py`（本任务只含排班与查询部分，其余函数留待 Task 5）
- Test: `tests/test_doctor_tool.py`

- [ ] **Step 1: 写失败测试（排班部分）**

`tests/test_doctor_tool.py`（本任务先只写前两个测试函数，Task 5 再追加）：

```python
"""医生工具层测试。"""
import pytest

from db.connection import get_connection
from tools.doctor_tool import get_schedules, upsert_schedules


@pytest.fixture
def neike_doctor_id():
    """内科某医生 id（种子数据）。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT doc.id FROM doctors doc JOIN departments d ON d.id=doc.department_id "
                "WHERE d.name='内科' ORDER BY doc.id LIMIT 1"
            )
            row = cur.fetchone()
        assert row
        return row["id"]
    finally:
        conn.close()


def test_upsert_and_get_schedules(neike_doctor_id):
    result = upsert_schedules(
        neike_doctor_id,
        [
            {"date": "2099-01-01", "period": "上午", "available_slots": 12},
            {"date": "2099-01-01", "period": "下午", "available_slots": 5},
        ],
    )
    assert result["success"], result
    got = get_schedules(neike_doctor_id, start="2099-01-01", end="2099-01-02")
    assert got["success"]
    entries = {(s["date"], s["period"]): s["available_slots"] for s in got["schedules"]}
    assert entries[("2099-01-01", "上午")] == 12
    assert entries[("2099-01-01", "下午")] == 5


def test_upsert_slots_zero_removes(neike_doctor_id):
    upsert_schedules(
        neike_doctor_id,
        [{"date": "2099-01-02", "period": "上午", "available_slots": 8}],
    )
    result = upsert_schedules(
        neike_doctor_id,
        [{"date": "2099-01-02", "period": "上午", "available_slots": 0}],
    )
    assert result["success"]
    got = get_schedules(neike_doctor_id, start="2099-01-02", end="2099-01-02")
    assert got["schedules"] == []


def test_upsert_rejects_bad_period(neike_doctor_id):
    result = upsert_schedules(
        neike_doctor_id,
        [{"date": "2099-01-03", "period": "晚间", "available_slots": 3}],
    )
    assert result["success"] is False


def test_upsert_rejects_slots_out_of_range(neike_doctor_id):
    result = upsert_schedules(
        neike_doctor_id,
        [{"date": "2099-01-03", "period": "上午", "available_slots": 99}],
    )
    assert result["success"] is False
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_doctor_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.doctor_tool'`

- [ ] **Step 3: 实现 doctor_tool 的排班与查询函数**

创建 `tools/doctor_tool.py`（本任务仅以下内容；Task 5 追加其余函数）：

```python
"""医生端业务工具：排班录入、今日预约、排队列表、统计、医生账号管理。"""

from __future__ import annotations

from datetime import datetime

from db.connection import get_connection
from db.schema import bootstrap

_bootstrapped = False

VALID_PERIODS = ("上午", "下午")


def _ensure_db() -> None:
    global _bootstrapped
    if not _bootstrapped:
        bootstrap()
        _bootstrapped = True


def upsert_schedules(doctor_id: int, entries: list[dict]) -> dict:
    """批量设置某医生排班。entries: [{date, period, available_slots}]，slots=0 删除时段。"""
    _ensure_db()
    clean: list[tuple[str, str, int]] = []
    for e in entries:
        date = str(e.get("date", "") or "").strip()
        period = str(e.get("period", "") or "").strip()
        slots = e.get("available_slots", 0)
        if not date or period not in VALID_PERIODS:
            return {"success": False, "message": f"排班项不合法：{e}"}
        try:
            slots = int(slots)
        except (TypeError, ValueError):
            return {"success": False, "message": f"号源数不合法：{e}"}
        if not 0 <= slots <= 50:
            return {"success": False, "message": "号源数需在 0–50 之间。"}
        clean.append((date, period, slots))

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for date, period, slots in clean:
                if slots == 0:
                    cur.execute(
                        """
                        DELETE FROM doctor_schedules
                        WHERE doctor_id = %s AND schedule_date = %s AND period = %s
                        """,
                        (doctor_id, date, period),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO doctor_schedules
                            (doctor_id, schedule_date, period, available_slots)
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE available_slots = VALUES(available_slots)
                        """,
                        (doctor_id, date, period, slots),
                    )
        conn.commit()
        return {"success": True, "message": f"已更新 {len(clean)} 条排班。"}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"success": False, "message": f"排班保存失败：{e}"}
    finally:
        conn.close()


def get_schedules(doctor_id: int, start: str | None = None, end: str | None = None) -> dict:
    """查询某医生排班（可限日期范围）。"""
    _ensure_db()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT schedule_date AS date, period, available_slots
                FROM doctor_schedules
                WHERE doctor_id = %s
            """
            params: list = [doctor_id]
            if start:
                sql += " AND schedule_date >= %s"
                params.append(start)
            if end:
                sql += " AND schedule_date <= %s"
                params.append(end)
            sql += " ORDER BY schedule_date, period"
            cur.execute(sql, params)
            rows = cur.fetchall()
        for row in rows:
            if hasattr(row.get("date"), "strftime"):
                row["date"] = row["date"].strftime("%Y-%m-%d")
        return {"success": True, "schedules": rows}
    finally:
        conn.close()


def get_doctor_detail(doctor_id: int) -> dict | None:
    """医生档案（含科室名）。"""
    _ensure_db()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT doc.id, doc.name, doc.title, doc.specialty,
                       doc.department_id, d.name AS department
                FROM doctors doc
                JOIN departments d ON d.id = doc.department_id
                WHERE doc.id = %s
                """,
                (doctor_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_doctor_tool.py -v`
Expected: 4 passed

- [ ] **Step 5: 改造 appointment_tool（移除随机排班）**

`tools/appointment_tool.py` 两处修改：

(1) 把 `_ensure_schedule` 整个函数替换为只读版本：

```python
def _get_schedule_periods(conn, doctor_id: int, date: str) -> list[str]:
    """返回医生某日已有排班的时段（不再随机生成）。"""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT period, available_slots
            FROM doctor_schedules
            WHERE doctor_id = %s AND schedule_date = %s
            """,
            (doctor_id, date),
        )
        rows = cur.fetchall()
    return [r["period"] for r in rows if r["available_slots"] > 0] or [
        r["period"] for r in rows
    ]
```

(2) `query_schedule` 中 `periods = _ensure_schedule(conn, doc["id"], date)` 改为 `periods = _get_schedule_periods(conn, doc["id"], date)`。

(3) `create_appointment` 中 `_ensure_schedule(conn, doc["id"], date)` 替换为存在性校验：

```python
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT available_slots FROM doctor_schedules
                WHERE doctor_id = %s AND schedule_date = %s AND period = %s
                """,
                (doc["id"], date, period),
            )
            slot_row = cur.fetchone()
        if not slot_row or slot_row["available_slots"] <= 0:
            return {"success": False, "message": "该时段暂无可约号源（未排班或已约满）。"}
```

- [ ] **Step 6: 验证患者端仍可用（回归）**

```bash
.venv/Scripts/python.exe -c "
from tools.appointment_tool import query_schedule, create_appointment
r = query_schedule('内科')
print('schedule ok:', r['success'], '| first:', r['schedule'][0]['periods'])
c = create_appointment('内科', '张建国', r['date'], r['schedule'][0]['periods'][0], '测试患者', '13800000000')
print('appt:', c['success'], c.get('appointment_id'), c.get('message'))
"
```

Expected: schedule ok True 且有排班（种子 7 天）；appt True 返回 APT 编号。若提示「未排班」说明种子排班未生成，回 Task 1 检查。

- [ ] **Step 7: 提交**

```bash
git add tools/doctor_tool.py tools/appointment_tool.py tests/test_doctor_tool.py
git commit -m "feat(tools): 排班真实录入与随机排班移除"
```

---

### Task 5: doctor_tool 其余函数（今日预约/排队列表/统计/医生账号管理）

**Files:**
- Modify: `tools/doctor_tool.py`
- Modify: `tests/test_doctor_tool.py`（追加测试）
- Modify: `tools/appointment_tool.py`（`list_doctors_full` 归属判断：实现放 doctor_tool，appointment_tool 不动）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_doctor_tool.py` 末尾追加：

```python
from tools import queue_tool
from tools.doctor_tool import (
    create_doctor,
    get_stats,
    list_doctors_full,
    list_today_appointments,
    list_waiting_tickets,
    list_users_with_features,
    update_doctor,
)


def test_list_today_appointments(neike_doctor_id):
    from tools.appointment_tool import create_appointment
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")
    r = create_appointment("内科", "张建国", today, "上午", "赵患者", "13800000001")
    assert r["success"], r
    got = list_today_appointments(neike_doctor_id)
    assert got["success"]
    assert any(a["patient_name"] == "赵患者" for a in got["appointments"])


def test_list_waiting_tickets():
    dept = "外科"
    queue_tool.take_number(dept, "排队患者")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM departments WHERE name = %s", (dept,))
            dept_id = cur.fetchone()["id"]
    finally:
        conn.close()
    tickets = list_waiting_tickets(dept_id)
    assert any(t["patient_name"] == "排队患者" for t in tickets)


def test_get_stats_shape():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT d.id, doc.id AS doctor_id FROM doctors doc "
                "JOIN departments d ON d.id=doc.department_id WHERE d.name='内科' LIMIT 1"
            )
            row = cur.fetchone()
    finally:
        conn.close()
    got = get_stats(doctor_id=row["doctor_id"], department_id=row["id"])
    assert got["success"]
    assert set(got["stats"]["totals"]) == {"appointments", "called", "diagnosis"}


def test_create_and_update_doctor():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM departments WHERE name = '眼科'")
            dept_id = cur.fetchone()["id"]
    finally:
        conn.close()
    r = create_doctor(dept_id, "测试医生", "主治医师", "测试", "testdoctor1", "123456")
    assert r["success"], r
    doctor_id = r["doctor_id"]
    r2 = update_doctor(doctor_id, name="测试医生改")
    assert r2["success"]
    r3 = update_doctor(doctor_id, enabled=False)
    assert r3["success"]
    full = list_doctors_full()
    assert full["success"]
    match = [d for d in full["doctors"] if d["id"] == doctor_id]
    assert match and match[0]["name"] == "测试医生改"
    assert match[0]["account_enabled"] == 0


def test_list_users_with_features():
    got = list_users_with_features()
    assert got["success"]
    by_name = {u["username"]: u for u in got["users"]}
    assert "zhangjianguo" in by_name
    assert len(by_name["zhangjianguo"]["feature_keys"]) == 5
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_doctor_tool.py -v`
Expected: FAIL（ImportError：doctor_tool 无这些函数）— 原 4 个测试仍通过。

- [ ] **Step 3: 追加实现**

在 `tools/doctor_tool.py` 追加（文件头部 import 区加 `from datetime import datetime, timedelta`；`from services.auth import hash_password` 与 `from services.permissions import FEATURE_KEYS, grant_features` 放在函数内 import，避免测试环境循环导入）：

```python
def list_today_appointments(doctor_id: int, date: str | None = None) -> dict:
    """某医生某日（默认今天）的预约列表（不含已取消）。"""
    _ensure_db()
    date = date or datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.appointment_id, a.schedule_date AS date, a.period,
                       a.patient_name, a.phone, a.status
                FROM appointments a
                WHERE a.doctor_id = %s AND a.schedule_date = %s AND a.status != '已取消'
                ORDER BY a.period, a.appointment_id
                """,
                (doctor_id, date),
            )
            return {"success": True, "date": date, "appointments": cur.fetchall()}
    finally:
        conn.close()


def list_waiting_tickets(department_id: int) -> list[dict]:
    """某科室等待/就诊中的队列（按号码升序）。"""
    _ensure_db()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT queue_number, patient_name, status
                FROM queue_tickets
                WHERE department_id = %s AND status IN ('waiting', 'serving')
                ORDER BY queue_number ASC
                """,
                (department_id,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def get_stats(
    doctor_id: int | None = None,
    department_id: int | None = None,
    days: int = 7,
) -> dict:
    """统计近 N 天：预约数/叫号数/诊断数按日趋势与合计。doctor_id 为空统计全院。"""
    _ensure_db()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.schedule_date AS day, COUNT(*) AS c
                FROM appointments a
                WHERE a.schedule_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                  AND (%s IS NULL OR a.doctor_id = %s)
                  AND (%s IS NULL OR a.department_id = %s)
                GROUP BY a.schedule_date ORDER BY a.schedule_date
                """,
                (days, doctor_id, doctor_id, department_id, department_id),
            )
            appts = cur.fetchall()
            cur.execute(
                """
                SELECT DATE(q.taken_at) AS day, COUNT(*) AS c
                FROM queue_tickets q
                WHERE q.status IN ('serving', 'done')
                  AND q.taken_at >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                  AND (%s IS NULL OR q.department_id = %s)
                GROUP BY DATE(q.taken_at) ORDER BY day
                """,
                (days, department_id, department_id),
            )
            called = cur.fetchall()
            cur.execute(
                """
                SELECT DATE(r.created_at) AS day, COUNT(*) AS c
                FROM diagnosis_records r
                WHERE r.created_at >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                  AND (%s IS NULL OR r.doctor_id = %s)
                  AND (%s IS NULL OR r.department_id = %s)
                GROUP BY DATE(r.created_at) ORDER BY day
                """,
                (days, doctor_id, doctor_id, department_id, department_id),
            )
            records = cur.fetchall()
        for rows in (appts, called, records):
            for row in rows:
                if hasattr(row.get("day"), "strftime"):
                    row["day"] = row["day"].strftime("%Y-%m-%d")
        return {
            "success": True,
            "stats": {
                "appointments_by_day": appts,
                "called_by_day": called,
                "diagnosis_by_day": records,
                "totals": {
                    "appointments": sum(r["c"] for r in appts),
                    "called": sum(r["c"] for r in called),
                    "diagnosis": sum(r["c"] for r in records),
                },
            },
        }
    finally:
        conn.close()


def list_doctors_full() -> dict:
    """全部医生（含账号状态，管理员用）。"""
    _ensure_db()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT doc.id, doc.name, doc.title, doc.specialty,
                       doc.department_id, d.name AS department,
                       doc.user_id, u.username, u.status AS account_enabled
                FROM doctors doc
                JOIN departments d ON d.id = doc.department_id
                LEFT JOIN users u ON u.id = doc.user_id
                ORDER BY doc.id
                """
            )
            return {"success": True, "doctors": cur.fetchall()}
    finally:
        conn.close()


def list_users_with_features() -> dict:
    """账号列表 + 已授功能（管理员权限配置用）。"""
    _ensure_db()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, display_name, phone, role, status FROM users ORDER BY id"
            )
            users = cur.fetchall()
            cur.execute("SELECT user_id, feature_key FROM user_permissions WHERE granted = 1")
            grants: dict[int, list[str]] = {}
            for row in cur.fetchall():
                grants.setdefault(row["user_id"], []).append(row["feature_key"])
        for u in users:
            u["feature_keys"] = sorted(grants.get(u["id"], []))
        return {"success": True, "users": users}
    finally:
        conn.close()


def create_doctor(
    department_id: int, name: str, title: str, specialty: str,
    username: str, password: str,
) -> dict:
    """新建医生 + 登录账号（默认授予全部医生功能）。"""
    from services.auth import hash_password
    from services.permissions import FEATURE_KEYS as ALL_FEATURES
    from services.permissions import grant_features

    _ensure_db()
    name = (name or "").strip()
    username = (username or "").strip()
    if not name or not username:
        return {"success": False, "message": "医生姓名与登录用户名必填"}
    if len(password or "") < 6:
        return {"success": False, "message": "密码至少 6 位"}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM departments WHERE id = %s", (department_id,))
            if not cur.fetchone():
                return {"success": False, "message": "科室不存在"}
            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cur.fetchone():
                return {"success": False, "message": f"用户名 {username} 已存在"}
            cur.execute(
                """
                INSERT INTO users (username, password_hash, display_name, role)
                VALUES (%s, %s, %s, 'doctor')
                """,
                (username, hash_password(password), name),
            )
            uid = cur.lastrowid
            cur.execute(
                """
                INSERT INTO doctors (department_id, name, title, specialty, user_id)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (department_id, name, title, specialty, uid),
            )
            doctor_id = cur.lastrowid
        conn.commit()
        grant_features(uid, list(ALL_FEATURES))
        return {
            "success": True,
            "doctor_id": doctor_id,
            "user_id": uid,
            "message": f"医生 {name} 创建成功，登录账号 {username}",
        }
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"success": False, "message": f"创建失败：{e}"}
    finally:
        conn.close()


def update_doctor(doctor_id: int, **fields) -> dict:
    """修改医生信息；enabled=False 禁用其登录账号。"""
    _ensure_db()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, user_id FROM doctors WHERE id = %s", (doctor_id,))
            row = cur.fetchone()
            if not row:
                return {"success": False, "message": f"未找到医生 {doctor_id}"}
            sets, params = [], []
            for key in ("name", "title", "specialty", "department_id"):
                if key in fields and fields[key] is not None:
                    sets.append(f"{key} = %s")
                    params.append(fields[key])
            if sets:
                params.append(doctor_id)
                cur.execute(f"UPDATE doctors SET {', '.join(sets)} WHERE id = %s", params)
            if "enabled" in fields and row["user_id"]:
                cur.execute(
                    "UPDATE users SET status = %s WHERE id = %s",
                    (1 if fields["enabled"] else 0, row["user_id"]),
                )
        conn.commit()
        return {"success": True, "message": "医生信息已更新"}
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"success": False, "message": f"更新失败：{e}"}
    finally:
        conn.close()
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_doctor_tool.py -v`
Expected: 10 passed（原 4 + 新 6）

- [ ] **Step 5: 提交**

```bash
git add tools/doctor_tool.py tests/test_doctor_tool.py
git commit -m "feat(tools): 今日预约/排队列表/统计/医生账号管理"
```

---

### Task 6: 诊断落库 hook（agent 暂存 + main 流程接入）

**Files:**
- Modify: `agents/diagnosis_agent.py`
- Modify: `main.py`
- Test: `tests/test_diagnosis_hook.py`

- [ ] **Step 1: 写失败测试（绕过 LLM，直接测 hook 机制）**

`tests/test_diagnosis_hook.py`：

```python
"""诊断完成后自动落库（不触发 LLM）。"""
from db.connection import get_connection
from main import MedicalSystem
from tools.diagnosis_tool import list_records


def test_maybe_save_diagnosis_persists_record():
    system = MedicalSystem()
    agent = system.agents["diagnosis"]
    agent.last_diagnosis = {
        "conclusion": "考虑紧张性头痛，建议休息观察。",
        "collected_info": {"main_symptom": "头痛", "duration": "三天"},
    }
    system._maybe_save_diagnosis(
        user={"id": None, "display_name": "测试患者"}, session_id="hook-test"
    )
    result = list_records(limit=50)
    assert result["success"]
    names = [r["patient_name"] for r in result["records"]]
    assert "测试患者" in names
    # hook 后暂存被清空，不会重复落库
    assert agent.last_diagnosis is None
    system._maybe_save_diagnosis(user={"id": None, "display_name": "测试患者"}, session_id="hook-test")
    result2 = list_records(limit=50)
    count = sum(1 for r in result2["records"] if r["patient_name"] == "测试患者")
    assert count == 1


def test_diagnosis_agent_generate_stashes_before_reset():
    from agents.diagnosis_agent import DiagnosisAgent

    agent = DiagnosisAgent()
    agent.collected_info = {"main_symptom": "头痛", "duration": "一天"}
    # 直接调用私有方法会触发 LLM；这里只验证 reset 前的暂存路径通过
    # last_diagnosis 字段存在（Task 实现后为 None 或 dict）
    assert hasattr(agent, "last_diagnosis")
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_diagnosis_hook.py -v`
Expected: FAIL — `AttributeError: 'MedicalSystem' object has no attribute '_maybe_save_diagnosis'`（且 DiagnosisAgent 无 last_diagnosis）

- [ ] **Step 3: 修改 DiagnosisAgent**

`agents/diagnosis_agent.py` 三处：

(1) `__init__` 末尾加：

```python
        self.last_diagnosis: dict | None = None  # 最近一次诊断结论（main 落库后清空）
```

(2) `_generate_diagnosis` 中，`response = self.chat_stream(...)` 与 `self._reset_state()` 之间插入：

```python
        self.last_diagnosis = {
            "conclusion": response,
            "collected_info": dict(self.collected_info),
        }
```

- [ ] **Step 4: 修改 main.py**

(1) 文件顶部 import 区（`from tools import symptom_tool` 风格一致）加：

```python
from tools import diagnosis_tool
```

(2) `process_message` 签名改为：

```python
    def process_message(
        self,
        user_message: str,
        echo: bool = True,
        user: dict | None = None,
        session_id: str | None = None,
    ) -> dict:
```

(3) 新增方法（放 `_handle_chitchat` 之前）：

```python
    def _maybe_save_diagnosis(self, user: dict | None, session_id: str | None) -> None:
        """诊断完成后落库（失败仅记日志，不影响对话）。"""
        agent = self.agents["diagnosis"]
        last = getattr(agent, "last_diagnosis", None)
        if not last:
            return
        try:
            diagnosis_tool.save_record(
                session_id=session_id or "-",
                user_id=user.get("id") if user else None,
                patient_name=(user or {}).get("display_name") or "匿名患者",
                collected_info=last["collected_info"],
                conclusion=last["conclusion"],
            )
        except Exception as e:  # noqa: BLE001
            print(f"[diagnosis] 落库失败：{e}")
        finally:
            agent.last_diagnosis = None
```

(4) 诊断多轮分支（`if self.current_agent and self.current_agent in ["diagnosis"]:` 内，`return {...}` 之前）调用：

```python
            self._maybe_save_diagnosis(user, session_id)
```

(5) 主路由分支中 `if intent == "diagnosis":` 的 `result["collected_info"] = ...` 块之后调用：

```python
        if intent == "diagnosis":
            result["collected_info"] = dict(agent.collected_info)
            result["round_count"] = agent.round_count
            self._maybe_save_diagnosis(user, session_id)
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_diagnosis_hook.py -v`
Expected: 2 passed

- [ ] **Step 6: 回归 CLI 入口（不实际调用 LLM，仅启动检查）**

```bash
.venv/Scripts/python.exe -c "from main import MedicalSystem; s = MedicalSystem(); print('ok', sorted(s.agents.keys()))"
```

Expected: ok ['appointment', 'consultation', 'diagnosis', 'queue']

- [ ] **Step 7: 提交**

```bash
git add agents/diagnosis_agent.py main.py tests/test_diagnosis_hook.py
git commit -m "feat(core): 诊断结论自动落库 hook"
```

---

### Task 7: api/deps.py 权限依赖 + schemas 扩展

**Files:**
- Create: `api/deps.py`
- Modify: `api/schemas.py`
- Test: `tests/test_deps.py`

- [ ] **Step 1: 写失败测试**

`tests/test_deps.py`：

```python
"""权限依赖测试（直接调依赖函数，不依赖 HTTP）。"""
import pytest
from fastapi import HTTPException

from api.deps import require_doctor, require_doctor_feature, require_user


def test_require_user_no_token():
    with pytest.raises(HTTPException) as exc:
        require_user(authorization=None)
    assert exc.value.status_code == 401


def test_require_doctor_rejects_patient():
    from services.auth import login_password

    r = login_password("zhangsan", "123456")
    assert r["success"]
    with pytest.raises(HTTPException) as exc:
        require_doctor(user=r["user"])
    assert exc.value.status_code == 403


def test_require_doctor_ok_for_seeded_doctor():
    from services.auth import login_password

    r = login_password("zhangjianguo", "123456")
    assert r["success"]
    ctx = require_doctor(user=r["user"])
    assert ctx["doctor"]["name"] == "张建国"


def test_require_doctor_feature_blocks_ungranted():
    from services.auth import login_password
    from services.permissions import grant_features

    r = login_password("zhangjianguo", "123456")
    uid = r["user"]["id"]
    grant_features(uid, ["view_stats"])  # 只剩统计
    ctx = require_doctor(user=r["user"])
    ok = require_doctor_feature("view_stats")(ctx)
    assert ok == ctx
    with pytest.raises(HTTPException) as exc:
        require_doctor_feature("call_queue")(ctx)
    assert exc.value.status_code == 403
    grant_features(uid, ["call_queue", "view_appointments", "manage_schedules",
                         "view_records", "view_stats"])  # 复原
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_deps.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.deps'`

- [ ] **Step 3: 实现 api/deps.py**

```python
"""FastAPI 权限依赖。"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from services import auth as auth_service
from services import permissions as perm_service


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


def current_user(authorization: str | None = Header(None)) -> dict | None:
    """可选登录用户（未登录返回 None）。"""
    return auth_service.get_user_by_token(_bearer_token(authorization))


def require_user(authorization: str | None = Header(None)) -> dict:
    user = auth_service.get_user_by_token(_bearer_token(authorization))
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user


def require_admin(user: dict = Depends(require_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def require_doctor(user: dict = Depends(require_user)) -> dict:
    """doctor 角色且关联医生档案，返回 {'user': ..., 'doctor': ...}。"""
    if user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="需要医生账号")
    from db.connection import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM doctors WHERE user_id = %s", (user["id"],))
            doctor = cur.fetchone()
    finally:
        conn.close()
    if not doctor:
        raise HTTPException(status_code=403, detail="医生账号未关联医生档案")
    return {"user": user, "doctor": doctor}


def require_doctor_feature(feature_key: str):
    """医生功能依赖：doctor 档案 + 功能授权（admin 直接放行）。"""

    def dep(ctx: dict = Depends(require_doctor)) -> dict:
        user = ctx["user"]
        if user["role"] != "admin" and not perm_service.has_feature(user["id"], feature_key):
            raise HTTPException(
                status_code=403,
                detail=f"该账号未授权功能「{perm_service.feature_label(feature_key)}」",
            )
        return ctx

    return dep
```

注意：手动测试中直接调 `require_doctor(user=...)` 会绕过 `Depends` 默认值（FastAPI 对直接调用的函数会把默认参数原样传入），这正是 Step 1 测试依赖的行为。路由中使用时由 FastAPI 注入 Header。

- [ ] **Step 4: schemas.py 追加请求模型**

在 `api/schemas.py` 末尾追加：

```python
class ScheduleEntry(BaseModel):
    date: str
    period: str
    available_slots: int


class SchedulesSaveRequest(BaseModel):
    entries: list[ScheduleEntry] = []


class AdminSchedulesSaveRequest(BaseModel):
    doctor_id: int
    entries: list[ScheduleEntry] = []


class FeatureGrantRequest(BaseModel):
    feature_keys: list[str] = []


class DoctorCreateRequest(BaseModel):
    department_id: int
    name: str
    title: str = ""
    specialty: str = ""
    username: str
    password: str = "123456"
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_deps.py -v`
Expected: 4 passed

- [ ] **Step 6: 提交**

```bash
git add api/deps.py api/schemas.py tests/test_deps.py
git commit -m "feat(api): 权限依赖与请求模型"
```

---

### Task 8: 医生/管理员路由 + server.py 接线

**Files:**
- Create: `api/doctor_routes.py`
- Create: `api/admin_routes.py`
- Modify: `api/server.py`
- Modify: `requirements.txt`（pytest、httpx）
- Test: `tests/test_api_doctor.py`

- [ ] **Step 1: 写失败测试（TestClient）**

`tests/test_api_doctor.py`：

```python
"""医生端/管理员端 API 测试。"""
import pytest
from fastapi.testclient import TestClient

from api.server import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["success"], data
    return data["token"]


def test_doctor_me(client):
    token = _login(client, "zhangjianguo", "123456")
    r = client.get("/api/doctor/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["doctor"]["name"] == "张建国"
    assert data["doctor"]["department"] == "内科"
    assert len(data["features"]) == 5


def test_doctor_me_401_without_token(client):
    r = client.get("/api/doctor/me")
    assert r.status_code == 401


def test_patient_token_gets_403(client):
    token = _login(client, "zhangsan", "123456")
    r = client.get("/api/doctor/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_call_next_flow(client):
    token = _login(client, "zhangjianguo", "123456")
    h = {"Authorization": f"Bearer {token}"}
    # 内科队列加人
    from tools.queue_tool import take_number

    take_number("内科", "叫号测试患者")
    r = client.post("/api/doctor/call-next", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["success"], data
    assert "叫号测试患者" in data["message"]


def test_admin_permissions_flow(client):
    token = _login(client, "admin", "admin123")
    h = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/admin/permissions/features", headers=h)
    assert r.status_code == 200
    keys = {f["key"] for f in r.json()["features"]}
    assert "call_queue" in keys

    r = client.get("/api/admin/permissions/users", headers=h)
    assert r.status_code == 200
    users = {u["username"]: u for u in r.json()["users"]}
    assert "zhangjianguo" in users

    # 授权后登录的医生 features 变化
    uid = users["zhangjianguo"]["id"]
    r = client.put(f"/api/admin/permissions/users/{uid}",
                   json={"feature_keys": ["call_queue"]}, headers=h)
    assert r.status_code == 200, r.text
    dtoken = _login(client, "zhangjianguo", "123456")
    me = client.get("/api/doctor/me", headers={"Authorization": f"Bearer {dtoken}"}).json()
    assert me["features"] == ["call_queue"]
    # 复原
    client.put(f"/api/admin/permissions/users/{uid}",
               json={"feature_keys": ["call_queue", "view_appointments",
                                      "manage_schedules", "view_records", "view_stats"]},
               headers=h)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_doctor.py -v`
Expected: FAIL — 404（路由不存在）或 ImportError

- [ ] **Step 3: 实现 api/doctor_routes.py**

```python
"""医生端接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import require_doctor, require_doctor_feature
from services import permissions as perm_service
from tools import diagnosis_tool, doctor_tool, queue_tool

router = APIRouter(prefix="/api/doctor", tags=["doctor"])


@router.get("/me")
def doctor_me(ctx: dict = Depends(require_doctor)):
    detail = doctor_tool.get_doctor_detail(ctx["doctor"]["id"])
    if not detail:
        raise HTTPException(status_code=403, detail="医生档案不存在")
    return {
        "success": True,
        "doctor": detail,
        "features": sorted(perm_service.get_user_features(ctx["user"]["id"])),
    }


@router.get("/schedules")
def my_schedules(
    start: str | None = None,
    end: str | None = None,
    ctx: dict = Depends(require_doctor_feature("manage_schedules")),
):
    return doctor_tool.get_schedules(ctx["doctor"]["id"], start, end)


@router.put("/schedules")
def save_my_schedules(
    payload: dict,
    ctx: dict = Depends(require_doctor_feature("manage_schedules")),
):
    return doctor_tool.upsert_schedules(ctx["doctor"]["id"], payload.get("entries", []))


@router.get("/appointments/today")
def my_appointments(
    date: str | None = None,
    ctx: dict = Depends(require_doctor_feature("view_appointments")),
):
    return doctor_tool.list_today_appointments(ctx["doctor"]["id"], date)


def _dept_of(ctx: dict) -> dict:
    detail = doctor_tool.get_doctor_detail(ctx["doctor"]["id"])
    if not detail:
        raise HTTPException(status_code=403, detail="医生档案不存在")
    return detail


@router.get("/queue")
def my_queue(ctx: dict = Depends(require_doctor_feature("call_queue"))):
    detail = _dept_of(ctx)
    result = queue_tool.query_queue(detail["department"])
    if result.get("success"):
        result["waiting_list"] = doctor_tool.list_waiting_tickets(detail["department_id"])
    return result


@router.post("/call-next")
def my_call_next(ctx: dict = Depends(require_doctor_feature("call_queue"))):
    detail = _dept_of(ctx)
    return queue_tool.call_next(detail["department"])


@router.get("/records")
def my_records(
    user_id: int | None = None,
    ctx: dict = Depends(require_doctor_feature("view_records")),
):
    return diagnosis_tool.list_records(department_id=ctx["doctor"]["department_id"], user_id=user_id)


@router.get("/records/{record_id}")
def record_detail(
    record_id: int,
    ctx: dict = Depends(require_doctor_feature("view_records")),
):
    return diagnosis_tool.get_record(record_id)


@router.get("/stats")
def my_stats(ctx: dict = Depends(require_doctor_feature("view_stats"))):
    doctor = ctx["doctor"]
    return doctor_tool.get_stats(doctor_id=doctor["id"], department_id=doctor["department_id"])
```

- [ ] **Step 4: 实现 api/admin_routes.py**

```python
"""管理员端接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import require_admin
from api.schemas import (
    AdminSchedulesSaveRequest,
    DoctorCreateRequest,
    FeatureGrantRequest,
)
from services import permissions as perm_service
from tools import doctor_tool

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/doctors")
def list_doctors(_: dict = Depends(require_admin)):
    return doctor_tool.list_doctors_full()


@router.post("/doctors")
def create_doctor(req: DoctorCreateRequest, _: dict = Depends(require_admin)):
    return doctor_tool.create_doctor(
        req.department_id, req.name, req.title, req.specialty, req.username, req.password
    )


@router.put("/doctors/{doctor_id}")
def update_doctor(doctor_id: int, payload: dict, _: dict = Depends(require_admin)):
    return doctor_tool.update_doctor(doctor_id, **payload)


@router.put("/schedules")
def admin_schedules(req: AdminSchedulesSaveRequest, _: dict = Depends(require_admin)):
    return doctor_tool.upsert_schedules(
        req.doctor_id, [e.model_dump() for e in req.entries]
    )


@router.get("/permissions/features")
def permission_features(_: dict = Depends(require_admin)):
    return {
        "success": True,
        "features": [{"key": k, "label": v} for k, v in perm_service.DOCTOR_FEATURES],
    }


@router.get("/permissions/users")
def permission_users(_: dict = Depends(require_admin)):
    return doctor_tool.list_users_with_features()


@router.put("/permissions/users/{user_id}")
def grant_user_features(
    user_id: int, req: FeatureGrantRequest, _: dict = Depends(require_admin)
):
    return perm_service.grant_features(user_id, req.feature_keys)


@router.get("/stats")
def admin_stats(_: dict = Depends(require_admin)):
    return doctor_tool.get_stats()
```

- [ ] **Step 5: server.py 接线**

(1) import 区：把

```python
from api import session as session_store
```

之后追加：

```python
from api import admin_routes, deps, doctor_routes
```

(2) 删除 server.py 本地 `_bearer_token` 与 `current_user` 两个函数（`# ── 健康 / 状态 ──` 之前的区域），替换为：

```python
from api.deps import current_user  # noqa: F401  (保留向后引用)
```

并把这两个函数体删除——保留对 `current_user` 的引用方式不变（`create_appointment`/`take_number` 仍用 `current_user(authorization)`，函数签名一致）。

(3) chat 接口改：

```python
@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, authorization: str | None = Header(None)):
    from api.deps import _bearer_token

    user = auth_service.get_user_by_token(_bearer_token(authorization))
    sid, system = session_store.get_or_create_session(req.session_id)
    try:
        result = system.process_message(
            req.message, echo=False, user=user, session_id=sid
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"处理消息失败: {e}") from e
    ...
```

（函数体其余部分不变。）

(4) 在 `app.add_middleware(...)` 之后加：

```python
app.include_router(doctor_routes.router)
app.include_router(admin_routes.router)
```

- [ ] **Step 6: requirements.txt 追加**

```text
pytest>=8.0.0
httpx>=0.27.0
```

然后安装：`.venv/Scripts/pip.exe install pytest httpx`（若已存在则跳过）。

- [ ] **Step 7: 运行确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_doctor.py -v`
Expected: 5 passed

- [ ] **Step 8: 全量后端测试回归**

Run: `.venv/Scripts/python.exe -m pytest tests/ -v`
Expected: 全部 passed（test_permissions 4 + test_doctor_tool 10 + test_diagnosis_tool 3 + test_deps 4 + test_diagnosis_hook 2 + test_api_doctor 5 = 28）

- [ ] **Step 9: 提交**

```bash
git add api/doctor_routes.py api/admin_routes.py api/server.py requirements.txt tests/test_api_doctor.py
git commit -m "feat(api): 医生端/管理员端接口与接线"
```

---

### Task 9: Vben Admin 脚手架 + 登录/请求/路由框架

**Files:**
- Create: `web/`（clone 模板后裁剪）
- Modify: `.gitignore`

- [ ] **Step 1: 克隆模板并去嵌套 git**

```bash
cd D:/Work/Projects/Python/MedicalDiagnosisAgent
git clone --depth 1 https://github.com/vbenjs/vue-vben-admin.git web
rm -rf web/.git
```

网络失败时改用镜像：`git clone --depth 1 https://gitee.com/anncwb/vue-vben-admin.git web`（同样 `rm -rf web/.git`）。

- [ ] **Step 2: 安装依赖**

```bash
cd web && pnpm install
```

Expected: 无 fatal 错误即可（postinstall 失败可 `pnpm install` 重试一次）。耗时较长（5-15 分钟）。

- [ ] **Step 3: .gitignore 追加**

项目根 `.gitignore` 追加：

```gitignore
# doctor portal (Vben)
web/node_modules/
web/**/dist/
web/.turbo/
```

- [ ] **Step 4: 环境变量与代理（apps/web-antd）**

`web/apps/web-antd/.env.development`（不存在则创建）：

```env
VITE_GLOB_API_URL=/api
VITE_BASE=/doctor/
```

`web/apps/web-antd/.env.production`（不存在则创建）：

```env
VITE_GLOB_API_URL=/api
VITE_BASE=/doctor/
```

`web/apps/web-antd/vite.config.mts` 中 `vite` 配置块内加 server 代理（若已有 `server` 块则合并）：

```ts
    server: {
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
```

- [ ] **Step 5: 关闭 mock**

在 `web/apps/web-antd/vite.config.mts` 中查找 `mock` 相关插件（`viteMockDevServerPlugin` / `viteMockBuildPlugin` 或 `vben:vite-mock` 注释块）：按模板自带注释移除 mock 插件引用。然后检查 `web/apps/web-antd/src/api/core/auth.ts`（或 `src/api/auth.ts`，以实际文件为准）——Vben v5 默认 `loginApi` 走 `requestClient.post('/auth/login')` 且带 mock 判断，替换整个文件为：

```ts
import { requestClient } from '#/api/request';

interface LoginResult {
  success: boolean;
  message?: string;
  token: string;
  user: {
    id: number;
    username: string;
    display_name: string;
    role: string;
    phone?: string;
  };
}

/**
 * 登录：对接 FastAPI /api/auth/login（账号密码）
 * 返回 { accessToken } 供 Vben authStore 使用
 */
export async function loginApi(data: {
  username: string;
  password: string;
}): Promise<{ accessToken: string }> {
  const result: LoginResult = await requestClient.post('/auth/login', data);
  if (!result.success) {
    throw new Error(result.message || '登录失败');
  }
  // 登录用户信息与功能授权存入 localStorage（医生门户用）
  localStorage.setItem('doctor_user', JSON.stringify(result.user));
  return { accessToken: result.token };
}

export interface DoctorMe {
  doctor: {
    id: number;
    name: string;
    title: string;
    specialty: string;
    department_id: number;
    department: string;
  };
  features: string[];
}

export async function getDoctorMeApi(): Promise<DoctorMe> {
  return requestClient.get('/doctor/me');
}
```

- [ ] **Step 6: 请求客户端适配（响应为原生 JSON，非 {code,data} 包壳）**

修改 `web/apps/web-antd/src/api/request.ts`：

(1) `createRequestClient` 选项加 `responseReturn: 'body'`；

(2) 找到 `defaultResponseInterceptor` 引用处，若其对 `code !== 0` 抛错/重定向，替换为透传实现：

```ts
async function responseInterceptor(response: AxiosResponse) {
  return response.data;
}
```

（若模板版本无此函数，直接删除 `responseInterceptor: defaultResponseInterceptor` 配置行即可。401 跳登录由 FastAPI 的 401 触发 Vben 内置未授权处理，若无内置处理则在响应拦截器加：`if (response.status === 401) { window.location.href = '/auth/login'; }`）

- [ ] **Step 7: 医生状态 store**

创建 `web/apps/web-antd/src/store/doctor.ts`：

```ts
import { defineStore } from 'pinia';

interface DoctorState {
  features: string[];
  doctor: {
    id: number;
    name: string;
    title: string;
    department_id: number;
    department: string;
  } | null;
}

export const useDoctorStore = defineStore('doctor', {
  state: (): DoctorState => ({
    features: [],
    doctor: null,
  }),
  actions: {
    setDoctor(info: DoctorState) {
      this.doctor = info.doctor;
      this.features = info.features;
    },
    hasFeature(key: string): boolean {
      return this.features.includes(key);
    },
    reset() {
      this.doctor = null;
      this.features = [];
    },
  },
});
```

- [ ] **Step 8: 登录后拉取医生信息并注入路由守卫**

(1) 在 `web/apps/web-antd/src/router/guard.ts` 的登录成功后的守卫逻辑（afterEach 或 beforeEach 中用户已认证分支）追加一次初始化调用（幂等）：

```ts
import { useDoctorStore } from '#/store/doctor';

async function loadDoctorContext() {
  const doctorStore = useDoctorStore();
  if (doctorStore.doctor) return;
  try {
    const { getDoctorMeApi } = await import('#/api/core/auth');
    const me = await getDoctorMeApi();
    doctorStore.setDoctor({ doctor: me.doctor, features: me.features });
    // 未授权功能菜单隐藏（meta.featureKey 不在授权列表内）
    router.getRoutes().forEach((route) => {
      const key = (route.meta as any).featureKey as string | undefined;
      if (key && !me.features.includes(key)) {
        (route.meta as any).hideInMenu = true;
      }
    });
  } catch {
    // 非医生账号（如纯 admin）无 /doctor/me 数据，忽略
  }
}
```

并在对应守卫分支调用 `await loadDoctorContext()`。

(2) 未授权直接访问 URL 时重定向：同一守卫中加

```ts
    const key = (to.meta as any).featureKey as string | undefined;
    if (key && !doctorStore.hasFeature(key)) {
      return { path: '/' };
    }
```

- [ ] **Step 9: 业务路由注册**

创建 `web/apps/web-antd/src/router/routes/modules/doctor.ts`：

```ts
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    name: 'CallQueue',
    path: '/call-queue',
    component: () => import('#/views/doctor/call-queue.vue'),
    meta: { title: '叫号台', icon: 'lucide:volume-2', featureKey: 'call_queue' },
  },
  {
    name: 'MyAppointments',
    path: '/appointments',
    component: () => import('#/views/doctor/appointments.vue'),
    meta: { title: '今日预约', icon: 'lucide:calendar-clock', featureKey: 'view_appointments' },
  },
  {
    name: 'MySchedules',
    path: '/schedules',
    component: () => import('#/views/doctor/schedules.vue'),
    meta: { title: '排班管理', icon: 'lucide:calendar-range', featureKey: 'manage_schedules' },
  },
  {
    name: 'Records',
    path: '/records',
    component: () => import('#/views/doctor/records.vue'),
    meta: { title: '诊断记录', icon: 'lucide:file-text', featureKey: 'view_records' },
  },
  {
    name: 'Stats',
    path: '/stats',
    component: () => import('#/views/doctor/stats.vue'),
    meta: { title: '就诊统计', icon: 'lucide:bar-chart-3', featureKey: 'view_stats' },
  },
];

export default routes;
```

创建 `web/apps/web-antd/src/router/routes/modules/admin.ts`：

```ts
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    name: 'AdminDoctors',
    path: '/admin/doctors',
    component: () => import('#/views/admin/doctors.vue'),
    meta: { title: '医生管理', icon: 'lucide:stethoscope', accessCodes: ['admin'] },
  },
  {
    name: 'AdminPermissions',
    path: '/admin/permissions',
    component: () => import('#/views/admin/permissions.vue'),
    meta: { title: '权限配置', icon: 'lucide:shield-check', accessCodes: ['admin'] },
  },
  {
    name: 'AdminStats',
    path: '/admin/stats',
    component: () => import('#/views/admin/stats.vue'),
    meta: { title: '全院统计', icon: 'lucide:activity', accessCodes: ['admin'] },
  },
];

export default routes;
```

创建 `web/apps/web-antd/src/router/routes/modules/board.ts`（候诊大屏，**顶层独立路由、不入布局**——参照模板 `core.ts` 中 login 路由的顶层写法；若模板把未声明布局的路由自动包进 BasicLayout，则按模板 login 的实际写法调整）：

```ts
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    name: 'Board',
    path: '/board',
    component: () => import('#/views/board/index.vue'),
    meta: { title: '候诊大屏', hideInMenu: true },
  },
];

export default routes;
```

- [ ] **Step 10: 验证 dev server 起得来**

```bash
cd web && pnpm dev --filter @vben/web-antd
```

Expected: 5173 端口启动（模板若配置其他端口以输出为准）。浏览器开 http://localhost:5173/doctor/auth/login（路径与 VITE_BASE 相关，若 404 试 http://localhost:5173/auth/login）。确认登录页渲染后 Ctrl+C 停掉。

- [ ] **Step 11: 提交**

```bash
git add web/apps/web-antd/src/api/core/auth.ts web/apps/web-antd/src/api/request.ts web/apps/web-antd/src/store/doctor.ts web/apps/web-antd/src/router/routes/modules/doctor.ts web/apps/web-antd/src/router/routes/modules/admin.ts web/apps/web-antd/src/router/routes/modules/board.ts web/apps/web-antd/src/router/guard.ts web/apps/web-antd/.env.development web/apps/web-antd/.env.production web/apps/web-antd/vite.config.mts .gitignore
git commit -m "feat(web): Vben 脚手架与登录/权限路由框架"
```

（若路径与模板实际结构有出入，以实际创建的文件路径为准 add。）

---

### Task 10: 医生端五个页面 + 候诊大屏

**Files:**
- Create: `web/apps/web-antd/src/views/doctor/call-queue.vue`
- Create: `web/apps/web-antd/src/views/doctor/appointments.vue`
- Create: `web/apps/web-antd/src/views/doctor/schedules.vue`
- Create: `web/apps/web-antd/src/views/doctor/records.vue`
- Create: `web/apps/web-antd/src/views/doctor/stats.vue`
- Create: `web/apps/web-antd/src/views/board/index.vue`

- [ ] **Step 1: 叫号台 call-queue.vue**

```vue
<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';

import { Page, useVbenModal } from '@vben/common-ui';
import { Button, List, Tag, message } from 'ant-design-vue';

import { useDoctorStore } from '#/store/doctor';

interface Ticket {
  queue_number: number;
  patient_name: string;
  status: string;
}

const doctorStore = useDoctorStore();
const current = ref<number | null>(null);
const waitingCount = ref(0);
const waitingList = ref<Ticket[]>([]);
const loading = ref(false);
let timer: ReturnType<typeof setInterval> | null = null;

async function refresh() {
  const res = await fetch('/api/doctor/queue', {
    headers: { Authorization: `Bearer ${localStorage.getItem('accessToken') || ''}` },
  });
  const data = await res.json();
  if (data.success) {
    current.value = data.current_serving || 0;
    waitingCount.value = data.waiting_count || 0;
    waitingList.value = data.waiting_list || [];
  }
}

async function callNext() {
  loading.value = true;
  try {
    const res = await fetch('/api/doctor/call-next', {
      method: 'POST',
      headers: { Authorization: `Bearer ${localStorage.getItem('accessToken') || ''}` },
    });
    const data = await res.json();
    if (data.success) {
      message.success(data.message);
      await refresh();
    } else {
      message.warning(data.message || '叫号失败');
    }
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  refresh();
  timer = setInterval(refresh, 5000);
});
onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>

<template>
  <Page title="叫号台">
    <div class="flex gap-4">
      <div class="w-72 shrink-0">
        <div class="mb-4 rounded-lg bg-gray-50 p-4 text-center">
          <div class="text-sm text-gray-500">{{ doctorStore.doctor?.department }} 当前叫号</div>
          <div class="my-2 text-6xl font-bold text-blue-600">
            {{ current || '—' }}
          </div>
          <div class="text-sm text-gray-500">等待 {{ waitingCount }} 人</div>
          <Button
            :loading="loading"
            class="mt-4 h-14 w-full text-lg"
            type="primary"
            @click="callNext"
          >
            叫 下 一 个
          </Button>
        </div>
      </div>
      <div class="flex-1 rounded-lg border border-gray-100 p-4">
        <h3 class="mb-2 text-base font-medium">等待队列</h3>
        <List :data-source="waitingList" :locale="{ emptyText: '暂无等待患者' }">
          <template #renderItem="{ item }">
            <List.Item>
              <div class="flex w-full items-center justify-between">
                <span class="text-lg font-semibold">{{ item.queue_number }} 号</span>
                <span>{{ item.patient_name }}</span>
                <Tag :color="item.status === 'serving' ? 'blue' : 'default'">
                  {{ item.status === 'serving' ? '就诊中' : '等待中' }}
                </Tag>
              </div>
            </List.Item>
          </template>
        </List>
      </div>
    </div>
  </Page>
</template>
```

- [ ] **Step 2: 今日预约 appointments.vue**

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { DatePicker, Table, Tag } from 'ant-design-vue';

import dayjs from 'dayjs';

const date = ref(dayjs());
const rows = ref<any[]>([]);
const loading = ref(false);

const columns = [
  { title: '预约号', dataIndex: 'appointment_id' },
  { title: '时段', dataIndex: 'period' },
  { title: '患者', dataIndex: 'patient_name' },
  { title: '电话', dataIndex: 'phone' },
  { title: '状态', dataIndex: 'status' },
];

async function load() {
  loading.value = true;
  try {
    const res = await fetch(
      `/api/doctor/appointments/today?date=${date.value.format('YYYY-MM-DD')}`,
      { headers: { Authorization: `Bearer ${localStorage.getItem('accessToken') || ''}` } },
    );
    const data = await res.json();
    rows.value = data.success ? data.appointments : [];
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <Page title="今日预约">
    <div class="mb-4 flex items-center gap-2">
      <DatePicker v-model:value="date" @change="load" />
    </div>
    <Table
      :columns="columns"
      :data-source="rows"
      :loading="loading"
      :pagination="{ pageSize: 20 }"
      row-key="appointment_id"
    >
      <template #bodyCell="{ column, record }">
        <Tag v-if="column.dataIndex === 'status'" color="green">
          {{ record.status }}
        </Tag>
      </template>
    </Table>
  </Page>
</template>
```

- [ ] **Step 3: 排班管理 schedules.vue**

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { Button, DatePicker, InputNumber, Select, Table, message } from 'ant-design-vue';

import dayjs from 'dayjs';

interface Row {
  date: string;
  period: '上午' | '下午';
  available_slots: number;
  key: string;
}

const range = ref<[dayjs.Dayjs, dayjs.Dayjs]>([
  dayjs(),
  dayjs().add(6, 'day'),
]);
const rows = ref<Row[]>([]);
const loading = ref(false);

const columns = [
  { title: '日期', dataIndex: 'date', width: 140 },
  { title: '时段', dataIndex: 'period', width: 100 },
  {
    title: '号源数（0 = 停诊）',
    dataIndex: 'available_slots',
    width: 220,
  },
];

async function load() {
  loading.value = true;
  try {
    const start = range.value[0].format('YYYY-MM-DD');
    const end = range.value[1].format('YYYY-MM-DD');
    const res = await fetch(`/api/doctor/schedules?start=${start}&end=${end}`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('accessToken') || ''}` },
    });
    const data = await res.json();
    const existing = data.success ? data.schedules : [];
    const map = new Map(existing.map((s: any) => [`${s.date}|${s.period}`, s.available_slots]));
    const list: Row[] = [];
    for (let d = dayjs(start); !d.isAfter(dayjs(end)); d = d.add(1, 'day')) {
      for (const period of ['上午', '下午'] as const) {
        const key = `${d.format('YYYY-MM-DD')}|${period}`;
        list.push({
          date: d.format('YYYY-MM-DD'),
          period,
          available_slots: map.get(key) ?? 10,
          key,
        });
      }
    }
    rows.value = list;
  } finally {
    loading.value = false;
  }
}

async function save() {
  const res = await fetch('/api/doctor/schedules', {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem('accessToken') || ''}`,
    },
    body: JSON.stringify({
      entries: rows.value.map((r) => ({
        date: r.date,
        period: r.period,
        available_slots: r.available_slots,
      })),
    }),
  });
  const data = await res.json();
  if (data.success) {
    message.success(data.message);
  } else {
    message.error(data.message || '保存失败');
  }
}

onMounted(load);
</script>

<template>
  <Page title="排班管理">
    <div class="mb-4 flex items-center gap-3">
      <DatePicker.RangePicker v-model:value="range" @change="load" />
      <Button type="primary" @click="save">保存排班</Button>
    </div>
    <Table
      :columns="columns"
      :data-source="rows"
      :loading="loading"
      :pagination="false"
      row-key="key"
    >
      <template #bodyCell="{ column, record }">
        <InputNumber
          v-if="column.dataIndex === 'available_slots'"
          v-model:value="record.available_slots"
          :max="50"
          :min="0"
        />
      </template>
    </Table>
  </Page>
</template>
```

- [ ] **Step 4: 诊断记录 records.vue**

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { Descriptions, Drawer, Table, Tag } from 'ant-design-vue';

const rows = ref<any[]>([]);
const detail = ref<any>(null);
const open = ref(false);
const loading = ref(false);

const columns = [
  { title: '患者', dataIndex: 'patient_name' },
  { title: '科室', dataIndex: 'department' },
  { title: '主诉', dataIndex: 'chief_complaint' },
  { title: '时间', dataIndex: 'created_at' },
];

async function load() {
  loading.value = true;
  try {
    const res = await fetch('/api/doctor/records', {
      headers: { Authorization: `Bearer ${localStorage.getItem('accessToken') || ''}` },
    });
    const data = await res.json();
    rows.value = data.success ? data.records : [];
  } finally {
    loading.value = false;
  }
}

async function showDetail(record: any) {
  const res = await fetch(`/api/doctor/records/${record.id}`, {
    headers: { Authorization: `Bearer ${localStorage.getItem('accessToken') || ''}` },
  });
  const data = await res.json();
  detail.value = data.success ? data.record : record;
  open.value = true;
}

onMounted(load);
</script>

<template>
  <Page title="诊断记录">
    <Table
      :columns="columns"
      :data-source="rows"
      :loading="loading"
      :pagination="{ pageSize: 20 }"
      row-key="id"
      @row-click="showDetail"
    />
    <Drawer v-model:open="open" title="诊断详情" width="560">
      <Descriptions v-if="detail" :column="1" bordered size="small">
        <Descriptions.Item label="患者">{{ detail.patient_name }}</Descriptions.Item>
        <Descriptions.Item label="科室">{{ detail.department || '—' }}</Descriptions.Item>
        <Descriptions.Item label="主诉">{{ detail.chief_complaint || '—' }}</Descriptions.Item>
        <Descriptions.Item label="诊断结论">{{ detail.conclusion }}</Descriptions.Item>
      </Descriptions>
    </Drawer>
  </Page>
</template>
```

- [ ] **Step 5: 统计 stats.vue**

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { Card, Col, Row, Statistic, Table } from 'ant-design-vue';

const totals = ref({ appointments: 0, called: 0, diagnosis: 0 });
const byDay = ref<any[]>([]);
const loading = ref(false);

const columns = [
  { title: '日期', dataIndex: 'day' },
  { title: '预约数', dataIndex: 'appointments' },
  { title: '叫号数', dataIndex: 'called' },
  { title: '诊断数', dataIndex: 'diagnosis' },
];

async function load() {
  loading.value = true;
  try {
    const res = await fetch('/api/doctor/stats', {
      headers: { Authorization: `Bearer ${localStorage.getItem('accessToken') || ''}` },
    });
    const data = await res.json();
    if (data.success) {
      totals.value = data.stats.totals;
      const days = new Map<string, any>();
      for (const row of data.stats.appointments_by_day) {
        days.set(row.day, { day: row.day, appointments: row.c, called: 0, diagnosis: 0 });
      }
      for (const row of data.stats.called_by_day) {
        const d = days.get(row.day) ?? { day: row.day, appointments: 0, called: 0, diagnosis: 0 };
        d.called = row.c;
        days.set(row.day, d);
      }
      for (const row of data.stats.diagnosis_by_day) {
        const d = days.get(row.day) ?? { day: row.day, appointments: 0, called: 0, diagnosis: 0 };
        d.diagnosis = row.c;
        days.set(row.day, d);
      }
      byDay.value = [...days.values()].sort((a, b) => (a.day < b.day ? -1 : 1));
    }
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <Page title="就诊统计">
    <Row :gutter="16" class="mb-4">
      <Col :span="8">
        <Card><Statistic title="近 7 天预约" :value="totals.appointments" /></Card>
      </Col>
      <Col :span="8">
        <Card><Statistic title="近 7 天叫号" :value="totals.called" /></Card>
      </Col>
      <Col :span="8">
        <Card><Statistic title="近 7 天诊断" :value="totals.diagnosis" /></Card>
      </Col>
    </Row>
    <Table
      :columns="columns"
      :data-source="byDay"
      :loading="loading"
      :pagination="false"
      row-key="day"
    />
  </Page>
</template>
```

- [ ] **Step 6: 候诊大屏 board/index.vue（公开全屏）**

```vue
<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';

const department = ref('内科');
const current = ref(0);
const waiting = ref<{ queue_number: number; patient_name: string; status: string }[]>([]);
let timer: ReturnType<typeof setInterval> | null = null;

async function refresh() {
  const res = await fetch(`/api/queue/${department.value}`);
  const data = await res.json();
  if (data.success) {
    current.value = data.current_serving || 0;
    waiting.value = (data.waiting_list || []).filter((t: any) => t.status === 'waiting');
  }
}

onMounted(() => {
  refresh();
  timer = setInterval(refresh, 5000);
});
onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>

<template>
  <div class="flex h-screen flex-col bg-slate-900 text-white">
    <div class="flex items-center justify-between px-8 py-4">
      <h1 class="text-3xl font-bold">{{ department }} · 候诊叫号</h1>
      <select v-model="department" class="rounded bg-slate-800 px-2 py-1" @change="refresh">
        <option value="内科">内科</option>
        <option value="外科">外科</option>
        <option value="儿科">儿科</option>
      </select>
    </div>
    <div class="flex flex-1 gap-8 overflow-hidden px-8 pb-8">
      <div class="flex w-1/2 flex-col items-center justify-center rounded-2xl bg-slate-800">
        <div class="text-xl text-slate-300">当前叫号</div>
        <div class="my-4 text-[12rem] font-black leading-none text-emerald-400">
          {{ current || '—' }}
        </div>
      </div>
      <div class="w-1/2 overflow-y-auto rounded-2xl bg-slate-800 p-6">
        <h2 class="mb-4 text-2xl font-semibold">等待队列（{{ waiting.length }} 人）</h2>
        <div
          v-for="t in waiting.slice(0, 10)"
          :key="t.queue_number"
          class="mb-3 flex items-center justify-between rounded-lg bg-slate-700 px-6 py-4 text-2xl"
        >
          <span class="font-bold text-amber-300">{{ t.queue_number }} 号</span>
          <span>{{ t.patient_name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 7: 手动冒烟（需后端运行）**

```bash
# 终端 1：后端
.venv/Scripts/python.exe -m api.server
# 终端 2：前端 dev
cd web && pnpm dev --filter @vben/web-antd
```

浏览器（以 VITE_BASE 实际路径为准）：
1. 打开医生门户登录页，用 `zhangjianguo/123456` 登录 → 进入叫号台；
2. 患者端 http://127.0.0.1:8000 取号（内科）；
3. 医生端点「叫下一个」→ 号码更新；
4. 排班管理改号源保存 → 患者端排班查询反映变化；
5. 打开 `/board` → 大屏显示当前叫号。

- [ ] **Step 8: 提交**

```bash
git add web/apps/web-antd/src/views/doctor web/apps/web-antd/src/views/board
git commit -m "feat(web): 医生端五页面与候诊大屏"
```

---

### Task 11: 管理员页面（医生管理/权限配置/全院统计）

**Files:**
- Create: `web/apps/web-antd/src/views/admin/doctors.vue`
- Create: `web/apps/web-antd/src/views/admin/permissions.vue`
- Create: `web/apps/web-antd/src/views/admin/stats.vue`

- [ ] **Step 1: 医生管理 doctors.vue**

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { Button, Form, Input, Modal, Select, Switch, Table, message } from 'ant-design-vue';

const rows = ref<any[]>([]);
const departments = ref<{ id: number; name: string }[]>([]);
const loading = ref(false);
const modalOpen = ref(false);
const form = ref({
  department_id: null as number | null,
  name: '',
  title: '',
  specialty: '',
  username: '',
  password: '123456',
});

const columns = [
  { title: '姓名', dataIndex: 'name' },
  { title: '科室', dataIndex: 'department' },
  { title: '职称', dataIndex: 'title' },
  { title: '专长', dataIndex: 'specialty' },
  { title: '登录账号', dataIndex: 'username' },
  { title: '账号状态', dataIndex: 'account_enabled' },
];

function authHeaders(): Record<string, string> {
  return { Authorization: `Bearer ${localStorage.getItem('accessToken') || ''}` };
}

async function load() {
  loading.value = true;
  try {
    const [dr, dp] = await Promise.all([
      fetch('/api/admin/doctors', { headers: authHeaders() }).then((r) => r.json()),
      fetch('/api/departments').then((r) => r.json()),
    ]);
    rows.value = dr.doctors || [];
    departments.value = (dp.data?.departments || []).map((name: string, i: number) => ({
      id: i + 1,
      name,
    }));
  } finally {
    loading.value = false;
  }
}

async function toggleEnabled(record: any, checked: boolean) {
  const res = await fetch(`/api/admin/doctors/${record.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ enabled: checked }),
  });
  const data = await res.json();
  if (!data.success) message.error(data.message || '操作失败');
  await load();
}

async function create() {
  const res = await fetch('/api/admin/doctors', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(form.value),
  });
  const data = await res.json();
  if (data.success) {
    message.success(data.message);
    modalOpen.value = false;
    form.value = { department_id: null, name: '', title: '', specialty: '', username: '', password: '123456' };
    await load();
  } else {
    message.error(data.message || '创建失败');
  }
}

onMounted(load);
</script>

<template>
  <Page title="医生管理">
    <div class="mb-4">
      <Button type="primary" @click="modalOpen = true">新建医生</Button>
    </div>
    <Table
      :columns="columns"
      :data-source="rows"
      :loading="loading"
      :pagination="{ pageSize: 20 }"
      row-key="id"
    >
      <template #bodyCell="{ column, record }">
        <Switch
          v-if="column.dataIndex === 'account_enabled'"
          :checked="record.account_enabled === 1"
          @change="(v: boolean) => toggleEnabled(record, v)"
        />
      </template>
    </Table>

    <Modal v-model:open="modalOpen" title="新建医生" @ok="create">
      <Form layout="vertical">
        <Form.Item label="姓名" required>
          <Input v-model:value="form.name" />
        </Form.Item>
        <Form.Item label="科室" required>
          <Select
            v-model:value="form.department_id"
            :options="departments.map((d) => ({ label: d.name, value: d.id }))"
          />
        </Form.Item>
        <Form.Item label="职称">
          <Input v-model:value="form.title" />
        </Form.Item>
        <Form.Item label="专长">
          <Input v-model:value="form.specialty" />
        </Form.Item>
        <Form.Item label="登录用户名" required>
          <Input v-model:value="form.username" />
        </Form.Item>
        <Form.Item label="初始密码">
          <Input v-model:value="form.password" />
        </Form.Item>
      </Form>
    </Modal>
  </Page>
</template>
```

- [ ] **Step 2: 权限配置 permissions.vue**

```vue
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { Checkbox, Select, Tag, message } from 'ant-design-vue';

const users = ref<any[]>([]);
const features = ref<{ key: string; label: string }[]>([]);
const selectedId = ref<number | null>(null);
const checked = ref<string[]>([]);

const selected = computed(() => users.value.find((u) => u.id === selectedId.value));

function authHeaders(): Record<string, string> {
  return { Authorization: `Bearer ${localStorage.getItem('accessToken') || ''}` };
}

async function load() {
  const [u, f] = await Promise.all([
    fetch('/api/admin/permissions/users', { headers: authHeaders() }).then((r) => r.json()),
    fetch('/api/admin/permissions/features', { headers: authHeaders() }).then((r) => r.json()),
  ]);
  users.value = u.users || [];
  features.value = f.features || [];
}

async function onSelect(id: number) {
  selectedId.value = id;
  const user = users.value.find((u) => u.id === id);
  checked.value = user?.feature_keys || [];
}

async function save() {
  const res = await fetch(`/api/admin/permissions/users/${selectedId.value}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ feature_keys: checked.value }),
  });
  const data = await res.json();
  if (data.success) {
    message.success('已保存');
    await load();
  } else {
    message.error(data.message || '保存失败');
  }
}

onMounted(load);
</script>

<template>
  <Page title="权限配置">
    <div class="flex gap-6">
      <div class="w-72 shrink-0">
        <Select
          class="w-full"
          placeholder="选择账号"
          :options="users.map((u) => ({ label: `${u.display_name}（${u.username}）`, value: u.id }))"
          @change="onSelect"
        />
        <div v-if="selected" class="mt-4 rounded-lg bg-gray-50 p-4">
          <div class="mb-2">
            角色：
            <Tag :color="selected.role === 'admin' ? 'red' : selected.role === 'doctor' ? 'blue' : 'default'">
              {{ selected.role }}
            </Tag>
          </div>
          <div class="text-sm text-gray-500">
            {{ selected.role === 'admin' ? '管理员拥有全部权限，无需配置' : '勾选该账号可使用的医生门户功能' }}
          </div>
        </div>
      </div>
      <div class="flex-1">
        <template v-if="selected && selected.role !== 'admin'">
          <Checkbox.Group v-model:value="checked" class="flex flex-col gap-3">
            <Checkbox v-for="f in features" :key="f.key" :value="f.key">
              {{ f.label }}
            </Checkbox>
          </Checkbox.Group>
          <a-button class="mt-6" type="primary" @click="save">保存授权</a-button>
        </template>
        <div v-else class="py-10 text-center text-gray-400">
          请先选择账号；admin 账号无需配置
        </div>
      </div>
    </div>
  </Page>
</template>
```

- [ ] **Step 3: 全院统计 admin/stats.vue**

复用 Task 10 Step 5 的 stats.vue 结构，仅把接口换成 `/api/admin/stats`（新建文件完整粘贴并修改 URL）。

- [ ] **Step 4: 手动冒烟**

登录 `admin/admin123`：
1. 「医生管理」新建医生 → 患者端/医生端可用其账号登录；
2. 「权限配置」回收 zhangjianguo 的「叫号台」→ 重新登录 zhangjianguo → 菜单无叫号台、直访 `/call-queue` 被重定向；
3. 「全院统计」显示数据。

- [ ] **Step 5: 提交**

```bash
git add web/apps/web-antd/src/views/admin
git commit -m "feat(web): 管理员三页面（医生管理/权限配置/全院统计）"
```

---

### Task 12: 生产构建挂载 + 端到端冒烟 + 文档

**Files:**
- Modify: `api/server.py`（挂载 dist）
- Modify: `README.md`

- [ ] **Step 1: 构建前端**

```bash
cd web && pnpm build --filter @vben/web-antd
```

Expected: 产出 `web/apps/web-antd/dist/index.html`（含 assets 目录）。

- [ ] **Step 2: FastAPI 挂载**

在 `api/server.py` 前端静态资源区（`# ── 前端静态资源 ──` 之后）追加：

```python
# ── 医生门户（Vben 构建产物） ───────────────────────────────

DOCTOR_DIST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "web", "apps", "web-antd", "dist",
)

if os.path.isdir(DOCTOR_DIST):
    app.mount(
        "/doctor/assets",
        StaticFiles(directory=os.path.join(DOCTOR_DIST, "assets")),
        name="doctor-assets",
    )

    @app.get("/doctor")
    def doctor_index():
        return FileResponse(os.path.join(DOCTOR_DIST, "index.html"))

    @app.get("/doctor/{full_path:path}")
    def doctor_spa(full_path: str):
        candidate = os.path.join(DOCTOR_DIST, full_path)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(DOCTOR_DIST, "index.html"))
```

- [ ] **Step 3: 端到端冒烟（单端口生产形态）**

```bash
.venv/Scripts/python.exe -m api.server
```

依次验证：
```bash
curl -s -o /dev/null -w "doctor: %{http_code}\n" http://127.0.0.1:8000/doctor
curl -s -o /dev/null -w "doctor SPA: %{http_code}\n" http://127.0.0.1:8000/doctor/call-queue
curl -s http://127.0.0.1:8000/api/health
```

Expected: 全 200；`/api/health` 返回 ok。浏览器打开 http://127.0.0.1:8000/doctor → 登录 → 叫号台；患者端 http://127.0.0.1:8000 取号后医生端叫号；`/doctor/board` 大屏显示。

- [ ] **Step 4: README 更新**

在 README「快速开始」的 Web 工作台小节后追加：

```markdown
### 医生门户（Vben Admin）

**开发模式：**

```bash
cd web && pnpm install
pnpm dev --filter @vben/web-antd   # 前端 dev server（默认 5173，代理 /api → 8000）
python -m api.server               # 后端
```

**生产模式：** `pnpm build --filter @vben/web-antd` 后由 FastAPI 直接托管，访问 `/doctor`。

**演示账号：**

| 账号 | 密码 | 角色 | 说明 |
|------|------|------|------|
| admin | admin123 | 管理员 | 医生管理/权限配置/全院统计 |
| zhangjianguo 等 | 123456 | 医生 | 拼音用户名，与种子医生一一对应（如 内科·张建国） |
| zhangsan | 123456 | 患者 | 患者工作台 |

**权限配置：** admin 登录后可在「权限配置」为每个账号勾选医生门户功能（叫号台/今日预约/排班管理/诊断记录/就诊统计），医生登录后菜单按授权动态显示。
```

- [ ] **Step 5: 最终回归 + 提交**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
git add api/server.py README.md
git commit -m "feat(deploy): 医生门户生产构建挂载与文档"
```

Expected: 28 passed（若测试库有历史脏数据，用 `MYSQL_DATABASE=meddesk_test` 重建：`mysql -e "DROP DATABASE meddesk_test"` 后重跑）。

---

## Self-Review 记录

- **Spec 覆盖**：§3 五处数据模型变更 → Task 1；§4 医生接口 → Task 8；§4 管理接口（含权限配置 3 接口）→ Task 8；§5 Vben 门户（登录/布局/6 路由/权限菜单/管理员页）→ Task 9-11；§6 权限双层校验 → Task 7+9；§7 诊断落库 hook → Task 6；§8 范围外未涉及。诊断落库患者身份经 `/api/chat` Authorization → Task 8 Step 5。
- **类型一致性**：`require_doctor` 返回 `{user, doctor}`（Task 7），路由消费处（Task 8）统一用 `ctx["doctor"]`/`ctx["user"]`；`upsert_schedules(doctor_id, entries)` 签名在 Task 4/5/8 一致；`grant_features` 返回 `{success, granted}` 与 Task 8 测试断言一致。
- **已知取舍**：Vben 模板内部文件路径随版本可能微调，Task 9 各步均注明「以实际文件为准」的定位方法；`web/` 首次 `pnpm install` 依赖网络与时间。
