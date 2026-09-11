"""表结构初始化与种子数据。"""

from __future__ import annotations

import random

from db.connection import ensure_database, get_connection

# 与原内存 mock 保持一致的科室/医生种子
SEED_DEPARTMENTS: dict[str, list[dict]] = {
    "内科": [
        {"name": "张建国", "title": "主任医师", "specialty": "心血管、高血压"},
        {"name": "李明华", "title": "副主任医师", "specialty": "呼吸系统疾病"},
        {"name": "王芳", "title": "主治医师", "specialty": "消化系统疾病"},
    ],
    "外科": [
        {"name": "刘强", "title": "主任医师", "specialty": "普通外科"},
        {"name": "陈伟", "title": "副主任医师", "specialty": "骨科"},
    ],
    "儿科": [
        {"name": "赵敏", "title": "主任医师", "specialty": "小儿呼吸"},
        {"name": "孙丽", "title": "副主任医师", "specialty": "小儿消化"},
    ],
    "妇产科": [
        {"name": "周洁", "title": "主任医师", "specialty": "妇科肿瘤"},
        {"name": "吴婷", "title": "副主任医师", "specialty": "产科"},
    ],
    "眼科": [
        {"name": "黄明", "title": "主任医师", "specialty": "白内障、青光眼"},
    ],
    "耳鼻喉科": [
        {"name": "郑伟", "title": "副主任医师", "specialty": "鼻炎、中耳炎"},
    ],
    "皮肤科": [
        {"name": "林小红", "title": "主任医师", "specialty": "湿疹、银屑病"},
    ],
    "中医科": [
        {"name": "马永健", "title": "主任医师", "specialty": "中医内科调理"},
    ],
    "骨科": [
        {"name": "杨志刚", "title": "主任医师", "specialty": "脊柱外科"},
        {"name": "陈伟", "title": "副主任医师", "specialty": "关节外科"},
    ],
    "神经内科": [
        {"name": "韩冰", "title": "主任医师", "specialty": "脑血管疾病"},
    ],
    "口腔科": [
        {"name": "许洁", "title": "主治医师", "specialty": "口腔修复"},
    ],
    "精神科": [
        {"name": "何志强", "title": "主任医师", "specialty": "抑郁症、焦虑症"},
    ],
}

DDL = [
    """
    CREATE TABLE IF NOT EXISTS departments (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(50) NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS doctors (
        id INT AUTO_INCREMENT PRIMARY KEY,
        department_id INT NOT NULL,
        name VARCHAR(50) NOT NULL,
        title VARCHAR(50) NOT NULL DEFAULT '',
        specialty VARCHAR(120) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_dept_doctor (department_id, name),
        KEY idx_doctors_dept (department_id),
        CONSTRAINT fk_doctors_dept FOREIGN KEY (department_id)
            REFERENCES departments (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS doctor_schedules (
        id INT AUTO_INCREMENT PRIMARY KEY,
        doctor_id INT NOT NULL,
        schedule_date DATE NOT NULL,
        period VARCHAR(10) NOT NULL,
        available_slots INT NOT NULL DEFAULT 10,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_doc_date_period (doctor_id, schedule_date, period),
        KEY idx_sched_date (schedule_date),
        CONSTRAINT fk_sched_doctor FOREIGN KEY (doctor_id)
            REFERENCES doctors (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS appointments (
        appointment_id VARCHAR(20) PRIMARY KEY,
        department_id INT NOT NULL,
        doctor_id INT NOT NULL,
        schedule_date DATE NOT NULL,
        period VARCHAR(10) NOT NULL,
        patient_name VARCHAR(50) NOT NULL,
        phone VARCHAR(20) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT '已预约',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        KEY idx_appt_date (schedule_date),
        KEY idx_appt_patient (patient_name, phone),
        CONSTRAINT fk_appt_dept FOREIGN KEY (department_id)
            REFERENCES departments (id),
        CONSTRAINT fk_appt_doctor FOREIGN KEY (doctor_id)
            REFERENCES doctors (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS appointment_seq (
        id INT NOT NULL
    ) ENGINE=InnoDB
    """,
    """
    CREATE TABLE IF NOT EXISTS queue_states (
        department_id INT PRIMARY KEY,
        current_number INT NOT NULL DEFAULT 0,
        counter INT NOT NULL DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_queue_state_dept FOREIGN KEY (department_id)
            REFERENCES departments (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS queue_tickets (
        id INT AUTO_INCREMENT PRIMARY KEY,
        department_id INT NOT NULL,
        queue_number INT NOT NULL,
        patient_name VARCHAR(50) NOT NULL,
        status ENUM('waiting', 'serving', 'done', 'cancelled') NOT NULL DEFAULT 'waiting',
        taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        called_at DATETIME NULL,
        UNIQUE KEY uq_dept_number (department_id, queue_number),
        KEY idx_queue_dept_status (department_id, status),
        CONSTRAINT fk_ticket_dept FOREIGN KEY (department_id)
            REFERENCES departments (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    # ── 用户 / 多平台登录 ─────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(64) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL DEFAULT '',
        display_name VARCHAR(64) NOT NULL DEFAULT '',
        phone VARCHAR(20) NULL,
        role ENUM('patient', 'doctor', 'admin') NOT NULL DEFAULT 'patient',
        status TINYINT NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        KEY idx_users_phone (phone)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS user_identities (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        provider VARCHAR(32) NOT NULL,
        external_id VARCHAR(128) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_provider_ext (provider, external_id),
        KEY idx_identity_user (user_id),
        CONSTRAINT fk_identity_user FOREIGN KEY (user_id)
            REFERENCES users (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_tokens (
        token VARCHAR(64) PRIMARY KEY,
        user_id INT NOT NULL,
        provider VARCHAR(32) NOT NULL DEFAULT 'password',
        expires_at DATETIME NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        KEY idx_token_user (user_id),
        CONSTRAINT fk_token_user FOREIGN KEY (user_id)
            REFERENCES users (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS sms_codes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        phone VARCHAR(20) NOT NULL,
        code VARCHAR(10) NOT NULL,
        expires_at DATETIME NOT NULL,
        used TINYINT NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        KEY idx_sms_phone (phone)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]

# 已有库的增量列（user_id 关联）
ALTERS = [
    (
        "appointments",
        "user_id",
        "ALTER TABLE appointments ADD COLUMN user_id INT NULL AFTER phone",
    ),
    (
        "queue_tickets",
        "user_id",
        "ALTER TABLE queue_tickets ADD COLUMN user_id INT NULL AFTER patient_name",
    ),
]


def _ensure_columns(conn) -> None:
    with conn.cursor() as cur:
        for table, column, stmt in ALTERS:
            cur.execute(
                """
                SELECT COUNT(*) AS c FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s AND COLUMN_NAME = %s
                """,
                (table, column),
            )
            if cur.fetchone()["c"] == 0:
                cur.execute(stmt)


def init_schema() -> None:
    ensure_database()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for stmt in DDL:
                cur.execute(stmt)
            # 预约号发号器
            cur.execute("SELECT COUNT(*) AS c FROM appointment_seq")
            row = cur.fetchone()
            if not row or row["c"] == 0:
                cur.execute("INSERT INTO appointment_seq (id) VALUES (1000)")
        _ensure_columns(conn)
        conn.commit()
    finally:
        conn.close()


def seed_if_empty() -> None:
    """科室/医生为空时写入种子数据。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM departments")
            if cur.fetchone()["c"] > 0:
                pass
            else:
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
                # 初始化各科室队列状态
                cur.execute("SELECT id FROM departments")
                for row in cur.fetchall():
                    cur.execute(
                        "INSERT INTO queue_states (department_id, current_number, counter) VALUES (%s, 0, 0)",
                        (row["id"],),
                    )
        conn.commit()
        seed_demo_users(conn)
    finally:
        conn.close()


def seed_demo_users(conn=None) -> None:
    """写入演示账号（幂等）。"""
    from services.auth import hash_password

    own = conn is None
    if own:
        conn = get_connection()
    try:
        demo = [
            ("admin", "admin123", "系统管理员", "admin", "13800000001"),
            ("zhangsan", "123456", "张三", "patient", "13800000002"),
            ("doctor", "123456", "李医生", "doctor", "13800000003"),
        ]
        with conn.cursor() as cur:
            for username, password, display, role, phone in demo:
                cur.execute("SELECT id FROM users WHERE username = %s", (username,))
                if cur.fetchone():
                    continue
                cur.execute(
                    """
                    INSERT INTO users (username, password_hash, display_name, phone, role)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (username, hash_password(password), display, phone, role),
                )
                uid = cur.lastrowid
                # 绑定手机号平台身份
                cur.execute(
                    """
                    INSERT IGNORE INTO user_identities (user_id, provider, external_id)
                    VALUES (%s, 'phone', %s)
                    """,
                    (uid, phone),
                )
        conn.commit()
    finally:
        if own:
            conn.close()


def bootstrap() -> None:
    init_schema()
    seed_if_empty()


if __name__ == "__main__":
    bootstrap()
    print("MySQL schema ready.")
