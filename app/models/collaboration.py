"""协作沟通模块 - 数据访问层"""
from app.models.db import get_connection


class CollabGroupRepository:
    """群组数据操作"""

    @staticmethod
    def get_list(page=1, limit=20, user_id=None):
        offset = (page - 1) * limit
        with get_connection() as conn:
            if user_id:
                # 只返回当前用户所在的群组
                rows = conn.execute("""
                    SELECT cg.*, u.username as creator_name,
                        (SELECT COUNT(1) FROM collab_group_members WHERE group_id=cg.id) as member_count
                    FROM collab_groups cg
                    LEFT JOIN users u ON cg.creator_id = u.id
                    WHERE cg.id IN (
                        SELECT group_id FROM collab_group_members WHERE member_type='user' AND member_id=?
                    ) AND cg.is_active=1
                    ORDER BY cg.id DESC LIMIT ? OFFSET ?
                """, (user_id, limit, offset)).fetchall()
                total = conn.execute("""
                    SELECT COUNT(1) as cnt FROM collab_groups cg
                    WHERE cg.id IN (
                        SELECT group_id FROM collab_group_members WHERE member_type='user' AND member_id=?
                    ) AND cg.is_active=1
                """, (user_id,)).fetchone()["cnt"]
            else:
                rows = conn.execute("""
                    SELECT cg.*, u.username as creator_name,
                        (SELECT COUNT(1) FROM collab_group_members WHERE group_id=cg.id) as member_count
                    FROM collab_groups cg
                    LEFT JOIN users u ON cg.creator_id = u.id
                    WHERE cg.is_active=1
                    ORDER BY cg.id DESC LIMIT ? OFFSET ?
                """, (limit, offset)).fetchall()
                total = conn.execute("SELECT COUNT(1) as cnt FROM collab_groups WHERE is_active=1").fetchone()["cnt"]
        return [dict(r) for r in rows], total

    @staticmethod
    def create(name, creator_id, description=""):
        with get_connection() as conn:
            c = conn.execute(
                "INSERT INTO collab_groups (name, description, creator_id) VALUES (?,?,?)",
                (name, description, creator_id)
            )
            group_id = c.lastrowid
            # 创建者自动加入群组
            conn.execute(
                "INSERT OR IGNORE INTO collab_group_members (group_id, member_type, member_id, role) VALUES (?,?,?,?)",
                (group_id, 'user', creator_id, 'owner')
            )
            return group_id

    @staticmethod
    def update(group_id, name, description=""):
        with get_connection() as conn:
            conn.execute(
                "UPDATE collab_groups SET name=?, description=? WHERE id=?",
                (name, description, group_id)
            )
        return True

    @staticmethod
    def delete(group_id):
        with get_connection() as conn:
            conn.execute("DELETE FROM collab_messages WHERE group_id=?", (group_id,))
            conn.execute("DELETE FROM collab_group_members WHERE group_id=?", (group_id,))
            conn.execute("DELETE FROM collab_groups WHERE id=?", (group_id,))
        return True

    @staticmethod
    def delete_batch(ids):
        if not ids: return False
        with get_connection() as conn:
            ph = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM collab_messages WHERE group_id IN ({ph})", ids)
            conn.execute(f"DELETE FROM collab_group_members WHERE group_id IN ({ph})", ids)
            conn.execute(f"DELETE FROM collab_groups WHERE id IN ({ph})", ids)
        return True

    @staticmethod
    def get_by_id(group_id):
        with get_connection() as conn:
            row = conn.execute(
                "SELECT cg.*, u.username as creator_name FROM collab_groups cg LEFT JOIN users u ON cg.creator_id=u.id WHERE cg.id=?",
                (group_id,)
            ).fetchone()
        return dict(row) if row else None


class CollabMemberRepository:
    """群组成员数据操作"""

    @staticmethod
    def get_members(group_id):
        """获取群组所有成员（用户+数字员工）"""
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT cgm.*,
                    CASE WHEN cgm.member_type='user' THEN u.username
                         WHEN cgm.member_type='employee' THEN de.name
                    END as member_name,
                    CASE WHEN cgm.member_type='user' THEN u.username
                         WHEN cgm.member_type='employee' THEN de.name
                    END as display_name
                FROM collab_group_members cgm
                LEFT JOIN users u ON cgm.member_type='user' AND cgm.member_id=u.id
                LEFT JOIN digital_employees de ON cgm.member_type='employee' AND cgm.member_id=de.id
                WHERE cgm.group_id=?
                ORDER BY cgm.member_type ASC, cgm.id ASC
            """, (group_id,)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def add_member(group_id, member_type, member_id, role='member'):
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO collab_group_members (group_id, member_type, member_id, role) VALUES (?,?,?,?)",
                (group_id, member_type, member_id, role)
            )
        return True

    @staticmethod
    def remove_member(group_id, member_type, member_id):
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM collab_group_members WHERE group_id=? AND member_type=? AND member_id=?",
                (group_id, member_type, member_id)
            )
        return True

    @staticmethod
    def get_available_users(group_id=None):
        """获取可邀请的用户列表（排除已在群中的）"""
        with get_connection() as conn:
            if group_id:
                rows = conn.execute("""
                    SELECT id, username FROM users
                    WHERE id NOT IN (
                        SELECT member_id FROM collab_group_members WHERE group_id=? AND member_type='user'
                    )
                    ORDER BY id
                """, (group_id,)).fetchall()
            else:
                rows = conn.execute("SELECT id, username FROM users ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_available_employees(group_id=None):
        """获取可邀请的数字员工列表（排除已在群中的）"""
        with get_connection() as conn:
            if group_id:
                rows = conn.execute("""
                    SELECT id, name, role_desc FROM digital_employees
                    WHERE id NOT IN (
                        SELECT member_id FROM collab_group_members WHERE group_id=? AND member_type='employee'
                    ) AND is_active=1
                    ORDER BY id
                """, (group_id,)).fetchall()
            else:
                rows = conn.execute("SELECT id, name, role_desc FROM digital_employees WHERE is_active=1 ORDER BY id").fetchall()
        return [dict(r) for r in rows]


class CollabMessageRepository:
    """群聊消息数据操作"""

    @staticmethod
    def get_messages(group_id, limit=100, before_id=None):
        """获取群聊消息"""
        with get_connection() as conn:
            if before_id:
                rows = conn.execute("""
                    SELECT cm.*,
                        CASE WHEN cm.sender_type='user' THEN u.username
                             WHEN cm.sender_type='employee' THEN de.name
                        END as sender_name,
                        CASE WHEN cm.sender_type='employee' THEN de.name
                        END as employee_name
                    FROM collab_messages cm
                    LEFT JOIN users u ON cm.sender_type='user' AND cm.sender_id=u.id
                    LEFT JOIN digital_employees de ON cm.sender_type='employee' AND cm.sender_id=de.id
                    WHERE cm.group_id=? AND cm.id < ?
                    ORDER BY cm.id ASC LIMIT ?
                """, (group_id, before_id, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT cm.*,
                        CASE WHEN cm.sender_type='user' THEN u.username
                             WHEN cm.sender_type='employee' THEN de.name
                        END as sender_name,
                        CASE WHEN cm.sender_type='employee' THEN de.name
                        END as employee_name
                    FROM collab_messages cm
                    LEFT JOIN users u ON cm.sender_type='user' AND cm.sender_id=u.id
                    LEFT JOIN digital_employees de ON cm.sender_type='employee' AND cm.sender_id=de.id
                    WHERE cm.group_id=?
                    ORDER BY cm.id ASC LIMIT ?
                """, (group_id, limit)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def add_message(group_id, sender_type, sender_id, content, mentioned_id=None, tokens_used=0):
        """添加消息"""
        with get_connection() as conn:
            c = conn.execute(
                "INSERT INTO collab_messages (group_id, sender_type, sender_id, content, mentioned_id, tokens_used) VALUES (?,?,?,?,?,?)",
                (group_id, sender_type, sender_id, content, mentioned_id, tokens_used)
            )
            return c.lastrowid

    @staticmethod
    def get_employee_info(employee_id):
        """获取数字员工详细信息（模型引擎+技能）"""
        with get_connection() as conn:
            row = conn.execute("""
                SELECT de.*, am.name as model_name, am.model_name as model_id_name,
                    am.api_key, am.base_url
                FROM digital_employees de
                LEFT JOIN ai_models am ON de.model_engine_id = am.id
                WHERE de.id=?
            """, (employee_id,)).fetchone()
        if not row:
            return None
        emp = dict(row)
        # 获取该员工的技能列表
        if emp.get("skill_ids"):
            skill_ids = [int(s.strip()) for s in emp["skill_ids"].split(",") if s.strip().isdigit()]
            if skill_ids:
                from app.models.skill import SkillRepository
                emp["skills"] = SkillRepository.get_names_by_ids(skill_ids)
                # 获取技能详情（用于构建prompt）
                with get_connection() as conn:
                    ph = ",".join("?" * len(skill_ids))
                    skill_rows = conn.execute(
                        f"SELECT * FROM skills WHERE id IN ({ph})", skill_ids
                    ).fetchall()
                    emp["skill_details"] = [dict(s) for s in skill_rows]
            else:
                emp["skills"] = []
                emp["skill_details"] = []
        else:
            emp["skills"] = []
            emp["skill_details"] = []
        return emp
